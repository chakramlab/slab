from configuration_IQ import config, qubit_freq, rr_LO, qubit_LO, ge_IF
from qm.qua import *
from qm import SimulationConfig
from qm.QuantumMachinesManager import QuantumMachinesManager
import numpy as np
import matplotlib.pyplot as plt
from slab import*
from slab.instruments import instrumentmanager
im = InstrumentManager()
LO_q = im['RF5']
LO_r = im['RF8']
# atten = im['atten']
from slab.dsfit import*

###############
# qubit_spec_prog:
###############
f_min = -4e6
f_max = 4e6
df = 40e3

f_vec = np.arange(f_min, f_max + df/2, df)
f_vec = f_vec + qubit_freq

LO_q.set_frequency(qubit_LO)
LO_q.set_ext_pulse(mod=False)
LO_q.set_power(18)
LO_r.set_frequency(rr_LO)
LO_r.set_ext_pulse(mod=False)
LO_r.set_power(13)
# atten.set_attenuator(12.0)
# time.sleep(1)

avgs = 500
reset_time = 500000
simulation = 0
with program() as qubit_spec:

    ##############################
    # declare real-time variables:
    ##############################

    n = declare(int)        # Averaging
    f = declare(int)        # Frequencies
    I = declare(fixed)
    Q = declare(fixed)
    I1 = declare(fixed)
    Q1 = declare(fixed)
    I2 = declare(fixed)
    Q2 = declare(fixed)

    I_st = declare_stream()
    Q_st = declare_stream()

    ###############
    # the sequence:
    ###############
    with for_(n, 0, n < avgs, n + 1):

        with for_(f, ge_IF + f_min, f <= ge_IF + f_max, f + df):

            update_frequency("qubit", f)
            wait(reset_time// 4, "qubit")# wait for the qubit to relax, several T1s
            play("saturation"*amp(0.1), "qubit", duration=12500)
            align("qubit", "rr")
            measure("long_readout", "rr", None, demod.full("long_integW1", I1, 'out1'), demod.full("long_integW2", Q1, 'out1'),
                demod.full("long_integW1", I2, 'out2'), demod.full("long_integW2", Q2, 'out2'))

            assign(I, I1 + Q2)
            assign(Q, -Q1 + I2)

            save(I, I_st)
            save(Q, Q_st)

    with stream_processing():

        I_st.buffer(len(f_vec)).average().save('I')
        Q_st.buffer(len(f_vec)).average().save('Q')

qmm = QuantumMachinesManager()
qm = qmm.open_qm(config)

if simulation:
    """To simulate the pulse sequence"""
    job = qm.simulate(qubit_spec, SimulationConfig(150000))
    samples = job.get_simulated_samples()
    samples.con1.plot()

else:
    """To run the actual experiment"""
    job = qm.execute(qubit_spec, duration_limit=0, data_limit=0)
    print("Experiment done")

    res_handles = job.result_handles
    res_handles.wait_for_all_values()
    I_handle = res_handles.get("I")
    Q_handle = res_handles.get("Q")
    I = I_handle.fetch_all()
    Q = Q_handle.fetch_all()
    print("Data collection done!")

    fig, axs = plt.subplots(1, 2, figsize=(10, 5))
    axs[0].plot(f_vec/1e9, I, 'o')
    axs[0].plot(f_vec/1e9, Q, 'o')
    axs[0].set_xlabel('Freq (GHz)')
    axs[0].set_ylabel('I/Q')
    amps = np.sqrt(np.array(I)**2 + 1*np.array(Q)**2)
    ph = np.arctan2(np.array(Q), np.array(I))
    ph = np.unwrap(ph, discont=3.141592653589793, axis=-1)
    m = (ph[-1]-ph[0])/(f_vec[-1] - f_vec[0])
    ph = ph - m*f_vec*0.95
    ph = ph - np.mean(ph)
    axs[1].plot(f_vec/1e9, -amps, 'b')
    p = fitlor(f_vec/1e9, -amps, showfit=False)
    x = np.array(f_vec)/1e9
    axs[1].plot(f_vec/1e9, lorfunc(p, f_vec/1e9), label=r'$\nu_{q}$ = %.4f GHz'% x[np.argmin(amps)])
    print("fits = ", p)

    ax2 = axs[1].twinx()
    ax2.plot(f_vec/1e9, ph, 'r')
    axs[1].set_xlabel('Freq (GHz)')
    axs[1].set_ylabel('amp')
    ax2.set_ylabel('$\\varphi$')
    axs[1].legend(loc='best')
    fig.show()