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
4. Calls action handler to publish a payload to the topic, 'TCXAction', with target action
5. Returns a successful 
<!--stackedit_data:
eyJoaXN0b3J5IjpbLTEzMjgxODYwNjJdfQ==
-->