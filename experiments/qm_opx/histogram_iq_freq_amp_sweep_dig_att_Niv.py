from configuration_IQ import config, qubit_LO, rr_LO, rr_IF, rr_freq
from qm.qua import*
from qm import SimulationConfig
from qm.QuantumMachinesManager import QuantumMachinesManager
import numpy as np
from tqdm import tqdm
from scipy.optimize import curve_fit
import matplotlib.pyplot as plt
import pandas as pd
from slab import*
from slab.instruments import instrumentmanager
from slab.dsfit import*
im = InstrumentManager()
LO_q = im['RF5']
LO_r = im['RF8']
atten = im["atten"]

def doublegauss(bins, *p):
    a1, sigma1, mu1 = p[0], p[1], p[2]
    a2, sigma2, mu2 = p[3], p[4], p[5]

    y1 = a1 * ((1 / (np.sqrt(2 * np.pi) * sigma1)) *
               np.exp(-0.5 * (1 / sigma1 * (bins - mu1)) ** 2))
    y2 = a2 * ((1 / (np.sqrt(2 * np.pi) * sigma2)) *
               np.exp(-0.5 * (1 / sigma2 * (bins - mu2)) ** 2))
    y = y1 + y2

    return y

def hist(p):
    ig_opt = np.array(p[0])
    qg_opt = np.array(p[1])
    ie_opt = np.array(p[2])
    qe_opt = np.array(p[3])
    ran = 1
    numbins = 200
    xg, yg = np.median(ig_opt), np.median(qg_opt)
    xe, ye = np.median(ie_opt), np.median(qe_opt)
    xlims = [xg-ran/5, xg+ran/5]
    ylims = [yg-ran/5, yg+ran/5]
    theta = -np.arctan((ye-yg)/(xe-xg))
    ig_new, qg_new = ig_opt*cos(theta) - qg_opt*sin(theta), ig_opt*sin(theta) + qg_opt*cos(theta)
    ie_new, qe_new = ie_opt*cos(theta) - qe_opt*sin(theta), ie_opt*sin(theta) + qe_opt*cos(theta)

    xg, yg = np.median(ig_new), np.median(qg_new)
    xe, ye = np.median(ie_new), np.median(qe_new)

    xlims = [xg-ran/5, xg+ran/5]
    ylims = [yg-ran/5, yg+ran/5]

    ng, binsg = np.histogram(ig_new, bins=numbins, range=xlims)
    ne, binse = np.histogram(ie_new, bins=numbins, range=xlims)
    fid_i = np.abs(((np.cumsum(ng) - np.cumsum(ne)) / ng.sum())).max()
    ng, binsg = np.histogram(qg_new, bins=numbins, range=ylims)
    ne, binse = np.histogram(qe_new, bins=numbins, range=ylims)
    fid_q = np.abs(((np.cumsum(ng) - np.cumsum(ne)) / ng.sum())).max()

    return [fid_i, fid_q]

##################
# histogram_prog:
##################
LO_q.set_frequency(qubit_LO)
LO_q.set_ext_pulse(mod=False)
LO_q.set_power(16)
LO_r.set_frequency(rr_LO)
LO_r.set_ext_pulse(mod=True)
LO_r.set_power(18)

atten.set_attenuator(0.0)
time.sleep(1)

reset_time = 500000
avgs = 2000

