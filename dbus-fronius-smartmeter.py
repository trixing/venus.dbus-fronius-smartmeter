#!/usr/bin/env python

"""
Created by Ralf Zimmermann (mail@ralfzimmermann.de) in 2020.
This code and its documentation can be found on: https://github.com/RalfZim/venus.dbus-fronius-smartmeter
Used https://github.com/victronenergy/velib_python/blob/master/dbusdummyservice.py as basis for this service.
Reading information from the Fronius Smart Meter via http REST API and puts the info on dbus.
"""
import gobject
import platform
import logging
import sys
import os
import requests # for http GET
import thread   # for daemon = True

# our own packages
sys.path.insert(1, os.path.join(os.path.dirname(__file__), '../ext/velib_python'))
from vedbus import VeDbusService

class DbusDummyService:
  def role_changed(self, path, val):
    if val not in self.allowed_roles:
       return False
    old, inst = self.get_role_instance()
    self.settings['instance'] = '%s:%s' % (val, inst)
    return True

  def get_role_instance(self):
     val = self.settings['instance'].split(':')
     return val[0], int(val[1])

  def __init__(self, servicename, deviceinstance, paths, productname='Fronius Smart Meter', connection='Fronius Smart Meter service'):
    self._dbusservice = VeDbusService(servicename)
    self._paths = paths
    self.settings = {'instance': 'grid:40'}

    logging.debug("%s /DeviceInstance = %d" % (servicename, deviceinstance))

    # Create the management objects, as specified in the ccgx dbus-api document
    self._dbusservice.add_path('/Mgmt/ProcessName', __file__)
    self._dbusservice.add_path('/Mgmt/ProcessVersion', 'Unkown version, and running on Python ' + platform.python_version())
    self._dbusservice.add_path('/Mgmt/Connection', connection)

    # Create the mandatory objects
    self._dbusservice.add_path('/DeviceInstance', deviceinstance)
    self._dbusservice.add_path('/ProductId', 16) # value used in ac_sensor_bridge.cpp of dbus-cgwacs
    self._dbusservice.add_path('/ProductName', productname)
    self._dbusservice.add_path('/FirmwareVersion', 0.1)
    self._dbusservice.add_path('/HardwareVersion', 0)
    self._dbusservice.add_path('/Connected', 1)

    self.allowed_roles = ['grid', 'pvinverter', 'genset']
    self.default_role = 'grid'
    self.role = self.default_role
    self._dbusservice.add_path('/AllowedRoles', self.allowed_roles)
    #self._dbusservice.add_path('/Role', self.role, writeable=True,
    #                           onchangecallback=self.role_changed)

    for path, settings in self._paths.iteritems():
      self._dbusservice.add_path(
        path, settings['initial'], writeable=True, onchangecallback=self._handlechangedvalue)

    gobject.timeout_add(1000, self._safe_update)

  def _safe_update(self):
    try:
        self._update()
    except Exception as e:
        logging.error('Error running update %s' % e)

  def _update(self):
    URL = "http://192.168.2.100/solar_api/v1/GetMeterRealtimeData.cgi?Scope=Device&DeviceId=0&DataCollection=MeterRealtimeData"
    meter_r = requests.get(url = URL, timeout=10)
    meter_data = meter_r.json() 
    # Frequency_Phase_Average

    MeterConsumption = meter_data['Body']['Data']['PowerReal_P_Sum']
    self._dbusservice['/Ac/Power'] = MeterConsumption # positive: consumption, negative: feed into grid
    self._dbusservice['/Ac/L1/Voltage'] = meter_data['Body']['Data']['Voltage_AC_Phase_1']
    self._dbusservice['/Ac/L2/Voltage'] = meter_data['Body']['Data']['Voltage_AC_Phase_2']
    self._dbusservice['/Ac/L3/Voltage'] = meter_data['Body']['Data']['Voltage_AC_Phase_3']
    self._dbusservice['/Ac/L1/Current'] = meter_data['Body']['Data']['Current_AC_Phase_1']
    self._dbusservice['/Ac/L2/Current'] = meter_data['Body']['Data']['Current_AC_Phase_2']
    self._dbusservice['/Ac/L3/Current'] = meter_data['Body']['Data']['Current_AC_Phase_3']
    self._dbusservice['/Ac/L1/Power'] = meter_data['Body']['Data']['PowerReal_P_Phase_1']
    self._dbusservice['/Ac/L2/Power'] = meter_data['Body']['Data']['PowerReal_P_Phase_2']
    self._dbusservice['/Ac/L3/Power'] = meter_data['Body']['Data']['PowerReal_P_Phase_3']
    self._dbusservice['/Ac/Energy/Forward'] = float(meter_data['Body']['Data']['EnergyReal_WAC_Sum_Consumed']) / 1000.
    self._dbusservice['/Ac/Energy/Reverse'] = float(meter_data['Body']['Data']['EnergyReal_WAC_Sum_Produced']) / 1000.
    logging.info("House Consumption: %s" % (MeterConsumption))
    return True

  def _handlechangedvalue(self, path, value):
    logging.debug("someone else updated %s to %s" % (path, value))
    return True # accept the change

def main():
  logging.basicConfig(level=logging.INFO)
  thread.daemon = True # allow the program to quit

  from dbus.mainloop.glib import DBusGMainLoop
  # Have a mainloop, so we can send/receive asynchronous calls to and from dbus
  DBusGMainLoop(set_as_default=True)

  pvac_output = DbusDummyService(
    servicename='com.victronenergy.grid.fronius',
    deviceinstance=40,
    paths={
      '/Ac/Power': {'initial': 0},
      '/Ac/L1/Voltage': {'initial': 0},
      '/Ac/L2/Voltage': {'initial': 0},
      '/Ac/L3/Voltage': {'initial': 0},
      '/Ac/L1/Current': {'initial': 0},
      '/Ac/L2/Current': {'initial': 0},
      '/Ac/L3/Current': {'initial': 0},
      '/Ac/L1/Power': {'initial': 0},
      '/Ac/L2/Power': {'initial': 0},
      '/Ac/L3/Power': {'initial': 0},
      '/Ac/Energy/Forward': {'initial': 0}, # energy bought from the grid
      '/Ac/Energy/Reverse': {'initial': 0}, # energy sold to the grid
    })

  logging.info('Connected to dbus, and switching over to gobject.MainLoop() (= event based)')
  mainloop = gobject.MainLoop()
  mainloop.run()

if __name__ == "__main__":
  main()
