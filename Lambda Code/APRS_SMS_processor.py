import os
import json
import urllib
import logging
import base64
import hmac
import boto3
from hashlib import sha1, sha256
from twilio.rest import Client


#setup logger
logger = logging.getLogger()
logger.setLevel("INFO")

#setup environment variables
INBOUND_WEBHOOK_URL = os.environ['REQUEST_URL']
TWILIO_ACCOUNT_SID = os.environ['TWILIO_ACCOUNT_SID']
TWILIO_AUTH_TOKEN = os.environ['TWILIO_AUTH_TOKEN']
MESSAGING_SERVICE_SID = os.environ['TWILIO_MSG_SERVICE_SID']


def lambda_handler(event, context):
  #setup return object
  lambda_return = {'Status': '200', 'Message': '', 'Code':''}

  #define test event - remove
  event = {"version": "2.0", "routeKey": "$default", "rawPath": "/", "rawQueryString": "", "headers": {"content-length": "462", "x-amzn-tls-version": "TLSv1.2", "x-forwarded-proto": "https", "x-forwarded-port": "443", "x-forwarded-for": "54.225.56.82", "x-twilio-signature": "vuYGHb+n89QhGFEOaNgqg4nnk+o=", "x-home-region": "us1", "accept": "*/*", "x-amzn-tls-cipher-suite": "ECDHE-RSA-AES128-GCM-SHA256", "x-amzn-trace-id": "Root=1-664fb255-4a2c7bba78c325b802bfb4f2", "i-twilio-idempotency-token": "38053878-a5d4-4295-a906-cca8f58027c9", "host": "wlbzgytolyvqirav53yrx4bm3q0ooaxi.lambda-url.us-west-2.on.aws", "content-type": "application/x-www-form-urlencoded", "user-agent": "TwilioProxy/1.1"}, "requestContext": {"accountId": "anonymous", "apiId": "wlbzgytolyvqirav53yrx4bm3q0ooaxi", "domainName": "wlbzgytolyvqirav53yrx4bm3q0ooaxi.lambda-url.us-west-2.on.aws", "domainPrefix": "wlbzgytolyvqirav53yrx4bm3q0ooaxi", "http": {"method": "POST", "path": "/", "protocol": "HTTP/1.1", "sourceIp": "54.225.56.82", "userAgent": "TwilioProxy/1.1"}, "requestId": "d7a64d63-9daa-4327-8548-a61e75816b1e", "routeKey": "$default", "stage": "$default", "time": "23/May/2024:21:17:09 +0000", "timeEpoch": 1716499029182}, "body": "VG9Db3VudHJ5PVVTJlRvU3RhdGU9TkMmU21zTWVzc2FnZVNpZD1TTTI4NzljMjUzODQ5MTY4YWZmMWEzNTBjNWI1ODhjOGQzJk51bU1lZGlhPTAmVG9DaXR5PSZGcm9tWmlwPTk0MzAyJlNtc1NpZD1TTTI4NzljMjUzODQ5MTY4YWZmMWEzNTBjNWI1ODhjOGQzJkZyb21TdGF0ZT1DQSZTbXNTdGF0dXM9cmVjZWl2ZWQmRnJvbUNpdHk9UEFMTytBTFRPJkJvZHk9U3RhcnQrd2U3c2tpLTkrJkZyb21Db3VudHJ5PVVTJlRvPSUyQjE5ODA5OTgyNzc3Jk1lc3NhZ2luZ1NlcnZpY2VTaWQ9TUc1OWVkMTliYjYzZjcwYzAzYjZkZjllOWU5OWVmYzk1MiZUb1ppcD0mTnVtU2VnbWVudHM9MSZNZXNzYWdlU2lkPVNNMjg3OWMyNTM4NDkxNjhhZmYxYTM1MGM1YjU4OGM4ZDMmQWNjb3VudFNpZD1BQzQ0NWJjOTk5NDVmNmY2YWUzMjc5OTQyMzNhOTZhYzZjJkZyb209JTJCMTY1MDgxNDE2NDgmQXBpVmVyc2lvbj0yMDEwLTA0LTAx", "isBase64Encoded": True}
  print("received: " + str(event))
  
  #First, collect and decode the headers to extract the signature and url
  #if we don't have a twilio signature header, throw exception and exit
  #request_payload = json.loads(event)
  #print(event["headers"]["x-twilio-signature"])
  try:
    twilio_signature = event["headers"]["x-twilio-signature"]
    logger.info("inbound SMS signature: " +twilio_signature)
    #body is in base64, decode
    request_body = base64.b64decode(event["body"])
    print(request_body.decode('utf8'))
    payload = request_body.decode('utf8')
    logger.info("inbound SMS body: " +payload)
  except Exception as err:
    #TODO: review exception - if no header, fail gracefully.
    #if err.<graceful>:
      lambda_return =  {'Status': '400', 'Message': 'Invalid SMS received', 'Code':'iSMS'}
      return {
        'statusCode': lambda_return['Status'],
        'body': json.dumps(lambda_return)
      }
    #else
      # logger.exception("Exception in SMS: " + (f"{type(err).__name__} was raised: {err}"))
    #endif
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
    #Split required fields - phone number, SMS body, and callsign
    inbound_number = event['From']
    raw_text_body = form_parameters['Body']
    text_body = split(raw_text_body)
            
    action_req = text_body[0].upper()
    #todo: do I need to put this in a try? how does this fail?
    callsign = text_body[1].upper()

    #command response logic begins here  
    #define the outbound status message variable
    outbound_status_message = ""

    if(action_req == "START"):
      #if body is START: Identify callsign, Store number in DB, along with callsign, timestamp, and active flag. Return SMS opt-in message
      logger.info("Start message received from: " +callsign)
      outbound_status_message = configure_cron_job(callsign, inbound_number, TRUE)
      send_sms(inbound_number, outbound_status_message)
    elif(action_req == "STOP"):
      #if body is STOP: Identify callsign, remove callsign from DB. Return SMS message monitoring stopped
      logger.info("Stop message received from: " +callsign)
      outbound_status_message = configure_cron_job(callsign, inbound_number, FALSE)
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

