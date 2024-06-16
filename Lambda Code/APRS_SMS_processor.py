import os
import json
import urllib
import logging
import base64
import hmac
import boto3
import time
import calendar
from datetime import datetime, timezone, timedelta
from hashlib import sha1
from twilio.rest import Client


#setup logger
logger = logging.getLogger()
logger.setLevel("INFO")

#setup environment variables
INBOUND_WEBHOOK_URL = os.environ['REQUEST_URL']
TWILIO_ACCOUNT_SID = os.environ['TWILIO_ACCOUNT_SID']
TWILIO_AUTH_TOKEN = os.environ['TWILIO_AUTH_TOKEN']
MESSAGING_SERVICE_SID = os.environ['TWILIO_MSG_SERVICE_SID']

#set application defaults
default_schedule_expiration_hours = 4
default_maximum_schedule_hours = 24

def lambda_handler(event, context):
    #setup return object
    lambda_return = {'Status': '200', 'Message': '', 'Code':''}
  
    logger.info("received: " + str(event))
  
    #First, collect and decode the headers to extract the signature and url
    #if we don't have a twilio signature header, throw exception and exit
    try:
        twilio_signature = event["headers"]["x-twilio-signature"]
        logger.info("inbound SMS signature: " +twilio_signature)
        #body is in base64, decode
        request_body = base64.b64decode(event["body"])
        payload = request_body.decode('utf8')
        logger.info("inbound SMS body: " +payload)
    except Exception as err:
        logger.error("Exception in Webhook parsing: " + (f"{type(err).__name__} was raised: {err}"))
        lambda_return =  {'Status': '400', 'Message': 'Invalid SMS received', 'Code':'iSMS'}
        return {
            'statusCode': lambda_return['Status'],
            'body': json.dumps(lambda_return)
        }
    #endtry

    #at this point, we should have a valid twilio webhook and have decoded the body
    #split the body payload into dictionary of parameters
    res = dict()
    x=payload.split("&")
    for i in x:
        a,b=i.split("=")
        res[a]=[urllib.parse.unquote_plus(b)]
    #endfor  
    # printing result
    print("The parsed URL Params : " + str(res))

    #feed headers and parameters into the validator function
    request_valid = twilio_validator(twilio_signature, res)

    #if request is valid, process.  Otherwise, exit
    if request_valid:
        logger.info("Received Valid SMS")
        #Split required fields - phone number, SMS body, and callsign into strings
        try:
            inbound_number = res['From'][0]
            raw_text_body = res['Body']
            text_body = raw_text_body[0].split()
            action_req = text_body[0].upper()
            callsign = text_body[1].upper()
        except Exception as err:
            logger.info("Exception in SMS parsing: " + (f"{type(err).__name__} was raised: {err}"))
            outbound_status_message = "Invalid Command: Use START, STOP, or STATUS followed by callsign. ex. START AB1CDE"
            send_sms(inbound_number, outbound_status_message)
            return {
                'statusCode': lambda_return['Status'],
                'body': json.dumps(lambda_return)
            }
        #endtry
        
        #command response logic begins here
        #define the outbound status message variable
        outbound_status_message = ""
        if(action_req == "START"):
            #if body is START: Identify callsign, Store number in DB, along with callsign, timestamp, and active flag. Return SMS opt-in message
            logger.info("Start message received from: " +callsign)
            outbound_status_message = configure_cron_job(callsign, inbound_number, True)
            send_sms(inbound_number, outbound_status_message)
        elif(action_req == "STOP"):
            #if body is STOP: Identify callsign, remove callsign from DB. Return SMS message monitoring stopped
            logger.info("Stop message received from: " +callsign)
            outbound_status_message = configure_cron_job(callsign, inbound_number, False)
            send_sms(inbound_number, outbound_status_message)
        elif(action_req == "STATUS"):
            #if body is STATUS: Identify callsign, return status from DB
            logger.info("Status message received from: " +callsign)
            outbound_status_message = monitor_status(callsign)
            logger.info("Monitor status for " +callsign +"is: " +outbound_status_message)
            send_sms(inbound_number, outbound_status_message)
        else:
            #else: return help message or nothing
            logger.info("invalid command received")
            send_sms(inbound_number,"Invalid Command: Use START, STOP, or STATUS followed by callsign. ex. START AB1CDE")
        #endif
    # if request is not from twilio, give appropriate response
    else:
        logger.error("ERROR: SMS Signature Failed")
        lambda_return = {'Status': '400', 'Message': 'SMS Signature validation failed', 'Code':'iSMS'}
    #endif
    return {
        'statusCode': lambda_return['Status'],
        'body': json.dumps(lambda_return)
        }
#end handler

