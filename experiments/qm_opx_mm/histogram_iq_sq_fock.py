from configuration_IQ import config, rr_IF, readout_len, ge_IF, qubit_freq, two_chi, disc_file_opt, storage_cal_file
from qm.qua import *
from qm import SimulationConfig
from qm.QuantumMachinesManager import QuantumMachinesManager
import numpy as np
import scipy
from scipy.optimize import curve_fit
import matplotlib.pyplot as plt
from h5py import File
from slab import*
import os
from slab.dataanalysis import get_next_filename

##################
# histogram_prog:
##################
def alpha_awg_cal(alpha, cav_amp=1.0, cal_file=storage_cal_file[1]):
    # takes input array of omegas and converts them to output array of amplitudes,
    # using a calibration h5 file defined in the experiment config
    # pull calibration data from file, handling properly in case of multimode cavity
    with File(cal_file, 'r') as f:
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

def snap_seq(fock_state=0):

    if fock_state==0:
        play("CW"*amp(0.0),'storage_mode1', duration=alpha_awg_cal(1.143, cav_amp=opx_amp))
        align('storage_mode1', 'qubit_mode0')
        play("res_2pi"*amp(0.0), 'qubit_mode0')
        align('storage_mode1', 'qubit_mode0')
        play("CW"*amp(-0.0),'storage_mode1', duration=alpha_awg_cal(-0.58, cav_amp=opx_amp))

    elif fock_state==1:
        play("CW"*amp(opx_amp),'storage_mode1', duration=alpha_awg_cal(1.143, cav_amp=opx_amp))
        align('storage_mode1', 'qubit_mode0')
        play("res_2pi"*amp(1.0), 'qubit_mode0')
        align('storage_mode1', 'qubit_mode0')
        play("CW"*amp(-opx_amp),'storage_mode1', duration=alpha_awg_cal(-0.58, cav_amp=opx_amp))

    elif fock_state==2:
        play("CW"*amp(opx_amp),'storage_mode1', duration=alpha_awg_cal(0.497, cav_amp=opx_amp))
        align('storage_mode1', 'qubit_mode0')
        play("res_2pi"*amp(1.0), 'qubit_mode0')
        align('storage_mode1', 'qubit_mode0')
        play("CW"*amp(-opx_amp),'storage_mode1', duration=alpha_awg_cal(1.133, cav_amp=opx_amp))
        update_frequency('qubit_mode0', ge_IF[0] + two_chi[1])
        align('storage_mode1', 'qubit_mode0')
        play("res_2pi"*amp(1.0), 'qubit_mode0')
        align('storage_mode1', 'qubit_mode0')
        play("CW"*amp(opx_amp),'storage_mode1', duration=alpha_awg_cal(0.432, cav_amp=opx_amp))
        update_frequency('qubit_mode0', ge_IF[0])

    elif fock_state==3:
        play("CW"*amp(opx_amp),'storage_mode1', duration=alpha_awg_cal(0.531, cav_amp=opx_amp))
        align('storage_mode1', 'qubit_mode0')
        play("res_2pi"*amp(1.0), 'qubit_mode0')
        align('storage_mode1', 'qubit_mode0')
        play("CW"*amp(-opx_amp),'storage_mode1', duration=alpha_awg_cal(0.559, cav_amp=opx_amp))
        update_frequency('qubit_mode0', ge_IF[0] + two_chi[1])
        align('storage_mode1', 'qubit_mode0')
        play("res_2pi"*amp(1.0), 'qubit_mode0')
        align('storage_mode1', 'qubit_mode0')
        play("CW"*amp(opx_amp),'storage_mode1', duration=alpha_awg_cal(0.946, cav_amp=opx_amp))
        update_frequency('qubit_mode0', ge_IF[0] + 2*two_chi[1])
        align('storage_mode1', 'qubit_mode0')
        play("res_2pi"*amp(1.0), 'qubit_mode0')
        align('storage_mode1', 'qubit_mode0')
        play("CW"*amp(-opx_amp),'storage_mode1', duration=alpha_awg_cal(0.358, cav_amp=opx_amp))
        update_frequency('qubit_mode0', ge_IF[0])

l_min = 5
l_max = 45
dl = 4

l_vec = np.arange(l_min, l_max + dl/2, dl)

avgs = 4000
reset_time = int(7.5e6)

simulation = 0

pulse_len = readout_len

w_plus = [(1.0, pulse_len)]
w_minus = [(-1.0, pulse_len)]
w_zero = [(0.0, pulse_len)]

