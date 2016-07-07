# -*- coding: utf-8 -*-
"""
Created on 5 Jul 2015

@author: Nelson Leung
"""

from slab.instruments import SocketInstrument


class M8195A(SocketInstrument):
    """Keysight M8195A Arbitrary Waveform Class"""
    # default_port=5025
    def __init__(self, name='M8195A', address='', enabled=True,timeout = 1000):
        address = address.upper()

        SocketInstrument.__init__(self, name, address, enabled, timeout)
        self._loaded_waveforms = []

    def get_id(self):
        return self.query("*IDN?")

    ## 6.8 :ARM/TRIGger Subsystem
    def stop_output(self, channel):
        self.write(':ABOR%d' %channel)

    def set_module_delay(self,seconds):
        self.write(':ARM:MDEL %f' %seconds)

    def get_module_delay(self):
        return self.query(':ARM:MDEL?')

    def set_sample_delay(self,value):
        self.write(':ARM:SDEL %d' %value)

    def get_sample_delay(self):
        return self.query(':ARM:SDEL?')

    def set_arming_mode(self, value):
        if value in ['SELF','ARM']:
            self.write(':INIT:CONT:ENAB %s' %value)
        else:
            raise Exception('M8195A: Invalid arming mode')

    def get_arming_mode(self):
        return self.query(':INIT:CONT:ENAB?')

    def set_continuous_mode(self,state):
        if state in ['on', 'ON', True, 1, '1']:
            self.write(':INIT:CONT:STAT ON')
        elif state in ['off', 'OFF', False, 0, '0']:
            self.write(':INIT:CONT:STAT OFF')
        else:
            raise Exception('M8195A: Invalid continuous mode command')

    def get_continuous_mode(self):
        return self.query(':INIT:CONT:STAT?')

    def set_gate_mode(self,state):
        if state in ['on', 'ON', True, 1, '1']:
            self.write(':INIT:GATE:STAT ON')
        elif state in ['off', 'OFF', False, 0, '0']:
            self.write(':INIT:GATE:STAT OFF')
        else:
            raise Exception('M8195A: Invalid continuous mode command')

    def get_gate_mode(self):
        return self.query(':INIT:GATE:STAT?')

    def start_all_output(self):
        self.write(':INIT:IMM')

    def set_trigger_level(self,value):
        self.write(':ARM:TRIG:LEV %f' %value)

    def get_trigger_level(self):
        return self.query(':ARM:TRIG:LEV?')

    def set_trigger_input_slope(self,value):
        if value in ['POS','NEG','EITH']:
            self.write(':ARM:TRIG:SLOP %s' %value)
        else:
            raise Exception('M8195A: Invalid trigger slope')

    def get_trigger_input_slope(self):
        return self.query(':ARM:TRIP:SLOP?')

    def set_trigger_source(self,value):
        if value in ['TRIG','EVEN','INT']:
            self.write(':ARM:TRIG:SOUR %s' %value)
        else:
            raise Exception('M8195A: Invalid trigger source')

    def get_trigger_source(self):
        return self.query(':ARM:TRIG:SOUR?')

    def set_internal_trigger_frequency(self,value):
        self.write(':ARM:TRIG:FREQ %f' %value)

    def get_internal_trigger_frequency(self):
        return self.query(':ARM:TRIG:FREQ?')

    def set_trigger_operation_mode(self,value):
        if value in ['ASYN','SYNC']:
            self.write(':ARM:TRIG:OPER %s' %value)
        else:
            raise Exception('M8195A: Invalid trigger operation mode')

    def get_trigger_operation_mode(self):
        return self.query(':ARM:TRIG:OPER?')

    def set_event_level(self,value):
        self.write(':ARM:EVEN:LEV %f' %value)

    def get_event_level(self):
        return self.query(':ARM:EVEN:LEV?')

    def set_event_input_slope(self,value):
        if value in ['POS','NEG','EITH']:
            self.write(':ARM:EVEN:SLOP %s' %value)
        else:
            raise Exception('M8195A: Invalid trigger slope')

    def get_event_input_slope(self):
        return self.query(':ARM:EVEN:SLOP?')

    def set_enable_event_source(self,value):
        if value in ['TRIG','EVEN']:
            self.write(':TRIG:SOUR:ENAB %s' %value)
        else:
            raise Exception('M8195A: Invalid trigger source')

    def get_enable_event_source(self):
        return self.query(':TRIG:SOUR:ENAB?')

    def set_enable_hardware_input_disable_state(self,state):
        if state in ['on', 'ON', True, 1, '1']:
            self.write(':TRIG:ENAB:HWD ON')
        elif state in ['off', 'OFF', False, 0, '0']:
            self.write(':TRIG:ENAB:HWD OFF')
        else:
            raise Exception('M8195A: Invalid continuous mode command')

    def get_enable_hardware_input_disable_state(self):
        return self.query(':TRIG:ENAB:HWD?')

    def set_trigger_hardware_input_disable_state(self,state):
        if state in ['on', 'ON', True, 1, '1']:
            self.write(':TRIG:BEG:HWD ON')
        elif state in ['off', 'OFF', False, 0, '0']:
            self.write(':TRIG:BEG:HWD OFF')
        else:
            raise Exception('M8195A: Invalid continuous mode command')

    def get_trigger_hardware_input_disable_state(self):
        return self.query(':TRIG:BEG:HWD?')

    def set_advancement_hardware_input_disable_state(self,state):
        if state in ['on', 'ON', True, 1, '1']:
            self.write(':TRIG:ADV:HWD ON')
        elif state in ['off', 'OFF', False, 0, '0']:
            self.write(':TRIG:ADV:HWD OFF')
        else:
            raise Exception('M8195A: Invalid continuous mode command')

    def get_advancement_hardware_input_disable_state(self):
        return self.query(':TRIG:ADV:HWD?')

    ## 6.9 TRIGger - Trigger Input
    def set_advancement_event_source(self,value):
        if value in ['TRIG','EVEN','INT']:
            self.write(':TRIG:SOUR:ADV %s' %value)
        else:
            raise Exception('M8195A: Invalid advancement event source')

    def get_advancement_event_source(self):
        return self.query(':TRIG:SOUR:ADV?')

    def send_trigger_enable_event(self):
        self.write(':TRIG:ENAB')

    def send_trigger_begin_event(self):
        self.write(':TRIG:BEG')

    def send_trigger_gate(self,state):
        if state in ['on', 'ON', True, 1, '1']:
            self.write(':TRIG:BEG:GATE ON')
        elif state in ['off', 'OFF', False, 0, '0']:
            self.write(':TRIG:BEG:GATE OFF')
        else:
            raise Exception('M8195A: Invalid trigger gate state')

    def get_trigger_gate(self):
        return self.query(':TRIG:BEG:GATE?')

    def send_trigger_advancement_event(self):
        self.write(':TRIG:ADV')

    ## 6.10 :FORMat Subsystem
    def set_byte_order(self,value):
        if value in ['NORM','SWAP']:
            self.write(':FORM:BORD %s' %value)
        else:
            raise Exception('M8195A: Invalid Byte Order')

    def get_byte_order(self):
        return self.query(':FORM:BORD?')

    ## 6.11 :INSTrument Subsystem
    def get_slot_number(self):
        return self.query(':INST:SLOT?')

    def flash_access_led(self, seconds):
        self.write(':INST:IDEN %d' %seconds)

    def stop_flash_access_led(self):
        self.write(':INST:IDEN:STOP')

    def get_hwardware_revision_number(self):
        return self.query(':INST:HWR?')

    def set_dac_mode(self,value):
        if value in ['SING','DUAL','FOUR','MARK','DCD','DCM']:
            self.write(':INST:DACM %s' %value)
        else:
            raise Exception('M8195A: Invalid DAC mode')

    def get_dac_mode(self):
        return self.query(':INST:DACM?')

    def set_dac_sample_rate_divider(self,value):
        if value in [1,2,4]:
            self.write(':INST:MEM:EXT:RDIV DIV%d' %value)
        else:
            raise Exception('M8195A: Invalid DAC sample rate divider')

    def get_dac_sample_rate_divider(self):
        return self.query(':INST:MEM:EXT:RDIV?')

    def get_multi_module_configuration(self):
        return self.query(':INST:MMOD:CONF?')

    def get_multi_module_mode(self):
        return self.query(':INST:MMOD:MODE?')

    ## 6.12 :MMEMory Subsystem

    def get_disk_usage_information(self, value):
        return self.query(':MMEM:CAT? %s' %value)

    def set_default_directory(self,value):
        self.write('MMEM:CDIR %s' %value)

    def get_default_directory(self):
        return self.query(':MMEM:CDIR?')

    def file_copy(self,file,new_file):
        self.write(':MMEM:COPY %s, %s' %(file,new_file))

    def file_delete(self,value):
        self.write(':MMEM:DEL %s' %(value))

    def set_file_data(self,file,data):
        # <data> is in 488.2 block format
        self.write(':MMEM:DATA %s, %s' %(file,data))

    def get_file_data(self,file):
        return self.query(':MMEM:DATA? %s' %file)

    def create_directory(self,value):
        self.write(':MMEM:MDIR %s' %value)

    def move_path(self,old_path,new_path):
        self.write(':MMEM:MOVE %s, %s' %(old_path,new_path))

    def remove_directory(self,value):
        self.write(':MMEM:RDIR %s' %value)

    def load_state_from_file(self,value):
        self.write(':MMEM:LOAD:CST %s' %value)

    def store_state_to_file(self,value):
        self.write(':MMEM:STOR:CST %s' %value)

    ## 6.13 Output subsystem

    def set_enabled(self, channel, state):
        if state in ['on', 'ON', True, 1, '1']:
            self.write(':OUTP%d ON' % channel)
        elif state in ['off', 'OFF', False, 0, '0']:
            self.write(':OUTP%d OFF' % channel)
        else:
            raise Exception('M8195A: Invalid enabled state')

    def get_enabled(self, channel):
        return self.query(':OUTP%d?' % (channel))

    def set_output_clock_source(self,value):
        if value in ['INT','EXT','SCLK1','SCLK2']:
            self.write(':OUTP:ROSC:SOUR %s' %value)
        else:
            raise Exception('M8195A: Invalid reference source')

    def get_output_clock_source(self):
        return self.query(':OUTP:ROSC:SOUR?')

    def set_sample_clock_divider(self,value):
        self.write(':OUTP:ROSC:SCD %d' %value)

    def get_sample_clock_divider(self):
        return self.query('OUTP:ROSC:SCD?')

    def set_reference_clock_divider_1(self,value):
        self.write(':OUTP:ROSC:RCD1 %d' %value)

    def get_freference_clock_divider_1(self):
        return self.query(':OUTP:ROSC:RCD1?')

    def set_reference_clock_divider_2(self,value):
        self.write(':OUTP:ROSC:RCD2 %d' %value)

    def get_freference_clock_divider_2(self):
        return self.query(':OUTP:ROSC:RCD2?')

    def set_differential_offset(self,channel,value):
        self.write(':OUTP%d:DIOF %f' %(channel,value))

    def get_differential_offset(self,channel):
        return self.query(':OUTP%d:DIOF?' %channel)

    def rate_divider_codename(self, rate_divider):
        if rate_divider == 1:
            codename = 'FRAT'
        elif rate_divider == 2:
            codename = 'HRAT'
        elif rate_divider == 4:
            codename = 'QRAT'
        else:
            raise Exception('M8195A: Invalid rate divider')
        return codename

    def set_fir_coefficients(self,channel,rate_divider,value):
        # value is comma-separated values

        codename = self.rate_divider_codename(rate_divider)

        self.write(':OUTP%d:FILT:%s %s' %(channel,codename,value))

    def get_fir_coefficients(self,channel,rate_divider):
        # value is comma-separated values

        codename = self.rate_divider_codename(rate_divider)

        return self.query(':OUTP%d:FILT:%s?' %(channel,codename))

    def set_fir_type(self,channel,rate_divider,value):
        codename = self.rate_divider_codename(rate_divider)

        if rate_divider == 1:
            if value in ['LOWP','ZOH','USER']:
                self.write(':OUTP%d:FILT:%s:TYPE %s' %(channel,codename,value))
            else:
                raise Exception('M8195A: Invalid FIR type')
        elif rate_divider == 2 or rate_divider == 4:
            if value in ['NYQ','LIN','ZOH','USER']:
                self.write(':OUTP%d:FILT:%s:TYPE %s' %(channel,codename,value))
            else:
                raise Exception('M8195A: Invalid FIR type')

    def get_fir_type(self,channel,rate_divider):

        codename = self.rate_divider_codename(rate_divider)

        return self.query(':OUTP%d:FILT:%s:TYPE?' %(channel,codename))

    def set_fir_scale(self,channel,rate_divider,value):
        codename = self.rate_divider_codename(rate_divider)

        self.write(':OUTP%d:FILT:%s:SCAL %s' %(channel,codename,value))

    def get_fir_scale(self,channel,rate_divider):

        codename = self.rate_divider_codename(rate_divider)

        return self.query(':OUTP%d:FILT:%s:SCAL?' %(channel,codename))

    def set_fir_delay(self,channel,rate_divider,ps):
        codename = self.rate_divider_codename(rate_divider)

        if rate_divider == 1:
            if abs(ps) > 50:
                raise Exception('M8195A: Invalid FIR delay')
        elif rate_divider == 2:
            if abs(ps) > 100:
                raise Exception('M8195A: Invalid FIR delay')
        elif rate_divider == 4:
            if abs(ps) > 200:
                raise Exception('M8195A: Invalid FIR delay')

        self.write(':OUTP%d:FILT:%s:DEL %fps' %(channel,codename,ps))

    def get_fir_delay(self,channel,rate_divider):

        codename = self.rate_divider_codename(rate_divider)

        return self.query(':OUTP%d:FILT:%s:DEL?' %(channel,codename))

    ## 6.14 Sampling Frequency Commands

    def set_sample_frequency(self,value):
        self.write(':FREQ:RAST %f' %value)

    def get_sample_frequency(self):
        return self.query(':FREQ:RAST?')

    ## 6.15 Reference Oscillator Commands

    def set_reference_source(self,value):
        if value in ['EXT','AXI','INT']:
            self.write(':ROSC:SOUR %s' %value)
        else:
            raise Exception('M8195A: Invalid reference source')

    def get_reference_source(self):
        return self.query(':ROSC:SOUR?')

    def get_reference_source_availability(self,value):
        if value in ['EXT','AXI','INT']:
            return self.query(':ROSC:SOUR:CHEC? ' %value)
        else:
            raise Exception('M8195A: Invalid reference source')

    def set_reference_clock_frequency(self,value):
        if self.get_reference_source() == 'EXT':
            self.write(':ROSC:FREQ %f' %value)
        else:
            raise Exception('M8195A: Not in external reference source')

    def get_reference_clock_frequency(self):
        if self.get_reference_source() == 'EXT':
            return self.query(':ROSC:FREQ?')
        else:
            raise Exception('M8195A: Not in external reference source')

    def set_reference_clock_range(self,value):
        if self.get_reference_source() == 'EXT':
            if value in ['RANG1','RANG2']:
                self.write(':ROSC:RANG %s' %value)
            else:
                raise Exception('M8195A: Not in valid reference source frequency range')
        else:
            raise Exception('M8195A: Not in external reference source')

    def get_reference_clock_range(self):
        if self.get_reference_source() == 'EXT':
            return self.query(':ROSC:RANG?')
        else:
            raise Exception('M8195A: Not in external reference source')

    def set_reference_clock_range_frequency(self,range,value):
        if self.get_reference_source() == 'EXT':
            if range in ['RNG1','RNG2']:
                self.write(':ROSC:%s:FREQ %f' %(range,value))
            else:
                raise Exception('M8195A: Not in valid reference source frequency range')
        else:
            raise Exception('M8195A: Not in external reference source')

    def get_reference_clock_range_frequency(self,range):
        if self.get_reference_source() == 'EXT':
            if range in ['RNG1','RNG2']:
                return self.query(':ROSC:%s:FREQ?' %range)
        else:
            raise Exception('M8195A: Not in external reference source')


    ## 6.16 :VOLTage Subsystem

    def set_amplitude(self,channel,value):
        self.write(':VOLT%d %f' % (channel, value))

    def get_amplitude(self,channel):
        return self.query(':VOLT%d?' % (channel))

    def set_analog_high(self, channel, value):
        self.write(':VOLT%d:HIGH %f' % (channel, value))

    def get_analog_high(self, channel):
        return float(self.query(':VOLT%d:HIGH?' % (channel)))

    def set_analog_low(self, channel, value):
        self.write(':VOLT%d:LOW %f' % (channel, value))

    def get_analog_low(self, channel):
        return float(self.query(':VOLT%d:LOW?' % (channel)))

    def set_offset(self,channel,value):
        self.write(':VOLT%d:OFFS %f' % (channel, value))

    def get_offset(self,channel):
        return self.query(':VOLT%d:OFFS?' % (channel))

    def set_termination(self,channel,value):
        self.write(':VOLT%d:TERM %f' % (channel, value))

    def get_termination(self,channel):
        return self.query(':VOLT%d:TERM?' % (channel))

    ## 6.17 Function mode setting
    def set_mode(self,mode):
        if mode in ['ARB', 'STS','STSC']:
            self.write(':FUNC:MODE %s' %mode)
        else:
            raise Exception('M8195A: Invalid enabled mode')

    def get_mode(self):
        return self.query(':FUNC:MODE?')

    ## 6.18 :STABle Subsystem
    def reset_sequence(self):
        self.write(':STAB:RES')

    def write_sequence_data(self,sequence_table_index,segment_id,sequence_loop=1,segment_loop=1,start_address='0',end_address='#0xFFFFFFFF'):
        self.write(':STAB:DATA %d, #0x10000000, %d, %d, %d, %s, %s' %(sequence_table_index,sequence_loop,segment_loop,segment_id,start_address,end_address))

    def write_sequence_idle(self,sequence_table_index,sequence_loop=1,idle_sample='0',idle_delay=0):
        self.write(':STAB:DATA %d, #0x80000000,%d,0,%s,%f,0' %(sequence_table_index,sequence_loop,idle_sample,idle_delay))

    def read_sequence_data(self,sequence_table_index,length):
        return self.query(':STAB:DATA? %d, %d' %(sequence_table_index,length))

    def read_sequence_data_block(self,sequence_table_index,length):
        return self.query(':STAB:DATA:BLOC? %d, %d' %(sequence_table_index,length))

    def set_sequence_starting_id(self,sequence_table_index):
        self.write(':STAB:SEQ:SEL %d' %sequence_table_index)

    def get_sequence_starting_id(self):
        return self.query(':STAB:SEQ:SEL?')

    def get_sequence_execution_state(self):
        return self.query(':STAB:SEQ:STAT?')

    def set_dynamic_mode(self,state):
        if state in ['on', 'ON', True, 1, '1']:
            self.write(':STAB:DYN ON')
        elif state in ['off', 'OFF', False, 0, '0']:
            self.write(':STAB:DYN OFF')
        else:
            raise Exception('M8195A: Invalid dynamic mode command')

    def get_dynamic_mode(self):
        return self.query(':STAB:DYN?')

    def set_dynamic_starting_id(self,sequence_table_index):
        self.write(':STAB:DYN:SEL %d' %sequence_table_index)

    def set_scenario_starting_id(self,sequence_table_index):
        self.write(':STAB:SCEN:SEL %d' %sequence_table_index)

    def get_scenario_starting_id(self):
        return self.query(':STAB:SCEN:SEL?')

    def set_scenario_advancement_mode(self,value):
        if value in ['AUTO','COND','REP','SING']:
            self.write(':STAB:SCEN:ADV %s' %value)
        else:
            raise Exception('M8195A: Invalid scenario advancement mode')

    def get_scenario_advancement_mode(self):
        return self.query(':STAB:SCEN:ADV?')

    def set_scenario_loop(self,value):
        self.write(':STAB:SCEN:COUN %d' %value)

    def get_scenario_loop(self):
        return self.query(':STAB:SCEN:COUN?')

    ## 6.19 Frequency and Phase Response Data Access

    def get_frequency_phase_response_data(self,channel):
        return self.query(':CHAR%d?' %channel)

    ## 6.20 :TRACe Subsystem

    def set_waveform_sample_source(self,channel,value):
        if value in ['INT','EXT']:
            self.write(':TRAC%d:MMOD %s' %(channel,value))
        else:
            raise Exception('M8195A: Invalid waveform sample source')

    def get_waveform_sample_source(self,channel):
        return self.query('TRAC%d:MMOD?' %channel)

    def set_segment_size(self,channel,segment_id,length,init_value=0,write_only = False):
        if write_only:
            self.write('TRAC%d:DEF:WONL %d,%d,%f' %(channel,segment_id,length,init_value))
        else:
            self.write('TRAC%d:DEF %d,%d,%f' %(channel,segment_id,length,init_value))

    def set_new_segment_size(self,channel,length,init_value=0, write_only = False):
        if write_only:
            return self.query('TRAC%d:DEF:WONL:NEW? %d,%f' %(channel,length,init_value))
        else:
            return self.query('TRAC%d:DEF:NEW? %d,%f' %(channel,length,init_value))

    def set_segment_data(self,channel,segment_id,offset,data):
        #data in comma-separated list
        self.write(':TRAC%d:DATA %d,%d,%s' %(channel,segment_id,offset,data))

    def get_segment_data(self,channel,segment_id,offset,length):
        return self.query(':TRAC%d:DATA? %d,%d,%d' %(channel,segment_id,offset,length))

    def set_segment_data_from_file(self,channel,segment_id,file_name,data_type,marker_flag,padding,init_value,ignore_header_parameters):
        self.write(':TRAC%d:IMP %d,%s,%s,%s,%s,%d,%s' %(channel,segment_id,file_name,data_type,marker_flag,padding,init_value,ignore_header_parameters))

    def delete_segment(self,channel,segment_id):
        self.write(':TRAC%d:DEL %d' %(channel,segment_id))

    def delete_all_segment(self,channel):
        self.write(':TRAC%d:DEL:ALL' %channel)

    def get_segment_catalog(self,channel):
        return self.query(':TRAC%d:CAT?' %channel)

    def get_memory_space_amount(self,channel):
        return self.query(':TRAC%d:FREE?' %channel)

    def set_segment_name(self,channel,segment_id,name):
        self.write(':TRAC%d:NAME %d, %s' %(channel,segment_id,name))

    def get_segment_name(self,channel,segment_id):
        return self.query(':TRAC%d:NAME? %d' %(channel,segment_id))

    def set_segment_comment(self,channel,segment_id,comment):
        self.write(':TRAC%d:COMM %d, %s' %(channel,segment_id,comment))

    def get_segment_comment(self,channel,segment_id):
        return self.query(':TRAC%d:COMM? %d' %(channel,segment_id))

    def set_select_segment(self,channel,segment_id):
        self.write(':TRAC%d:SEL %d' %(channel,segment_id))

    def get_select_segment(self,channel):
        return self.query(':TRAC%d:SEL?' %channel)

    def set_selected_segment_advancement_mode(self,channel,value):
        if value in ['AUTO','COND','REP','SING']:
            self.write(':TRAC%d:ADV %s' %(channel,value))
        else:
            raise Exception('M8195A: Invalid segment advancement mode')

    def get_selected_segment_advancement_mode(self,channel):
        return self.query(':TRAC%d:ADV?' %channel)

    def set_selected_segment_loop(self,channel,value):
        self.write(':TRAC%d:COUN %d' %(channel,value))

    def get_selected_segment_loop(self,channel):
        return self.query(':TRAC%d:COUN?' %channel)

    def set_selected_segment_marker_enable(self,channel,state):
        if state in ['on', 'ON', True, 1, '1']:
            self.write(':TRAC:MARK%d ON' %channel)
        elif state in ['off', 'OFF', False, 0, '0']:
            self.write(':TRAC:MARK%d OFF' %channel)
        else:
            raise Exception('M8195A: Invalid selected segment marker enable command')

    def get_selected_segment_marker_enable(self,channel):
        return self.query(':TRAC%d:MARK?' %channel)


    ## 6.21 :TEST Subsystem

    def get_power_on_self_tests_result(self):
        return self.query(':TEST:PON?')

    def get_power_on_self_tests_results_with_test_message(self):
        return self.query(':TEST:TST?')