def twilio_validator(signature, res):
# if twilioSignature exists and message from authorized number, create a validator & a dictionary of received data
    return_value = False
    s = INBOUND_WEBHOOK_URL.strip()
    t = "/"
    if res:
        for param_name in sorted(set(res)):
            value = res[param_name]
            temp_out = ''.join(map(str, value))
            t += param_name + temp_out
        #endfor
    #endif
    test_string = s+t
    logger.info("Validator test String: " +test_string)
    # compute signature and compare signatures
    mac = hmac.new((TWILIO_AUTH_TOKEN).encode("utf-8"), test_string.encode("utf-8"), sha1)
    computed = base64.b64encode(mac.digest())
    computed = computed.decode("utf-8").strip()
    logger.info("Validator Computed signature: " +computed +" Provided signature: " +signature)
    
    if(computed == signature):
        return_value = True
    else:
        test_string = s +":443" +t
        mac = hmac.new((TWILIO_AUTH_TOKEN).encode("utf-8"), test_string.encode("utf-8"), sha1)
        computed = base64.b64encode(mac.digest())
        computed = computed.decode("utf-8").strip()
        logger.info("Validator Computed signature: " +computed +" Provided signature: " +signature)
        if(computed == signature):
            return_value = True
        #endif
    #endif
    return return_value
#end twilio_validator

#function sends sms message. Does not return a value, will throw exception if fails
def send_sms(sms_to_number, message_body):
    #code to send a response SMS
    try:
        logger.info("SMS message send request: " +sms_to_number +", " +message_body)
        client = Client(TWILIO_ACCOUNT_SID,TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            messaging_service_sid= MESSAGING_SERVICE_SID,
            to= sms_to_number,
            body= message_body
            )
    except Exception as err:
        logger.exception("Exception in SMS: " + (f"{type(err).__name__} was raised: {err}"))
    #endtry
#end send_sms

#function to check the most recent APRS packet received and return human-readable string
def monitor_status(callsign):
    #set the return value
    return_value = "not found"
    try:
        #create a database connection to find most recent status
        simpleDBclient = boto3.client('sdb')
        getDB_response = simpleDBclient.get_attributes(
            DomainName='APRS_tracker',
            ItemName= callsign
            )
        #look for record for the callsign and extract last report
        logger.info("DB Response obtained")
        if "Attributes" in getDB_response:
            for attribute in getDB_response["Attributes"]:
                if attribute["Name"] == "comment":
                    previous_comment = attribute["Value"]
                    previous_recorded_temp = float(previous_comment[2:7])
                elif attribute["Name"] == "report_time":
                    previous_reported_time = attribute["Value"]
                elif attribute["Name"] == "alert_sent":
                    alert_sent = attribute["Value"]
                #endif
            #endfor
            #TODO: find if cron job is still active, and for how long
            current_epoch_time = time.time()
            test_epoch_time = calendar.timegm(time.strptime(previous_reported_time,"%Y-%m-%dT%H:%M:%SZ%z"))
            test_delta_in_min = (current_epoch_time - test_epoch_time) / 60
            
            return_value = ("Most recent report was: %.2f F at: %.0f minutes ago. Alert Status is: " %(previous_recorded_temp, test_delta_in_min)) + alert_sent
            
        else:
            #we don't have a record
            #TODO: should we look for the cron job?
            return_value = "No record found for this callsign"
        #endif
    except Exception as err:
        lambda_return['Status'] = "500"
        lambda_return['Message'] = "Exception in Monitor: " +(f"{type(err).__name__} was raised: {err}")
        lambda_return['Code'] = "MON"
        
        logger.exception(lambda_return['Message'])
        return_value = "database error"
    finally:
        simpleDBclient.close()
        return return_value 
    #endtry
#end monitor_status

