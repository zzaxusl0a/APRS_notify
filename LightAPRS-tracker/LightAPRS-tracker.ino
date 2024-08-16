#include <Arduino.h>
#include <Wire.h>
#include <math.h>
#include <stdio.h>
#include <avr/dtostrf.h>
#include <ZeroAPRS.h>                       //https://github.com/hakkican/ZeroAPRS
#include <SparkFun_Ublox_Arduino_Library.h> //https://github.com/sparkfun/SparkFun_Ublox_Arduino_Library
#include <Adafruit_BMP085.h>                //https://github.com/adafruit/Adafruit-BMP085-Library
#include <OneWire.h>
#include <DallasTemperature.h>

#define BattPin       A5
#define GpsPwr        7
#define PwDwPin       A3
#define PowerHL       A4
#define PttPin        3
#define ONE_WIRE_BUS  A2
#define GPSEnablePin  A1


//macros
#define GpsON       digitalWrite(GpsPwr, LOW)
#define GpsOFF      digitalWrite(GpsPwr, HIGH)
#define PttON       digitalWrite(PttPin, HIGH)
#define PttOFF      digitalWrite(PttPin, LOW)
#define RadioON     digitalWrite(PwDwPin, HIGH)
#define RadioOFF    digitalWrite(PwDwPin, LOW)
#define RfHiPwr     digitalWrite(PowerHL, HIGH)
#define RfLowPwr    digitalWrite(PowerHL, LOW)

#define DEVMODE // Development mode. Uncomment to enable for debugging.

//******************************  APRS CONFIG **********************************
char    CallSign[7]="XXXXXX"; //DO NOT FORGET TO CHANGE YOUR CALLSIGN
int8_t  CallNumber=9;//SSID http://www.aprs.org/aprs11/SSIDs.txt
char    Symbol='>'; // 'O' for balloon, '>' for car, for more info : http://www.aprs.org/symbols/symbols-new.txt
bool    alternateSymbolTable = false ; //false = '/' , true = '\'

char Frequency[9]="144.3900"; //default frequency. 144.3900 for US, 144.8000 for Europe

char    comment[40] = "LightAPRS 2.0"; // Max 40 char but shorter is better.
char    StatusMessage[50] = "LightAPRS 2.0 w. firmware by WE7SKI";

//location to set spoofed GPS coordinates to when GPS switch is off.
//APRS.fi will not plot / accept beacons with no location data
//format is decimal degrees
float f_spoof_lat = 40.378155;
float f_spoof_long = -105.517733;
//*****************************************************************************

uint16_t  BeaconWait=50;  //seconds sleep for next beacon (HF or VHF). This is optimized value, do not change this if possible.
uint16_t  BattWait=60;    //seconds sleep if super capacitors/batteries are below BattMin (important if power source is solar panel) 
float     BattMin=3.3;    // min Volts to wake up.
float     DraHighVolt=5.0;    // min Volts for radio module (DRA818V) to transmit (TX) 1 Watt, below this transmit 0.5 Watt.

//******************************  APRS SETTINGS *********************************

//do not change WIDE path settings below if you don't know what you are doing :) 
uint8_t   Wide1=1; // 1 for WIDE1-1 path
uint8_t   Wide2=1; // 1 for WIDE2-1 path

/**
Airborne stations above a few thousand feet should ideally use NO path at all, or at the maximum just WIDE2-1 alone.  
Due to their extended transmit range due to elevation, multiple digipeater hops are not required by airborne stations.  
Multi-hop paths just add needless congestion on the shared APRS channel in areas hundreds of miles away from the aircraft's own location.  
NEVER use WIDE1-1 in an airborne path, since this can potentially trigger hundreds of home stations simultaneously over a radius of 150-200 miles. 
 */
uint8_t pathSize=2; // 2 for WIDE1-N,WIDE2-N ; 1 for WIDE2-N
boolean autoPathSizeHighAlt = false; //force path to WIDE2-N only for high altitude (airborne) beaconing (over 1.000 meters (3.280 feet)) 
boolean  aliveStatus = true; //for tx status message on first wake-up just once.
boolean radioSetup = false; //do not change this, temp value
static char telemetry_buff[100];// telemetry buffer
uint16_t TxCount = 1; //increased +1 after every APRS transmission

