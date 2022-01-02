"""
Created on May 2021

@author: Ankur Agrawal, Schuster Lab
"""
from configuration_IQ import config, ge_IF, qubit_freq, two_chi, disc_file_opt, storage_IF, st_self_kerr
from qm.qua import *
from qm.QuantumMachinesManager import QuantumMachinesManager
from qm import SimulationConfig, LoopbackInterface
from TwoStateDiscriminator_2103 import TwoStateDiscriminator
import numpy as np
import matplotlib.pyplot as plt
from slab import*
from h5py import File
import os
import scipy
from slab.dataanalysis import get_next_filename
"""Binary decomposition pre and post repeated resolved pi pulses to estimate the cavity state decay"""
def alpha_awg_cal(alpha, cav_amp=1.0):
    # takes input array of omegas and converts them to output array of amplitudes,
    # using a calibration h5 file defined in the experiment config
    # pull calibration data from file, handling properly in case of multimode cavity
    cal_path = 'C:\_Lib\python\slab\experiments\qm_opx_mm\drive_calibration'

    fn_file = cal_path + '\\00000_2021_11_24_cavity_square_mode_2.h5'

    with File(fn_file, 'r') as f:
        omegas = np.array(f['omegas'])
        amps = np.array(f['amps'])
    # assume zero frequency at zero amplitude, used for interpolation function
    omegas = np.append(omegas, 0.0)
    amps = np.append(amps, 0.0)

    o_s = omegas
    a_s = amps

    # interpolate data, transfer_fn is a function that for each omega returns the corresponding amp
    transfer_fn = scipy.interpolate.interp1d(a_s, o_s)

    omega_desired = transfer_fn(cav_amp)

    pulse_length = (alpha/omega_desired)
    """Returns time in units of 4ns for FPGA"""
    return abs(pulse_length)//4+1

t_chi = int(abs(0.5*1e9/two_chi[1])) #qubit rotates by pi in this time

"""Coherent drive to create Fock state in the cavity"""
cav_len = 400
cav_amp = 0.00
""""Coherent drive to simulate the dark matter push"""
coh_len = 400
coh_amp = 0.00

# Fock1: D(-0.580) * S(0,pi) * D(1.143) * |0>
# Fock2: D(0.432) * S(1,pi) * D(-1.133) * S(0,pi) * D(0.497) * |0>
# Fock3: D(0.344) * S(2,pi) * D(-1.072) * S(1,pi) * D(-1.125) * S(0,pi) * D(1.878) * |0>
# Fock4: D(-0.284) * S(3,pi) * D(0.775) * S(2,pi) * D(-0.632) * S(1,pi) * D(-0.831) * S(0,pi) * D(1.555) * |0>


simulation_config = SimulationConfig(
    duration=60000,
    simulation_interface=LoopbackInterface(
        [("con1", 1, "con1", 1), ("con1", 2, "con1", 2)], latency=230, noisePower=0.5**2
    )
)

qmm = QuantumMachinesManager()
discriminator = TwoStateDiscriminator(qmm, config, True, 'rr', disc_file_opt, lsb=True)
##################
avgs = 5000
reset_time = int(3.5e6)
simulation = 0

num_pi_pulses_m = 10 #need even number to bring the qubit back to 'g' before coherent drive
num_pi_pulses_n = 0