def twilio_validator(signature, params)
  # if twilioSignature exists and message from authorized number, create a validator & a dictionary of received data
  
  s = "https://wlbzgytolyvqirav53yrx4bm3q0ooaxi.lambda-url.us-west-2.on.aws/"
  if res:
    for param_name in sorted(set(res)):
      value = res[param_name]
      temp_out = ''.join(map(str, value))
      s += param_name + temp_out
    #endfor
  #endif
  # compute signature and compare signatures
  mac = hmac.new(("8dc3ca5f7c98bad20ccaad0f2d24c82d").encode("utf-8"), s.encode("utf-8"), sha1)
  computed = base64.b64encode(mac.digest())
  computed = computed.decode("utf-8").strip()
  #implement re-test including port 443 for inclusivity.
  s += ":443"
#end twilio_validator

#function sends sms message. Does not return a value, will throw exception if fails
def send_sms(sms_to_number, message_body)
  #code to send a response SMS
  try:
     client = Client(TWILIO_ACCOUNT_SID,TWILIO_AUTH_TOKEN)
     message = client.messages.create(
       messaging_service_sid= MESSAGE_SERVICE_SID,
       to= sms_to_number,
       body= message_body
     )
  except Exception as err:
     logger.exception("Exception in SMS: " + (f"{type(err).__name__} was raised: {err}"))
  #endtry
#end send_sms

#function to check the most recent APRS packet received and return human-readable string
def monitor_status(callsign)
  #set the return value
  return_value = "not found"
  
  try:
    #create a database connection to find most recent status
    simpleDBclient = boto3.client('sdb')
    getDB_response = simpleDBclient.get_attributes(
      DomainName='APRS_tracker',
      ItemName= callsign
    )
    #look for record for callsign
    if "Attributes" in getDB_response:
      #we have a record for this name, get the alert flag
      for attribute in getDB_response["Attributes"]:
        if attribute["Name"] == "alert_sent":
          alert_sent = attribute["Value"]
        #endif
      #endfor
      #extract details from the comment
      for attribute in getDB_response["Attributes"]:
        if attribute["Name"] == "comment":
          previous_comment = attribute["Value"]
          previous_recorded_temp = float(previous_comment[2:7])
          #TODO: extract last recorded time - here or elsewhere?
          #previous_reported_time = time.strftime('%Y-%m-%dT%H:%M:%SZ%z', time.localtime(lasttime_int))
          previous_reported_time = "now"
        #endif
      #endfor
      #TODO: find if cron job is still active, and for how long?
      #we now have required variables, set the return value
      return_value = "Most Recent report was: " +previous_recorded_temp +"F at: " +previous_reported_time)
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
def configure_cron_job(callsign, inbound_sms_number, monitor_active)
  try:
    #set up the EventBridge scheduler object
    EB_client = boto3.client('scheduler')
    #parse the request
    if(monitor_active):
      #request is to create a new monitor, or edit an existing one
      #may need an anti-abuse here to avoid extending past xx hours
      #see: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/scheduler/client/create_schedule.html
      #TODO: create a scheduling group called APRS_monitor
      
      return_value = "Monitoring active for: " +callsign
    else:
      #request is to delete monitor
      #need to check that the request to delete is coming from the originating number
      #see: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/scheduler/client/delete_schedule.html
      #TODO: check all this - it's psuedocode!
      #list schedule (returns dict)
      requested_schedule_list = client.list_schedules(
        GroupName='APRS_monitor',
        NamePrefix=callsign
      )
      
      #get schedule from list
      requested_schedule = client.get_schedule(
        GroupName='APRS_monitor',
        Name=requested_schedule_list.schedules[0].Name
      )
  
      #should have the correct schedule in the requested_schedule object. Check for phone number match
      #in the input JSON
      print(json.dumps(requested_schedule.Target.Input)
        
      if requested_schedule.Target.Input.Phone = inbound_sms_number:
        #parse the request and delete monitor
        response = client.delete_schedule(
          GroupName='APRS_monitor',
          Name=requested_schedule.Name
        )
        return_value = "Monitoring stopped for: " +callsign
      else:
         return_value = "You do not have permission to stop monitoring for: " +callsign
      #endif
    #endif

  except Exception as err:
     lambda_return['Status'] = "500"
     lambda_return['Message'] = "Exception in SCH: " +(f"{type(err).__name__} was raised: {err}")
     lambda_return['Code'] = "SCH"
        
     logger.exception(lambda_return['Message'])
     return_value = "Exception occured. Monitoring not changed"
  finally:
    EB_client.close()
    return return_value
  #endtry
#end configure_cron_job



#eof
