#!/usr/bin/env python3

from influxdb import InfluxDBClient
from datetime import datetime, timedelta
from os import path
import sys
import os
import time
import yaml
import logging
import subprocess
import json
import paho.mqtt.client as mqtt

# Change working dir to the same dir as this script
os.chdir(sys.path[0])

class DataCollector:
    def __init__(self, influx_yaml, topics_yaml):
        self.influx_yaml = influx_yaml
        self.influx_map = None
        self.influx_map_last_change = -1
        log.info('InfluxDB:')
        for influx_config in sorted(self.get_influxdb(), key=lambda x:sorted(x.keys())):
            log.info('\t {} <--> {}'.format(influx_config['host'], influx_config['name']))
        self.topics_yaml = topics_yaml
        self.topics_map = None
        self.topics_map_map_last_change = -1
        log.info('Topics:')
        for topics_config in sorted(self.get_topics(), key=lambda x:sorted(x.keys())):
            log.info('\t {} <--> {}'.format(topics_config['topic'], topics_config['name']))

    def get_topics(self):
        assert path.exists(self.topics_yaml), 'Topics not found: %s' % self.topics_yaml
        if path.getmtime(self.topics_yaml) != self.topics_map_map_last_change:
            try:
                log.info('Reloading topics as file changed')
                new_map = yaml.load(open(self.topics_yaml))
                self.topics_map = new_map['topics']
                self.topics_map_map_last_change = path.getmtime(self.topics_yaml)
            except Exception as e:
                log.warning('Failed to re-load topics, going on with the old one.')
                log.warning(e)
        return self.topics_map

    def get_influxdb(self):
        assert path.exists(self.influx_yaml), 'InfluxDB map not found: %s' % self.influx_yaml
        if path.getmtime(self.influx_yaml) != self.influx_map_last_change:
            try:
                log.info('Reloading influxDB map as file changed')
                new_map = yaml.load(open(self.influx_yaml))
                self.influx_map = new_map['influxdb']
                self.influx_map_last_change = path.getmtime(self.influx_yaml)
            except Exception as e:
                log.warning('Failed to re-load influxDB map, going on with the old one.')
                log.warning(e)
        return self.influx_map
       

    def on_message(self, client, userdata, message):
        influxdb = self.get_influxdb()
        t_utc = datetime.utcnow()
        t_str = t_utc.isoformat() + 'Z'
        
        value = message.payload

        is_value_json_dict = False
        try:
            stored_message = json.loads(value)
            is_value_json_dict = isinstance(stored_message, dict)
        except ValueError:
            pass

        if is_value_json_dict:
            for key in stored_message.keys():
                try:
                    stored_message[key] = float(stored_message[key])
                except ValueError:
                    pass
        else:
            try:
                value = float(value)
            except ValueError:
                pass
                value = str(value)
            stored_message = {'value': value}
        
        json_body = [
            {
                'measurement': 'mqtt2influx',
                'tags': {
                    'topic': message.topic,
                },
                'time': t_str,
                'fields': stored_message
            }
        ]
        
        if len(json_body) > 0:
#            influx_id_name = dict() # mapping host to name

            #log.debug(json_body)

            for influx_config in influxdb:
#                influx_id_name[influx_config['host']] = influx_config['name']

                DBclient = InfluxDBClient(influx_config['host'],
                                        influx_config['port'],
                                        influx_config['user'],
                                        influx_config['password'],
                                        influx_config['dbname'])
                try:
                    DBclient.write_points(json_body)
                    log.info(t_str + ' Data written in {}.' .format(influx_config['name']) % len(json_body) )
                except Exception as e:
                    log.error('Data not written! in {}' .format(influx_config['name']))
                    log.error(e)
                    raise
        else:
            log.warning(t_str, 'No data sent.')


    def on_connect(self, client, userdata, flags, rc ):
    
        # Subscribing in on_connect() means that if we lose the connection and
        # reconnect then subscriptions will be renewed. There are other methods to achieve this.

        log.info( "MQTT Connected with result code: " + str( rc ) )

        if rc == 0:
            topics = self.get_topics()
            
            for topics_subscribe in topics:
                client.subscribe(topics_subscribe['topic'])
                log.info('Subscribe topic: {}' .format(topics_subscribe['topic']))
            


if __name__ == '__main__':

    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--mqtt_host', default="localhost", help='MQTT host. Default "localhost"')
    parser.add_argument('--mqtt_port', default=1883, help='MQTT port. Default "1883"')
    parser.add_argument('--delay', default=60,
                        help='Delay start delay (seconds), default 60')
    parser.add_argument('--topics', default='topics.yml',
                        help='YAML file containing topics to subscribe and save in influxdb. Default "topics.yml"')
    parser.add_argument('--influxdb', default='influx_config.yml',
                        help='YAML file containing Influx Host, port, user etc. Default "influx_config.yml"')
    parser.add_argument('--log', default='CRITICAL',
                        help='Log levels, DEBUG, INFO, WARNING, ERROR or CRITICAL')
    parser.add_argument('--logfile', default='',
                        help='Specify log file, if not specified the log is streamed to console')
    args = parser.parse_args()
    host = args.mqtt_host
    port = int(args.mqtt_port)
    delay = int(args.delay)
    loglevel = args.log.upper()
    logfile = args.logfile

    # Setup logging
    log = logging.getLogger('mqtt2influx-logger')
    log.setLevel(getattr(logging, loglevel))

    if logfile:
        loghandle = logging.FileHandler(logfile, 'w')
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        loghandle.setFormatter(formatter)
    else:
        loghandle = logging.StreamHandler()

    log.addHandler(loghandle)

    log.info('Sleep {} seconds for booting' .format( delay ))

    time.sleep( delay )

    log.info('Started app')
    
    collector = DataCollector(influx_yaml=args.influxdb,
                              topics_yaml=args.topics)

    client = mqtt.Client()
    client.on_connect = collector.on_connect
    client.on_message = collector.on_message
    
    client.connect( host, port )
    
    time.sleep( 4 )

    # Blocking call that processes network traffic, dispatches callbacks and
    # handles reconnecting.
    # Other loop*() functions are available that give a threaded interface and a
    # manual interface.
    client.loop_forever() 
    


