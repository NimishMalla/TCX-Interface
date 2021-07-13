# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

# Nimish's main

import argparse
import json
from awscrt import io, mqtt, auth, http
from awsiot import mqtt_connection_builder
import sys
import os
import threading
import RPi.GPIO as GPIO
import time
import asyncio
from uuid import uuid4
import logging





#GPIO 
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
parser.add_argument('--message', default="", help=                                     "Message to publish. " +
                                                                                       "Specify empty string to publish nothing.")
parser.add_argument('--count', default=0, type=int, help=                           "Number of messages to publish/receive before exiting. " +
                                                                                       "Specify 0 to run forever.")
parser.add_argument('--use-websocket', default=False, action='store_true', help=    "To use a websocket instead of raw mqtt. If you " +
                                                                                       "specify this option you must specify a region for signing, you can also enable proxy mode.")
parser.add_argument('--signing-region', default='us-east-1', help=                  "If you specify --use-web-socket, this " +
                                                                                       "is the region that will be used for computing the Sigv4 signature")
parser.add_argument('--proxy-host', help=                                           "Hostname for proxy to connect to. Note: if you use this feature, " +
                                                                                       "you will likely need to set --root-ca to the ca for your proxy.")
parser.add_argument('--proxy-port', type=int, default=8080, help=                   "Port for proxy to connect to.")
parser.add_argument('--verbosity', choices=[x.name for x in io.LogLevel], default=io.LogLevel.NoLogs.name,
    help='Logging level')

# Using globals to simplify sample code
args = parser.parse_args()
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

received_count = 0
received_all_event = threading.Event()

# Callback when connection is accidentally lost.
def on_connection_interrupted(connection, error, **kwargs):
    print("Connection interrupted. error: {}".format(error))


# Callback when an interrupted connection is re-established.
def on_connection_resumed(connection, return_code, session_present, **kwargs):
    print("Connection resumed. return_code: {} session_present: {}".format(return_code, session_present))

    if return_code == mqtt.ConnectReturnCode.ACCEPTED and not session_present:
        print("Session did not persist. Resubscribing to existing topics...")
        resubscribe_future, _ = connection.resubscribe_existing_topics()

        # Cannot synchronously wait for resubscribe result because we're on the connection's event-loop thread,
        # evaluate result with a callback instead.
        resubscribe_future.add_done_callback(on_resubscribe_complete)


def on_resubscribe_complete(resubscribe_future):
        resubscribe_results = resubscribe_future.result()
        print("Resubscribe results: {}".format(resubscribe_results))

        for topic, qos in resubscribe_results['topics']:
            if qos is None:
                sys.exit("Server rejected resubscribe to topic: {}".format(topic))

# Resets relay array to ideal original state - all buttons off and switch set to wifi
def setAllHigh():
    GPIO.output(22, GPIO.HIGH)
    GPIO.output(13, GPIO.HIGH)
    GPIO.output(19, GPIO.HIGH)
    GPIO.output(26, GPIO.HIGH)
    GPIO.output(12, GPIO.HIGH)
    GPIO.output(16, GPIO.HIGH)
    GPIO.output(20, GPIO.HIGH)
    GPIO.output(21, GPIO.HIGH)

# Performs a two-finger salute to reset the TCX and get ready for re-provisioning
def doSalute():
    GPIO.output(26, GPIO.LOW)       # switch to wired
    logging.debug('switch relay 4 to wired')
    time.sleep(3)                   # wait for switch
    GPIO.output(13, GPIO.LOW)       # press filter pump
    logging.debug('press relay 2')
    GPIO.output(19, GPIO.LOW)       # press switch mode
    logging.debug('press relay 3')
    time.sleep(5)                   # hold buttons down
    GPIO.output(26, GPIO.HIGH)      # switch to wifi
    logging.debug('switch relay 4 to wifi')
    time.sleep(5)                   # wait for reset
    GPIO.output(13, GPIO.HIGH)      # release filter pump
    logging.debug('release relay 2')
    GPIO.output(19, GPIO.HIGH)      # release switch mode
    logging.debug('release relay 3')
    sys.exit()

# 'Presses' once on the filter pump button
def pressFilterPump():
    GPIO.output(13, GPIO.LOW)       # press filter pump
    logging.debug('press relay 2')
    time.sleep(0.25)                   # hold briefly
    logging.debug('wait')
    GPIO.output(13, GPIO.HIGH)      # release filter pump
    logging.debug('release relay 2')
    sys.exit()