#manages the monitoring cron job. Requires a callsign, sms number, and boolean active flag
#returns a human-readable status string
#TODO: add some kind of abuse rate-limiting here
def configure_cron_job(callsign, inbound_sms_number, monitor_active):
    try:
        #set up the EventBridge scheduler object
        EB_client = boto3.client('scheduler')
        #parse the request
        if(monitor_active):
            #request is to create a new monitor, or edit an existing one
            #see: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/scheduler/client/create_schedule.html
            
            #calculate x hours from now to set expiration window
            monitor_expiration_time = datetime.now(timezone.utc) + timedelta(hours=default_schedule_expiration_hours)
            #set up event input string
            lambda_event_input_string ="{\"APRS_name\":\"" +callsign +"\",\"SMS_to\":\"" +inbound_sms_number +"\"}"
            #create schedule entry
            try:
                EB_client.create_schedule(
                    ActionAfterCompletion='DELETE',
                    Description='Runs the APRS notify lambda every 5 minutes to test for temperature change',
                    EndDate=monitor_expiration_time,
                    FlexibleTimeWindow={
                        "Mode": "OFF"
                    },
                    GroupName="APRS_monitor_schedules",
                    Name=callsign,
                    ScheduleExpression="rate(5 minutes)",
                    Target={
                        "Arn": "arn:aws:lambda:us-west-2:764880901691:function:TemperatureAlert",
                        "Input": lambda_event_input_string,
                        "RetryPolicy": {
                            "MaximumEventAgeInSeconds": 86400,
                            "MaximumRetryAttempts": 0
                        },
                        "RoleArn": "arn:aws:iam::764880901691:role/service-role/Amazon_EventBridge_Scheduler_LAMBDA_9f7d527372"
                    }
                )
                return_value = "APRS Monitor: Session started for site "+callsign +". Monitoring automatically stops in " +str(default_schedule_expiration_hours) +" hours. Text STOP to end. Text STATUS for status. Message & Data rates may apply."
            except EB_client.exceptions.ConflictException:
                #there is a conflict. Check the creation time. If greater than max allowed time, do not allow extension
                logger.info("Creation Requested for already running monitor in: " +callsign)
                #get the current schedule
                current_schedule = EB_client.get_schedule(
                    GroupName="APRS_monitor_schedules",
                    Name=callsign
                )
                schedule_creation_time = current_schedule["CreationDate"]
                current_utc_time = datetime.now(timezone.utc)
                maximum_schedule_time = schedule_creation_time + timedelta(hours=default_maximum_schedule_hours)
                if(current_utc_time < maximum_schedule_time):
                    #allow update of schedule
                    #calculate x hours from now to set expiration window
                    monitor_expiration_time = datetime.now(timezone.utc) + timedelta(hours=default_schedule_expiration_hours)
                    #set up event input string
                    lambda_event_input_string ="{\"APRS_name\":\"" +callsign +"\",\"SMS_to\":\"" +inbound_sms_number +"\"}"
                    EB_client.update_schedule(
                        ActionAfterCompletion='DELETE',
                        Description='Runs the APRS notify lambda every 5 minutes to test for temperature change',
                        EndDate=monitor_expiration_time,
                        FlexibleTimeWindow={
                            "Mode": "OFF"
                        },
                        GroupName="APRS_monitor_schedules",
                        Name=callsign,
                        ScheduleExpression="rate(5 minutes)",
                        Target={
                            "Arn": "arn:aws:lambda:us-west-2:764880901691:function:TemperatureAlert",
                            "Input": lambda_event_input_string,
                            "RetryPolicy": {
                                "MaximumEventAgeInSeconds": 86400,
                                "MaximumRetryAttempts": 0
                            },
                            "RoleArn": "arn:aws:iam::764880901691:role/service-role/Amazon_EventBridge_Scheduler_LAMBDA_9f7d527372"
                        }
                    )
                    return_value = "Monitoring active for: " +callsign +". Monitoring automatically stops in " +str(default_schedule_expiration_hours) +" hours. Data and Msg charges may apply. STOP to end."
                else:
                    return_value = "Extension Limit Reached. STOP to end."
                #endif
            #end conflictexception handling
            #endtry (note: general exceptions will be caught by the previous handler)
        else:
            #request is to delete monitor
            #need to check that the request to delete is coming from the originating number
            requested_schedule_list = EB_client.list_schedules(
                GroupName='APRS_monitor_schedules',
                NamePrefix=callsign
                )

            #get schedule from list
            requested_schedule = EB_client.get_schedule(
                GroupName='APRS_monitor_schedules',
                Name=requested_schedule_list['Schedules'][0]['Name']
                )
            #should have the correct schedule in the requested_schedule object. Check for phone number match
            #in the input JSON
            lambda_arguments = json.loads(requested_schedule['Target']['Input'])
            print(lambda_arguments['SMS_to'])
            if (lambda_arguments['SMS_to'] == str(inbound_sms_number)):
            #parse the request and delete monitor
                response = EB_client.delete_schedule(
                    GroupName='APRS_monitor_schedules',
                    Name=requested_schedule['Name']
                    )
                return_value = "Monitoring stopped for: " +callsign
            else:
                return_value = "You do not have permission to stop monitoring for: " +callsign
            #endif
        #endif

    except Exception as err:
        logger.exception("Exception in SCH: " +(f"{type(err).__name__} was raised: {err}"))
        return_value = "Exception occured. Monitoring not changed"
    finally:
        EB_client.close()
        return return_value
    #endtry
#end configure_cron_job

#This calls the handler. Use only when testing.
#you will need to capture and create a test_event_object
#print(lambda_handler(test_event,"b"))

#eof
