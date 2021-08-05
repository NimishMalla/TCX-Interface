import json
import boto3

client = boto3.client('iot-data', region_name='us-east-1')



def doAction(action):
    # Set topic, qos, payload
    client.publish(
        topic = 'TCXAction',
        qos = 1,
        payload = json.dumps({ "action": action })
    )
    
def doTempAction(sensor, val):
    client.publish(
        topic = 'TCXTemp',
        qos = 1,
        payload = json.dumps({"action": "temperature", "sensor": sensor, "val": val})
    )

    
def failure(type, action):
    # Called when invalid input is given
    if type == 'ne':
        return {'statusCode': 200,'body': json.dumps(f"ERROR: Non-existing Command: {action}")}
    else:
        return {'statusCode': 200,'body': json.dumps("ERROR: Incorrect Format")}
    
def existing(action, cl):
    # Called when any existing action is requested
    if action == 'quit':
        doAction(action)
        return {'statusCode': 200,'body': json.dumps("Sent command: Quitting program")}
    elif action == 'temperature':
        if len(cl) == 3 and list(cl.keys())[1] == 'sensor' and list(cl.keys())[2] == 'val':
            sensor, val = cl['sensor'], cl['val']
            if type(sensor) != str or val.isdigit() == False:
                doTempAction('fail', val)
                return failure('f', 'format: wrong types for temperature')
            val = round(int(val)/10)*10
            doTempAction(sensor, val)
            return {'statusCode': 200,'body': json.dumps(f"Sent command: Change temperature of {sensor} to {val}")}
        else:
            doTempAction(sensor, val)
            return failure('f', 'format: not enough args for temperature')
    else:
        doAction(action)
        return {'statusCode': 200,'body': json.dumps(f"Sent command: {action}")}

def lambda_handler(event, context):
    options = ['salute', 'provision', 'filterpump', 'switchmode', 'switchwifi', 'switchwired', 'quit', 'temperature']
    commandList = event['queryStringParameters']
    if len(commandList) == 0 or len(commandList) >= 4:
        return failure('f', 'format: no arg or too many args')
    
    if list(commandList.keys())[0] != 'action':
        return failure('f', 'format: no action arg')
    
    action = commandList['action']
    if action not in options:
        doAction(action)
        return failure('ne', action)
    else:
        return existing(action, commandList)
