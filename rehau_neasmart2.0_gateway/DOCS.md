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
- `startup_global_mode` and `startup_global_state` default to `0`, which sends no startup command and leaves the values unknown until REHAU or Home Assistant supplies them. If your base never republishes global registers, configure deterministic startup values using mode `1-5` and state `1-6`. These are real commands and can change the system when the base next reads them.
- Global mode values are `1` Auto, `2` Heating, `3` Cooling, `4` Manual Heating, and `5` Manual Cooling. Global state values are `1` Normal, `2` Reduced, `3` Standby, `4` Time Program, `5` Party, and `6` Holiday/Absence.
- `suppress_sysbus_noise` defaults to `true`. It filters only known proprietary multi-base traffic rejected by pymodbus; suppression counters remain visible in `/health`. Set it to `false` for raw protocol troubleshooting.

The gateway supports the documented master plus four-slave topology. Zone addresses therefore span base IDs `1-5`, channel IDs `1-12`, and Modbus room registers through `6001`.

## Health endpoint

- `GET /health` returns JSON including `registers_receiving_updates`, `registers_stale`, `registers_age_seconds`, `last_register_write`, `stale_after_seconds`, `persist_command_registers`, `command_sync_timeout_seconds`, `pending_command_registers`, startup defaults, and `pymodbus_sysbus_noise` counters
- Every REST response also includes the freshness headers `X-Rehau-Registers-Stale`, `X-Rehau-Registers-Age-Seconds`, and `X-Rehau-Last-Register-Write`

## Known issues

- On startup, command registers are zeroed unless `persist_command_registers` is explicitly enabled. REHAU normally republishes zone values after reading zero; global mode/state may remain unknown unless Home Assistant writes them or startup defaults are configured.
- The documented SYSBUS register map does not expose individual room actuator output or valve state.
- SQLITE is not the best for very slow disks, network disk (if missing `flock()`) and SD Cards (writes happening at every registers update can kill them)
- Flask development server
- API Auth & Ingress