def snap_seq(fock_state=0):

    if fock_state==0:
        play("CW"*amp(0.0), 'storage_mode1', duration=alpha_awg_cal(1.143))
        align('storage_mode1', 'qubit_mode0')
        play("res_pi"*amp(0.0), 'qubit_mode0')
        align('storage_mode1', 'qubit_mode0')
        play("CW"*amp(-0.0), 'storage_mode1', duration=alpha_awg_cal(-0.58))

    elif fock_state==1:
        play("CW"*amp(1.0), 'storage_mode1', duration=alpha_awg_cal(1.143))
        align('storage_mode1', 'qubit_mode0')
        play("res_pi"*amp(2.0), 'qubit_mode0')
        align('storage_mode1', 'qubit_mode0')
        play("CW"*amp(-1.0), 'storage_mode1', duration=alpha_awg_cal(-0.58))

    elif fock_state==2:
        play("CW"*amp(1.0), 'storage_mode1', duration=alpha_awg_cal(0.497))
        align('storage_mode1', 'qubit_mode0')
        play("res_pi"*amp(2.0), 'qubit_mode0')
        align('storage_mode1', 'qubit_mode0')
        play("CW"*amp(-1.0), 'storage_mode1', duration=alpha_awg_cal(1.133))
        update_frequency('qubit_mode0', ge_IF[0] + two_chi[1])
        align('storage_mode1', 'qubit_mode0')
        play("res_pi"*amp(2.0), 'qubit_mode0')
        align('storage_mode1', 'qubit_mode0')
        play("CW"*amp(1.0), 'storage_mode1', duration=alpha_awg_cal(0.432))
        update_frequency('qubit_mode0', ge_IF[0])

    elif fock_state==3:
        play("CW"*amp(1.0), 'storage_mode1', duration=alpha_awg_cal(0.531))
        align('storage_mode1', 'qubit_mode0')
        play("res_pi"*amp(2.0), 'qubit_mode0')
        align('storage_mode1', 'qubit_mode0')
        play("CW"*amp(-1.0), 'storage_mode1', duration=alpha_awg_cal(0.559))
        update_frequency('qubit_mode0', ge_IF[0] + two_chi[1])
        align('storage_mode1', 'qubit_mode0')
        play("res_pi"*amp(2.0), 'qubit_mode0')
        align('storage_mode1', 'qubit_mode0')
        play("CW"*amp(1.0), 'storage_mode1', duration=alpha_awg_cal(0.946))
        update_frequency('qubit_mode0', ge_IF[0] + 2*two_chi[1])
        align('storage_mode1', 'qubit_mode0')
        play("res_pi"*amp(2.0), 'qubit_mode0')
        align('storage_mode1', 'qubit_mode0')
        play("CW"*amp(-1.0), 'storage_mode1', duration=alpha_awg_cal(0.358))
        update_frequency('qubit_mode0', ge_IF[0])

