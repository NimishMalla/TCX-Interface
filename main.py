# main.py
import json
from awscrt import io, mqtt, auth, http
from awsiot import mqtt_connection_builder
import sys
from os import _exit
import threading
import RPi.GPIO as GPIO
import time
import asyncio
from uuid import uuid4
import logging
import smbus
import configparser

cfp = configparser.ConfigParser()
cfp.read('/home/pi/Desktop/TCX1/config.ini')
cfd = {}
for k,v in cfp.items('Config'):
    cfd[k] = v
DEBUG = int(cfd['debug'])
ENDPOINT = cfd['endpoint']
CERT = cfd['cert']
ROOT_CA = cfd['root_ca']
KEY = cfd['key']
CLIENT_ID = "test-" + str(uuid4())
TOPIC = cfd['topic']
TOPIC2 = cfd['topic2']
MODE = int(cfd['mode'])
COUNT = 0
SIGNING_REGION = 'us-east-1'
VERBOSITY = io.LogLevel.NoLogs.name



# Setup GPIO defaults
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(6, GPIO.OUT, initial=GPIO.HIGH) #1
PROV = 6
GPIO.setup(13, GPIO.OUT, initial=GPIO.HIGH) #2
FPUMP = 13
GPIO.setup(19, GPIO.OUT, initial=GPIO.HIGH) #3
SMODE = 19
if MODE == 0:
    GPIO.setup(26, GPIO.OUT, initial=GPIO.LOW) #4
else:
    GPIO.setup(26, GPIO.OUT, initial=GPIO.HIGH) #4
SCONN = 26

# Setup I2C bus for digital potentiometer
bus = smbus.SMBus(1)
bus.write_i2c_block_data(0x2c, 0x00, [0x32])
time.sleep(0.5)
bus.write_i2c_block_data(0x2c, 0x01, [0x32])
time.sleep(0.5)
bus.write_i2c_block_data(0x2c, 0x02, [0x32])
time.sleep(1)

'''
----------------------------------------------------------------------------------------------------------------------------------------------------
'''

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
io.init_logging(getattr(io.LogLevel, VERBOSITY), 'stderr')

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
    global MODE
    time.sleep(1)
    if MODE == 0:
        GPIO.output(SCONN, GPIO.HIGH) # switch to wifi
        MODE = 1
        logging.debug('switch relay 4 to wifi')
    elif MODE == 1:
        GPIO.output(SCONN, GPIO.LOW) # switch to wired
        MODE = 0
        logging.debug('switch relay 4 to wired')
    time.sleep(3)
    
    GPIO.output(FPUMP, GPIO.LOW) # press filter pump
    logging.debug('press relay 2')
    GPIO.output(SMODE, GPIO.LOW) # press switch mode
    logging.debug('press relay 3')
    time.sleep(3)
    
    if MODE == 0:
        GPIO.output(SCONN, GPIO.HIGH) # switch to wifi
        MODE = 1
        logging.debug('switch relay 4 to wifi')
    elif MODE == 1:
        GPIO.output(SCONN, GPIO.LOW) # switch to wired
        MODE = 0
        logging.debug('switch relay 4 to wired')
    time.sleep(2)
    
    GPIO.output(FPUMP, GPIO.HIGH)      # release filter pump
    logging.debug('release relay 2')
    GPIO.output(SMODE, GPIO.HIGH)      # release switch mode
    logging.debug('release relay 3')
    sys.exit()
    
    
# 'Presses' once on the filter pump button
def pressFilterPump():
    '''Send brief LOW signal to GPIO13 (filter pump)'''
    GPIO.output(FPUMP, GPIO.LOW)       # press filter pump
    logging.debug('press relay 2')
    time.sleep(0.25)                   # hold briefly
    logging.debug('wait')
    GPIO.output(FPUMP, GPIO.HIGH)      # release filter pump
    logging.debug('release relay 2')
    sys.exit()

# 'Presses' once on the Bluetooth button
def pressProvision():
    '''Send brief LOW signal to GPIO6 (provision)'''
    GPIO.output(PROV, GPIO.LOW)       # press Bluetooth
    logging.debug('press relay 1')
    time.sleep(0.25)                   # hold briefly
    logging.debug('wait')
    GPIO.output(PROV, GPIO.HIGH)      # release Bluetooth
    logging.debug('release relay 1')
    sys.exit()

