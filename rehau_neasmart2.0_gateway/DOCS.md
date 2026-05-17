# Home Assistant Add-on: Rehau Neasmart 2.0 Gateway 

This Add-On is used to provide a shim between the Rehau Neasmart 2.0 SysBus interface (glorified Modbus) and Homeassistant through a set of REST APIs

This Add-On was built to be used in conjunction with a custom integration to expose the Rehau Neasmart 2.0 system as a climate entity

This Add-On supports persistent storage (static size at around 3M) for registers state storage

## How to use

- Configure your Serial to USB adapter or a ModbusRTU Slave to ModbusTCP adapter. [Here's the how-to for the waveshare RS485 TO POE ETH (B)](./waveshare_poegw_howto.md)
- Install the addon by adding this addon repository to you homeassistant installation
- Configure the addon specifying the Serial port path or listening address in the `listening_address` field, configure a `listening_port` matching the ModbusRTU Slave to ModbusTCP adapter configuration 
- Configure whether to use `tcp` or `serial` as `server_type` (if you have specified a Serial port in the listening address you'll need to use serial)
- Configure `slave_ids` if needed. The default is `[240, 241]` because the Rehau base may poll both documented gateway IDs while broadcasting measurements on unit `0`. The legacy `slave_id` option is still accepted for older configurations.
- Optionally tune `registers_stale_after_seconds` to control how long previously persisted register values are considered fresh after the last Modbus write. When the timeout is exceeded, the REST API exposes the data as stale so the Home Assistant integration can mark entities unavailable instead of showing frozen values.
- `persist_command_registers` defaults to `false` and should usually stay that way. This prevents zone/global command registers from being restored from the SQLite cache after a restart, which can otherwise re-apply old presets or setpoints.
- `command_sync_timeout_seconds` controls how long a REST/HA command write is protected from older Modbus broadcast writes while waiting for the Rehau base to read it.

## Health endpoint

- `GET /health` now returns JSON including `registers_receiving_updates`, `registers_stale`, `registers_age_seconds`, `last_register_write`, `stale_after_seconds`, `persist_command_registers`, `command_sync_timeout_seconds`, and `pending_command_registers`
- Every REST response also includes the freshness headers `X-Rehau-Registers-Stale`, `X-Rehau-Registers-Age-Seconds`, and `X-Rehau-Last-Register-Write`

## Known issues

- The addon on first startup will init an empty database so all write regs will be zeroed, a change on write regs is required to start showing those values in reading
- If the addon is down and a change happens through other means (eg. app, thermostat) the register won't be updated and on addon restart the old value will be re-read through the bus and the change will be invalidated
- SQLITE is not the best for very slow disks, network disk (if missing `flock()`) and SD Cards (writes happening at every registers update can kill them)
- Flask development server
- API Auth & Ingress