def bd():
    play("pi2", 'qubit_mode0') # unconditional
    wait(t_chi//4+1, 'qubit_mode0')
    frame_rotation(np.pi, 'qubit_mode0')
    play("pi2", 'qubit_mode0')
    align('qubit_mode0', 'rr')
    discriminator.measure_state("clear", "out1", "out2", bit1, I=I)

    reset_frame('qubit_mode0')
    wait(250, "rr")
    align('qubit_mode0', "rr")

    play("pi2", 'qubit_mode0') # unconditional
    wait(t_chi//4//2-4, 'qubit_mode0') # subtracted 3 to make the simulated waveforms accurate
    with if_(bit1==0):
        frame_rotation(np.pi, 'qubit_mode0')
        play("pi2", 'qubit_mode0')
    with else_():
        frame_rotation(3/2*np.pi, 'qubit_mode0')
        play("pi2", 'qubit_mode0')
    align('qubit_mode0', 'rr')
    discriminator.measure_state("clear", "out1", "out2", bit2, I=I)


with program() as binary_decomposition:

    ##############################
    # declare real-time variables:
    ##############################

    n = declare(int)      # Averaging
    i = declare(int)      # Amplitudes
    t = declare(int) #array of time delays
    bit1 = declare(bool)
    bit2 = declare(bool)
    bit3 = declare(bool)
    num1 = declare(int)
    num2 = declare(int)
    I = declare(fixed)

    num1_st = declare_stream()
    num2_st = declare_stream()
    bit3_st = declare_stream()

    ###############
    # the sequence:
    ###############

    with for_(n, 0, n < avgs, n + 1):

        wait(reset_time//4, 'storage_mode1')
        update_frequency('qubit_mode0', ge_IF[0])
        update_frequency('storage_mode1', storage_IF[1])
        ########################
        snap_seq(fock_state=1)
        ########################

        """First binary decomposition here"""
        align('storage_mode1', 'qubit_mode0')
        bd()
        assign(num1, Cast.to_int(bit1) + 2*Cast.to_int(bit2))
        save(num1, num1_st)
        """First BD after the state prep ends here"""
        ########################
        update_frequency('qubit_mode0', ge_IF[0] + (num1)*two_chi[1])
        reset_frame('qubit_mode0')
        update_frequency('storage_mode1', storage_IF[1] + (num1*(num1-1))*st_self_kerr)

        # """Flip the qubit to |g> before repeated pi pulses"""
        # align('rr',  'qubit_mode0')
        # with if_(bit2):
        #     play('pi', 'qubit_mode0')
        # align('rr', 'qubit_mode0')
        ########################

        ########################
        """Repeated pi pulses"""

        with for_(i, 0, i < num_pi_pulses_m, i+1):
            wait(250, "rr")
            align('qubit_mode0', "rr")
            play("res_pi", 'qubit_mode0')
            align('qubit_mode0', 'rr')
            discriminator.measure_state("clear", "out1", "out2", bit3, I=I)
            save(bit3, bit3_st)
        ########################

        reset_frame('qubit_mode0')
        update_frequency('qubit_mode0', ge_IF[0])

        """active reset to bring qubit back to 'g' before the next BD"""
        with if_(bit3):
            align('rr', 'qubit_mode0')
            play('pi', 'qubit_mode0')

        align('storage_mode1', 'rr')

        play('CW'*amp(0.01), 'storage_mode1', duration=100)

        align('qubit_mode0', 'storage_mode1')

        """Post BD starts"""
        bd()

        assign(num2, Cast.to_int(bit1) + 2*Cast.to_int(bit2))
        save(num2, num2_st)

    with stream_processing():
        num1_st.save_all('num1')
        num2_st.save_all('num2')
        bit3_st.boolean_to_int().buffer(num_pi_pulses_m+num_pi_pulses_n).save_all('bit3')

qm = qmm.open_qm(config)
if simulation:
    """To simulate the pulse sequence"""
    job = qm.simulate(binary_decomposition, simulation_config)
    samples = job.get_simulated_samples()
    samples.con1.plot()
    result_handles = job.result_handles

else:
    """To run the actual experiment"""
    job = qm.execute(binary_decomposition, duration_limit=0, data_limit=0)
    print("Experiment execution Done")

    result_handles = job.result_handles
    result_handles.wait_for_all_values()
    num1 = result_handles.get('num1').fetch_all()['value']
    num2 = result_handles.get('num2').fetch_all()['value']
    bit3 = result_handles.get('bit3').fetch_all()['value']

    p_cav = [np.sum(num1==0)*100/avgs, np.sum(num1==1)*100/avgs, np.sum(num1==2)*100/avgs, np.sum(num1==3)*100/avgs]

    print("n=0 => {}, n=1 => {}, n=2 => {}, n=3 => {}".format(p_cav[0], p_cav[1], p_cav[2], p_cav[3]))

    p_cav = [np.sum(num2==0)*100/avgs, np.sum(num2==1)*100/avgs, np.sum(num2==2)*100/avgs, np.sum(num2==3)*100/avgs]

    print("n=0 => {}, n=1 => {}, n=2 => {}, n=3 => {}".format(p_cav[0], p_cav[1], p_cav[2], p_cav[3]))
    #
    # num3 = num2-num1
    #
    # p_cav = [np.sum(num3==0)*100/avgs, np.sum(num3==1)*100/avgs, np.sum(num3==2)*100/avgs, np.sum(num3==3)*100/avgs]
    #
    # print("n=0 => {}, n=1 => {}, n=2 => {},n=3 => {}".format(p_cav[0], p_cav[1], p_cav[2], p_cav[3]))

    # job.halt()
    #
    # path = os.getcwd()
    # data_path = os.path.join(path, "data/")
    # seq_data_file = os.path.join(data_path,
    #                              get_next_filename(data_path, 'stim_em_bd_rp_debug', suffix='.h5'))
    # print(seq_data_file)
    # with File(seq_data_file, 'w') as f:
    #     f.create_dataset("p_cav", data=p_cav)
    #     f.create_dataset("amp", data=cav_amp)
    #     f.create_dataset("time", data=cav_len*4)
    #     f.create_dataset("num1", data=num1)
    #     f.create_dataset("num2", data=num2)
    #     f.create_dataset("bit3", data=bit3)
    #     f.create_dataset("pi_m", data=num_pi_pulses_m)
    #     f.create_dataset("pi_n", data=num_pi_pulses_n)