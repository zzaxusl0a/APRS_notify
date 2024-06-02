import os
import json
import urllib
import logging
import base64
import hmac
import boto3
from hashlib import sha1, sha256


#setup logger
logger = logging.getLogger()
logger.setLevel("INFO")



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
  catch:
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
    #Split required fields - phone number, SMS body, and callsign
    inbound_number = event['From']
    raw_text_body = form_parameters['Body']
    text_body = split(raw_text_body)
            
    action_req = text_body[0].upper()
    #todo: do I need to put this in a try? how does this fail?
    callsign = text_body[1].upper()

    #command response logic begins here     
    if(action_req == "START"):
      #if body is START: Identify callsign, Store number in DB, along with callsign, timestamp, and active flag. Return SMS opt-in message
      logger.info("Start message received from: " +callsign)
    elif(action_req == "STOP"):
      #if body is STOP: Identify callsign, remove callsign from DB. Return SMS message monitoring stopped
      logger.info("Stop message received from: " +callsign)
    elif(action_req == "STATUS"):
      #if body is STATUS: Identify callsign, return status from DB
      logger.info("Status message received from: " +callsign)
    else:
      #else: return help message or nothing
      logger.info("invalid message received")
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
  #s = os.environ['REQUEST_URL']
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

def send_sms(phone_number, body)
  #code to send a response SMS

#end send_sms


#eof
