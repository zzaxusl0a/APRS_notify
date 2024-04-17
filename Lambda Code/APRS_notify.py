import os
import base64
import boto3
import json
import time
import urllib3
import logging

from twilio.rest import Client

#setup logger
logger = logging.getLogger()
logger.setLevel("INFO")


#set program configuration here
Maximum_Temperature = 85
Minimum_Temperature = 40
Maximum_Temp_Delta = 3
Maximum_Beacon_Age = 5 #in minutes

#pick up environment variables
APRSFI_API = os.environ['APRSFI_KEY']
TWILIO_ACCOUNT_SID = os.environ['TWILIO_ACCOUNT_SID']
TWILIO_AUTH_TOKEN = os.environ['TWILIO_AUTH_TOKEN']
MESSAGING_SERVICE_SID = os.environ['TWILIO_MSG_SERVICE_SID']



#the Lambda Handler is called by AWS. Acts as core of the application
def lambda_handler(event, context):
    
    #SET EVENT FLAGS HERE
    APRS_name = "XXXXXX"
    SMS_to = "+18005551212"
    
    #set up response item
    lambda_return = {'Status': '200', 'Message': '', 'Code':''}
    
    try:
        #create instance of urllib3 and PoolManager
        http = urllib3.PoolManager()
        # Retrieve the JSON from the URL
        url = "https://api.aprs.fi/api/get?name=" +APRS_name +"&what=loc&apikey=" +APRSFI_API +"&format=json"
        response = http.request('GET',url)
        body_data = response.data
        json_payload = json.loads(body_data)
    except Exception as err:
        lambda_return['Status'] = "500"
        lambda_return['Message'] = "APRS:Exception in APRS Query: " +(f"{type(err).__name__} was raised: {err}")
        lambda_return['Code'] = "APRS"
        
        logger.exception(lambda_return['Message'])
        return {
        
            'statusCode': lambda_return['Status'],
            'body': json.dumps(lambda_return)
        }
    finally:
        http.clear()
    #endtry
    
    #continuing. We should have a good response from APRS.FI at this point
    # Check if the result field is "fail"
    result = json_payload['result']
    if result == 'fail':
        comment = "Request Failed " +json_payload['description']
        #send_alert(comment, "False")
    elif not(200 <= response.status <= 299):
        lambda_return['Status'] = "500"
        lambda_return['Message'] = "APRS:Response not 200: " +str(response.status)
        lambda_return['Code'] = "APRS"
        
        logger.exception(lambda_return['Message'])
        return {
            'statusCode': lambda_return['Status'],
            'body': json.dumps(lambda_return)
        }
    else:
        # Extract the comment from the JSON  WARNING. NOT SANITIZED!
        comment = json_payload['entries'][0]['comment']
        # Extract the last published time from the JSON
        lasttime_int = int(json_payload['entries'][0]['lasttime'])
        #print("JSON payload\n")
        #print(json.dumps(json_payload))
    #endif
    
    #we now have the required data from the APRS packet.
    
    try:
        #create a database connection
        simpleDBclient = boto3.client('sdb')
        getDB_response = simpleDBclient.get_attributes(
            DomainName='APRS_tracker',
            ItemName= APRS_name
        )
        
        #identify if we have seen this before
        if "Attributes" in getDB_response:
            #we have a record for this name, get the alert flag
            for attribute in getDB_response["Attributes"]:
                if attribute["Name"] == "alert_sent":
                    alert_sent = attribute["Value"]
                #endif
            #endfor
            #also pick up the comment for the previous temperature value
            for attribute in getDB_response["Attributes"]:
                if attribute["Name"] == "comment":
                    previous_comment = attribute["Value"]
                    previous_recorded_temp = float(previous_comment[2:7])
                #endif
            #endfor
            print("SDB:Existing entry found in DB for " +APRS_name +". Alert value is " +alert_sent)
        else:
            print("SDB:New entry in DB for " + APRS_name)
            #we don't have a record, set alert flag to false
            alert_sent = 'False'
        #endif
        
        #Parse the comment and test the temperature
        internal_temp = float(comment[2:7])
        bmp_temp = float(comment[11:16])
        
        #print("Internal temp: %.2f , BMP temp: %.2f") %(internal_temp,bmp_temp)
        
        #temperature will report 200 on known sensor error
        if internal_temp > 199:
           message_string = "Temperature Sensor Malfunction error 200"
           send_alert(message_string, alert_sent,SMS_to)
           alert_sent = 'True'
        
        #if temperature is over, go to alert
        elif internal_temp >= Maximum_Temperature:
            message_string = "Temperature exceeds Maximum! Internal Temp: %.2f" %internal_temp
            send_alert(message_string, alert_sent,SMS_to)
            alert_sent = 'True'
        
        #elseif temperature is below freezing, go to alert
        elif internal_temp <= Minimum_Temperature:
            message_string = "Temperature below Minimum! Internal Temp: %.2f" %internal_temp
            send_alert(message_string, alert_sent,SMS_to)
            alert_sent = 'True'
        
        #elseif internal and BMP temp are different by greater than 20F, go to alert
        elif not ((bmp_temp - 20) < internal_temp < (bmp_temp + 20)):
            message_string = "Temperature Sensor Mismatch! Internal Temp: %.2f, BMP Temp: %.2f" %(internal_temp, bmp_temp)
            send_alert(message_string, alert_sent,SMS_to)
            alert_sent = 'True'
                
        else:
            #if temperature has passed these checks, check the time
            #convert APRS last reported time to ISO object
            #need this for database logging and comparison
            lasttime_iso = time.strftime('%Y-%m-%dT%H:%M:%SZ%z', time.localtime(lasttime_int))
            #get current time from clock
            test_time_int = int(time.time())
            test_time_iso = time.strftime('%Y-%m-%dT%H:%M:%SZ%z', time.localtime(test_time_int))
        
            #test if report is greater than allowed minutes old
            if test_time_int > (lasttime_int + (Maximum_Beacon_Age * 60)):
                message_string = "APRS report is greater than " + str(Maximum_Beacon_Age) +" minutes old. Last Reported time: " + lasttime_iso
                send_alert(message_string, alert_sent,SMS_to)
                alert_sent = 'True'
            elif not ((previous_recorded_temp - Maximum_Temp_Delta) < internal_temp < (previous_recorded_temp + Maximum_Temp_Delta)):
                message_string = "Temperature Delta Too High! Internal Temp: %.2f, Previous Temp: %.2f " %(internal_temp,previous_recorded_temp)
                send_alert(message_string, alert_sent,SMS_to)
                alert_sent = 'True'
            else:
                #temperature and time passed checks
                message_string = "APRS is ok and current"
                alert_sent = 'False'
            #endif   
        #endtemp if here
        lambda_return['Message'] = message_string
        
        
        #Complete by publishing the current state in the database
        DBresponse = simpleDBclient.put_attributes(
            DomainName='APRS_tracker',
            ItemName=APRS_name,
            Attributes=[
                {
                    'Name': 'report_time',
                    'Value': lasttime_iso,
                    'Replace': True
                },
                {
                    'Name': 'comment',
                    'Value': comment,
                    'Replace': True
                },
                {
                    'Name': 'alert_sent',
                    'Value': alert_sent,
                    'Replace': True
                }
            ]
        )
        #TODO alert if DB response is not 200
   
        
    except Exception as err:
        lambda_return['Status'] = "500"
        lambda_return['Message'] = "Exception in SDB: " +(f"{type(err).__name__} was raised: {err}")
        lambda_return['Code'] = "SDB"
        
        logger.exception(lambda_return['Message'])
        return {
            'statusCode': lambda_return['Status'],
            'body': json.dumps(lambda_return)
        }
    finally:
        simpleDBclient.close()
    #endtry
    

    # Return to close the lambda
    return {
        'statusCode': lambda_return['Status'],
        'body': json.dumps(lambda_return)
    }