with program() as histogram:

    ##############################
    # declare real-time variables:
    ##############################

    n = declare(int)      # Averaging
    f = declare(int)
    i = declare(int)

    Ig = declare(fixed)
    Qg = declare(fixed)

    I1 = declare(fixed)
    Q1 = declare(fixed)
    I2 = declare(fixed)
    Q2 = declare(fixed)

    Ie = declare(fixed)
    Qe = declare(fixed)
    # If = declare(fixed)
    # Qf = declare(fixed)

    Ig_st = declare_stream()
    Qg_st = declare_stream()

    Ie_st = declare_stream()
    Qe_st = declare_stream()


    with for_(i, 0, i < len(amp_vec), i + 1):

        with for_(n, 0, n < avgs, n + 1):

            with for_(f, rr_IF + f_min, f < rr_IF + f_max + df/2, f + df):

                update_frequency("rr", f)

                """Just readout without playing anything"""
                wait(reset_time//4, "rr")
                measure("long_readout", "rr", None, demod.full("long_integW1", I1, 'out1'),
                        demod.full("long_integW2", Q1, 'out1'),
                        demod.full("long_integW1", I2, 'out2'), demod.full("long_integW2", Q2, 'out2'))

                assign(Ig, I1 + Q2)
                assign(Qg, I2 - Q1)
                save(Ig, Ig_st)
                save(Qg, Qg_st)

                align("qubit", "rr")

                """Play a ge pi pulse and then readout"""
                wait(reset_time // 4, "qubit")
                play("pi", "qubit")
                align("qubit", "rr")
                measure("long_readout", "rr", None, demod.full("long_integW1", I1, 'out1'),
                        demod.full("long_integW2", Q1, 'out1'),
                        demod.full("long_integW1", I2, 'out2'), demod.full("long_integW2", Q2, 'out2'))

                assign(Ie, I1 + Q2)
                assign(Qe, I2 - Q1)
                save(Ie, Ie_st)
                save(Qe, Qe_st)

    with stream_processing():
        Ig_st.save_all('Ig')
        Qg_st.save_all('Qg')

        Ie_st.save_all('Ie')
        Qe_st.save_all('Qe')

qmm = QuantumMachinesManager()
qm = qmm.open_qm(config)
job = qm.execute(histogram, duration_limit=0, data_limit=0)









for att in tqdm(amp_vec):
    while not job.is_paused():
        time.sleep(0.01)
    atten.set_attenuator(att)
    print(att)
    time.sleep(0.1)
    job.resume()

print("Waiting for the data")

job.result_handles.wait_for_all_values()

Ig = job.result_handles.Ig.fetch_all()['value']
Ie = job.result_handles.Ie.fetch_all()['value']
Qg = job.result_handles.Qg.fetch_all()['value']
Qe = job.result_handles.Qe.fetch_all()['value']
print("Data fetched")

fid = []
for ii in range(len(amp_vec)):
    fid_f = []
    for jj in range(len(f_vec)):
        ig = Ig[int(jj+ii*len(amp_vec))::int(len(amp_vec)*len(f_vec))]
        qg = Qg[int(jj+ii*len(amp_vec))::int(len(amp_vec)*len(f_vec))]
        ie = Ie[int(jj+ii*len(amp_vec))::int(len(amp_vec)*len(f_vec))]
        qe = Qe[int(jj+ii*len(amp_vec))::int(len(amp_vec)*len(f_vec))]
        p = [ig, qg, ie, qe]
        f = hist(p)[0]
        fid_f.append(f)
    fid.append(fid_f)

"""Plotting the fidelity data as a function of amp and freq"""
# fid = np.transpose(fid)
f_vec = (rr_freq + f_vec)/1e9

ind = [np.argmax(fid)//len(f_vec), np.argmax(fid)%len(f_vec)] #index for maximum fidelity
fid_max = fid[ind[0]][ind[1]]

fig, ax = plt.subplots(figsize=(8, 6))
pcm = ax.pcolormesh(f_vec, amp_vec, fid, cmap='RdBu', vmin=0.5, vmax=1)
fig.colorbar(pcm, ax=ax)
ax.axvline(x=f_vec[ind[1]], color='k', linestyle='--')
ax.axhline(y=amp_vec[ind[0]], color='k', linestyle='--')
ax.axvline(x=8.0518, color='r', linestyle='--')
ax.axvline(x=8.0515, color='b', linestyle='--')
ax.set_title('F = %.2f at readout power = %.3f (V) and readout frequency = %.4f GHz'%(fid_max, amp_vec[ind[0]],f_vec[ind[1]]))

print("#############################################################################################")
print('Optimal fidelity of %f at readout power = %f (V) and readout frequency = %f GHz'%(fid_max, amp_vec[ind[0]],f_vec[ind[1]]))
print("#############################################################################################")
ax.set_xlim(np.min(f_vec), np.max(f_vec))
ax.set_xlabel('Readout frequency (GHz)')
ax.set_ylabel('IF Amp (V)')
plt.show()
