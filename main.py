# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

# Nimish's main

import argparse
import json
from awscrt import io, mqtt, auth, http
from awsiot import mqtt_connection_builder
import sys
#import os
from os import _exit
import threading
import RPi.GPIO as GPIO
import time
import asyncio
from uuid import uuid4
import logging
import boto3
import smbus



# Setup GPIO defaults
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(22, GPIO.OUT, initial=GPIO.HIGH) #1
GPIO.setup(13, GPIO.OUT, initial=GPIO.HIGH) #2
GPIO.setup(19, GPIO.OUT, initial=GPIO.HIGH) #3
GPIO.setup(26, GPIO.OUT, initial=GPIO.HIGH) #4
GPIO.setup(12, GPIO.OUT, initial=GPIO.HIGH) #5
GPIO.setup(16, GPIO.OUT, initial=GPIO.HIGH) #6
GPIO.setup(20, GPIO.OUT, initial=GPIO.HIGH) #7
GPIO.setup(21, GPIO.OUT, initial=GPIO.HIGH) #8


# This sample uses the Message Broker for AWS IoT to send and receive messages
# through an MQTT connection. On startup, the device connects to the server,
# subscribes to a topic, and begins publishing messages to that topic.
# The device should receive those same messages back from the message broker,
# since it is subscribed to that same topic.

parser = argparse.ArgumentParser(
    description="Send and receive messages through and MQTT connection.")
parser.add_argument('--debug', default=2, help=                                     "Level of feedback desired.")
parser.add_argument('--endpoint', required=True, help=                              "Your AWS IoT custom endpoint, not including a port. " +
                                                                                       "Ex: \"abcd123456wxyz-ats.iot.us-east-1.amazonaws.com\"")
parser.add_argument('--cert', help=                                                 "File path to your client certificate, in PEM format.")
parser.add_argument('--key', help=                                                  "File path to your private key, in PEM format.")
parser.add_argument('--root-ca', help=                                              "File path to root certificate authority, in PEM format. " +
                                                                                       "Necessary if MQTT server uses a certificate that's not already in " +
                                                                                       "your trust store.")
parser.add_argument('--client-id', default="test-" + str(uuid4()), help=            "Client ID for MQTT connection.")
parser.add_argument('--topic', default="test/topic", help=                          "Topic to subscribe to, and publish messages to.")
parser.add_argument('--topic2', default="TCXTemp", help=                            "Topic to use for temperature changes")
parser.add_argument('--count', default=0, type=int, help=                           "Number of messages to publish/receive before exiting. " +
                                                                                       "Specify 0 to run forever.")
parser.add_argument('--signing-region', default='us-east-1', help=                  "If you specify --use-web-socket, this " +
                                                                                       "is the region that will be used for computing the Sigv4 signature")
parser.add_argument('--verbosity', choices=[x.name for x in io.LogLevel], default=io.LogLevel.NoLogs.name,
    help='Logging level')

'''
----------------------------------------------------------------------------------------------------------------------------------------------------
'''

# Parse run parameters from terminal launch
args = parser.parse_args()

# Setup I2C bus for digital potentiometer
bus = smbus.SMBus(1)

# Declare temperature conversions
temps = {
    10: 0xD0,
    20: 0x90,
    38: 0x5F,
    30: 0x58,
    40: 0x47,
    50: 0x32,
    60: 0x28,
    70: 0x20,
    80: 0x1A,
    90: 0x14,
    100: 0x10,
    110: 0xC,
    120: 0xA
    }

# Setup debug level selection
DEBUG = int(args.debug)
if DEBUG == 1:
    DEBUG = logging.DEBUG
    print('DEBUG set to DEBUG')
elif DEBUG == 2:
    DEBUG = logging.INFO
    print('DEBUG set to INFO')
else:
    DEBUG = logging.CRITICAL
    print('DEBUG set to NONE')
logging.basicConfig(format='%(message)s', level=DEBUG)
io.init_logging(getattr(io.LogLevel, args.verbosity), 'stderr')

# Set received count to default
received_count = 0
received_all_event = threading.Event()

'''
----------------------------------------------------------------------------------------------------------------------------------------------------
'''

# Callback when connection is accidentally lost.
def on_connection_interrupted(connection, error, **kwargs):
    logging.info("Connection interrupted. error: {}".format(error))


