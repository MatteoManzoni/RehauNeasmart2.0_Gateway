#!/usr/bin/env python3

import asyncio
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
import dpt_9001
import const
from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusServerContext,
    ModbusSlaveContext,
)
from pymodbus import __version__ as pymodbus_version
from pymodbus.framer import (
    ModbusRtuFramer,
    ModbusSocketFramer,
)
from pymodbus.device import ModbusDeviceIdentification
from pymodbus.server import (
    StartAsyncSerialServer,
    StartAsyncTcpServer,
)
from flask import Flask, request
from sqlitedict import SqliteDict

app = Flask(__name__)

_logger = logging.getLogger(__name__)
_logger.setLevel(logging.INFO)


class LockingPersistentDataBlock(ModbusSequentialDataBlock):
    lock = threading.Lock()
    reg_dict = None
    last_bus_write_ts = None
    stale_after_seconds = const.DEFAULT_REGISTERS_STALE_AFTER_SECONDS
    persist_command_registers = const.DEFAULT_PERSIST_COMMAND_REGISTERS
    command_sync_timeout_seconds = const.DEFAULT_COMMAND_SYNC_TIMEOUT_SECONDS
    command_registers = set()
    pending_command_registers = {}

    def setValues(self, address, value):
        self.set_modbus_values(address, value)

    def set_modbus_values(self, address, value, function_code=None):
        self._set_values(address, value, source="modbus", function_code=function_code)

    def set_rest_values(self, address, value):
        self._set_values(address, value, source="rest", function_code=None)

    def _set_values(self, address, value, source, function_code):
        with self.lock:
            if not isinstance(value, list):
                value = [value]
            now = time.time()
            values_to_store = list(value)
            for k in range(0, len(value)):
                register = address + k
                register_value = value[k]
                if source == "modbus" and self._should_ignore_modbus_command_write(
                    register,
                    register_value,
                    now,
                    function_code,
                ):
                    values_to_store[k] = super().getValues(register, count=1)[0]
                    continue
                if source == "rest":
                    self._mark_pending_command_register(register, register_value, now)
                if self._should_persist_register(register):
                    self.reg_dict[register] = register_value
            super().setValues(address, values_to_store)
            if source == "modbus":
                self.__class__.last_bus_write_ts = now

    def getValues(self, address, count=1):
        return self.get_modbus_values(address, count=count, function_code=None)

    def get_modbus_values(self, address, count=1, function_code=None):
        with self.lock:
            result = super().getValues(address, count=count)
            if function_code == const.READ_HR_CODE:
                self._mark_pending_command_registers_read(address, count)
            return result

    def get_rest_values(self, address, count=1):
        with self.lock:
            result = super().getValues(address, count=count)
            return result

    @classmethod
    def create_lpdb(cls, reg_datastore_path):
        if not os.path.exists(reg_datastore_path):
            _logger.warning("Initialising DB at {}".format(reg_datastore_path))
            init_dict = SqliteDict(reg_datastore_path, tablename=const.SQLITEDICT_REGS_TABLE, autocommit=False)
            for k in range(0, 65536):
                init_dict[k] = 0
            init_dict.commit()
            init_dict.close()

        _logger.warning("Using DB at {}".format(reg_datastore_path))
        cls.reg_dict = SqliteDict(reg_datastore_path, tablename=const.SQLITEDICT_REGS_TABLE, autocommit=True)

        sorted_dict = dict(sorted(cls.reg_dict.iteritems(), key=lambda x: int(x[0])))

        return cls(const.REGS_STARTING_ADDR, list(sorted_dict.values()))

    @classmethod
    def configure_staleness(cls, stale_after_seconds):
        cls.stale_after_seconds = max(int(stale_after_seconds), 1)

    @classmethod
    def configure_command_registers(cls, persist_command_registers):
        cls.persist_command_registers = bool(persist_command_registers)
        cls.command_registers = cls._build_command_registers()
        cls.pending_command_registers = {}

    @classmethod
    def configure_command_sync_timeout(cls, command_sync_timeout_seconds):
        cls.command_sync_timeout_seconds = max(int(command_sync_timeout_seconds), 1)

    @classmethod
    def _build_command_registers(cls):
        registers = {
            const.GLOBAL_OP_MODE_ADDR,
            const.GLOBAL_OP_STATE_ADDR,
        }
        for base_id in range(1, const.MAX_BASES + 1):
            for zone_id in range(1, const.MAX_ZONES_PER_BASE + 1):
                zone_addr = (base_id - 1) * const.NEASMART_BASE_SLAVE_ADDR + zone_id * const.BASE_ZONE_ID
                registers.add(zone_addr)
                registers.add(zone_addr + const.ZONE_SETPOINT_ADDR_OFFSET)
        return registers

    @classmethod
    def _should_persist_register(cls, register):
        return cls.persist_command_registers or register not in cls.command_registers

    @classmethod
    def _mark_pending_command_register(cls, register, value, now):
        if register not in cls.command_registers:
            return
        cls.pending_command_registers[register] = {
            "value": value,
            "ts": now,
        }

    @classmethod
    def _pending_command_register(cls, register, now):
        pending = cls.pending_command_registers.get(register)
        if pending is None:
            return None
        if now - pending["ts"] > cls.command_sync_timeout_seconds:
            del cls.pending_command_registers[register]
            _logger.warning(
                "Pending command register %s timed out before Rehau read it",
                register,
            )
            return None
        return pending

    @classmethod
    def _should_ignore_modbus_command_write(cls, register, value, now, function_code):
        if function_code not in (const.WRITE_HR_CODE, 16, 22, 23):
            return False
        pending = cls._pending_command_register(register, now)
        if pending is None:
            return False
        if pending["value"] == value:
            del cls.pending_command_registers[register]
            return False
        _logger.info(
            "Ignoring stale Modbus write to pending command register %s: %s != %s",
            register,
            value,
            pending["value"],
        )
        return True

    @classmethod
    def _mark_pending_command_registers_read(cls, address, count):
        for register in range(address, address + count):
            if register in cls.pending_command_registers:
                del cls.pending_command_registers[register]

    def clear_command_registers(self):
        if self.__class__.persist_command_registers:
            return
        with self.lock:
            for register in self.__class__.command_registers:
                super().setValues(register, [0])
                self.reg_dict[register] = 0
            self.__class__.pending_command_registers = {}

    @classmethod
    def freshness_info(cls):
        if cls.last_bus_write_ts is None:
            return {
                "registers_stale": True,
                "registers_age_seconds": None,
                "last_register_write": None,
                "stale_after_seconds": cls.stale_after_seconds,
                "persist_command_registers": cls.persist_command_registers,
                "command_sync_timeout_seconds": cls.command_sync_timeout_seconds,
                "pending_command_registers": 0,
            }

        age_seconds = round(time.time() - cls.last_bus_write_ts, 3)
        last_register_write = datetime.fromtimestamp(
            cls.last_bus_write_ts, tz=timezone.utc
        ).isoformat().replace("+00:00", "Z")

        return {
            "registers_stale": age_seconds > cls.stale_after_seconds,
            "registers_age_seconds": age_seconds,
            "last_register_write": last_register_write,
            "stale_after_seconds": cls.stale_after_seconds,
            "persist_command_registers": cls.persist_command_registers,
            "command_sync_timeout_seconds": cls.command_sync_timeout_seconds,
            "pending_command_registers": len(cls.pending_command_registers),
        }


