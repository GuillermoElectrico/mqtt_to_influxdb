#!/bin/bash

## Service or script to monitor if it is running 
SERVICE=mqtt_to_influxdb.py

while :
do
	result=$(ps ax|grep -v grep|grep $SERVICE)
#	echo ${#result}
	if [ ${#result} != 0 ] 
	then
		# everything is ok 
		# every 10 seconds we test if it is still ok 
		sleep 10
	else
		# is not working 
		# start script (in this case a python script) 
		/home/pi/mqtt_to_influxdb/$SERVICE > /var/log/mqtt_to_influxdb.log &
		# we wait for it to load 
		sleep 10
	fi
done