# Callback when an interrupted connection is re-established.
def on_connection_resumed(connection, return_code, session_present, **kwargs):
    logging.info("Connection resumed. return_code: {} session_present: {}".format(return_code, session_present))

    if return_code == mqtt.ConnectReturnCode.ACCEPTED and not session_present:
        logging.info("Session did not persist. Resubscribing to existing topics...")
        resubscribe_future, _ = connection.resubscribe_existing_topics()

        # Cannot synchronously wait for resubscribe result because we're on the connection's event-loop thread,
        # evaluate result with a callback instead.
        resubscribe_future.add_done_callback(on_resubscribe_complete)


def on_resubscribe_complete(resubscribe_future):
        resubscribe_results = resubscribe_future.result()
        logging.info("Resubscribe results: {}".format(resubscribe_results))

        for topic, qos in resubscribe_results['topics']:
            if qos is None:
                sys.exit("Server rejected resubscribe to topic: {}".format(topic))

'''
----------------------------------------------------------------------------------------------------------------------------------------------------
'''

# Performs a two-finger salute to reset the TCX and get ready for re-provisioning
def doSalute():
    '''Send sequence to 2-finger-salute'''
    time.sleep(1)
    GPIO.output(26, GPIO.LOW)       # switch to wired
    logging.debug('switch relay 4 to wired')
    time.sleep(3)                   # wait for switch
    GPIO.output(13, GPIO.LOW)       # press filter pump
    logging.debug('press relay 2')
    GPIO.output(19, GPIO.LOW)       # press switch mode
    logging.debug('press relay 3')
    time.sleep(3)                   # hold buttons down
    GPIO.output(26, GPIO.HIGH)      # switch to wifi
    logging.debug('switch relay 4 to wifi')
    time.sleep(2)                   # wait for reset
    GPIO.output(13, GPIO.HIGH)      # release filter pump
    logging.debug('release relay 2')
    GPIO.output(19, GPIO.HIGH)      # release switch mode
    logging.debug('release relay 3')
    sys.exit()

# 'Presses' once on the filter pump button
def pressFilterPump():
    '''Send brief LOW signal to GPIO13 (filter pump)'''
    GPIO.output(13, GPIO.LOW)       # press filter pump
    logging.debug('press relay 2')
    time.sleep(0.25)                   # hold briefly
    logging.debug('wait')
    GPIO.output(13, GPIO.HIGH)      # release filter pump
    logging.debug('release relay 2')
    sys.exit()

# 'Presses' once on the Bluetooth button
def pressProvision():
    '''Send brief LOW signal to GPIO22 (provision)'''
    GPIO.output(22, GPIO.LOW)       # press Bluetooth
    logging.debug('press relay 1')
    time.sleep(0.25)                   # hold briefly
    logging.debug('wait')
    GPIO.output(22, GPIO.HIGH)      # release Bluetooth
    logging.debug('release relay 1')
    sys.exit()

# 'Presses' once on the switch mode button
def pressSwitchMode():
    '''Send brief LOW signal to GPIO19 (switch mode)'''
    GPIO.output(19, GPIO.LOW)       # press switch mode
    logging.debug('press relay 3')
    time.sleep(0.25)                   # hold briefly
    logging.debug('wait')
    GPIO.output(19, GPIO.HIGH)      # release switch mode
    logging.debug('release relay 3')
    sys.exit()

# 'Switches' TCX to wifi mode
def switchWifi():
    '''Output HIGH (default) signal to GPIO26 (switch) to activate wifi mode'''
    GPIO.output(26, GPIO.HIGH)
    logging.debug('switch relay 4 high')

# 'Switches' TCX to wired mode
def switchWired():
    '''Output LOW signal to GPIO26 (switch) to activate wired mode'''
    GPIO.output(26, GPIO.LOW)
    logging.debug('switch relay 4 low')

# Called when action message received
def actionHandler(action):
    '''Handles buttons and switch by starting threads targeting respective function. Returns False on error or True on success.'''
    global status
    if action == 'salute':
        thr = threading.Thread(target=doSalute)
    elif action == 'provision':
        thr = threading.Thread(target=pressProvision)
    elif action == 'filterpump':
        thr = threading.Thread(target=pressFilterPump)
    elif action == 'switchmode':
        thr = threading.Thread(target=pressSwitchMode)
    elif action == 'switchwifi':
        thr = threading.Thread(target=switchWifi)
    elif action == 'switchwired':
        thr = threading.Thread(target=switchWired)
    elif action == 'quit':
        _exit(0)
    else:
        logging.info(f'ERROR: Received non-existing Command: {action}')
        return False
    thr.start()
    return True

