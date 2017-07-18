from arcgis.gis import GIS

import time
import requests
import datetime
import configparser
import os
from slackclient import SlackClient

if os.environ['USER'] == 'brianmccall':
    DEBUG = True
working_dir = os.path.split(os.path.realpath(__file__))[0]

Config = configparser.ConfigParser()
Config.read(os.path.join(working_dir, "config.ini"))

def ConfigSectionMap(section):
    dict1 = {}
    options = Config.options(section)
    for option in options:
        try:
            dict1[option] = Config.get(section, option)
            if dict1[option] == -1:
                DebugPrint("skip: %s" % option)
        except:
            print("exception on %s!" % option)
            dict1[option] = None
    return dict1


RESULTOFFSET = 0
existing_policies = []

# Config vars
arcgis_user = ConfigSectionMap('credentials')['arcgis_user']
arcgis_password = ConfigSectionMap('credentials')['arcgis_password']
geomac_item_id = ConfigSectionMap('credentials')['geomac_item_id']
hotpin_item_id = ConfigSectionMap('credentials')['hotpin_item_id']
slack_token = ConfigSectionMap('slack')['slack_token']
slack_channel = ConfigSectionMap('slack')['slack_channel']
hotpin_url = ConfigSectionMap('incident_dashboard')['url']

#get all current features into a list
def import_geomac_pins():
    if DEBUG:
        print('Downloading data...')
    global arcgis_user
    global arcgis_password
    global geomac_item_id
    try:
        gis = GIS(username=arcgis_user, password=arcgis_password)
    except Exception as e:
        notify_error('Failed to login: ' + str(e))

    try:
        layer = gis.content.get(geomac_item_id).layers[0]
    except Exception as e:
        notify_error('Failed to retrieve geoMAC layer ' + str(e))

    # used 25 here to to offset time script was running
    date_minus_1 = datetime.datetime.now() - datetime.timedelta(hours=25)
    date_minus_1 = date_minus_1.strftime("%Y/%m/%d")
    where_clause = ' REPORT_DATE >= date\'%s\' ' % date_minus_1
    geomac_fset = layer.query(where="%s" % where_clause)

    if len(geomac_fset.features) > 0:
        token = get_token()
        url = get_resource_url(token)

    for fire in geomac_fset:
        # must use the attributes.lat/long because the geometry.x/y is the wrong spatial reference
        y = fire.attributes['LATITUDE']
        x = fire.attributes['LONGITUDE']

        hotpins = do_buffer_query(url, token, x, y)

        if len(hotpins['features']) < 1:
            create_hotpin(x, y, fire.attributes)

def get_token():
    global arcgis_user
    global arcgis_password
    url = "https://www.arcgis.com/sharing/generateToken"
    payload = {"username": arcgis_user, "password": arcgis_password, "referer": "www.arcgis.com", "f": "json"}
    try:
        r = requests.post(url, data=payload)
    except Exception as e:
        notify_error('Failed to get token ' + str(e))
    j = r.json()
    return j['token']


def get_resource_url(token):
    global hotpin_item_id
    url = " http://www.arcgis.com/sharing/rest/content/items/" + hotpin_item_id
    payload = {"token": token, "f": "json"}
    try:
        r = requests.post(url, data=payload)
    except Exception as e:
        notify_error('Could not find hotpin layer ' + str(e))
    j = r.json()
    return j['url']


def do_buffer_query(url, token, x, y):
    if DEBUG:
        print('Doing Buffer...')
    token = token
    url = url + "/0/query"
    id_pin_location = "%s , %s" % (x, y)

    payload = {
        "where": '',
        "geometry": id_pin_location,
        "geometryType": "esriGeometryPoint",
        "spatialRel": "esriSpatialRelIntersects",
        "distance": "5",
        "units": "esriSRUnit_StatuteMile",
        "outFields": "*",
        "returnGeometry": "true",
        "f": "json",
        "token": token
    }
    r = requests.post(url, data=payload)
    j = r.json()
    return j


def create_hotpin(x,y, details):
    if DEBUG:
        print('Creating Hotpin...')
    global hotpin_url
    payload = {
        "name": details['FIRE_NAME'],
        "name_alt": "",
        "status": "Continuing",
        "irwin_id":"",
        "wlf_thread_id": "",
        "qad_thread_id":"",
        "complex_is": "null",
        "complex_parent":"0",
        "featured": "null",
        "date_report": time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(details['REPORT_DATE']/1000)),
        "date_start": time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(details['START_DATE']/1000)),
        "hashtag": details['FIRE_NAME'],
        "radio_freq": "",
        "inciweb_url":"",
        "state": details['STATE'],
        "region":"0",
        "county": "",
        "unit_code":"123",
        "fire_number": "",
        "acres_ia": "",
        "acres_current": details['AREA_'],
        "acres_official": details['AREA_'],
        "ros": "Moderate",
        "roc": "",
        "fuel_type": "",
        "land_owner":"",
        "threat_life": "null",
        "threat_struct":"null",
        "road_closures": "null",
        "evac":"",
        "hazards_spec": "",
        "injuries_rpt":"null",
        "nat_prep_lvl": "Unknown",
        "containment": details['PER_CONT'],
        "lat_rpt_dd": y,
        "lng_rpt_dd": x,
}
    try:
        requests.post(hotpin_url, data=payload)
    except Exception as e:
        notify_error('Error while creating pin ' + str(e))


def notify_error(message):
    global slack_token
    global slack_channel

    sc = SlackClient(slack_token)
    try:
        sc.api_call(
            "chat.postMessage",
            channel=slack_channel,
            text=message
        )
    except Exception as e:
        print("error" + str(e))
    quit()


import_geomac_pins()