b = (30.0/180)*np.pi
w_plus_cos = [(np.cos(b), pulse_len)]
w_minus_cos = [(-np.cos(b), pulse_len)]
w_plus_sin = [(np.sin(b), pulse_len)]
w_minus_sin = [(-np.sin(b), pulse_len)]
config['integration_weights']['cos']['cosine'] = w_plus_cos
config['integration_weights']['cos']['sine'] = w_minus_sin
config['integration_weights']['sin']['cosine'] = w_plus_sin
config['integration_weights']['sin']['sine'] = w_plus_cos
config['integration_weights']['minus_sin']['cosine'] = w_minus_sin
config['integration_weights']['minus_sin']['sine'] = w_minus_cos
opx_amp = 1.0
f_target = 3
with program() as histogram:

    ##############################
    # declare real-time variables:
    ##############################

    n = declare(int)      # Averaging

    I = declare(fixed)
    Q = declare(fixed)

    l = declare(int)

    Ig_st = declare_stream()
    Qg_st = declare_stream()

    Ie_st = declare_stream()
    Qe_st = declare_stream()

    # update_frequency('rr', rr_IF+5e3)

    ###############
    # the sequence:
    ###############

    # update_frequency("rr", rr_IF + f_target*10e3)

    with for_(n, 0, n < avgs, n + 1):

        """readout with a storage playing anything"""
        update_frequency("qubit_mode0", ge_IF[0])
        wait(reset_time// 4, "storage_mode1")# wait for the storage to relax, several T1s
        snap_seq(fock_state=f_target)
        align("rr", "storage_mode1")
        measure("readout", "rr", None,
                dual_demod.full('cos', 'out1', 'minus_sin', 'out2', I),
                dual_demod.full('sin', 'out1', 'cos', 'out2', Q))
        save(I, Ig_st)
        save(Q, Qg_st)

        align("storage_mode1", "qubit_mode0", "rr")

        """Play a ge pi pulse and then readout"""
        update_frequency("qubit_mode0", ge_IF[0])
        wait(2000, "qubit_mode0")
        play("pi", "qubit_mode0")
        align("qubit_mode0", "rr")
        measure("readout", "rr", None,
                dual_demod.full('cos', 'out1', 'minus_sin', 'out2', I),
                dual_demod.full('sin', 'out1', 'cos', 'out2', Q))

        save(I, Ie_st)
        save(Q, Qe_st)

    with stream_processing():
        Ig_st.save_all('Ig')
        Qg_st.save_all('Qg')

        Ie_st.save_all('Ie')
        Qe_st.save_all('Qe')

qmm = QuantumMachinesManager()
qm = qmm.open_qm(config)

if simulation:
    """To simulate the pulse sequence"""
    job = qm.simulate(histogram, SimulationConfig(15000))
    samples = job.get_simulated_samples()
    samples.con1.plot()

else:
    """To run the actual experiment"""
    job = qm.execute(histogram, duration_limit=0, data_limit=0)
    print("Done")

    res_handles = job.result_handles
    res_handles.wait_for_all_values()

    Ig_handle = res_handles.get("Ig")
    Qg_handle = res_handles.get("Qg")

    Ie_handle = res_handles.get("Ie")
    Qe_handle = res_handles.get("Qe")

    Ig = np.array(Ig_handle.fetch_all()['value'])
    Qg = np.array(Qg_handle.fetch_all()['value'])

    Ie = np.array(Ie_handle.fetch_all()['value'])
    Qe = np.array(Qe_handle.fetch_all()['value'])

    plt.figure()
    # plt.plot(Ig, Qg,'.')
    plt.plot(Ie, Qe,'.')
    # plt.plot(If, Qf,'.')

    plt.axis('equal')
    #
    # job.halt()

    # Ig = job.result_handles.Ig.fetch_all()['value']
    # Ie = job.result_handles.Ie.fetch_all()['value']
    # Qg = job.result_handles.Qg.fetch_all()['value']
    # Qe = job.result_handles.Qe.fetch_all()['value']
    # print("Data fetched")
    #
    # job.halt()
    #
    # path = os.getcwd()
    # data_path = os.path.join(path, "data/")
    # seq_data_file = os.path.join(data_path,
    #                              get_next_filename(data_path, 'histogram_sq_fock', suffix='.h5'))
    # print(seq_data_file)
    #
    # with File(seq_data_file, 'w') as f:
    #     f.create_dataset("ig", data=Ig)
    #     f.create_dataset("qg", data=Qg)
    #     f.create_dataset("ie", data=Ie)
    #     f.create_dataset("qe", data=Qe)
    #     f.create_dataset("fock", data=f_target)
