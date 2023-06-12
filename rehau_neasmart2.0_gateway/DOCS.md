# Home Assistant Add-on: Rehau Neasmart 2.0 Gateway 

This Add-On is used to provide a shim between the Rehau Neasmart 2.0 SysBus interface (glorified Modbus) and Homeassistant through a set of REST APIs

This Add-On was built to be used in conjunction with a custom integration to expose the Rehau Neasmart 2.0 system as a climate entity

This Add-On supports persistent storage (static size at around 3M) for registers state storage

## How to use

- Configure your Serial to USB adapter or a ModbusRTU Slave to ModbusTCP adapter.
- Install the addon by adding this addon repository to you homeassistant installation
- Configure the addon specifying the Serial port path or listening address in the `listening_address` field, configure a `listening_port` matching the ModbusRTU Slave to ModbusTCP adapter configuration 
- Configure whether to use `tcp` or `serial` as `server_type` (if you have specified a Serial port in the listening address you'll need to use serial)
- Configure a `slave_id` valid ids are 240 and 241. This addon can co-exist with the KNX GW albeit a different ID

## Known issues

- The addon on first startup will init an empty database so all write regs will be zeroed, a change on write regs is required to start showing those values in reading
- If the addon is down and a change happens through other means (eg. app, thermostat) the register won't be updated and on addon restart the old value will be re-read through the bus and the change will be invalidated
- SQLITE is not the best for very slow disks, network disk (if missing `flock()`) and SD Cards (writes happening at every registers update can kill them)