class RehauModbusSlaveContext(ModbusSlaveContext):
    def getValues(self, fc_as_hex, address, count=1):
        if not self.zero_mode:
            address += 1
        datastore = self.store[self.decode(fc_as_hex)]
        if hasattr(datastore, "get_modbus_values"):
            return datastore.get_modbus_values(address, count=count, function_code=fc_as_hex)
        return datastore.getValues(address, count)

    def setValues(self, fc_as_hex, address, values):
        if not self.zero_mode:
            address += 1
        datastore = self.store[self.decode(fc_as_hex)]
        if hasattr(datastore, "set_modbus_values"):
            datastore.set_modbus_values(address, values, function_code=fc_as_hex)
            return
        datastore.setValues(address, values)


def parse_slave_ids(config):
    configured_slave_ids = config.get("slave_ids")
    if configured_slave_ids is None:
        legacy_slave_id = int(config.get("slave_id", const.DEFAULT_SLAVE_ID))
        if legacy_slave_id in const.DEFAULT_SLAVE_IDS:
            return list(const.DEFAULT_SLAVE_IDS)
        return [legacy_slave_id]

    if isinstance(configured_slave_ids, str):
        configured_slave_ids = [
            slave_id.strip()
            for slave_id in configured_slave_ids.split(",")
            if slave_id.strip()
        ]
    elif isinstance(configured_slave_ids, int):
        configured_slave_ids = [configured_slave_ids]

    slave_ids = []
    for slave_id in configured_slave_ids:
        slave_id = int(slave_id)
        if slave_id <= 0 or slave_id > 247:
            raise ValueError(f"invalid slave id {slave_id}")
        if slave_id not in slave_ids:
            slave_ids.append(slave_id)

    if not slave_ids:
        raise ValueError("at least one slave id is required")
    return slave_ids


