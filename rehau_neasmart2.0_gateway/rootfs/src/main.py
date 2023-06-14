#!/usr/bin/env python3

import asyncio
import json
import logging
import os
import threading
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

    def setValues(self, address, value):
        with self.lock:
            if not isinstance(value, list):
                value = [value]
            for k in range(0, len(value)):
                self.reg_dict[address + k] = value[k]
            super().setValues(address, value)

    def getValues(self, address, count=1):
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


def setup_server_context(datastore_path):
    datablock = LockingPersistentDataBlock.create_lpdb(datastore_path)
    slave_context = {
        slave_id: ModbusSlaveContext(
            di=None,
            co=None,
            hr=datablock,
            ir=None,
            zero_mode=True,
        ),
    }

    return ModbusServerContext(slaves=slave_context, single=False)


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
        return app.response_class(
            response=json.dumps({"err": "invalid base id"}),
            status=400,
            mimetype='application/json'
        )
    if zone_id > 12 or base_id < 1:
        return app.response_class(
            response=json.dumps({"err": "invalid zone id"}),
            status=400,
            mimetype='application/json'
        )

    zone_addr = (base_id - 1) * const.NEASMART_BASE_SLAVE_ADDR + zone_id * const.BASE_ZONE_ID

    if request.method == 'GET':
        data = {
            "state": context[slave_id].getValues(
                const.READ_HR_CODE,
                zone_addr,
                count=1)[0],
            "setpoint": dpt_9001.unpack_dpt9001(context[slave_id].getValues(
                const.READ_HR_CODE,
                zone_addr + const.ZONE_SETPOINT_ADDR_OFFSET,
                count=1)[0]),
            "temperature": dpt_9001.unpack_dpt9001(context[slave_id].getValues(
                const.READ_HR_CODE,
                zone_addr + const.ZONE_TEMP_ADDR_OFFSET,
                count=1)[0]),
            "relative_humidity": context[slave_id].getValues(
                const.READ_HR_CODE,
                zone_addr + const.ZONE_RH_ADDR_OFFSET,
                count=1)[0]
        }

        response = app.response_class(
            response=json.dumps(data),
            status=200,
            mimetype='application/json'
        )
    elif request.method == 'POST':
        payload = request.json
        op_state = payload.get("state")
        setpoint = payload.get("setpoint")
        if not op_state and not setpoint:
            return app.response_class(
                response=json.dumps({"err": "one of state or setpoint need to be specified"}),
                status=400,
                mimetype='application/json'
            )
        if type(op_state) is not int or op_state == 0 or op_state > 6:
            return app.response_class(
                response=json.dumps({"err": "invalid state"}),
                status=400,
                mimetype='application/json'
            )
        if (type(setpoint) is not int and type(setpoint) is not float) or op_state == 0 or op_state > 6:
            return app.response_class(
                response=json.dumps({"err": "invalid setpoint"}),
                status=400,
                mimetype='application/json'
            )
        if op_state:
            if not isinstance(op_state, list):
                op_state = [op_state]
            context[slave_id].setValues(
                const.READ_HR_CODE,
                zone_addr,
                op_state)
        if setpoint:
            dpt_9001_setpoint = dpt_9001.pack_dpt9001(setpoint)
            if not isinstance(dpt_9001_setpoint, list):
                dpt_9001_setpoint = [dpt_9001_setpoint]
            context[slave_id].setValues(
                const.READ_HR_CODE,
                zone_addr + const.ZONE_SETPOINT_ADDR_OFFSET,
                dpt_9001_setpoint)
        response = app.response_class(
            status=202
        )

    return response


@app.route("/mixedgroups/<int:group_id>", methods=['GET'])
def get_mixed_circuit(group_id=None):
    if group_id == 0 or group_id > 3:
        return app.response_class(
            response=json.dumps({"err": "invalid mixed group id"}),
            status=400,
            mimetype='application/json'
        )
    data = {
        "pump_state": context[slave_id].getValues(
            const.READ_HR_CODE,
            const.MIXEDGROUP_BASE_REG[group_id] + const.MIXEDGROUP_PUMP_STATE_OFFSET,
            count=1)[0],
        "mixing_valve_opening_percentage": context[slave_id].getValues(
            const.READ_HR_CODE,
            const.MIXEDGROUP_BASE_REG[group_id] + const.MIXEDGROUP_VALVE_OPENING_OFFSET,
            count=1)[0],
        "flow_temperature": dpt_9001.unpack_dpt9001(context[slave_id].getValues(
            const.READ_HR_CODE,
            const.MIXEDGROUP_BASE_REG[group_id] + const.MIXEDGROUP_FLOW_TEMP_OFFSET,
            count=1)[0]),
        "return_temperature": dpt_9001.unpack_dpt9001(context[slave_id].getValues(
            const.READ_HR_CODE,
            const.MIXEDGROUP_BASE_REG[group_id] + const.MIXEDGROUP_RETURN_TEMP_OFFSET,
            count=1)[0])
    }
    response = app.response_class(
        response=json.dumps(data),
        status=200,
        mimetype='application/json'
    )
    return response


