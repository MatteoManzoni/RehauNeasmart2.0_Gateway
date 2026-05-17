## 0.2.9

- Listen on both documented Rehau gateway unit IDs (`240` and `241`) by default so pymodbus does not discard one half of the base-unit polling cycle
- Keep REST/HA command writes pending until the Rehau base reads them, ignoring older broadcast writes during that short sync window
- Treat invalid KNX DPT 9 temperature sentinel values as missing data instead of reporting impossible `670760.96°C` temperatures

## 0.2.8

- Do not persist zone/global command registers by default to avoid replaying old presets and setpoints after restart
- Add `persist_command_registers` option for opting back into the legacy behavior when needed

## 0.2.7

- Track freshness of Modbus register updates and expose it through `/health` plus response headers
- Avoid reporting REST writes as if they were live Modbus traffic
- Add configurable stale-data timeout for easier troubleshooting of frozen Home Assistant entities

## 0.2.6

- Fix POST endpoint set zone op_status temperature target, typos

## 0.2.5

- Fix POST endpoint set zone op_status temperature target

## 0.2.4

- Consolidate usage of singular v plural

## 0.2.3

- Consolidate meaning of state v status 

## 0.2.2

- Remove shadowing of binary status for pumps, dehumidifiers running status

## 0.2.1

- Fix ported go -> python KNX DPT9001 pack function to accommodate for python 256 int to byte mapping

## 0.2.0

- First release of at least working addon

## 0.1.0

- Initial release