//******************************  GPS SETTINGS   *********************************
int16_t   GpsResetTime=1800; // timeout for reset if GPS is not fixed
boolean ublox_high_alt_mode_enabled = false; //do not change this
int16_t GpsInvalidTime=0; //do not change this
boolean gpsSetup=false; //do not change this.

//********************************************************************************

SFE_UBLOX_GPS myGPS;
Adafruit_BMP085 bmp;
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);
DeviceAddress insideThermometer;

int GPSEnableState = 0;  //if false, do not use GPS for time / location
boolean DS18B20active = false;  //set up value to allow for temperature sensor retry

void setup() {
  // While the energy rises slowly with the solar panel, 
  // using the analog reference low solves the analog measurement errors.
  analogReference(AR_INTERNAL1V65);
  pinMode(PttPin, OUTPUT);
  pinMode(GpsPwr, OUTPUT);
  pinMode(BattPin, INPUT);
  pinMode(PwDwPin, OUTPUT);
  pinMode(PowerHL, OUTPUT);
  pinMode(GPSEnablePin, INPUT);
  
  GpsOFF;
  PttOFF;
  RadioOFF; 
  RfLowPwr;

  SerialUSB.begin(115200);
  // Wait up to 5 seconds for serial to be opened, to allow catching
  // startup messages on native USB boards (that do not reset when
  // serial is opened).
  //Watchdog.reset();  
  unsigned long start = millis();
  while (millis() - start < 5000 && !SerialUSB){;}
  //Watchdog.reset(); 

  SerialUSB.println(F("Starting build 2024.08.15.r1"));
  Serial1.begin(9600);// for DorjiDRA818V

  APRS_init();
  APRS_setCallsign(CallSign, CallNumber);
  APRS_setDestination("APLIGA", 0);
  APRS_setPath1("WIDE1", Wide1);
  APRS_setPath2("WIDE2", Wide2);
  APRS_setPathSize(2);
  APRS_useAlternateSymbolTable(alternateSymbolTable);
  APRS_setSymbol(Symbol);
  APRS_setPathSize(pathSize);
  APRS_setGain(2);

  configDra818(Frequency);

  Wire.begin();
  bmp.begin();  //bmp sensor gets temp and pressure from the box itself

  //start the temperature sensor
  startDS18B20();

  // print systems are ready
  SerialUSB.println(F(""));
  SerialUSB.print(F("APRS (VHF) CallSign: "));
  SerialUSB.print(CallSign);
  SerialUSB.print(F("-"));
  SerialUSB.println(CallNumber);


}

void loop() {

if (readBatt() > BattMin) {  //battery power must be above minimum, or we skip to the end and wait to charge
    //appears that this will send the status message only on startup, then goes to sleep if battery minimum is not met
    if (aliveStatus) {	
      sendStatus();	   	  
      aliveStatus = false;

      while (readBatt() < BattMin) {
        sleepSeconds(BattWait); 
      }
   
    }
    // after checking for startup / status message, loop begins here
    //start GPS if not running already
    if(!gpsSetup) {gpsStart();}
      
    //Models for GPS: DYN_MODEL_PORTABLE, DYN_MODEL_STATIONARY, DYN_MODEL_PEDESTRIAN, DYN_MODEL_AUTOMOTIVE, DYN_MODEL_SEA, 
    //DYN_MODEL_AIRBORNE1g, DYN_MODEL_AIRBORNE2g, DYN_MODEL_AIRBORNE4g, DYN_MODEL_WRIST, DYN_MODEL_BIKE
    //DYN_MODEL_PORTABLE is suitable for most situations except airborne vehicles.      
    if(!ublox_high_alt_mode_enabled){setupUBloxDynamicModel(DYN_MODEL_PORTABLE);}

    //read the state of the GPS enable switch
    GPSEnableState = digitalRead(GPSEnablePin);

    if(GPSEnableState == 0) {
      SerialUSB.println("GPS switch is off"); 
    }
    else {
      SerialUSB.println("GPS switch is on");
    }
      
    //Call the GPS to get location
    myGPS.getPVT();    //gets position, velocity, time from GPS
    //print GPS output to serial
    gpsDebug();

    //Moved the APRS path size to default as this should never be flown.
    APRS_setPathSize(pathSize);
    
    //this loop tests for a GPS fix of more than 3 satellites.  
    //If we have a 3D lock, reset the invalid counter
    if ( (myGPS.getFixType() != 0) && (myGPS.getSIV() > 3) ) {
       GpsInvalidTime=0;
    }
    else{
       // We drop to here if the GPS reports no lock or less than 3 satellites
       // Set the GPS Invalid Time tracker and set the GPS Enable switch to false, since we have bad data
       GpsInvalidTime++;
       if(GpsInvalidTime > GpsResetTime){
         GpsOFF;
         ublox_high_alt_mode_enabled = false; //gps sleep mode resets high altitude mode.
         delay(1000);
         GpsON;
         GpsInvalidTime=0;
       }
       GPSEnableState = 0;
    }

    //prepare the APRS packet information
       SerialUSB.print("GPS Enable State is: ");
       SerialUSB.println(GPSEnableState);
    updatePosition();
    updateTelemetry();
    
    //sendLocation assembled and sends the packet
    sendLocation();
    SerialUSB.flush();
    //sleep for beaconing seconds.  Not doing smartbeaconing.
    sleepSeconds(BeaconWait);       
          
   }
   //we get here only if there isn't enough power to transmit, wait to charge
   else {
    sleepSeconds(BattWait);
   }
//loop ends
}