def setup_server_context(datastore_path, slave_ids):
    datablock = LockingPersistentDataBlock.create_lpdb(datastore_path)
    datablock.clear_command_registers()
    slave_context = {
        slave_id: RehauModbusSlaveContext(
            di=None,
            co=None,
            hr=datablock,
            ir=None,
            zero_mode=True,
        )
        for slave_id in slave_ids
    }

    return ModbusServerContext(slaves=slave_context, single=False), datablock


def enrich_response(response):
    freshness = LockingPersistentDataBlock.freshness_info()
    response.headers["X-Rehau-Registers-Stale"] = str(freshness["registers_stale"]).lower()
    response.headers["X-Rehau-Stale-After-Seconds"] = str(freshness["stale_after_seconds"])
    if freshness["registers_age_seconds"] is not None:
        response.headers["X-Rehau-Registers-Age-Seconds"] = str(freshness["registers_age_seconds"])
    if freshness["last_register_write"] is not None:
        response.headers["X-Rehau-Last-Register-Write"] = freshness["last_register_write"]
    return response


def json_response(payload, status=200):
    return enrich_response(
        app.response_class(
            response=json.dumps(payload),
            status=status,
            mimetype='application/json'
        )
    )


def empty_response(status=202):
    return enrich_response(app.response_class(status=status))


async def run_modbus_server(server_context, server_addr, conn_type):
    identity = ModbusDeviceIdentification(
        info_name={
            "VendorName": "Pymodbus",
            "ProductCode": "PM",
            "VendorUrl": "https://github.com/pymodbus-dev/pymodbus/",
            "ProductName": "Pymodbus Server",
            "ModelName": "Pymodbus Server",
            "MajorMinorRevision": pymodbus_version,
        }
    )
    if conn_type == "tcp":
        return await StartAsyncTcpServer(
            context=server_context,
            identity=identity,
            address=server_addr,
            framer=ModbusSocketFramer,
            allow_reuse_address=True,
            ignore_missing_slaves=True,
            broadcast_enable=True,
        )
    elif conn_type == "serial":
        return await StartAsyncSerialServer(
            context=server_context,
            identity=identity,
            port=server_addr,
            framer=ModbusRtuFramer,
            stopbits=const.NEASMART_SYSBUS_STOP_BITS,
            bytesize=const.NEASMART_SYSBUS_DATA_BITS,
            parity=const.NEASMART_SYSBUS_PARITY,
            ignore_missing_slaves=True,
            broadcast_enable=True,
        )


