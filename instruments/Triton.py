from slab.instruments import SocketInstrument
import re
import time

#may have to pip install pint
from pint import UnitRegistry, Context
ureg = UnitRegistry()
Q = ureg.Quantity

class Triton(SocketInstrument):
    def __init__(self, name="Triton", address='192.168.14.242', port='33576', enabled=True, timeout=10):
        SocketInstrument.__init__(self, name, address+":"+port, enabled, timeout)
        self.mc_heater=1
        self.mc_thermometer=5
        self.recv_length=65536
        self.end_char='\n'
        self.timeout=timeout


    def query_t(self, cmd):
        self.write(cmd)
        return self.read_line(timeout=self.timeout, eof_char='\n')

    def user_stat(self):
        return self.query_t('READ:SYS:USER').split(self.end_char)[0].split(':')[-1]

    def set_turbo(self, state):
        if state==True:
            state="ON"
        elif state==False:
            state="OFF"
        else:
            raise TypeError('State must be bool')
        
        self.query_t('SET:DEV:TURB1:PUMP:SIG:STATE:'+state)

    def collect_mix(self):
        self.query_t('SET:SYS:DR:ACTN:COLL')

    def pre_cool(self):
        self.query_t('SET:SYS:DR:ACTN:PCL')

    def warmup(self):
        self.query_t('SET:SYS:DR:ACTN:WARM')

    def cooldown(self):
        self.query_t('SET:SYS:DR:ACTN:CLDN')    

    def get_status(self):
        return self.query_t('READ:SYS:DR:STATUS')

    def get_automation(self):
        return self.query_t('READ:SYS:DR:ACTN')

    def stop_automation(self):
        self.query_t('SET:SYS:DR:ACTN:STOP')

    def empty_precool(self):
        self.query_t('SET:SYS:DR:ACTN:EPCL')

    def pause_precool(self):
        self.query_t('SET:SYS:DR:ACTN:PCOND')

    def restart_precool(self):
        self.query_t('SET:SYS:DR:ACTN:RCOND')

    def set_forepump(self, state):
        if state==True:
            state="ON"
        elif state==False:
            state="OFF"
        else:
            raise TypeError('State must be bool')
        
        self.query_t('SET:DEV:FP:PUMP:SIG:STATE:'+state)

    def set_compressor(self, state):
        if state==True:
            state="ON"
        elif state==False:
            state="OFF"
        else:
            raise TypeError('State must be bool')
        
        self.query_t('SET:DEV:COMP:PUMP:SIG:STATE:'+state)

    def set_pulse_tube(self, state):
        if state==True:
            state="ON"
        elif state==False:
            state="OFF"
        else:
            raise TypeError('State must be bool')
        
        self.query_t('SET:DEV:C1:PTC:SIG:STATE:'+state)

    def get_turbo(self):
        return self.query_t('READ:DEV:TURB1:PUMP:SIG:STATE').split(self.end_char)[0].split(':')[-1]

    def get_forepump(self):
        return self.query_t('READ:DEV:FP:PUMP:SIG:STATE').split(self.end_char)[0].split(':')[-1]

    def get_compressor(self):
        return self.query_t('READ:DEV:COMP:PUMP:SIG:STATE').split(self.end_char)[0].split(':')[-1]

    def get_pulse_tube(self):
        return self.query_t('READ:DEV:C1:PTC:SIG:STATE').split(self.end_char)[0].split(':')[-1]

    def get_temperature(self, ch):
        if ch<1 and ch>10:
            raise Exception('Not a valid temperature channel number')
        data=self.query_t(f"READ:DEV:T{ch}:TEMP:SIG:TEMP")
        temp=data.split('\n')[0].split(':')[-1]
        return Q(temp).magnitude

    def set_mc_temp_loop(self, set_temp ,heater_range=0.0316, state=False):
        if state==True:
            state="ON"
        elif state==False:
            state="OFF"
        else:
            raise TypeError('State must be bool')
        t_set=self.query_t(f'SET:DEV:T{self.mc_thermometer}:TEMP:LOOP:TSET:{set_temp}')
        p_set=self.query_t(f'SET:DEV:T{self.mc_thermometer}:TEMP:LOOP:RANGE:{heater_range}')
        state=self.query_t(f'SET:DEV:T{self.mc_thermometer}:TEMP:LOOP:MODE:{state}')

    def set_mc_temp_loop_state(self, state=False):
        if state==True:
            state="ON"
        elif state==False:
            state="OFF"
        else:
            raise TypeError('State must be bool')
        state=self.query_t(f'SET:DEV:T{self.mc_thermometer}:TEMP:LOOP:MODE:{state}')

    def set_mc_loop_set_temp(self, set_temp):
        t_set=self.query_t(f'SET:DEV:T{self.mc_thermometer}:TEMP:LOOP:TSET:{set_temp}')

    def set_mc_loop_heater_range(self, heater_range=0.0316):
        p_set=self.query_t(f'SET:DEV:T{self.mc_thermometer}:TEMP:LOOP:RANGE:{heater_range}')

    def get_mc_loop_set_temp(self, get_temp):
        t_set=self.query_t(f'READ:DEV:T{self.mc_thermometer}:TEMP:LOOP:TSET')

    def get_mc_loop_heater_range(self):
        p_set=self.query_t(f'GET:DEV:T{self.mc_thermometer}:TEMP:LOOP:RANGE')