void gpsStart(){  
  bool gpsBegin=false;  
  while(!gpsBegin){
    GpsON;
    delay(1000);
    Wire.begin();
    gpsBegin=myGPS.begin();
    if(gpsBegin)break;
    #if defined(DEVMODE)  
    SerialUSB.println(F("Ublox GPS not detected at default I2C address. Will try again"));
    #endif 
    delay(2000);
  }
   // do not overload the buffer system from the GPS, disable UART output
  myGPS.setUART1Output(0); //Disable the UART1 port output 
  myGPS.setUART2Output(0); //Disable Set the UART2 port output
  myGPS.setI2COutput(COM_TYPE_UBX); //Set the I2C port to output UBX only (turn off NMEA noise)
  myGPS.saveConfiguration(); //Save the current settings to flash and BBR  
  gpsSetup=true;
}

void sleepSeconds(int sec) {
  PttOFF;
  RadioOFF;

  SerialUSB.flush();
  for (int i = 0; i < sec; i++) {
    delay(1000);   
  }

}

byte configDra818(char *freq)
{
  RadioON;
  char ack[3];
  int n;
  delay(2000);
  char cmd[50];//"AT+DMOSETGROUP=0,144.8000,144.8000,0000,4,0000"
  sprintf(cmd, "AT+DMOSETGROUP=0,%s,%s,0000,4,0000", freq, freq);
  Serial1.println(cmd);
  SerialUSB.println("RF Config");
  ack[2] = 0;
  while (ack[2] != 0xa)
  {
    if (Serial1.available() > 0) {
      ack[0] = ack[1];
      ack[1] = ack[2];
      ack[2] = Serial1.read();
    }
  }
  delay(2000);
  RadioOFF;

  if (ack[0] == 0x30) {
      SerialUSB.print(F("Frequency updated: "));
      SerialUSB.print(freq);
      SerialUSB.println(F("MHz"));
    } else {
      SerialUSB.println(F("Frequency update error!!!"));    
    }
  return (ack[0] == 0x30) ? 1 : 0;
}