# 'Presses' once on the switch mode button
def pressSwitchMode():
    '''Send brief LOW signal to GPIO19 (switch mode)'''
    GPIO.output(SMODE, GPIO.LOW)       # press switch mode
    logging.debug('press relay 3')
    time.sleep(0.25)                   # hold briefly
    logging.debug('wait')
    GPIO.output(SMODE, GPIO.HIGH)      # release switch mode
    logging.debug('release relay 3')
    sys.exit()

# 'Switches' TCX to wifi mode
def switchWifi():
    '''Output HIGH (default) signal to GPIO26 (switch) to activate wifi mode'''
    GPIO.output(SCONN, GPIO.HIGH)
    MODE = 1
    logging.debug('switch relay 4 high')

# 'Switches' TCX to wired mode
def switchWired():
    '''Output LOW signal to GPIO26 (switch) to activate wired mode'''
    GPIO.output(SCONN, GPIO.LOW)
    MODE = 0
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
        bus.write_i2c_block_data(0x2c, 0x02, [val])
        logging.debug(f'send {val} to 0x2c channel 4')

# Callback when the action topic receives a message
def on_action_received(topic, payload, dup, qos, retain, **kwargs):
    '''Relays action requests to handler'''
    data = json.loads(payload)
    
    if actionHandler(data['action']):
        logging.info("Received message from topic '{}': {}".format(topic, payload.decode("utf-8")))

    global received_count
    received_count += 1
    if received_count == COUNT:
        received_all_event.set()

# Callback when the temperature topic receives a message
def on_temp_received(topic, payload, dup, qos, retain, **kwargs):
    '''Relays temperature requests to handler'''
    data = json.loads(payload)
    
    logging.info("Received message from topic '{}': {}".format(topic, payload.decode("utf-8")))
    
    if data["sensor"] == 'fail':
        logging.info('ERROR: Incorrect format for requesting temperature')
    else:
        changeTemperature(data["sensor"], int(data["val"]))

    global received_count
    received_count += 1
    if received_count == COUNT:
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
        endpoint=ENDPOINT,
        cert_filepath=CERT,
        pri_key_filepath=KEY,
        client_bootstrap=client_bootstrap,
        ca_filepath=ROOT_CA,
        on_connection_interrupted=on_connection_interrupted,
        on_connection_resumed=on_connection_resumed,
        client_id=CLIENT_ID,
        clean_session=False,
        keep_alive_secs=6)

    # Connect to MQ client
    logging.info("Connecting to {} with client ID '{}'...".format(
        ENDPOINT, CLIENT_ID))

    connect_future = mqtt_connection.connect()

    # Future.result() waits until a result is available
    connect_future.result()
    logging.info("Connected!")

    # Subscribe to TCXAction
    logging.info("Subscribing to topic '{}'...".format(TOPIC))
    subscribe_future, packet_id = mqtt_connection.subscribe(
        topic=TOPIC,
        qos=mqtt.QoS.AT_LEAST_ONCE,
        callback=on_action_received)

    subscribe_result = subscribe_future.result()
    logging.info("Subscribed with {}".format(str(subscribe_result['qos'])))
    
    # Subscribe to TCXTemp
    logging.info("Subscribing to topic '{}'...".format(TOPIC2))
    subscribe_future_2, packet_id_2 = mqtt_connection.subscribe(
        topic=TOPIC2,
        qos=mqtt.QoS.AT_LEAST_ONCE,
        callback=on_temp_received)
    
    subscribe_result_2 = subscribe_future_2.result()
    logging.info("Subscribed with {}".format(str(subscribe_result_2['qos'])))

    # Publish message to server desired number of times.
    # This step is skipped if message is blank.
    # This step loops forever if count was set to 0.
    

    # Wait for all messages to be received.
    # This waits forever if count was set to 0.
    if COUNT != 0 and not received_all_event.is_set():
        logging.info("Waiting for all messages to be received...")

    received_all_event.wait()
    logging.info("{} message(s) received.".format(received_count))

    # Disconnect
    logging.info("Disconnecting...")
    disconnect_future = mqtt_connection.disconnect()
    disconnect_future.result()
    logging.info("Disconnected!")
