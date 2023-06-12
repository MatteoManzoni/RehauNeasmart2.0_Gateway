# Rehau Neasmart 2.0 Gateway Add-On

This Add-On simulates a Modbus slave through serial or ModbusTCP in order to iteract with a Rehau Neasmart 2.0 system, it exposes a set of RESTful apis to control the systems through an Homeassistant custom component.

This Add-On requires a Serial to USB adapter or a ModbusRTU Slave to ModbusTCP adapter. (ModbusRTU over TCP or ModbusRTU over UDP can be supported but are not at this time)
Something like an ESP or an Arduino works but many cheap off-the-shelf devices work too (eg. [this one I'm using now with PoE and DIN rail mounting](https://www.waveshare.com/wiki/RS485_TO_POE_ETH_(B)))


[Add-on documentation](./rehau_neasmart2.0_gateway/DOCS.md)

## Add-ons

This repository contains the following add-ons

### [Rehau Neasmart 2.0 Gateway Add-On](./rehau_neasmart2.0_gateway/)

![Supports aarch64 Architecture][aarch64-shield]
![Supports amd64 Architecture][amd64-shield]
![Supports armhf Architecture][armhf-shield]
![Supports armv7 Architecture][armv7-shield]
![Supports i386 Architecture][i386-shield]

_Modbus Slave <> REST shim between a Rehau Neasmart 2.0 system and Homeassistant._

[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-green.svg
[amd64-shield]: https://img.shields.io/badge/amd64-yes-green.svg
[armhf-shield]: https://img.shields.io/badge/armhf-yes-green.svg
[armv7-shield]: https://img.shields.io/badge/armv7-yes-green.svg
[i386-shield]: https://img.shields.io/badge/i386-yes-green.svg

### Disclaimer

Rehau, I asked you for your support and approval, you never answered, what I did was to give the community the choice to not be bound to KNX.
No IP was violated, no reverse engineering was involved, let's keep the discussion civil