//structures and sets variables in APRS object for lat, long, and time
void updatePosition() {
  // Convert and set latitude NMEA string Degree Minute Hundreths of minutes ddmm.hh[S,N].
  char latStr[10];
  int temp = 0;
  double d_lat;
  double dm_lat = 0.0;
 
  if(GPSEnableState != 0) {
    d_lat = myGPS.getLatitude() / 10000000.f;
  }
  else {
    d_lat = 0;
  }
  

  if (d_lat < 0.0) {
    temp = -(int)d_lat;
    dm_lat = temp * 100.0 - (d_lat + temp) * 60.0;
  } else {
    temp = (int)d_lat;
    dm_lat = temp * 100 + (d_lat - temp) * 60.0;
  }

  dtostrf(dm_lat, 7, 2, latStr);

  if (dm_lat < 1000) {
    latStr[0] = '0';
  }

  if (d_lat >= 0.0) {
    latStr[7] = 'N';
  } else {
    latStr[7] = 'S';
  }
 if(GPSEnableState == 0) {
    latStr[0] = '0';
    latStr[1] = '0';
    latStr[2] = '0';
    latStr[3] = '0';
  }

  APRS_setLat(latStr);

  // Convert and set longitude NMEA string Degree Minute Hundreths of minutes ddmm.hh[E,W].
  char lonStr[10];
  double d_lon;
  double dm_lon = 0.0;

  if(GPSEnableState != 0) {
    d_lon = myGPS.getLongitude() / 10000000.f;
  }
  else {
    d_lon = 0;
  }

  if (d_lon < 0.0) {
    temp = -(int)d_lon;
    dm_lon = temp * 100.0 - (d_lon + temp) * 60.0;
  } else {
    temp = (int)d_lon;
    dm_lon = temp * 100 + (d_lon - temp) * 60.0;
  }

  dtostrf(dm_lon, 8, 2, lonStr);

  if (dm_lon < 10000) {
    lonStr[0] = '0';
  }
  if (dm_lon < 1000) {
    lonStr[1] = '0';
  }

  if (d_lon <= 0.0) {
    lonStr[8] = 'W';
  } else {
    lonStr[8] = 'E';
  }
  
  if(GPSEnableState == 0) {
    lonStr[0] = '0';
    lonStr[1] = '0';
    lonStr[2] = '0';
    lonStr[3] = '0';
    lonStr[4] = '0';
  }
  APRS_setLon(lonStr);
  if(GPSEnableState != 0) {
    APRS_setTimeStamp(myGPS.getHour(), myGPS.getMinute(), myGPS.getSecond());
  }
  else {
    //setting timestamp to 99,99,99 triggers use of the alternate (no time) signal table
    APRS_setTimeStamp(99,99,99);
  }
}

//populates telemetry_buff array with heading, speed, altitude, temp and pressure from bmp, battery voltage, and number of satellites
//the comment text is added to the end of this array
void updateTelemetry() {
  //first fields are heading and speed. Set to zero if GPS has been disabled
  if(GPSEnableState != 0) {
    sprintf(telemetry_buff, "%03d", (int)(myGPS.getHeading() / 100000));
    telemetry_buff[3] += '/';
    sprintf(telemetry_buff + 4, "%03d", (int)(myGPS.getGroundSpeed() * 0.00194384f));
    telemetry_buff[7] = '/';
    telemetry_buff[8] = 'A';
    telemetry_buff[9] = '=';
    //fixing negative altitude values causing display bug on aprs.fi
    float tempAltitude = (myGPS.getAltitude() * 3.2808399)  / 1000.f;
    
    if (tempAltitude > 0) {
      //for positive values
      sprintf(telemetry_buff + 10, "%06lu", (long)tempAltitude);
    } else {
      //for negative values
      sprintf(telemetry_buff + 10, "%06d", (long)tempAltitude);
    }
  }
  else {  //GPS is not enabled
    sprintf(telemetry_buff, "000/000/A=000000");
  }
  telemetry_buff[16] = ' ';
  
  //Add temperature from DS18B20
  telemetry_buff[17] = 'T';
  telemetry_buff[18] = 'I';
  
  sensors.requestTemperatures(); // Send the command to get temperatures
  float internal_tempF = returnTemperatureF(insideThermometer);
  dtostrf(internal_tempF, 6, 2, telemetry_buff + 19);
  telemetry_buff[25] = ' ';
  
  //Add temperature and pressure from BMP
  telemetry_buff[26] = 'T';
  telemetry_buff[27] = 'B';
  float bmp_tempC = bmp.readTemperature();
  //TODO: conversion here
  dtostrf(DallasTemperature::toFahrenheit(bmp_tempC), 6, 2, telemetry_buff + 28);
  
  telemetry_buff[34] = ' ';
  telemetry_buff[35] = 'h';
  telemetry_buff[36] = 'P';
  telemetry_buff[37] = 'a';
  
  float pressure = bmp.readPressure() / 100.0; //Pa to hPa
  dtostrf(pressure, 7, 2, telemetry_buff + 38);
  telemetry_buff[45] = ' ';

  //Add voltage from battery
  telemetry_buff[46] = 'V';
    dtostrf(readBatt(), 5, 2, telemetry_buff + 47);
  telemetry_buff[52] = ' ';
  
  //Add TX count
  telemetry_buff[53] = 'T';
  telemetry_buff[54] = 'x';
  sprintf(telemetry_buff + 55, "%03d", TxCount);
  telemetry_buff[58] = ' ';
  
  //Add comment and close buffer
  sprintf(telemetry_buff + 59, "%s", comment);

  #if defined(DEVMODE)
  SerialUSB.print("Tel Buf: ");
  SerialUSB.println(telemetry_buff);
  #endif
}

