# TCX-Interface
Outline
-
This [project](https://zodiacpoolsystems.atlassian.net/wiki/spaces/STG/pages/1469644835/Project+-+TCX+Interface) aims to enable test team members to automate physical interaction with the TCX Command Hub system.

The code is hosted partially local and on the cloud - TCXAction.py is the AWS Lambda code and main.py is hosted locally on the Raspberry Pi needed to set the project up.

Lambda
- 
1. Creates a MQTT connection client
2. Receives event consisting of instructions from RESTful API Query Parameters
3. Verifies whether instruction exists and sends either a success or failure validation message
4. Calls action/temperature handler to publish a payload to the corresponding topic with target action
5. Returns a successful status code regardless in order to allow error-handling on the Pi as well

Main Script
-
6. Ran with argument flags and corresponding input to provide certification
7. Sets up GPIO outputs to default HIGH signal
8. Parses arguments to collect important information
9. Sets logging level (local verbosity) based on argument
10. Callback functions to act on various triggers (connection, interruptions, etc.)
11. Callback functions for various actions (bluetooth button, temperature, etc.)
12. Local handler to process payload received from Lambda through MQTT.
13. Action callback with success logging *or* failure logging

 Available Commands
 -
 - 'salute': two-finger salute to re-provision
 - 'provision': presses Bluetooth to Phone button
 - 'filterpump': presses Filter Pump button
 - 'switchmode': cycles through modes once
 - 'switchwifi': switches TCX to wifi mode
 - 'switchwired': switches TCX to wired mode
 - 'temperature', 'sensor', 'val'
 - 
<!--stackedit_data:
eyJoaXN0b3J5IjpbLTE1MzQ5ODY2NjEsLTQyMTk4Mzk5Ml19
-->