@app.route("/zones/<int:base_id>/<int:zone_id>", methods=['POST', 'GET'])
def zone(base_id=None, zone_id=None):
    if base_id > 4 or base_id < 1:
        return json_response({"err": "invalid base id"}, status=400)
    if zone_id > 12 or zone_id < 1:
        return json_response({"err": "invalid zone id"}, status=400)

    zone_addr = (base_id - 1) * const.NEASMART_BASE_SLAVE_ADDR + zone_id * const.BASE_ZONE_ID

    if request.method == 'GET':
        data = {
            "state": datablock.get_rest_values(
                zone_addr,
                count=1)[0],
            "setpoint": dpt_9001.unpack_temperature(datablock.get_rest_values(
                zone_addr + const.ZONE_SETPOINT_ADDR_OFFSET,
                count=1)[0]),
            "temperature": dpt_9001.unpack_temperature(datablock.get_rest_values(
                zone_addr + const.ZONE_TEMP_ADDR_OFFSET,
                count=1)[0]),
            "relative_humidity": datablock.get_rest_values(
                zone_addr + const.ZONE_RH_ADDR_OFFSET,
                count=1)[0]
        }

        response = json_response(data)
    elif request.method == 'POST':
        payload = request.json
        op_state = payload.get("state")
        setpoint = payload.get("setpoint")
        if op_state is None and setpoint is None:
            return json_response({"err": "one of state or setpoint need to be specified"}, status=400)
        if op_state is not None:
            if type(op_state) is not int or op_state == 0 or op_state > 6:
                return json_response({"err": "invalid state"}, status=400)
            if not isinstance(op_state, list):
                op_state = [op_state]
            datablock.set_rest_values(zone_addr, op_state)
        if setpoint is not None:
            if type(setpoint) is not int and type(setpoint) is not float:
                return json_response({"err": "invalid setpoint"}, status=400)
            dpt_9001_setpoint = dpt_9001.pack_dpt9001(setpoint)
            if not isinstance(dpt_9001_setpoint, list):
                dpt_9001_setpoint = [dpt_9001_setpoint]
            datablock.set_rest_values(zone_addr + const.ZONE_SETPOINT_ADDR_OFFSET, dpt_9001_setpoint)

        response = empty_response(status=202)

    return response


@app.route("/mixedgroups/<int:group_id>", methods=['GET'])
def get_mixed_circuit(group_id=None):
    if group_id == 0 or group_id > 3:
        return json_response({"err": "invalid mixed group id"}, status=400)
    data = {
        "pump_state": datablock.get_rest_values(
            const.MIXEDGROUP_BASE_REG[group_id] + const.MIXEDGROUP_PUMP_STATE_OFFSET,
            count=1)[0],
        "mixing_valve_opening_percentage": datablock.get_rest_values(
            const.MIXEDGROUP_BASE_REG[group_id] + const.MIXEDGROUP_VALVE_OPENING_OFFSET,
            count=1)[0],
        "flow_temperature": dpt_9001.unpack_temperature(datablock.get_rest_values(
            const.MIXEDGROUP_BASE_REG[group_id] + const.MIXEDGROUP_FLOW_TEMP_OFFSET,
            count=1)[0]),
        "return_temperature": dpt_9001.unpack_temperature(datablock.get_rest_values(
            const.MIXEDGROUP_BASE_REG[group_id] + const.MIXEDGROUP_RETURN_TEMP_OFFSET,
            count=1)[0])
    }
    response = json_response(data)
    return response


@app.route("/outsidetemperature", methods=['GET'])
def get_outside_temp():
    data = {
        "outside_temperature": dpt_9001.unpack_temperature(datablock.get_rest_values(
            const.OUTSIDE_TEMP_REG,
            count=1)[0]),
        "filtered_outside_temperature": dpt_9001.unpack_temperature(datablock.get_rest_values(
            const.FILTERED_OUTSIDE_TEMP_REG,
            count=1)[0])
    }
    response = json_response(data)
    return response


@app.route("/notifications", methods=['GET'])
def get_hints_warnings_errors_presence():
    data = {
        "hints_present": datablock.get_rest_values(
            const.HINTS_PRESENT_ADDR,
            count=1)[0] == 1,
        "warnings_present": datablock.get_rest_values(
            const.WARNINGS_PRESENT_ADDR,
            count=1)[0] == 1,
        "error_present": datablock.get_rest_values(
            const.ERRORS_PRESENT_ADDR,
            count=1)[0] == 1
    }

    response = json_response(data)
    return response


