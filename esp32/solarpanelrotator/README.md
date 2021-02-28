# Updates to the code:

I hate this editor, can not copy and paste text ...

- 7.12.2020 Jari Hiltunen project start
- 8.12.2020 Initial version ready before class splitting. Stepper shall follow the sun.
- 17.2.2021 Added limiter switch operation. Limiter switch is installed so that turning counterclockwise switch
          puller pushes the switch down. Counterwise turn must be limited to maximum steps (about 340 degrees rotation).
          Added solarpanel voltage reading.
- 18.2.2021: Changed to non-asynchronous model, because it does not make sense to have async in ULP mode.
           Corrected voltage values to conform voltage splitter values (divide by 2).
           Ready to go with MQTT and BME280
- 19.2.2021: Added error handling, runtimeconfig.json handling, rotation based on time differences and SOUTH_STEP etc.
- 20.2.2021: Changed stepper motor calculation, added (ported) Suntime calculation for sunset and sunrise.
- 21.2.2021: Fixed zeroposition, added counter to measure steps needed to bypass the limiter switch etc.
- 22.2.2021: Added DST calculation and set localtime() from timedifference
- 23.2.2021: Added boottimelogger. With this I try to find random bug which seems to cause code to crash. Something escapes from try: except.
- 26.2.2021: Testing solarpanel charging. Reorganized error trapping and corrected mistakes in StepperMotor-class
- 27.2.2021: Most likely catched error which caused code to crash. Relates to ntptime.settime() seldom OverFlow errors.
- 28.2.2021: Rootacause for seldom crashes is ntptime.settime() and now tried to catch error with another approach

* Design video https://youtu.be/3X_NrbZY1hA
* Latest 3D printable parts https://www.thingiverse.com/thing:4758620
* Operational video https://youtu.be/PPeND70pGnA
* Operational video https://youtu.be/X6Q_mx0qn1I

# Error debugging with boottime.log:

* Errored logging:
* ----------------
* Boottime Logger
* Old log renamed to old
* New file started
* ----------------
* Previous boot reason 1 
*  Parameter.py loaded OK
* runtimeconfig.json loaded OK

# find code part after OK and investigate which could cause crash

* Normal startup:
*  ----------------
* Boottime Logger
* Old log renamed to old
* New file started
* ----------------
* Previous boot reason 1 
* Parameter.py loaded OK
* runtimeconfig.json loaded OK
* Sunrise today (2021, 2, 27, 7, 34, 0, 0, 0), sunset today (2021, 2, 27, 17, 50, 0, 0, 0), now is daytime True
* Secondary circuit initialized
* Batteryreader circuit initialized
* Solarpanel circuit initialized
* Limiter switch circuit initialized
* Panel motor initialized
* I2C initialized
* BME280 initialized
* MQTTClient object initialized
* Execute main
* Free memory 55920
* MQTT Initialized
* Daytime is True, starting operations...
* (2021, 2, 27, 11, 39, 34, 5, 58): Normal rotation begings
* Rotated too much, rotating back half of time difference!
* Begin mqtt reporting
* Begin runtimedata save
* Runtimeconfig save complete
* Disconnect WiFi
* Wait 60 seconds
* ULP Sleep less than 3600
