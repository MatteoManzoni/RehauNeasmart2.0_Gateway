NEASMART_SYSBUS_BAUD = 38400
NEASMART_SYSBUS_DATA_BITS = 8
NEASMART_SYSBUS_STOP_BITS = 1
NEASMART_SYSBUS_PARITY = "N"
NEASMART_BASE_SLAVE_ADDR = 1200
BASE_ZONE_ID = 100
ZONE_SETPOINT_ADDR_OFFSET = 1
ZONE_TEMP_ADDR_OFFSET = 2
ZONE_RH_ADDR_OFFSET = 10
MIXEDGROUP_BASE_REG = {
    1: 10,
    2: 14,
    3: 18,
}
MIXEDGROUP_VALVE_OPENING_OFFSET = 0
MIXEDGROUP_PUMP_STATE_OFFSET = 1
MIXEDGROUP_FLOW_TEMP_OFFSET = 2
MIXEDGROUP_RETURN_TEMP_OFFSET = 3
OUTSIDE_TEMPERATURE_ADDR = 7
FILTERED_OUTSIDE_TEMPERATURE_ADDR = 8
HINTS_PRESENT_ADDR = 6
WARNINGS_PRESENT_ADDR = 5
ERRORS_PRESENT_ADDR = 3
GLOBAL_OP_MODE_ADDR = 1
GLOBAL_OP_STATUS_ADDR = 2
DEHUMIDIFIERS_ADDR_OFFSET = 21
EXTRA_PUMPS_ADDR_OFFSET = 30
READ_HR_CODE = 3
WRITE_HR_CODE = 6
OUTSIDE_TEMP_REG = 7
FILTERED_OUTSIDE_TEMP_REG = 8
SQLITEDICT_REGS_TABLE = "holding_registers"
DATASTORE_PATH = "/data/registers.db"
ADDON_OPT_PATH = "/data/options.json"
