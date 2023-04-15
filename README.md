# pylon2mqtt
Reads values from Pylontech US2000 batteries and publish to a MQTT broker

# Description
I wanted to read the values of my Pylontech batteries from console port (RS232 protocol) and use them in my HomeAssistant installation (through MQTT).
I found two interesting projects that could work for this:
* [ClassicDIY/PylonToMQTT](https://github.com/ClassicDIY/PylonToMQTT)
* [Frankkkkk/python-pylontech](https://github.com/Frankkkkk/python-pylontech)

but none of them worked for me, so I did a mix between them, creating this projects

The main changes I had to implement were:
* Start the communication at 1200 baud rate, and then change to 4800 baud rate
* Change the _address_ field on the commands to value=1. PylonToMQTT project uses 0 as main pack battery and python-pylontech project uses 2 as main pack battery (because of RS485 protocol specification). Neither 0 or 2 worked for me, I received responses with CID2 = 0x90 (address error), but 1 worked for me.
* Some methods use commands that do not exist in RS232 protocol specification, like method _get_version_info()_ which uses command 0xC1 or method _get_barcode()_ which uses command 0xC2. These methods returns an error frame with CID2 = 0x04 (CID2 invalidation), so I had to search for an alternative command.
* I have added some new commands (from python-pylontech and some by myself) like _get_protocol_version()_, _get_manufacturer_info()_ or _set_baud_rate()_

# How to use
PylontToMQTT project has different ways of use it, from a Docker, into a ESP32, from command line... I have implemented only command line way, so you can only run it with Pyhton.
However the only file I have changed is support/pylontech.py, so all other ways (ESP32, Docker...) should work if you replace only this file.

## Requirements
Install these libraries: paho-mqtt, pyserial, construct using pip:

```
pip install pyserial paho-mqtt construct
```

## Run it!
Run it from command line with python using this parameters:
```
--pylon_port </dev/ttyUSB0>     : The USB port on the raspberry pi (default is /dev/ttyUSB0).  
--rack_name <Main>              : The name used to identify the battery rack. 
--mqtt_host <127.0.0.1>         : The IP or URL of the MQTT Broker, defaults to 127.0.0.1 if unspecified.  
--mqtt_port <1883>              : The port to you to connect to the MQTT Broker, defaults to 1883 if unspecified.  
--mqtt_root <PylonToMQTT>       : The root for your MQTT topics, defaults to PylonToMQTT if unspecified.  
--mqtt_user <username>          : The username to access the MQTT Broker (default is no user).  
--mqtt_pass <password>          : The password to access the MQTT Broker (default is no password).
--publish_rate <5>              : The amount of seconds between updates when in wake mode (default is 5 seconds).
```

For example:
```
python3 pylon_to_mqtt.py --pylon_port /dev/ttyUSB0 --rack_name Main --mqtt_host 192.168.2.245 --mqtt_root Pylontech --mqtt_user tomascrespo --mqtt_pass mysecretpassword --publish_rate 5
```

## Run it as a service
I run it as a service in Debian 11 (bullseye). Instructions could be different for other Linux distros.

Create the file `pylon2mqtt.service` into `/etc/systemd/system` with contents:
```
[Unit]
Description=Read values from Pylontech batteries and publish into MQTT

[Service]
User=pi
WorkingDirectory=/home/pi/pylon2mqtt
ExecStart=python3 pylon_to_mqtt.py --pylon_port /dev/ttyUSB0 --rack_name Main --mqtt_host localhost --mqtt_root Pylontech --mqtt_user tomascrespo --mqtt_pass mysecretpassword --publish_rate 5
Restart=always

[Install]
WantedBy=multi-user.target
```

And finally run your service
```
sudo systemctl daemon-reload
sudo systemctl enable pylon2mqtt
sudo systemctl start pylon2mqtt
```
# Pylontech RS232 protocol specification
Pylontech RS232 protocol specification [in this file](https://github.com/tomascrespo/pylon2mqtt/blob/main/PYLON%20LFP%20Battery%20communication%20protocol%20-%20RS232%20V2.8%2020161216.pdf)


# @todo
* Try to change baud rate to greater speed, like 115200