@app.route("/outsidetemperature", methods=['GET'])
def get_outside_temp():
    data = {
        "outside_temperature": dpt_9001.unpack_dpt9001(context[slave_id].getValues(
            const.READ_HR_CODE,
            const.OUTSIDE_TEMP_REG,
            count=1)[0]),
        "filtered_outside_temperature": dpt_9001.unpack_dpt9001(context[slave_id].getValues(
            const.READ_HR_CODE,
            const.FILTERED_OUTSIDE_TEMP_REG,
            count=1)[0])
    }
    response = app.response_class(
        response=json.dumps(data),
        status=200,
        mimetype='application/json'
    )
    return response


@app.route("/notifications", methods=['GET'])
def get_hints_warnings_errors_presence():
    data = {
        "hints_present": context[slave_id].getValues(
            const.READ_HR_CODE,
            const.HINTS_PRESENT_ADDR,
            count=1)[0] == 1,
        "warnings_present": context[slave_id].getValues(
            const.READ_HR_CODE,
            const.WARNINGS_PRESENT_ADDR,
            count=1)[0] == 1,
        "error_present": context[slave_id].getValues(
            const.READ_HR_CODE,
            const.ERRORS_PRESENT_ADDR,
            count=1)[0] == 1
    }

    response = app.response_class(
        response=json.dumps(data),
        status=200,
        mimetype='application/json'
    )
    return response


@app.route("/mode", methods=['POST', 'GET'])
def mode():
    if request.method == 'GET':
        data = {
            "mode": context[slave_id].getValues(
                const.READ_HR_CODE,
                const.GLOBAL_OP_MODE_ADDR,
                count=1)[0]
        }

        response = app.response_class(
            response=json.dumps(data),
            status=200,
            mimetype='application/json'
        )
    elif request.method == 'POST':
        payload = request.json
        op_mode = payload.get("mode")
        if not op_mode:
            return app.response_class(
                response=json.dumps({"err": "missing mode key in payload"}),
                status=400,
                mimetype='application/json'
            )
        if type(op_mode) is not int or op_mode == 0 or op_mode > 5:
            return app.response_class(
                response=json.dumps({"err": "invalid mode"}),
                status=400,
                mimetype='application/json'
            )
        if not isinstance(op_mode, list):
            op_mode = [op_mode]
        context[slave_id].setValues(
            const.WRITE_HR_CODE,
            const.GLOBAL_OP_MODE_ADDR,
            op_mode)
        response = app.response_class(
            status=202,
        )

    return response


@app.route("/state", methods=['POST', 'GET'])
def state():
    if request.method == 'GET':
        data = {
            "state": context[slave_id].getValues(
                const.READ_HR_CODE,
                const.GLOBAL_OP_STATE_ADDR,
                count=1)[0]
        }
        response = app.response_class(
            response=json.dumps(data),
            status=200,
            mimetype='application/json'
        )

    elif request.method == 'POST':
        payload = request.json
        op_state = payload.get("state")
        if not op_state:
            return app.response_class(
                response=json.dumps({"err": "missing state key in payload"}),
                status=400,
                mimetype='application/json'
            )
        if type(op_state) is not int and op_state == 0 or op_state > 6:
            return app.response_class(
                response=json.dumps({"err": "invalid state"}),
                status=400,
                mimetype='application/json'
            )
        if not isinstance(op_state, list):
            op_state = [op_state]
        context[slave_id].setValues(
            const.WRITE_HR_CODE,
            const.GLOBAL_OP_STATE_ADDR,
            op_state)
        response = app.response_class(
            status=202,
        )

    return response


@app.route("/dehumidifiers/<int:dehumidifier_id>", methods=['GET'])
def get_dehumidifier(dehumidifier_id=None):
    if dehumidifier_id > 9 or dehumidifier_id < 1:
        return app.response_class(
            response=json.dumps({"err": "invalid dehumidifier id"}),
            status=400,
            mimetype='application/json'
        )
    data = {
        "dehumidifier_state": context[slave_id].getValues(
            const.READ_HR_CODE,
            dehumidifier_id + const.DEHUMIDIFIERS_ADDR_OFFSET,
            count=1)[0],
    }

    response = app.response_class(
        response=json.dumps(data),
        status=200,
        mimetype='application/json'
    )
    return response


@app.route("/pumps/<int:pump_id>", methods=['GET'])
def get_extra_pumps(pump_id=None):
    if pump_id > 5 or pump_id < 1:
        return app.response_class(
            response=json.dumps({"err": "invalid pump id"}),
            status=400,
            mimetype='application/json'
        )
    data = {
        "pump_state": context[slave_id].getValues(
            const.READ_HR_CODE,
            pump_id + const.EXTRA_PUMPS_ADDR_OFFSET,
            count=1)[0],
    }

    response = app.response_class(
        response=json.dumps(data),
        status=200,
        mimetype='application/json'
    )
    return response


@app.route("/health")
def get_health():
    return "OK"


if __name__ == "__main__":

    with open(const.ADDON_OPT_PATH) as f:
        config = json.load(f)
        addr = config.get("listen_address", "0.0.0.0")
        port = config.get("listen_port", "502")
        server_type = config.get("server_type", "tcp")
        slave_id = config.get("slave_id", 240)

    context = setup_server_context(const.DATASTORE_PATH)

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