# 'Presses' once on the Bluetooth button
def pressProvision():
    GPIO.output(22, GPIO.LOW)       # press Bluetooth
    logging.debug('press relay 1')
    time.sleep(0.25)                   # hold briefly
    logging.debug('wait')
    GPIO.output(22, GPIO.HIGH)      # release Bluetooth
    logging.debug('release relay 1')
    sys.exit()

# 'Presses' once on the switch mode button
def pressSwitchMode():
    GPIO.output(19, GPIO.LOW)       # press switch mode
    logging.debug('press relay 3')
    time.sleep(0.25)                   # hold briefly
    logging.debug('wait')
    GPIO.output(19, GPIO.HIGH)      # release switch mode
    logging.debug('release relay 3')
    sys.exit()

# 'Switches' TCX to wifi mode
def switchWifi():
    GPIO.output(26, GPIO.HIGH)
    logging.debug('switch relay 4 high')

def switchWired():
    GPIO.output(26, GPIO.LOW)
    logging.debug('switch relay 4 low')

# Called when message received
def actionHandler(action):
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
        os._exit(0)
    else:
        logging.info(f'ERROR: Received non-existing Command: {action}')
        return False
    thr.start()
    return True

# Callback when the subscribed topic receives a message
def on_message_received(topic, payload, dup, qos, retain, **kwargs):
    data = json.loads(payload)
    
    if actionHandler(data['action']):
        logging.info("Received message from topic '{}': {}".format(topic, payload.decode("utf-8")))

    global received_count
    received_count += 1
    if received_count == args.count:
        received_all_event.set()

if __name__ == '__main__':
    # Spin up resources
    event_loop_group = io.EventLoopGroup(1)
    host_resolver = io.DefaultHostResolver(event_loop_group)
    client_bootstrap = io.ClientBootstrap(event_loop_group, host_resolver)

    if args.use_websocket == True:
        proxy_options = None
        if (args.proxy_host):
            proxy_options = http.HttpProxyOptions(host_name=args.proxy_host, port=args.proxy_port)

        credentials_provider = auth.AwsCredentialsProvider.new_default_chain(client_bootstrap)
        mqtt_connection = mqtt_connection_builder.websockets_with_default_aws_signing(
            endpoint=args.endpoint,
            client_bootstrap=client_bootstrap,
            region=args.signing_region,
            credentials_provider=credentials_provider,
            websocket_proxy_options=proxy_options,
            ca_filepath=args.root_ca,
            on_connection_interrupted=on_connection_interrupted,
            on_connection_resumed=on_connection_resumed,
            client_id=args.client_id,
            clean_session=False,
            keep_alive_secs=6)

    else:
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

    print("Connecting to {} with client ID '{}'...".format(
        args.endpoint, args.client_id))

    connect_future = mqtt_connection.connect()

    # Future.result() waits until a result is available
    connect_future.result()
    print("Connected!")

    #setAllHigh() # set all relays to high

    # Subscribe
    print("Subscribing to topic '{}'...".format(args.topic))
    subscribe_future, packet_id = mqtt_connection.subscribe(
        topic=args.topic,
        qos=mqtt.QoS.AT_LEAST_ONCE,
        callback=on_message_received)

    subscribe_result = subscribe_future.result()
    print("Subscribed with {}".format(str(subscribe_result['qos'])))

    # Publish message to server desired number of times.
    # This step is skipped if message is blank.
    # This step loops forever if count was set to 0.
    if args.message:
        if args.count == 0:
            print ("Sending messages until program killed")
        else:
            print ("Sending {} message(s)".format(args.count))

        publish_count = 1
        while (publish_count <= args.count) or (args.count == 0):
            message = "{} [{}]".format(args.message, publish_count)
            print("Publishing message to topic '{}': {}".format(args.topic, message))
            mqtt_connection.publish(
                topic=args.topic,
                payload=message,
                qos=mqtt.QoS.AT_LEAST_ONCE)
            time.sleep(3)
            publish_count += 1

    # Wait for all messages to be received.
    # This waits forever if count was set to 0.
    if args.count != 0 and not received_all_event.is_set():
        print("Waiting for all messages to be received...")

    received_all_event.wait()
    print("{} message(s) received.".format(received_count))

    # Disconnect
    print("Disconnecting...")
    disconnect_future = mqtt_connection.disconnect()
    disconnect_future.result()
    print("Disconnected!")
