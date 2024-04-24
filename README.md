# APRS_notify
Resources for building a temperature notification platform using the APRS radio system. Designed to be an extensible platform based on the LightAPRS radio module and using AWS and Twilio to provide alerting when the internal temperature exceeds preset maximums, or drops below freezing, where damage to plumbing systems can occur. Transmissions may also be picked up using handheld receivers when cellular singal is not available.

System uses the APRS.FI API for caching and delivery of APRS messages from the internet.  Read more at https://aprs.fi 

# Software requirements
## LightAPRS Firmware
Instructions on how to configure the LightAPRS board can be found ![here](https://github.com/lightaprs/LightAPRS-2.0)

At the time of publishing, you must replace the ZeroAPRS library provided by QRP Labs with the one provided in this repository, or in the main ![channel](https://github.com/hakkican/ZeroAPRS) (v1.0.2), in order to handle messages without GPS coordinates correctly.  Simply replace the ZeroAPRS directory and its contents before compling your sketch.

## AWS Infrastructure
Instructions on installing the Lambdas and configuring the required AWS resources can be found ![here](https://github.com/zzaxusl0a/APRS_notify/blob/main/images/APRS_notify%20documentation.docx.pdf)

# Hardware requirements
## Daughterboard
In order to support a switch to disable the GPS coordinates and an external temperature sensor, additional hardware is needed.  Use the schematic below to create a daughterboard to interact with the LightAPRS module.

![Daughterboard Schematic](https://github.com/zzaxusl0a/APRS_notify/assets/1844156/9b12fa11-6dd6-412b-b044-29a1633cca44)

### Bill Of Materials
| | Item | Description | Link |
|---|---|---|---|
||LightAPRS 2.0|APRS Radio Module|[QRPLabs](https://qrp-labs.com/lightaprs2.html)|
||12v-6v Power Supply|DC/DC converter for Radio module|[Amazon](https://www.amazon.com/Step-Down-Waterproof-Miniature-Converter-Supply/dp/B08RXBGH72/)|
||DS18B20 Sensor|External Temperature Sensor|[Mouser](https://mou.sr/428Tlbo)|
||SMA plug|Female PCB-Mount SMA jack|[Amazon](https://www.amazon.com/Superbat-Connectors-Connector-Coaxial-Bulkhead/dp/B09V5811S7)|
||4.7kΩ Resistor|Pull-Down for DS18B20|[Mouser](https://mou.sr/4aC7BNe)|
||10kΩ Resistor|Pull-Down for GPS control switch|[Mouser](https://mou.sr/4cXwR22)|
|optional|12v SPST switch|Switches for faceplate / control|[Amazon](https://www.amazon.com/gp/product/B012IJ35VQ)|
|optional|6-pin Chassis Connector|Allows for detachment of control panel and power|[Sparkfun](https://www.sparkfun.com/products/11475)|
|optional|Female Headers|To allow easy development on LightAPRS board|[Sparkfun](https://www.sparkfun.com/products/11895)|
|optional|Male Headers|To allow easy development on LightAPRS board|[Sparkfun](https://www.sparkfun.com/products/12693)|

## STL Files
Case designed for this project
Recommended to be printed using PETG, 20% infill, with supports:

[Case - PCB Mount Antenna](https://github.com/zzaxusl0a/APRS_notify/blob/main/STL%20files/APRS%20Case%20-%20PCB%20mount%20antenna%20-%20final%20version.stl)

[Control Panel](https://github.com/zzaxusl0a/APRS_notify/blob/main/STL%20files/APRS%20Control%20Panel%202-up.stl)

### Bill of Materials
| Item | Description |
|---|---|
|4X #1x3/8 pan-head screw|Holds LightAPRS board to base|
|4X #4x1/2 flat-head wood screw |Closes box|