@app.route("/mode", methods=['POST', 'GET'])
def mode():
    if request.method == 'GET':
        data = {
            "mode": datablock.get_rest_values(
                const.GLOBAL_OP_MODE_ADDR,
                count=1)[0]
        }

        response = json_response(data)
    elif request.method == 'POST':
        payload = request.json
        op_mode = payload.get("mode")
        if op_mode is None:
            return json_response({"err": "missing mode key in payload"}, status=400)
        if type(op_mode) is not int or op_mode == 0 or op_mode > 5:
            return json_response({"err": "invalid mode"}, status=400)
        if not isinstance(op_mode, list):
            op_mode = [op_mode]
        datablock.set_rest_values(const.GLOBAL_OP_MODE_ADDR, op_mode)
        response = empty_response(status=202)

    return response


@app.route("/state", methods=['POST', 'GET'])
def state():
    if request.method == 'GET':
        data = {
            "state": datablock.get_rest_values(
                const.GLOBAL_OP_STATE_ADDR,
                count=1)[0]
        }
        response = json_response(data)

    elif request.method == 'POST':
        payload = request.json
        op_state = payload.get("state")
        if op_state is None:
            return json_response({"err": "missing state key in payload"}, status=400)
        if type(op_state) is not int or op_state == 0 or op_state > 6:
            return json_response({"err": "invalid state"}, status=400)
        if not isinstance(op_state, list):
            op_state = [op_state]
        datablock.set_rest_values(const.GLOBAL_OP_STATE_ADDR, op_state)
        response = empty_response(status=202)

    return response


@app.route("/dehumidifiers/<int:dehumidifier_id>", methods=['GET'])
def get_dehumidifier(dehumidifier_id=None):
    if dehumidifier_id > 9 or dehumidifier_id < 1:
        return json_response({"err": "invalid dehumidifier id"}, status=400)
    data = {
        "dehumidifier_state": datablock.get_rest_values(
            dehumidifier_id + const.DEHUMIDIFIERS_ADDR_OFFSET,
            count=1)[0],
    }

    response = json_response(data)
    return response


@app.route("/pumps/<int:pump_id>", methods=['GET'])
def get_extra_pumps(pump_id=None):
    if pump_id > 5 or pump_id < 1:
        return json_response({"err": "invalid pump id"}, status=400)
    data = {
        "pump_state": datablock.get_rest_values(
            pump_id + const.EXTRA_PUMPS_ADDR_OFFSET,
            count=1)[0],
    }

    response = json_response(data)
    return response


@app.route("/health")
def get_health():
    freshness = LockingPersistentDataBlock.freshness_info()
    return json_response(
        {
            "status": "ok",
            "registers_receiving_updates": not freshness["registers_stale"],
            **freshness,
        }
    )


if __name__ == "__main__":

    with open(const.ADDON_OPT_PATH) as f:
        config = json.load(f)
        addr = config.get("listen_address", "0.0.0.0")
        port = config.get("listen_port", "502")
        server_type = config.get("server_type", "tcp")
        slave_ids = parse_slave_ids(config)
        registers_stale_after_seconds = config.get(
            "registers_stale_after_seconds",
            const.DEFAULT_REGISTERS_STALE_AFTER_SECONDS,
        )
        persist_command_registers = config.get(
            "persist_command_registers",
            const.DEFAULT_PERSIST_COMMAND_REGISTERS,
        )
        command_sync_timeout_seconds = config.get(
            "command_sync_timeout_seconds",
            const.DEFAULT_COMMAND_SYNC_TIMEOUT_SECONDS,
        )

    LockingPersistentDataBlock.configure_staleness(registers_stale_after_seconds)
    LockingPersistentDataBlock.configure_command_registers(persist_command_registers)
    LockingPersistentDataBlock.configure_command_sync_timeout(command_sync_timeout_seconds)
    context, datablock = setup_server_context(const.DATASTORE_PATH, slave_ids)
    _logger.info("Listening for Rehau Modbus slave ids: %s", slave_ids)

    server_thread = threading.Thread(target=app.run, kwargs={'host': '0.0.0.0'}, daemon=True)
    server_thread.start()

    if server_type == "tcp":
        addr = (addr, port)
    elif server_type == "serial":
        addr = addr
    else:
        _logger.critical("Unsupported server type")
        exit(1)

    asyncio.run(run_modbus_server(context, addr, server_type))
