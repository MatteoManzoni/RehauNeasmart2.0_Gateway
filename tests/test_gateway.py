"""Regression tests for gateway register synchronization."""

import pytest
from pymodbus.datastore import ModbusSequentialDataBlock

import const
import main


@pytest.fixture
def datablock():
    block = main.LockingPersistentDataBlock(0, [0] * 7000)
    block.reg_dict = {}
    block.configure_command_registers(False)
    block.configure_command_sync_timeout(30)
    main.LockingPersistentDataBlock.last_bus_write_ts = None
    block.initialize_command_registers(0, 0)
    return block


def test_all_five_bases_are_command_registers(datablock):
    assert 6000 in datablock.command_registers
    assert 6001 in datablock.command_registers


def test_cached_commands_are_cleared_without_persistence(datablock):
    ModbusSequentialDataBlock.setValues(datablock, 100, [3, 1234])
    datablock.reg_dict[100] = 3
    datablock.reg_dict[101] = 1234

    datablock.initialize_command_registers(0, 0)

    assert datablock.get_rest_values(100, 2) == [0, 0]
    assert datablock.reg_dict[100] == 0
    assert datablock.reg_dict[101] == 0


def test_rest_command_is_protected_until_rehau_reads_it(datablock):
    datablock.set_rest_values(100, [1])

    datablock.set_modbus_values(100, [3], function_code=const.WRITE_HR_CODE)
    assert datablock.get_rest_values(100) == [1]

    assert datablock.get_modbus_values(
        100,
        function_code=const.READ_HR_CODE,
    ) == [1]
    datablock.set_modbus_values(100, [3], function_code=const.WRITE_HR_CODE)
    assert datablock.get_rest_values(100) == [3]


def test_slave_context_preserves_rest_command_until_modbus_read(datablock):
    context = main.RehauModbusSlaveContext(
        di=None,
        co=None,
        hr=datablock,
        ir=None,
        zero_mode=True,
    )
    datablock.set_rest_values(100, [1])

    context.setValues(const.WRITE_HR_CODE, 100, [3])
    assert datablock.get_rest_values(100) == [1]

    assert context.getValues(const.READ_HR_CODE, 100, 1) == [1]
    context.setValues(const.WRITE_HR_CODE, 100, [3])
    assert datablock.get_rest_values(100) == [3]


def test_explicit_global_startup_defaults_are_served_as_commands(datablock):
    datablock.initialize_command_registers(2, 1)

    assert datablock.get_rest_values(const.GLOBAL_OP_MODE_ADDR) == [2]
    assert datablock.get_rest_values(const.GLOBAL_OP_STATE_ADDR) == [1]
    assert const.GLOBAL_OP_MODE_ADDR in datablock.pending_command_registers
    assert const.GLOBAL_OP_STATE_ADDR in datablock.pending_command_registers


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        ({}, (0, 0)),
        ({"startup_global_mode": None, "startup_global_state": None}, (0, 0)),
        ({"startup_global_mode": 3, "startup_global_state": 4}, (3, 4)),
        ({"startup_global_mode": "5", "startup_global_state": "6"}, (5, 6)),
    ],
)
def test_parse_startup_defaults(config, expected):
    assert main.parse_startup_defaults(config) == expected


@pytest.mark.parametrize(
    "config",
    [
        {"startup_global_mode": -1},
        {"startup_global_mode": 6},
        {"startup_global_state": -1},
        {"startup_global_state": 7},
    ],
)
def test_invalid_startup_defaults_are_rejected(config):
    with pytest.raises(ValueError):
        main.parse_startup_defaults(config)


def test_fifth_base_zone_endpoint(datablock):
    main.datablock = datablock
    client = main.app.test_client()

    response = client.get("/zones/5/12")

    assert response.status_code == 200
    assert response.get_json() == {
        "state": 0,
        "setpoint": 0.0,
        "temperature": 0.0,
        "relative_humidity": 0,
    }
    assert client.get("/zones/6/1").status_code == 400


def test_standby_setpoint_is_null_in_zone_endpoint(datablock):
    main.datablock = datablock
    ModbusSequentialDataBlock.setValues(datablock, 101, [0x8116])

    response = main.app.test_client().get("/zones/1/1")

    assert response.status_code == 200
    assert response.get_json()["setpoint"] is None