//triggers radio and calls APRS_sendLoc (zeroAPRS library)
void sendLocation() {
  //test the GPSEnableStatus flag to set symbols appropriately for location
  if(GPSEnableState !=0){
    APRS_useAlternateSymbolTable(alternateSymbolTable);
    APRS_setSymbol(Symbol);
  }
  else{
    APRS_useAlternateSymbolTable(true);
    APRS_setSymbol('.');
  }
  
  SerialUSB.println(F("Location sending with comment..."));
  if (readBatt() > DraHighVolt) RfHiPwr; //DRA Power 1 Watt
  else RfLowPwr; //DRA Power 0.5 Watt
  RadioON;
  delay(2000);
  PttON;
  delay(1000);  
  //APRS_sendLoc sends the packet.
  //calls APRS_perpareloc in the library with the telemetry_buff as the comment
  //then calls APRS_sendpacket
  SerialUSB.print("TelBuf before sendloc: ");
  SerialUSB.println(telemetry_buff);
  APRS_sendLoc(telemetry_buff);
  SerialUSB.print("APRS TRACK value: ");
  SerialUSB.println(APRS_getTrack());
  delay(10);
  PttOFF;
  RadioOFF;
  SerialUSB.print(F("Location sent with comment - "));
  SerialUSB.println(TxCount);  
  TxCount++;
}

//triggers radio and calls APRS_sendStatus (zeroAPRS library)
void sendStatus() {

  SerialUSB.println(F("Status sending..."));
  if (readBatt() > DraHighVolt) RfHiPwr; //DRA Power 1 Watt
  else RfLowPwr; //DRA Power 0.5 Watt
  RadioON;
  delay(2000);
  PttON;
  delay(1000);
  //APRS_sendstatus calls APRS_preparestatus, which appears to only send a status, not a position.
  APRS_sendStatus(StatusMessage);
  delay(10);
  PttOFF;
  RadioOFF;
  delay(1000);
  SerialUSB.print(F("Status sent - "));
  SerialUSB.println(TxCount);
  TxCount++;
}

//gpsDebug prints gps status to the serial console only
void gpsDebug() { 
#if defined(DEVMODE)
    byte fixType = myGPS.getFixType();
    SerialUSB.print(F("FixType: "));
    SerialUSB.print(fixType);    

    int SIV = myGPS.getSIV();
    SerialUSB.print(F(" Sats: "));
    SerialUSB.print(SIV);

    float flat = myGPS.getLatitude() / 10000000.f;    
    SerialUSB.print(F(" Lat: "));
    SerialUSB.print(flat);    

    float flong = myGPS.getLongitude() / 10000000.f;    
    SerialUSB.print(F(" Long: "));
    SerialUSB.print(flong);        

    float altitude = myGPS.getAltitude() / 1000;
    SerialUSB.print(F(" Alt: "));
    SerialUSB.print(altitude);
    SerialUSB.print(F(" (m)"));

    float speed = myGPS.getGroundSpeed();
    SerialUSB.print(F(" Speed: "));
    SerialUSB.print(speed * 0.00194384f);
    SerialUSB.print(F(" (kn/h)"));    
        
    SerialUSB.print(" Time: ");    
    SerialUSB.print(myGPS.getYear());
    SerialUSB.print("-");
    SerialUSB.print(myGPS.getMonth());
    SerialUSB.print("-");
    SerialUSB.print(myGPS.getDay());
    SerialUSB.print(" ");
    SerialUSB.print(myGPS.getHour());
    SerialUSB.print(":");
    SerialUSB.print(myGPS.getMinute());
    SerialUSB.print(":");
    SerialUSB.print(myGPS.getSecond());
    
    SerialUSB.print(" Temp: ");
    SerialUSB.print(bmp.readTemperature());
    SerialUSB.print(" C");
    
    SerialUSB.print(" Press: ");    
    SerialUSB.print(bmp.readPressure() / 100.0);
    SerialUSB.print(" hPa");
    SerialUSB.println();  

#endif
}

