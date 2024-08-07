#!/usr/bin/env python

"""MQTT monitoring relay for rtl_433 communication."""

# This program listens on a UDP socket for syslog messages with a json
# payload, and publishes the data via MQTT.  The broker connection is
# kept open (and automatically reconnects on failure).  Each device
# is mapped to its own topic,

# Dependencies:
#   Paho-MQTT; see https://pypi.python.org/pypi/paho-mqtt

#   Optionally: PEP 3143 - Standard daemon process library
#      (on 2.7,  pip install python-daemon)

# To enable daemon support, uncomment the following line and adjust
# run().  Note that print() is still used.
# import daemon

from __future__ import print_function
from __future__ import with_statement

import socket
import json
import paho.mqtt.client as mqtt

# The config class represents a config object.  The constructor takes
# an optional pathname, and will switch on the suffix (.yaml for now)
# and read a dictionary.
class rtlconfig(object):

    # Initialize with default values.
    c = {
        # Syslog socket configuration
        'UDP_IP': "127.0.0.1",
        'UDP_PORT': 1433,
        
        # MQTT broker configuration
        'MQTT_HOST': "127.0.0.1",
        'MQTT_PORT': 1883,
        'MQTT_USERNAME': None,
        'MQTT_PASSWORD': None,
        'MQTT_TLS': False,
        'MQTT_PREFIX': "sensor/rtl_433",
        'MQTT_INDIVIDUAL_TOPICS': True,
        'MQTT_JSON_TOPIC': True,
    }
    
    def __init__(self, f=None):
        fdict = None

        # Try to read a dictionary from f.
        if f:
            try:
                # Assume yaml. \todo Check and support other formats
                import yaml
                with open(f) as fh:
                    fdict = yaml.safe_load(fh)
            except:
                print('Did not read {f} (no yaml, not found, bad?).'.format(f=f))
            
        # Merge fdict into configdict.
        if fdict:
            for (k, v) in fdict.items():
                self.c[k] = v

    # Support c['name'] references.
    def __getitem__(self, k):
        return self.c[k]

# Create a config object, defaults modified by the config file if present.
c = rtlconfig("rtl_433_mqtt_relay.yaml")

def mqtt_connect(client, userdata, flags, rc):
    """Handle MQTT connection callback."""
    print("MQTT connected: " + mqtt.connack_string(rc))


def mqtt_disconnect(client, userdata, rc):
    """Handle MQTT disconnection callback."""
    print("MQTT disconnected: " + mqtt.connack_string(rc))


# Create listener for incoming json string packets.
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
sock.bind((c['UDP_IP'], c['UDP_PORT']))


# Map characters that will cause problems or be confusing in mqtt
# topics.
def sanitize(text):
    """Sanitize a name for Graphite/MQTT use."""
    return (text
            .replace(" ", "_")
            .replace("/", "_")
            .replace(".", "_")
            .replace("&", ""))


def publish_sensor_to_mqtt(mqttc, data, line):
    """Publish rtl_433 sensor data to MQTT."""

    # Construct a topic from the information that identifies which
    # device this frame is from.
    # NB: id is only used if channel is not present.
    path = c['MQTT_PREFIX']
    if "model" in data:
        path += "/" + sanitize(data["model"])
    if "channel" in data:
        path += "/" + str(data["channel"])
    if "id" in data:
        path += "/" + str(data["id"])

    if c['MQTT_INDIVIDUAL_TOPICS']:
        # Publish some specific items on subtopics.
        if "battery_ok" in data:
            mqttc.publish(path + "/battery", data["battery_ok"])

        if "humidity" in data:
            mqttc.publish(path + "/humidity", data["humidity"])

        if "temperature_C" in data:
            mqttc.publish(path + "/temperature", data["temperature_C"])

        if "depth_cm" in data:
            mqttc.publish(path + "/depth", data["depth_cm"])

    if c['MQTT_JSON_TOPIC']:
        # Publish the entire json string on the main topic.
        mqttc.publish(path, line)

def parse_syslog(line):
    """Try to extract the payload from a syslog line."""
    line = line.decode("ascii")  # also UTF-8 if BOM
    if line.startswith("<"):
        # Fields should be "<PRI>VER", timestamp, hostname, command, pid, mid, sdata, payload.
        # The payload might have spaces, so force split to stop after the sixth space.
        fields = line.split(None, 7)
        line = fields[-1]
    else:
        # Hope that the line was just json without the syslog header.
        pass
    return line


def rtl_433_probe():
    """Run a rtl_433 UDP listener."""

    ## Connect to MQTT
    if hasattr(mqtt, 'CallbackAPIVersion'):  # paho >= 2.0.0
        mqttc = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION1)
    else:
        mqttc = mqtt.Client()
    mqttc.on_connect = mqtt_connect
    mqttc.on_disconnect = mqtt_disconnect
    if c['MQTT_USERNAME'] != None:
        mqttc.username_pw_set(c['MQTT_USERNAME'], password=c['MQTT_PASSWORD'])
    if c['MQTT_TLS']:
        mqttc.tls_set()
    mqttc.connect_async(c['MQTT_HOST'], c['MQTT_PORT'], 60)
    mqttc.loop_start()

    ## Receive UDP datagrams, extract json, and publish.
    while True:
        line, addr = sock.recvfrom(1024)
        try:
            line = parse_syslog(line)
            data = json.loads(line)
            publish_sensor_to_mqtt(mqttc, data, line)

        except ValueError:
            pass


def run():
    """Run main or daemon."""
    # with daemon.DaemonContext(files_preserve=[sock]):
    #  detach_process=True
    #  uid
    #  gid
    #  working_directory
    rtl_433_probe()


if __name__ == "__main__":
    run()