# Called when temperature message received
def changeTemperature(sensor, val):
    '''Sends correct signals using I2C bus to digital potentiometer based on API parameters'''
    global bus
    global temps
    val = temps[val]
    
    if sensor == 'air':
        bus.write_i2c_block_data(0x2c, 0x00, [val])
        logging.debug(f'send {val} to 0x2c channel 1')
    elif sensor == 'water':
        bus.write_i2c_block_data(0x2c, 0x01, [val])
        logging.debug(f'send {val} to 0x2c channel 2')
    elif sensor == 'solar':
        bus.write_i2c_block_data(0x2c, 0x03, [val])
        logging.debug(f'send {val} to 0x2c channel 4')

# Callback when the action topic receives a message
def on_action_received(topic, payload, dup, qos, retain, **kwargs):
    '''Relays action requests to handler'''
    data = json.loads(payload)
    
    if actionHandler(data['action']):
        logging.info("Received message from topic '{}': {}".format(topic, payload.decode("utf-8")))

    global received_count
    received_count += 1
    if received_count == args.count:
        received_all_event.set()

# Callback when the temperature topic receives a message
def on_temp_received(topic, payload, dup, qos, retain, **kwargs):
    '''Relays temperature requests to handler'''
    data = json.loads(payload)
    
    logging.info("Received message from topic '{}': {}".format(topic, payload.decode("utf-8")))
    changeTemperature(data["sensor"], int(data["val"]))

    global received_count
    received_count += 1
    if received_count == args.count:
        received_all_event.set()        

'''
----------------------------------------------------------------------------------------------------------------------------------------------------
'''

if __name__ == '__main__':
    # Spin up resources
    event_loop_group = io.EventLoopGroup(1)
    host_resolver = io.DefaultHostResolver(event_loop_group)
    client_bootstrap = io.ClientBootstrap(event_loop_group, host_resolver)

    
    mqtt_connection = mqtt_connection_builder.mtls_from_path(
        endpoint=args.endpoint,
        cert_filepath=args.cert,
        pri_key_filepath=args.key,
        client_bootstrap=client_bootstrap,
        ca_filepath=args.root_ca,
        on_connection_interrupted=on_connection_interrupted,
        on_connection_resumed=on_connection_resumed,
        client_id=args.client_id,
        clean_session=False,
        keep_alive_secs=6)

    # Connect to MQ client
    logging.info("Connecting to {} with client ID '{}'...".format(
        args.endpoint, args.client_id))

    connect_future = mqtt_connection.connect()

    # Future.result() waits until a result is available
    connect_future.result()
    logging.info("Connected!")

    # Subscribe to TCXAction
    logging.info("Subscribing to topic '{}'...".format(args.topic))
    subscribe_future, packet_id = mqtt_connection.subscribe(
        topic=args.topic,
        qos=mqtt.QoS.AT_LEAST_ONCE,
        callback=on_action_received)

    subscribe_result = subscribe_future.result()
    logging.info("Subscribed with {}".format(str(subscribe_result['qos'])))
    
    # Subscribe to TCXTemp
    logging.info("Subscribing to topic TCXTemperature")
    subscribe_future_2, packet_id_2 = mqtt_connection.subscribe(
        topic=args.topic2,
        qos=mqtt.QoS.AT_LEAST_ONCE,
        callback=on_temp_received)
    
    subscribe_result_2 = subscribe_future_2.result()
    logging.info("Subscribed with {}".format(str(subscribe_result_2['qos'])))

    # Publish message to server desired number of times.
    # This step is skipped if message is blank.
    # This step loops forever if count was set to 0.
    

    # Wait for all messages to be received.
    # This waits forever if count was set to 0.
    if args.count != 0 and not received_all_event.is_set():
        logging.info("Waiting for all messages to be received...")

    received_all_event.wait()
    logging.info("{} message(s) received.".format(received_count))

    # Disconnect
    logging.info("Disconnecting...")
    disconnect_future = mqtt_connection.disconnect()
    disconnect_future.result()
    logging.info("Disconnected!")
