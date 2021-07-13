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

def lambda_handler(event, context):
    action = event['queryStringParameters']['action']
    
    options = ['salute', 'provision', 'filterpump', 'switchmode', 'switchwifi', 'switchwired', 'quit']
    body = f"Sent command: {action}"
    if action not in options:
        body = f"ERROR: Non-existing Command: {action}"
        doAction(action)
    else:
        if action == 'quit':
            body = 'Sent command: Quitting program'
        doAction(action)
    
    return {
        'statusCode': 200,
        'body': json.dumps(body)
    }