void setupUBloxDynamicModel(dynModel newDynamicModel) {
  // If we are going to change the dynamic platform model, let's do it here.
  // Possible values are:
  //DYN_MODEL_PORTABLE //Applications with low acceleration, e.g. portable devices. Suitable for most situations.
  //DYN_MODEL_STATIONARY //Used in timing applications (antenna must be stationary) or other stationary applications. Velocity restricted to 0 m/s. Zero dynamics assumed.
  //DYN_MODEL_PEDESTRIAN   //Applications with low acceleration and speed, e.g. how a pedestrian would move. Low acceleration assumed.
  //DYN_MODEL_AUTOMOTIVE   //Used for applications with equivalent dynamics to those of a passenger car. Low vertical acceleration assumed
  //DYN_MODEL_SEA        //Recommended for applications at sea, with zero vertical velocity. Zero vertical velocity assumed. Sea level assumed.
  //DYN_MODEL_AIRBORNE1g   //Airborne <1g acceleration. Used for applications with a higher dynamic range and greater vertical acceleration than a passenger car. No 2D position fixes supported.
  //DYN_MODEL_AIRBORNE2g   //Airborne <2g acceleration. Recommended for typical airborne environments. No 2D position fixes supported.
  //DYN_MODEL_AIRBORNE4g   //Airborne <4g acceleration. Only recommended for extremely dynamic environments. No 2D position fixes supported.
  //DYN_MODEL_WRIST      // Not supported in protocol versions less than 18. Only recommended for wrist worn applications. Receiver will filter out arm motion.
  //DYN_MODEL_BIKE       // Supported in protocol versions 19.2

    if (myGPS.setDynamicModel(newDynamicModel) == false) // Set the dynamic model to DYN_MODEL_AIRBORNE4g
    {
      #if defined(DEVMODE)
        SerialUSB.println(F("***!!! Warning: setDynamicModel failed !!!***"));
      #endif 
    }
    else
    {
      ublox_high_alt_mode_enabled = true;
      #if defined(DEVMODE)
        SerialUSB.print(F("Dynamic platform model changed successfully! : "));
        SerialUSB.println(myGPS.getDynamicModel());
      #endif  
    }
  
  } 

float readBatt() {

  float R1 = 560000.0; // 560K
  float R2 = 100000.0; // 100K
  float value = 0.0f;

  do {    
    value =analogRead(BattPin);
    value +=analogRead(BattPin);
    value +=analogRead(BattPin);
    value = value / 3.0f;
    value = (value * 1.65) / 1024.0f;
    value = value / (R2/(R1+R2));
  } while (value > 20.0);
  return value ;

}

//returns temperature from DS18B20 in a float value. Returns 200F on error.
float returnTemperatureF(DeviceAddress deviceAddress)
{

  //attempt to restart the temp sensor if there is a failure
  if(DS18B20active == false)
  {
    startDS18B20();
  }
  
  // method 2 - faster
  float tempC = sensors.getTempC(deviceAddress);
  if(tempC == DEVICE_DISCONNECTED_C) 
  {
    SerialUSB.println("Error: Could not read temperature data");
    return 200;
  }
  //SerialUSB.print("Temp C: ");
  //SerialUSB.print(tempC);
  //SerialUSB.print(" Temp F: ");
  float tempF = DallasTemperature::toFahrenheit(tempC);
  //SerialUSB.println(tempF); // Converts tempC to Fahrenheit

  return tempF;
}

// function to print a device address - support DS18B20 troubleshooting
void printAddress(DeviceAddress deviceAddress)
{
  for (uint8_t i = 0; i < 8; i++)
  {
    if (deviceAddress[i] < 16) Serial.print("0");
    SerialUSB.print(deviceAddress[i], HEX);
  }
}

//function to set up temperature sensor - note, is successful if 1 device is active on the bus
void startDS18B20()
{
    
  //start the temperature sensor
  SerialUSB.println("Locating devices...");
  sensors.begin();
  SerialUSB.print("Found ");
  SerialUSB.print(sensors.getDeviceCount(), DEC);
  SerialUSB.println(" devices.");
  if (!sensors.getAddress(insideThermometer, 0))
  {
    SerialUSB.println("Unable to find address for Device 0"); 
    DS18B20active=false;
  }
  else
  {
    // show the addresses we found on the bus
    SerialUSB.print("Device 0 Address: ");
    printAddress(insideThermometer);
    SerialUSB.println();
    DS18B20active = true;
  }
  //set the resolution to 9 bit (Each Dallas/Maxim device is capable of several different resolutions)
  sensors.setResolution(insideThermometer, 9);
}
