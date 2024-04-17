import os
import base64
import boto3
import json
import logging
import gzip

from twilio.rest import Client

#setup logger
logger = logging.getLogger()
logger.setLevel("INFO")

#pick up environment variables
TWILIO_ACCOUNT_SID = os.environ['TWILIO_ACCOUNT_SID']
TWILIO_AUTH_TOKEN = os.environ['TWILIO_AUTH_TOKEN']
MESSAGING_SERVICE_SID = os.environ['TWILIO_MSG_SERVICE_SID']


#watchdog script
#this lambda is called by CloudWatch when an error is logged by the temp logger
#a text message is fired with the error text
#TODO: stop the monitoring process

def lambda_handler(event, context):
    #set up response items
    lambda_return = {'Status': '200', 'Message': '', 'Code':''}
    outbound_message = "Alerting Stopped! Error: "
    
    #pick up event flags
    SMS_to = "+18005551212"
    
    #unpack AWS log
    try:
        logger.info((f"Logging Event: {event}"))
        cw_data = event['awslogs']['data']
        
        compressed_payload = base64.b64decode(cw_data)
        uncompressed_payload = gzip.decompress(compressed_payload)
        payload = json.loads(uncompressed_payload)
        
        print(json.dumps(payload))
        log_entries = payload["logEvents"]
        for log_event in log_entries:
            #print(json.dumps(log_event))
            #process the log event here into an SMS message
            log_message = log_event["message"].split("\t")
            log_message_content = log_message[3].split("\n")
            logger.info((f"Failure event: {log_message_content[0]}"))
            print(log_message_content[0])
            outbound_message = outbound_message + log_message_content[0]
        #endfor
        
        #truncate message to 2 message segments in the event we have multiple log entries
        outbound_message = outbound_message[:300]
        #we have an outbound message, send sms message
        logger.info((f"SMS content: {outbound_message}"))
        
        
        # insert Twilio Account SID into the REST API URL
        client = Client(TWILIO_ACCOUNT_SID,TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            messaging_service_sid=MESSAGING_SERVICE_SID,
            to=SMS_to,
            body= error_message
        )
        logger.info((f"SMS Sent: {message.sid}"))
        lambda_return['Message'] = outbound_message
        
    except Exception as err:
        lambda_return['Status'] = "500"
        lambda_return['Message'] = "Exception in SDB: " +(f"{type(err).__name__} was raised: {err}")
        lambda_return['Code'] = "WDG"
        
        logger.exception(lambda_return['Message'])
    #endtry
    # Return to close the lambda
    return {
        'statusCode': lambda_return['Status'],
        'body': json.dumps(lambda_return)
    }
#end lambda_handler

# This calls the handler. Use only when testing.
#print(lambda_handler("a","b"))

#eof