#end lambda_handler

#send alert publishes a SMS message. Currently through Twilio
#records message SID into database
#note! if alert_flag is FALSE, this will SEND a message!
def send_alert(error_message,alert_flag,sms_to_number):
    
    logger.info("SA:Error flag is: " +alert_flag +", Error message is: " +error_message)
    
    #if the alert flag is false, we want to send a message
    if alert_flag == "False":
            
        try:
             #create a database connection
            simpleDBclient = boto3.client('sdb')
            getDB_response = simpleDBclient.get_attributes(
                DomainName='APRS_tracker',
                ItemName= APRS_name
            )
            # insert Twilio Account SID into the REST API URL
            client = Client(TWILIO_ACCOUNT_SID,TWILIO_AUTH_TOKEN)
            message = client.messages.create(
                    messaging_service_sid= MESSAGE_SERVICE_SID,
                    to= sms_to_number,
                    body= error_message
                    )
            logger.info("SMS Sent")
            logger.info(message.sid)
            #record message SID in database for delivery test
            DBresponse = simpleDBclient.put_attributes(
                DomainName='APRS_tracker',
                ItemName=APRS_name,
                Attributes=[
                    {
                        'Name': 'SMS_sid',
                        'Value': message.sid,
                        'Replace': True
                    }
                ]
            )
            
        except Exception as err:
            logger.exception("Exception in SMS: " + (f"{type(err).__name__} was raised: {err}"))
        
        finally:
            simpleDBclient.close()
        #endtry
    #if the error flag is true, an alert has already been sent, so we just ignore
    else:
        logger.info("SA:Alert has already been sent. Message: " +error_message)
    #endif
#end send_alert

# This calls the handler. Use only when testing.
#print(lambda_handler("a","b"))

#eof
