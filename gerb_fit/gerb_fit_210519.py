from numpy import*
from pylab import*
import matplotlib.pyplot as plt
from h5py import File
import json
from slab.dsfit import *
from slab.aofit import *
import math
from slab import *
import numpy as np
from scipy.special import ellipk
from IPython.display import Image
import matplotlib
import matplotlib.pyplot as plt
from kfit import fit_lor
from kfit import fit_hanger
import os
from scipy.interpolate import interp1d
notebookdirectory = os.getcwd()
from scipy.signal import savgol_filter
from scipy.signal import find_peaks
print(os.getcwd())
from scipy.signal import argrelextrema
import copy

font = {'family' : 'normal',
        'weight' : 'normal',
        'size'   : 18}

matplotlib.rc('font', **font)

def decaysin_lm(x, amp, f, phi_0, T1, offset, exp0):
    return amp*np.sin(2.*np.pi*f*x+phi_0*np.pi/180.)*np.e**(-1.*(x-exp0)/T1)+offset

def decaysin3(p, x):
    return p[0] * np.sin(2. * np.pi * p[1] * x + p[2] * np.pi / 180.) * np.e ** (-1. * (x - x[0]) / p[3]) + p[4]

def iq_rot(I, Q, phi):
    """Digitially rotates IQdata by phi, calcualting phase as np.unrwap(np.arctan2(Q, I))
    :param I: I data from h5 file
    :param Q: Q data from h5 file
    :param phi: iq rotation desired (in degrees)
    :returns: rotated I, Q
    """
    phi = phi * np.pi / 180
    Irot = I * np.cos(phi) + Q * np.sin(phi)
    Qrot = -I * np.sin(phi) + Q * np.cos(phi)
    return I, Q


def iq_process(f, raw_I, raw_Q, ran=1, phi=0, sub_mean=True):
    """Converts digitial data to voltage data, rotates iq, subtracts off mean, calculates mag and phase
    :param f: frequency
    :param raw_I: I data from h5 file
    :param raw_Q: Q data from h5 file
    :param ran: range of DAC. If set to -1, doesn't convert data to voltage
    :param phi: iq rotation desired (in degrees)
    :param sub_mean: boolean, if True subtracts out average background in IQ data
    :returns: I, Q, mag, phase
    """
    if sub_mean:
        # ie, if want to subtract mean
        I = array(raw_I).flatten() - mean(array(raw_I).flatten())
        Q = array(raw_Q).flatten() - mean(array(raw_Q).flatten())
    else:
        I = array(raw_I).flatten()
        Q = array(raw_Q).flatten()

    # divide by 2**15 to convert from bits to voltage, *ran to get right voltage range
    if ran > 0:
        I = I / 2 ** 15 * ran
        Q = Q / 2 ** 15 * ran

    # calculate mag and phase
    phase = np.unwrap(np.arctan2(Q, I))
    mag = np.sqrt(np.square(I) + np.square(Q))

    # IQ rotate
    I, Q = iq_rot(I, Q, phi)

    return I, Q, mag, phase


def plot_freq_data(f, I, Q, mag, phase, expected_f, mag_phase_plot=False, polar=False, title='', marker=False):
    """Fits frequency data to a lorentzian, then plots data and prints result

    :param f -- data frequency
    :param I -- I data
    :param Q -- Q data
    :param mag -- mag data
    :param phase -- phase data
    :param expected_f -- expected frequency
    :param mag_phase_plot -- boolean, determines whether or not you plot mag and phase as well
    :param polar -- adds a plot of I and Q in polar coordinates
    :param title -- title of plot
    :param marker -- plots a vertical line at marker
    :returns: dsfit result
    """
    fig = plt.figure(figsize=(14, 5))

    ax = fig.add_subplot(111, title=title)
    ax.plot(f, I, 'b.-', label='I')
    ax.plot(f, Q, 'r.-', label='Q')
    if marker:
        ax.axvline(x=marker)
    ax.set_xlabel('Freq(GHz)')
    ax.set_ylabel('I and Q (V)')
    ax.set_xlim(f[0], f[-1])
    ax.legend(loc='upper right')

    if mag_phase_plot:
        fig = plt.figure(figsize=(14, 5))
        ax3 = fig.add_subplot(111, title=' Mag and phase')
        ax3.plot(f, mag, 'g.-', label='Magnitude')
        ax3.set_xlabel('Freq(GHz)')
        ax3.set_ylabel('Magnitude (V)')
        ax3.set_xlim(f[0], f[-1])
        p = fitlor(f, np.square(mag), showfit=False)
        ax3.plot(f, sqrt(lorfunc(p, f)), 'k.-', label='fit')
        ax3.axvline(p[2], color='k', linestyle='dashed', label="fit freq")
        ax3.axvline(expected_f, color='r', linestyle='dashed', label="expected freq")
        ax3.legend(loc='upper right')
        ax4 = ax3.twinx()
        ax4.plot(f, phase, 'm.-', label='Phase')
        ax4.set_ylabel('Phase')
        ax4.legend(loc='lower right')

    else:
        ax2 = ax.twinx()
        ax2.plot(f, mag, 'k.-', alpha=0.3, label='mag')
        ax2.set_ylabel('Mag (V)')
        p = fitlor(f, np.square(mag), showfit=False)
        ax2.plot(f, sqrt(lorfunc(p, f)), 'k--', label='fit')
        ax2.axvline(p[2], color='k', linestyle='dashed', label="fit  freq")
        ax2.axvline(expected_f, color='r', linestyle='dashed', label="expected  freq")
        ax2.legend(loc='lower right')

    maxpt = np.max(mag)
    maxpt_x = np.where(mag == maxpt)
    print("ANALYSIS")
    print("expected frequency: ", expected_f)
    print("Resonant frequency from fitting mag squared: ", p[2], "GHz")
    print("Max Point: ", f[maxpt_x], "GHz")
    print("HWHM: ", p[3] * 1e3, "MHz")
    print()
    fig.tight_layout()
    plt.show()

    if polar:
        plt.title("I vs Q polar plot")
        plt.xlabel("I")
        plt.ylabel("Q")
        plt.grid()
        plt.plot(I, Q)
        print("Qmin = " + str(np.min(Q)))
        print("Qmax = " + str(np.max(Q)))
        print("Imin = " + str(np.min(I)))
        print("Imax = " + str(np.max(I)))
        plt.show()

    return p

def get_params(hardware_cfg, experiment_cfg, quantum_device_cfg, on_qb):

    params = {}
    params['ran'] = hardware_cfg['awg_info']['keysight_pxi']['digtzr_vpp_range']
    params['readout_params'] = quantum_device_cfg['readout'][on_qb]
    params['readout_freq'] = params['readout_params'] ["freq"]
    params['dig_atten_qb'] = quantum_device_cfg['powers'][on_qb]['drive_digital_attenuation']
    params['dig_atten_rd'] = quantum_device_cfg['powers'][on_qb]['readout_drive_digital_attenuation']
    params['read_lo_pwr'] = quantum_device_cfg['powers'][on_qb]['readout_drive_lo_powers']
    params['qb_lo_pwr'] = quantum_device_cfg['powers'][on_qb]['drive_lo_powers']
    params['qb_freq'] = quantum_device_cfg['qubit'][on_qb]['freq']
    return params

def resonator_spectroscopy(filenb, phi=0, sub_mean=True, mag_phase_plot=False, polar=False, debug=False, marker=False):
    """Fits resonator_spectroscopoy data, then plots data and prints result

    Keyword arguments:
    filelist -- the data runs you want to analyze and plot
    phi -- in degrees, angle by which you want to rotate IQ
    sub_mean -- if True, subtracts out the average background of IQ measurements
    mag_phase_plot -- boolean, determines whether or not you plot mag and phase as well
    plar -- adds a plot of I and Q in polar coordinates
    debug -- print out experiment attributes
    marker -- plot vertical line where you expect
    """
    # the 'with' statement automatically opens and closes File a, even if code in the with block fails
    expt_name = "resonator_spectroscopy"
    filename = "..\\data\\" + str(filenb).zfill(5) + "_" + expt_name.lower() + ".h5"
    with File(filename, 'r') as a:
        # get data in from json file
        hardware_cfg = (json.loads(a.attrs['hardware_cfg']))
        experiment_cfg = (json.loads(a.attrs['experiment_cfg']))
        quantum_device_cfg = (json.loads(a.attrs['quantum_device_cfg']))
        expt_params = experiment_cfg[expt_name.lower()]

        on_qb = expt_params['on_qubits'][0]
        params = get_params(hardware_cfg, experiment_cfg, quantum_device_cfg, on_qb)
        readout_params = params['readout_params']
        ran = params['ran'] # range of DAC card for processing
        readout_f = params['readout_freq']
        dig_atten_qb = params['dig_atten_qb']
        dig_atten_rd = params['dig_atten_rd']
        read_lo_pwr = params['read_lo_pwr']
        qb_lo_pwr = params['qb_lo_pwr']

        I_raw = a['I']
        Q_raw = a['Q']
        f = arange(expt_params['start'] + readout_f, expt_params['stop'] + readout_f, expt_params['step'])[:len(I_raw)]

        if debug:
            print("DEBUG")
            print("averages =", expt_params['acquisition_num'])
            print("Rd LO pwr= ", read_lo_pwr, "dBm")
            print("Qb LO pwr= ", qb_lo_pwr, "dBm")
            print("Rd atten= ", dig_atten_rd, "dB")
            print("Qb atten= ", dig_atten_qb, "dB")
            print("Readout params", readout_params)
            print("experiment params", expt_params)
        # process I, Q data
        (I, Q, mag, phase) = iq_process(f=f, raw_I=I_raw, raw_Q=Q_raw, ran=ran, phi=phi, sub_mean=sub_mean)

        # plot and fit data
        title = expt_name
        plot_freq_data(f=f, I=I, Q=Q, mag=mag, phase=phase,
                       expected_f=readout_f, mag_phase_plot=mag_phase_plot, polar=polar, title=title, marker=marker)


def ff_ramp_cal_ppiq(filenb, phi=0, sub_mean=True, iq_plot=False, mag_phase_plot=False, polar=False, debug=False, marker=None,
                     slices=False):
    """Fits pulse_probe_iq data, then plots data and prints result
    :param filelist -- the data runs you want to analyze and plot
    :paramphi -- in degrees, angle by which you want to rotate IQ
    :paramsub_mean -- if True, subtracts out the average background of IQ measurements
    :parammag_phase_plot -- boolean, determines whether or not you plot mag and phase as well
    :paramplar -- adds a plot of I and Q in polar coordinates
    :paramdebug -- print out experiment attributes
    """
    # the 'with' statement automatically opens and closes File a, even if code in the with block fails
    expt_name = "ff_ramp_cal_ppiq"
    filename = "..\\data\\" + str(filenb).zfill(5) + "_" + expt_name.lower() + ".h5"
    with File(filename, 'r') as a:
        # get data in from json file
        hardware_cfg = (json.loads(a.attrs['hardware_cfg']))
        experiment_cfg = (json.loads(a.attrs['experiment_cfg']))
        quantum_device_cfg = (json.loads(a.attrs['quantum_device_cfg']))
        expt_params = experiment_cfg[expt_name.lower()]

        on_qb = expt_params['on_qubits'][0]
        params = get_params(hardware_cfg, experiment_cfg, quantum_device_cfg, on_qb)
        readout_params = params['readout_params']
        ran = params['ran'] # range of DAC card for processing
        readout_f = params['readout_freq']
        dig_atten_qb = params['dig_atten_qb']
        dig_atten_rd = params['dig_atten_rd']
        read_lo_pwr = params['read_lo_pwr']
        qb_lo_pwr = params['qb_lo_pwr']

        flux_vec = expt_params['ff_vec']
        print("flux vec {}".format(flux_vec))

        nu_q = params['qb_freq']  # expected qubit freq
        ppiqstart = experiment_cfg[expt_name]['start']
        ppiqstop = experiment_cfg[expt_name]['stop']
        ppiqstep = experiment_cfg[expt_name]['step']
        freqvals = np.arange(ppiqstart, ppiqstop, ppiqstep) + nu_q

        dtstart = experiment_cfg[expt_name]['dt_start']
        dtstop = experiment_cfg[expt_name]['dt_stop']
        dtstep = experiment_cfg[expt_name]['dt_step']
        t_vals = np.arange(dtstart, dtstop, dtstep)

        I_raw = a['I']
        Q_raw = a['Q']

        magarray = []
        parray = []
        for i in range(I_raw.shape[0]):
            # process I, Q data
            (I, Q, mag, phase) = iq_process(f=freqvals, raw_I=I_raw[i], raw_Q=Q_raw[i], ran=ran, phi=phi,
                                            sub_mean=sub_mean)
            magarray.append(mag)
            p = fitlor(freqvals, np.square(mag), showfit=False)
            parray.append(p)
            #magarray.append(np.append(mag, 0))
        #magarray.append(np.zeros(len(magarray[0])))

        if debug:
            print("DEBUG")
            print("averages =", expt_params['acquisition_num'])
            print("Rd LO pwr= ", read_lo_pwr, "dBm")
            print("Qb LO pwr= ", qb_lo_pwr, "dBm")
            print("Rd atten= ", dig_atten_rd, "dB")
            print("Qb atten= ", dig_atten_qb, "dB")
            print("Readout params", readout_params)
            print("experiment params", expt_params)

        x, y = np.meshgrid(freqvals, t_vals[:len(I_raw)])
        fig, ax = plt.subplots(1,1)
        fig.set_figheight(4)
        fig.set_figwidth(8)
        #freq_new = np.append(freqvals, 0)
        #tvals_new = np.append(t_vals[:len(I_raw)], 0)
        # print(freq_new.shape)
        # print(tvals_new.shape)
        #ax.pcolormesh(x, y, magarray, shading='flat', cmap='RdBu')
        ax.pcolormesh(x , y, magarray, shading='nearest', cmap='RdBu')
        ax.set_ylabel('dt (ns)')
        ax.set_xlabel('freq (GHz)')
        ax.set_title('PPIQ Sweep Across Flux Pulse')
        fig.tight_layout()
        plt.show()
        # figure(figsize=(12, 4))
        # plt.pcolormesh(x, y, magarray, shading='nearest', cmap='RdBu')
        # plt.show()

        if iq_plot:
            x, y = np.meshgrid(freqvals, t_vals[:len(I_raw)])
            figure(figsize=(12, 4))
            plt.pcolormesh(x, y, I_raw, shading='nearest', cmap='RdBu')
            plt.show()
            figure(figsize=(12, 4))
            plt.pcolormesh(x, y, Q_raw, shading='nearest', cmap='RdBu')
            plt.show()

        if slices:
            for i in range(I_raw.shape[0]):
                # process I, Q data
                (I, Q, mag, phase) = iq_process(f=freqvals, raw_I=I_raw[i], raw_Q=Q_raw[i], ran=ran, phi=phi,
                                                sub_mean=sub_mean)

                # plot and fit data
                title = expt_name
                plot_freq_data(f=freqvals, I=I, Q=Q, mag=mag, phase=phase,
                               expected_f=nu_q, mag_phase_plot=mag_phase_plot, polar=polar, title=title, marker=marker)
        return t_vals[:len(I_raw)], parray

def pulse_probe_iq(filenb, phi=0, sub_mean=True, mag_phase_plot=False, polar=False, debug=False, marker=None):
    """Fits pulse_probe_iq data, then plots data and prints result
    :param filelist -- the data runs you want to analyze and plot
    :paramphi -- in degrees, angle by which you want to rotate IQ
    :paramsub_mean -- if True, subtracts out the average background of IQ measurements
    :parammag_phase_plot -- boolean, determines whether or not you plot mag and phase as well
    :paramplar -- adds a plot of I and Q in polar coordinates
    :paramdebug -- print out experiment attributes
    """
    # the 'with' statement automatically opens and closes File a, even if code in the with block fails
    expt_name = "pulse_probe_iq"
    filename = "..\\data\\" + str(filenb).zfill(5) + "_" + expt_name.lower() + ".h5"
    with File(filename, 'r') as a:
        # get data in from json file
        hardware_cfg = (json.loads(a.attrs['hardware_cfg']))
        experiment_cfg = (json.loads(a.attrs['experiment_cfg']))
        quantum_device_cfg = (json.loads(a.attrs['quantum_device_cfg']))
        expt_params = experiment_cfg[expt_name.lower()]

        on_qb = expt_params['on_qubits'][0]
        params = get_params(hardware_cfg, experiment_cfg, quantum_device_cfg, on_qb)
        readout_params = params['readout_params']
        ran = params['ran'] # range of DAC card for processing
        readout_f = params['readout_freq']
        dig_atten_qb = params['dig_atten_qb']
        dig_atten_rd = params['dig_atten_rd']
        read_lo_pwr = params['read_lo_pwr']
        qb_lo_pwr = params['qb_lo_pwr']

        nu_q = params['qb_freq']  # expected qubit freq

        I_raw = a['I']
        Q_raw = a['Q']
        f = arange(expt_params['start'], expt_params['stop'], expt_params['step'])[:(len(I_raw))] + nu_q

        if debug:
            print("DEBUG")
            print("averages =", expt_params['acquisition_num'])
            print("Rd LO pwr= ", read_lo_pwr, "dBm")
            print("Qb LO pwr= ", qb_lo_pwr, "dBm")
            print("Rd atten= ", dig_atten_rd, "dB")
            print("Qb atten= ", dig_atten_qb, "dB")
            print("Readout params", readout_params)
            print("experiment params", expt_params)

        # process I, Q data
        (I, Q, mag, phase) = iq_process(f=f, raw_I=I_raw, raw_Q=Q_raw, ran=ran, phi=phi, sub_mean=sub_mean)

        # plot and fit data
        title = expt_name
        p = plot_freq_data(f=f, I=I, Q=Q, mag=mag, phase=phase,
                       expected_f=nu_q, mag_phase_plot=mag_phase_plot, polar=polar, title=title, marker=marker)
        return p

def ff_pulse_probe_iq(filenb, phi=0, sub_mean=True, mag_phase_plot=False, polar=False, debug=False, marker=None):
    """Fits pulse_probe_iq data, then plots data and prints result
    :param filelist -- the data runs you want to analyze and plot
    :paramphi -- in degrees, angle by which you want to rotate IQ
    :paramsub_mean -- if True, subtracts out the average background of IQ measurements
    :parammag_phase_plot -- boolean, determines whether or not you plot mag and phase as well
    :paramplar -- adds a plot of I and Q in polar coordinates
    :paramdebug -- print out experiment attributes
    """
    # the 'with' statement automatically opens and closes File a, even if code in the with block fails
    expt_name = "ff_pulse_probe_iq"
    filename = "..\\data\\" + str(filenb).zfill(5) + "_" + expt_name.lower() + ".h5"
    with File(filename, 'r') as a:
        # get data in from json file
        hardware_cfg = (json.loads(a.attrs['hardware_cfg']))
        experiment_cfg = (json.loads(a.attrs['experiment_cfg']))
        quantum_device_cfg = (json.loads(a.attrs['quantum_device_cfg']))
        expt_params = experiment_cfg[expt_name.lower()]

        on_qb = expt_params['on_qubits'][0]
        params = get_params(hardware_cfg, experiment_cfg, quantum_device_cfg, on_qb)
        readout_params = params['readout_params']
        ran = params['ran'] # range of DAC card for processing
        readout_f = params['readout_freq']
        dig_atten_qb = params['dig_atten_qb']
        dig_atten_rd = params['dig_atten_rd']
        read_lo_pwr = params['read_lo_pwr']
        qb_lo_pwr = params['qb_lo_pwr']

        nu_q = params['qb_freq']  # expected qubit freq
        ff_vec = expt_params['ff_vec']
        print("fast flux vec is {}".format(ff_vec))

        I_raw = a['I']
        Q_raw = a['Q']
        f = arange(expt_params['start'], expt_params['stop'], expt_params['step'])[:(len(I_raw))] + nu_q

        if debug:
            print("DEBUG")
            print("averages =", expt_params['acquisition_num'])
            print("Rd LO pwr= ", read_lo_pwr, "dBm")
            print("Qb LO pwr= ", qb_lo_pwr, "dBm")
            print("Rd atten= ", dig_atten_rd, "dB")
            print("Qb atten= ", dig_atten_qb, "dB")
            print("Readout params", readout_params)
            print("experiment params", expt_params)

        # process I, Q data
        (I, Q, mag, phase) = iq_process(f=f, raw_I=I_raw, raw_Q=Q_raw, ran=ran, phi=phi, sub_mean=sub_mean)

        # plot and fit data
        title = expt_name
        p = plot_freq_data(f=f, I=I, Q=Q, mag=mag, phase=phase,
                       expected_f=nu_q, mag_phase_plot=mag_phase_plot, polar=polar, title=title, marker=marker)
        return p

def rabi(filenb, phi=0, sub_mean=True, show=['I'], fitparams=None, domain=None, debug=False):
    """
    takes in rabi data, processes it, plots it, and fits it
    :param filenb: filenumber
    :param phi: desired iq rotation
    :param sub_mean: boolean, if you want to subract mean off data
    :param show: array of strings, whether you want to fit to I or Q or both
    :param fitparams: array of starting values for parameters
    :param domain: domain over which you want to fit, ie [1000, 2000]
    :param debug: boolean, prints out all experient parameters
    """

    # if you use gaussian pulses for Rabi, the time that you plot is the sigma -the actual pulse time is 4*sigma (4 being set in the code
    SIGMA_CUTOFF = 4

    expt_name = "rabi"
    filename = "..\\data\\" + str(filenb).zfill(5) + "_" + expt_name.lower() + ".h5"
    with File(filename, 'r') as a:
        #####IMPORT STUFF#####
        hardware_cfg = (json.loads(a.attrs['hardware_cfg']))
        experiment_cfg = (json.loads(a.attrs['experiment_cfg']))
        quantum_device_cfg = (json.loads(a.attrs['quantum_device_cfg']))
        expt_params = experiment_cfg[expt_name.lower()]

        pulse_type = expt_params['pulse_type']
        amp = expt_params['amp']

        on_qb = expt_params['on_qubits'][0]
        params = get_params(hardware_cfg, experiment_cfg, quantum_device_cfg, on_qb)
        readout_params = params['readout_params']
        ran = params['ran'] # range of DAC card for processing
        readout_f = params['readout_freq']
        dig_atten_qb = params['dig_atten_qb']
        dig_atten_rd = params['dig_atten_rd']
        read_lo_pwr = params['read_lo_pwr']
        qb_lo_pwr = params['qb_lo_pwr']
        nu_q = params['qb_freq']


        ####GET IQ #####
        I_raw = array(a["I"])
        Q_raw = array(a["Q"])
        (I, Q, mag, phase) = iq_process(f, I_raw, Q_raw, ran, phi, sub_mean)
        t = arange(expt_params['start'], expt_params['stop'], expt_params['step'])[:(len(I))]
        if pulse_type == "gauss":
            t = t * 4

        if debug:
            print("DEBUG")
            print("averages =", expt_params['acquisition_num'])
            print("Rd LO pwr= ", read_lo_pwr, "dBm")
            print("Qb LO pwr= ", qb_lo_pwr, "dBm")
            print("Rd atten= ", dig_atten_rd, "dB")
            print("Qb atten= ", dig_atten_qb, "dB")
            print("Readout params", readout_params)
            print("experiment params", expt_params)

            #####PLOT####
        title = expt_name + '$, \\nu_q$ = ' + str(around(nu_q, 3)) + ' GHz ' + 'amp = ' + str(amp)
        fig = plt.figure(figsize=(14, 5))
        ax = fig.add_subplot(111, title=title)
        for s in show:
            if s == "Q":
                ax.plot(t, eval(s), 'ro-', label=s)
            else:
                ax.plot(t, eval(s), 'bo-', label=s)
            ax.set_xlabel('Time (ns)')
            ax.set_ylabel(s + " (V)")

            ####FIT AND ANALYZE###
            p = fitdecaysin(t, eval(s), showfit=False, fitparams=fitparams, domain=domain)
            ax.plot(t, decaysin3(p, t), 'k-', label="fit")

            t_pi = 1 / (2 * p[1])
            t_half_pi = 1 / (4 * p[1])
            ax.axvline(t_pi, color='k', linestyle='dashed')
            ax.axvline(t_half_pi, color='k', linestyle='dashed')

            print("ANALYSIS " + s)
            if pulse_type == 'gauss':
                print("pulse type is GAUSS! pi_len in sigma to input into code to get right pulse out is:")
                print("Half pi length in sigma =", t_half_pi / 4, "sigma")
                print("pi length in sigma =", t_pi / 4, "sigma")
                print("\n")

            print("Half pi length in ns =", t_half_pi, "ns")
            print("pi length =", t_pi, "ns")
            print("suggested_pi_length = ", int(t_pi) + 1, "    suggested_pi_amp = ",
                  amp * (t_pi) / float(int(t_pi) + 1))
            print("Rabi decay time = ", p[3], "ns")
            if debug:
                print(p)

        ax.legend()
        plt.show()


def t1(filenb, phi=0, sub_mean=True, show=['I'], fitparams=None, domain=None, debug=False):
    """
    takes in t1 data, processes it, plots it, and fits it
    :param filenb: filenumber
    :param phi: desired iq rotation
    :param sub_mean: boolean, if you want to subract mean off data
    :param show: array of strings, whether you want to fit to I or Q or both
    :param fitparams: array of starting values for parameters
    :param domain: domain over which you want to fit, ie [1000, 2000]
    :param debug: boolean, prints out all experient parameters
    """

    expt_name = "t1"
    filename = "..\\data\\" + str(filenb).zfill(5) + "_" + expt_name.lower() + ".h5"
    with File(filename, 'r') as a:
        hardware_cfg = (json.loads(a.attrs['hardware_cfg']))
        experiment_cfg = (json.loads(a.attrs['experiment_cfg']))
        quantum_device_cfg = (json.loads(a.attrs['quantum_device_cfg']))
        expt_params = experiment_cfg[expt_name.lower()]

        on_qb = expt_params['on_qubits'][0]
        params = get_params(hardware_cfg, experiment_cfg, quantum_device_cfg, on_qb)
        readout_params = params['readout_params']
        ran = params['ran']  # range of DAC card for processing
        readout_f = params['readout_freq']
        dig_atten_qb = params['dig_atten_qb']
        dig_atten_rd = params['dig_atten_rd']
        read_lo_pwr = params['read_lo_pwr']
        qb_lo_pwr = params['qb_lo_pwr']
        nu_q = params['qb_freq']

        I_raw = array(a["I"])
        Q_raw = array(a["Q"])
        (I, Q, mag, phase) = iq_process(f, I_raw, Q_raw, ran, phi, sub_mean)
        t = arange(expt_params['start'], expt_params['stop'], expt_params['step'])[:(len(I))]

        if debug:
            print("DEBUG")
            print("averages =", expt_params['acquisition_num'])
            print("Rd LO pwr= ", read_lo_pwr, "dBm")
            print("Qb LO pwr= ", qb_lo_pwr, "dBm")
            print("Rd atten= ", dig_atten_rd, "dB")
            print("Qb atten= ", dig_atten_qb, "dB")
            print("Readout params", readout_params)
            print("experiment params", expt_params)

            ####PLOT####
        title = expt_name + '$, \\nu_q$ = ' + str(around(nu_q, 3)) + ' GHz '
        fig = plt.figure(figsize=(14, 5))
        ax = fig.add_subplot(111, title=title)
        t = t / 1000  # convert to us
        for s in show:
            if s == "Q":
                ax.plot(t, eval(s), 'ro-', label=s)
            else:
                ax.plot(t, eval(s), 'bo-', label=s)
            ax.set_xlabel('Time (us)')
            ax.set_ylabel(s + " (V)")

            ####ANALYZE
            p = fitexp(t, eval(s), fitparams=fitparams, domain=domain, showfit=False)
            T1 = p[3]
            ax.plot(t, expfunc(p, t), 'k-', label='fit')
            print("ANALYSIS " + s)
            print("T1  =", p[3], "us")
            if debug:
                print(p)

        ax.legend()
        plt.show()


def ramsey(filenb, phi=0, sub_mean=True, show=['I'], fitparams=None, domain=None, debug=False):
    """
    takes in ramsey data, processes it, plots it, and fits it
    :param filenb: filenumber
    :param phi: desired iq rotation
    :param sub_mean: boolean, if you want to subract mean off data
    :param show: array of strings, whether you want to fit to I or Q or both
    :param fitparams: array of starting values for parameters
    :param domain: domain over which you want to fit, ie [1000, 2000]
    :param debug: boolean, prints out all experient parameters
    """
    expt_name = 'ramsey'
    filename = "..\\data\\" + str(filenb).zfill(5) + "_" + expt_name.lower() + ".h5"
    with File(filename, 'r') as a:
        hardware_cfg = (json.loads(a.attrs['hardware_cfg']))
        experiment_cfg = (json.loads(a.attrs['experiment_cfg']))
        quantum_device_cfg = (json.loads(a.attrs['quantum_device_cfg']))
        expt_params = experiment_cfg[expt_name.lower()]

        ramsey_freq = expt_params['ramsey_freq'] * 1e3

        on_qb = expt_params['on_qubits'][0]
        params = get_params(hardware_cfg, experiment_cfg, quantum_device_cfg, on_qb)
        readout_params = params['readout_params']
        ran = params['ran']  # range of DAC card for processing
        readout_f = params['readout_freq']
        dig_atten_qb = params['dig_atten_qb']
        dig_atten_rd = params['dig_atten_rd']
        read_lo_pwr = params['read_lo_pwr']
        qb_lo_pwr = params['qb_lo_pwr']
        nu_q = params['qb_freq']

        I_raw = array(a["I"])
        Q_raw = array(a["Q"])
        (I, Q, mag, phase) = iq_process(f, I_raw, Q_raw, ran, phi, sub_mean)
        t = arange(expt_params['start'], expt_params['stop'], expt_params['step'])[:(len(I))]

        if debug:
            print("DEBUG")
            print("averages =", expt_params['acquisition_num'])
            print("Rd LO pwr= ", read_lo_pwr, "dBm")
            print("Qb LO pwr= ", qb_lo_pwr, "dBm")
            print("Rd atten= ", dig_atten_rd, "dB")
            print("Qb atten= ", dig_atten_qb, "dB")
            print("Readout params", readout_params)
            print("experiment params", expt_params)

        title = expt_name + '$, \\nu_q$ = ' + str(around(nu_q, 3)) + ' GHz '
        fig = plt.figure(figsize=(14, 5))
        ax = fig.add_subplot(111, title=title)
        t = t / 1000

        for s in show:
            if s == "Q":
                ax.plot(t, eval(s), 'ro-', label=s)
            else:
                ax.plot(t, eval(s), 'bo-', label=s)
            ax.set_xlabel('Time ($\mu$s)')
            ax.set_ylabel(s + " (V)")

            ######ANALYZE
            # p = fitdecaysin(t[3:],s[3:],fitparams = fitparams, domain = domain, showfit=False)
            p = fitdecaysin(t, eval(s), fitparams=fitparams, domain=domain, showfit=False)
            ax.plot(t, decaysin3(p, t), 'k-', label='fit')

            offset = ramsey_freq - p[1]
            nu_q_new = nu_q + offset * 1e-3

            print("ANALYSIS")
            print("Original qubit frequency choice =", nu_q, "GHz")
            print("ramsey freq = ", ramsey_freq, "MHz")
            print("Oscillation freq = ", p[1], " MHz")
            print("Offset freq between data and ramsey =", offset, "MHz")
            print("Suggested qubit frequency choice =", nu_q_new, "GHz")
            print("T2* =", p[3], "us")
        ax.legend()
        plt.show()


def echo(filenb, phi=0, sub_mean=True, show=['I'], fitparams=None, domain=None, debug=False):
    """
    takes in echo data, processes it, plots it, and fits it
    :param filenb: filenumber
    :param phi: desired iq rotation
    :param sub_mean: boolean, if you want to subract mean off data
    :param show: array of strings, whether you want to fit to I or Q or both
    :param fitparams: array of starting values for parameters
    :param domain: domain over which you want to fit, ie [1000, 2000]
    :param debug: boolean, prints out all experient parameters
    """
    expt_name = 'echo'
    filename = "..\\data\\" + str(filenb).zfill(5) + "_" + expt_name.lower() + ".h5"
    with File(filename, 'r') as a:
        hardware_cfg = (json.loads(a.attrs['hardware_cfg']))
        experiment_cfg = (json.loads(a.attrs['experiment_cfg']))
        quantum_device_cfg = (json.loads(a.attrs['quantum_device_cfg']))
        expt_params = experiment_cfg[expt_name.lower()]

        ramsey_freq = expt_params['ramsey_freq'] * 1e3

        on_qb = expt_params['on_qubits'][0]
        params = get_params(hardware_cfg, experiment_cfg, quantum_device_cfg, on_qb)
        readout_params = params['readout_params']
        ran = params['ran']  # range of DAC card for processing
        readout_f = params['readout_freq']
        dig_atten_qb = params['dig_atten_qb']
        dig_atten_rd = params['dig_atten_rd']
        read_lo_pwr = params['read_lo_pwr']
        qb_lo_pwr = params['qb_lo_pwr']
        nu_q = params['qb_freq']

        I_raw = array(a["I"])
        Q_raw = array(a["Q"])
        (I, Q, mag, phase) = iq_process(f, I_raw, Q_raw, ran, phi, sub_mean)
        t = arange(expt_params['start'], expt_params['stop'], expt_params['step'])[:(len(I))]

        if debug:
            print("DEBUG")
            print("averages =", expt_params['acquisition_num'])
            print("Rd LO pwr= ", read_lo_pwr, "dBm")
            print("Qb LO pwr= ", qb_lo_pwr, "dBm")
            print("Rd atten= ", dig_atten_rd, "dB")
            print("Qb atten= ", dig_atten_qb, "dB")
            print("Readout params", readout_params)
            print("experiment params", expt_params)

        title = expt_name + '$, \\nu_q$ = ' + str(around(nu_q, 3)) + ' GHz '
        fig = plt.figure(figsize=(14, 5))
        ax = fig.add_subplot(111, title=title)
        t = t / 1000

        for s in show:
            if s == "Q":
                ax.plot(t, eval(s), 'ro-', label=s)
            else:
                ax.plot(t, eval(s), 'bo-', label=s)
            ax.set_xlabel('Time ($\mu$s)')
            ax.set_ylabel(s + " (V)")

            ######ANALYZE
            # p = fitdecaysin(t[3:],s[3:],fitparams = fitparams, domain = domain, showfit=False)
            p = fitdecaysin(t, eval(s), fitparams=fitparams, domain=domain, showfit=False)
            print(p)
            ax.plot(t, decaysin3(p, t), 'k-', label='fit')

            offset = ramsey_freq - p[1]
            nu_q_new = nu_q + offset * 1e-3

            print("ANALYSIS")
            print("Original qubit frequency choice =", nu_q, "GHz")
            print("ramsey freq = ", ramsey_freq, "MHz")
            print("Oscillation freq = ", p[1], " MHz")
            print("Offset freq between data and ramsey =", offset, "MHz")
            print("Suggested qubit frequency choice =", nu_q_new, "GHz")
            print("Echo experiment: CP = ", expt_params['cp'], "CPMG = ", expt_params['cpmg'])
            print("Number of echoes = ", expt_params['echo_times'])
            print("T2 =", p[3], "us")
        ax.legend()
        plt.show()


def twotoneanalysis(fname):
    with SlabFile(fname) as f:
        magnitudedata = True
        phasedata = True
        rfreqpts = f['fpts-r'][:]
        rmagpts = f['mags-r'][:]
        rphasepts = f['phases-r'][:]
        qfreqpts = f['fpts-q'][:]
        qmagpts = f['mags-q'][:]
        qphasepts = f['phases-q'][:]
        tempstr = 'flux%s_actual_pts' % fname[-4]
        fluxpts = f[tempstr][:]
        # fluxpts = f['flux0_actual_pts'][:]
        fluxpts = fluxpts * 10 ** 3

        def padder(axis):
            paddedaxis = np.zeros(np.size(axis) + 1)
            diff = axis[1] - axis[0]
            for ii, elem in enumerate(axis):
                paddedaxis[ii] = elem
            paddedaxis[-1] = axis[-1] + diff
            return paddedaxis

        padrfreqpts = padder(rfreqpts[0])
        padqfreqpts = padder(qfreqpts[0])
        padfluxpts = padder(fluxpts)

        qmagptsnew = np.zeros(np.shape(qmagpts))

        refpt = qmagpts[0, 0]
        for i in range(np.size(qmagpts[:, 0])):
            qmagptsnew[i, :] = qmagpts[i, :]
            qmagptsnew[i, :] = savgol_filter(qmagptsnew[i, :], 101, 9)
            delta = np.average(qmagptsnew[i, 0:2000])
            qmagptsnew[i, :] = qmagptsnew[i, :] - delta
        for ii, current in enumerate(fluxpts):
            rphasepts[ii] = rphasepts[ii] * (np.pi / 180)
            rphasepts[ii] = np.unwrap(rphasepts[ii], np.pi - np.pi * .0001)
            mr, br = np.polyfit(rfreqpts[ii, 100:200], rphasepts[ii, 100:200], 1)
            rphasepts[ii] = (rphasepts[ii] - (rfreqpts[ii] * mr + br))
            delta = np.average(rphasepts[ii, 0:10]) - np.pi
            rphasepts[ii] = rphasepts[ii] - delta
        for ii, current in enumerate(fluxpts):
            qphasepts[ii] = qphasepts[ii] * (np.pi / 180)
            delta = np.average(qphasepts[ii, 0:20]) - np.pi
            qphasepts[ii] = qphasepts[ii] - delta
            mq, bq = np.polyfit(qfreqpts[ii, 10:-10], qphasepts[ii, 10:-10], 1)
            qphasepts[ii] = (qphasepts[ii] - (qfreqpts[ii] * mq + bq))
            #             delta = np.average(qphasepts[ii,0:20])-np.pi
            #             qphasepts[ii] = (qphasepts[ii] - delta)%(2*np.pi)
            qphasepts[ii] = savgol_filter(qphasepts[ii], 51, 3)

        start = 1
        stop = -1
        # plot mag vs freq single tone
        figure(figsize=(15, 4))
        subplot(111, title='S21 R%s' % (fname[-4]) + ' Single-Tone mag data', xlabel='Frequency (GHz)',
                ylabel='magnitude (dBm)')
        for ii, current in enumerate(fluxpts):
            print("Min peak at {}".format(rfreqpts[ii][np.argmin(rmagpts[ii])]))
            plt.plot(rfreqpts[ii], rmagpts[ii], label='Voltage (mV): %s' % (current))
        plt.show()
        # plot mag vs freq for all currents all on same graph
        figure(figsize=(15, 4))
        subplot(111, title='S21 R%s' % (fname[-4]) + ' Two-Tone mag data', xlabel='Frequency (GHz)',
                ylabel='magnitude (dBm)')
        for ii, current in enumerate(fluxpts):
            print("Max peak at {}".format(qfreqpts[ii][start:stop][np.argmax(qmagptsnew[ii][start:stop])]))
            plt.plot(qfreqpts[ii][start:stop], qmagptsnew[ii][start:stop], label='Voltage (mV): %s' % (current))
        plt.show()
        # plot phase vs freq for all currents all on same graph
        figure(figsize=(15, 4))
        subplot(111, title='S21 R%s' % (fname[-4]) + ' Two-Tone phase data', xlabel='Frequency (GHz)',
                ylabel='phase shift (rad)')
        for ii, current in enumerate(fluxpts):
            plt.plot(qfreqpts[ii][start:stop], qphasepts[ii][start:stop])
        plt.show()

        # Plot mag,phase for each current value
        #         for ii,current in enumerate(fluxpts):
        #             figure(figsize=(15,2*4))
        #             ax1=plt.subplot(211,title='S11 R1 Two-Tone phase data MAG')
        #             ax1.plot(qfreqpts[ii][start:stop],qmagptsnew[ii][start:stop],label = 'CURRENT: %s'%(str(current)))
        #             print('FLUX: ' + str(current) + ' QUBIT FREQ: ' + str(qfreqpts[ii][start:stop][np.argmax(qmagptsnew[ii][start:stop])]))
        #             ax2 = plt.subplot(212,title='S11 R1 Two-Tone phase data PHASE',xlabel='Frequency (GHz)',sharex=ax1)
        #             ax2.plot(qfreqpts[ii][start:stop],qphasepts[ii][start:stop])
        #             plt.show()

        figure(figsize=(15, 4))
        subplot(111, title='S21 Two-Tone magnitude data for Q %s' % fname[-4], xlabel='Frequency (GHz)',
                ylabel='Voltage (mV)')
        plt.pcolor(padqfreqpts, padfluxpts, qmagpts, cmap='RdBu')
        plt.show()

        figure(figsize=(15, 4))
        subplot(111, title='S21 Two-Tone phase data for Q %s' % fname[-4], xlabel='Frequency (GHz)',
                ylabel='Voltage (mV)')
        plt.pcolor(padqfreqpts, padfluxpts, qphasepts, cmap='RdBu')
        plt.show()

        ## plot qubit peaks vs current
        qmagpeaks = []
        qphasepeaks = []
        for ii, current in enumerate(fluxpts):
            qmagpeaks.append(qfreqpts[0][np.argmin(qmagpts[ii])])
            qphasepeaks.append(qfreqpts[0][np.argmin(qphasepts[ii])])

        figure(figsize=(15, 4))
        subplot(111, title='S21 Two-tone qubit peak vs current for Q%s' % fname[-4], xlabel='Voltage (mV)',
                ylabel='Freq (GHz)')
        plt.plot(fluxpts, qmagpeaks, label='mag')
        plt.plot(fluxpts, qphasepeaks, label='phase')
        plt.legend()
        plt.show()

def polynomial(p,x):
    return p[0]+p[1]*(x-p[-1])+p[2]*(x-p[-1])**2+p[3]*(x-p[-1])**3+p[4]*(x-p[-1])**4+p[5]*(x-p[-1])**5+p[6]*(x-p[-1])**6+p[7]*(x-p[-1])**7+p[8]*(x-p[-1])**8+p[9]*(x-p[-1])**9

def fitpolynomial(xdata,ydata,fitparams=None,domain=None,showfit=False,showstartfit=False,label=""):
    if domain is not None:
        fitdatax,fitdatay = selectdomain(xdata,ydata,domain)
    else:
        fitdatax=xdata
        fitdatay=ydata

        fitparams=[0,0,0,0,0,0,0,0,0,0,0,0]

    p1 = fitgeneral(fitdatax,fitdatay,polynomial,fitparams,domain=None,showfit=showfit,showstartfit=showstartfit,label=label)
    return p1

def invertedcos(p,x):
    return p[0]+p[1]/cos(p[2]*x-p[-1])

def fitinvertedcos(xdata,ydata,fitparams=None,domain=None,showfit=False,showstartfit=False,label=""):
    if domain is not None:
        fitdatax,fitdatay = selectdomain(xdata,ydata,domain)
    else:
        fitdatax=xdata
        fitdatay=ydata

        fitparams=[0,0,0,0,0,0,0,0,0,0,0,0]

    p1 = fitgeneral(fitdatax,fitdatay,invertedcos,fitparams,domain=None,showfit=showfit,showstartfit=showstartfit,label=label)
    return p1


# qubit H
def hamiltonian(Ec, Ej, d, flux, N=100):
    """
    Return the charge qubit hamiltonian as a Qobj instance.
    """
    m = np.diag(4 * Ec * (arange(-N, N + 1)) ** 2) - Ej * (cos(pi * flux) * 0.5 * (np.diag(np.ones(2 * N), -1) +
                                                                                   np.diag(np.ones(2 * N), 1)) +
                                                           1j * d * sin(pi * flux) * 0.5 * (
                                                                       np.diag(np.ones(2 * N), -1) -
                                                                       np.diag(np.ones(2 * N), 1)))
    return Qobj(m)


# JC H
def jc_hamiltonian(f_c, f_qs, g, flux, N_r=5, N_q=5):
    f_q = Qobj(diag(f_qs[0:N_q] - f_qs[0]))
    a = tensor(destroy(N_r), qeye(N_q))
    b = tensor(qeye(N_r), destroy(N_q))
    H = f_c * a.dag() * a + tensor(qeye(N_r), f_q) + g * (a.dag() + a) * (b.dag() + b)
    return Qobj(H)

def plot_energies(ng_vec, energies, ymax=(20, 3), ymin=(0,0)):
    """
    Plot energy levels as a function of bias parameter ng_vec.
    """
    fig, axes = plt.subplots(1,2, figsize=(16,6))

    for n in range(len(energies[0,:])):
        axes[0].plot(ng_vec, (energies[:,n]-energies[:,0])/(2*pi))
    axes[0].set_ylim(ymin[0], ymax[0])
    axes[0].set_xlabel(r'$flux$', fontsize=18)
    axes[0].set_ylabel(r'$E_n$', fontsize=18)

    for n in range(len(energies[0,:])):
        axes[1].plot(ng_vec, (energies[:,n]-energies[:,0])/(energies[:,1]-energies[:,0]))
    axes[1].set_ylim(ymin[1], ymax[1])
    axes[1].set_xlabel(r'$flux$', fontsize=18)
    axes[1].set_ylabel(r'$(E_n-E_0)/(E_1-E_0)$', fontsize=18)
    return fig, axes

def plot_energies_v2(ng_vec, energies, ymax=(20, 3), ymin=(0,0)):
    """
    Plot energy levels as a function of bias parameter ng_vec.
    """

    for n in range(len(energies[0,:])):
        plt.plot(ng_vec, (energies[:,n]-energies[:,0])/(2*pi),'--',linewidth=1)
    plt.ylim(ymin[0], ymax[0])
    plt.xlabel(r'$flux$', fontsize=20)
    plt.ylabel(r'$E_n$', fontsize=20)


def closest(lst, K):
    lst = np.asarray(lst)
    idx = (np.abs(lst - K)).argmin()
    return lst[idx]


def twotoneHJC(fname, details=True):
    with SlabFile(fname) as f:
        rfreqpts = f['fpts-r'][:]
        rmagpts = f['mags-r'][:]
        rphasepts = f['phases-r'][:]
        qfreqpts = f['fpts-q'][:]
        qmagpts = f['mags-q'][:]
        qphasepts = f['phases-q'][:]
        tempstr = 'flux%s_actual_pts' % fname[-4]
        fluxpts = f[tempstr][:]
        fluxpts = fluxpts * 10 ** 3

        def padder(axis):
            paddedaxis = np.zeros(np.size(axis) + 1)
            diff = axis[1] - axis[0]
            for ii, elem in enumerate(axis):
                paddedaxis[ii] = elem
            paddedaxis[-1] = axis[-1] + diff
            return paddedaxis

        padrfreqpts = padder(rfreqpts[0])
        padqfreqpts = padder(qfreqpts[0])
        padfluxpts = padder(fluxpts)
        qmagptsnew = np.zeros(np.shape(qmagpts))
        refpt = qmagpts[0, 0]
        for i in range(np.size(qmagpts[:, 0])):
            qmagptsnew[i, :] = qmagpts[i, :]
            qmagptsnew[i, :] = savgol_filter(qmagptsnew[i, :], 11, 3)
            delta = np.average(qmagptsnew[i, 0:2000])
            qmagptsnew[i, :] = qmagptsnew[i, :] - delta
        for ii, current in enumerate(fluxpts):
            rphasepts[ii] = rphasepts[ii] * (np.pi / 180)
            rphasepts[ii] = np.unwrap(rphasepts[ii], np.pi - np.pi * .0001)
            mr, br = np.polyfit(rfreqpts[ii, 100:200], rphasepts[ii, 100:200], 1)
            rphasepts[ii] = (rphasepts[ii] - (rfreqpts[ii] * mr + br))
            delta = np.average(rphasepts[ii, 0:10]) - np.pi
            rphasepts[ii] = rphasepts[ii] - delta
        for ii, current in enumerate(fluxpts):
            qphasepts[ii] = qphasepts[ii] * (np.pi / 180)
            delta = np.average(qphasepts[ii, 0:20]) - np.pi
            qphasepts[ii] = qphasepts[ii] - delta
            mq, bq = np.polyfit(qfreqpts[ii, 10:-10], qphasepts[ii, 10:-10], 1)
            qphasepts[ii] = (qphasepts[ii] - (qfreqpts[ii] * mq + bq))
            qphasepts[ii] = savgol_filter(qphasepts[ii], 11, 3)

        start = 1
        stop = -1
        # plot mag vs freq single tone

        if details == True:
            figure(figsize=(15, 4))
            subplot(111, title='S21 R%s' % (fname[-4]) + ' Two-Tone mag data', xlabel='Frequency (GHz)',
                    ylabel='magnitude (dBm)')
            for ii, current in enumerate(fluxpts):
                plt.plot(rfreqpts[ii], rmagpts[ii], label='Voltage (mV): %s' % (current))
            plt.show()

        if details == True:
            readout_freqs = []
            for ii, current in enumerate(fluxpts):
                min_freq = rfreqpts[0][np.argmin(rmagpts[ii])]
                readout_freqs.append(min_freq + 750e3)
                print("READOUT : %s" % (readout_freqs[ii]))
                print("FLUX PTS: %s" % (fluxpts[ii]))

        if details == True:
            # plot mag vs freq for all currents all on same graph
            figure(figsize=(15, 4))
            subplot(111, title='S21 R%s' % (fname[-4]) + ' Two-Tone mag data', xlabel='Frequency (GHz)',
                    ylabel='magnitude (dBm)')
            for ii, current in enumerate(fluxpts):
                plt.plot(qfreqpts[ii][start:stop], qmagptsnew[ii][start:stop], label='Voltage (mV): %s' % (current))
            plt.show()
            # plot phase vs freq for all currents all on same graph
            figure(figsize=(15, 4))
            subplot(111, title='S21 R%s' % (fname[-4]) + ' Two-Tone phase data', xlabel='Frequency (GHz)',
                    ylabel='phase shift (rad)')
            for ii, current in enumerate(fluxpts):
                plt.plot(qfreqpts[ii][start:stop], qphasepts[ii][start:stop])
            plt.show()

            figure(figsize=(15, 4))
            subplot(111, title='S21 Two-Tone magnitude data for Q %s' % fname[-4], xlabel='Frequency (GHz)',
                    ylabel='Voltage (mV)')
            plt.pcolor(padqfreqpts, padfluxpts, qmagpts, cmap='RdBu')
            plt.show()

            figure(figsize=(15, 4))
            subplot(111, title='S21 Two-Tone phase data for Q %s' % fname[-4], xlabel='Frequency (GHz)',
                    ylabel='Voltage (mV)')
            plt.pcolor(padqfreqpts, padfluxpts, qphasepts, cmap='RdBu')
            plt.show()

        resminima = []
        qubitpeaks = []
        for ii in np.arange(len(rmagpts)):
            resminima.append(rfreqpts[ii][np.argmin(rmagpts[ii])])
            qubitpeaks.append(qfreqpts[ii][np.argmax(qmagptsnew[ii])])
        if details == True:
            for ii, current in enumerate(fluxpts):
                figure(figsize=(15, 4))
                subplot(111, title='S21 R%s' % (fname[-4]) + ' Two-Tone mag data', xlabel='Frequency (GHz)',
                        ylabel='magnitude (dBm)')
                plt.plot(qfreqpts[ii][start:stop], qmagptsnew[ii][start:stop], label='Voltage (mV): %s' % (current))
                sigma = np.std(qmagptsnew[ii][start:stop])
                peaks, _ = find_peaks(qmagptsnew[ii][start:stop], height=None, prominence=sigma * 6, threshold=None, )
                print(qfreqpts[ii][peaks])
                plt.legend()
                plt.grid(True)
                plt.show()
    return [np.array(fluxpts) / 1e3, resminima, qubitpeaks]


def twotoneHJCfitter(fname, Ec, wqmax, wqmin, fc, g, flxoffset, flxscale, details=True):
    fluxpts, rmin, qpk = twotoneHJC(fname, details=False)
    flux = fluxpts
    Ec = Ec  # 2*pi* 0.250 #GHz
    wq_max_guess = wqmax  # GHz
    wq_min_guess = wqmin  # GHz  # 3.85
    f_c = fc  # 2*pi*6.15735 #GHz
    g = g  # 2*pi*0.074 #GHz

    Q_flux_offset = flxoffset  # -1.640328
    Q_flux_scale = flxscale  # 5.225

    Ej = (2 * pi * wq_max_guess + Ec) ** 2 / 8 / Ec
    d = (wq_min_guess / wq_max_guess) ** 2

    if details == True:
        print('Ec = 2*pi*', Ec / 2 / pi, ' GHz')
        print('Ej = 2*pi*', Ej / 2 / pi, ' GHz')
        print('d = ', d)
        print('Ec/Ej = ', Ej / Ec)

    f_qs_upper = np.asarray(hamiltonian(Ec, Ej, d, flux=0.0).eigenenergies())
    vr_energies_upper = np.asarray(jc_hamiltonian(f_c, f_qs_upper, g, flux=0.0).eigenenergies())

    if details == True:
        print('\nUpper sweet spot:')
        print('cavity freq = ', vr_energies_upper[argmin(abs(vr_energies_upper - f_c))] / 2 / pi, 'GHz')
        print('qubit freq = ', vr_energies_upper[argmin(abs(vr_energies_upper - f_c)) + 1] / 2 / pi, 'GHz')

    f_qs_lower = np.asarray(hamiltonian(Ec, Ej, d, flux=0.5).eigenenergies())
    vr_energies_lower = np.asarray(jc_hamiltonian(f_c, f_qs_lower, g, flux=0.5).eigenenergies())
    if details == True:
        print('\nLower sweet spot:')
        print('cavity freq = ', vr_energies_lower[argmin(abs(vr_energies_lower - f_c))] / 2 / pi, 'GHz')
        print('qubit freq = ', vr_energies_lower[argmin(abs(vr_energies_lower - f_c)) - 1] / 2 / pi, 'GHz')
    flux_vec = np.linspace(-2, 2, 401)

    # qubit energy levels
    energies = np.asarray([hamiltonian(Ec, Ej, d, flux).eigenenergies() for flux in flux_vec])

    # vacuum rabi energy levels
    vr_energies = np.asarray(
        [jc_hamiltonian(f_c, energies[ii], g, flux).eigenenergies() for (ii, flux) in enumerate(flux_vec)])

    #     ng_vec_old = Q_flux_scale*(flux_vec+Q_flux_offset_old/Q_flux_scale)
    ng_vec = Q_flux_scale * (flux_vec + Q_flux_offset / Q_flux_scale)
    energies = vr_energies

    if details == True:
        figure(num=None, figsize=(15, 10), dpi=80, facecolor='w', edgecolor='k')
        for n in range(1, 3):
            omegavsV = scipy.interpolate.interp1d(ng_vec, (energies[:, n] - energies[:, 0]) / (2 * pi), kind='cubic', )
            plt.plot(ng_vec, omegavsV(ng_vec), '--', linewidth=1, label='new_fit')
        plt.ylim(fc / (2 * np.pi) - .001, fc / (2 * np.pi) + .035)
        # plt.xlim(-0.1, 0.1)
        plt.xlabel(r'$flux$', fontsize=20)
        plt.ylabel(r'$E_n$', fontsize=20)
        plt.legend()
    else:
        for n in range(1, 3):
            omegavsV = scipy.interpolate.interp1d(ng_vec, (energies[:, n] - energies[:, 0]) / (2 * pi), kind='cubic', )
    if details == True:
        print('FLX: ')
        print(flux)
        print('rmin')
        print(rmin)
    if details == True:
        plt.scatter(np.array(flux), np.array(rmin) / 1e9, marker='o', s=5)
        figure(num=None, figsize=(15, 10), dpi=80, facecolor='w', edgecolor='k')
        for n in range(1, 3):
            omegavsV = scipy.interpolate.interp1d(ng_vec, (energies[:, n] - energies[:, 0]) / (2 * pi), kind='cubic', )
            plt.plot(ng_vec, omegavsV(ng_vec), '--', linewidth=1, label='new_fit')
        plt.ylim(4.1, 6.0)
        # plt.xlim(-0.1, 0.1)
        plt.xlabel(r'$flux$', fontsize=20)
        plt.ylabel(r'$E_n$', fontsize=20)
        plt.legend()
    else:
        for n in range(1, 3):
            omegavsV = scipy.interpolate.interp1d(ng_vec, (energies[:, n] - energies[:, 0]) / (2 * pi), kind='cubic', )

    if details == True:
        plt.scatter(np.array(flux), np.array(qpk) / 1e9, marker='o', s=5)

    energylist = (energies[:, 1] - energies[:, 0]) / (2 * np.pi)
    reslist = (energies[:, 2] - energies[:, 0]) / (2 * np.pi)
    voltlist = Q_flux_scale * (flux_vec + Q_flux_offset / Q_flux_scale)
    flxquantalist = voltlist / Q_flux_scale
    print('startpt for Voltage branch cut: ')
    startpt = np.argmin(np.abs(voltlist))
    print(startpt)

    lss = closest(argrelextrema(energylist, np.less)[0], startpt)
    uss = closest(argrelextrema(energylist, np.greater)[0], startpt)

    if lss > uss:
        temp = lss
        lss = uss
        uss = temp
    if details == True:
        print("Lower cut: ")
        print(lss)
        print("lower voltage:")
        print(voltlist[lss])
        print("lower energy:")
        print(energylist[lss])
        print("Upper cut: ")
        print(uss)
        print("Upper voltage: ")
        print(voltlist[uss])
        print('Upper energy: ')
        print(energylist[uss])

    if details == True:
        plt.figure(figsize=(12, 8))
        plt.plot(energylist[lss:uss], flxquantalist[lss:uss])
        plt.xlabel('frequency(GHz)')
        plt.ylabel('Bias (Flx Qnta)')
        plt.title('Inverse bias function')
        plt.show()

    #     energylistQ = energylist[lss:uss]
    #     voltlistQ = voltlist[lss:uss]
    #     flxquantalistQ = flxquantalist[lss:uss]

    reslistQ = reslist[lss:uss]
    energylistQ = energylist[lss:uss]
    voltlistQ = voltlist[lss:uss]
    flxquantalistQ = flxquantalist[lss:uss]

    return [reslistQ, energylistQ, voltlistQ, flxquantalistQ]


def HJCinterpolation(fname, Ec, wqmax, wqmin, fc, g, flxoffset, flxscale, details=True):
    fluxpts, rmin, qpk = twotoneHJC(fname, details=details)
    flux = fluxpts
    Ec = Ec  # 2*pi* 0.250 #GHz
    wq_max_guess = wqmax  # GHz
    wq_min_guess = wqmin  # GHz  # 3.85
    f_c = fc  # 2*pi*6.15735 #GHz
    g = g  # 2*pi*0.074 #GHz

    Q_flux_offset = flxoffset  # -1.640328
    Q_flux_scale = flxscale  # 5.225

    Ej = (2 * pi * wq_max_guess + Ec) ** 2 / 8 / Ec
    d = (wq_min_guess / wq_max_guess) ** 2

    f_qs_upper = np.asarray(hamiltonian(Ec, Ej, d, flux=0.0).eigenenergies())
    vr_energies_upper = np.asarray(jc_hamiltonian(f_c, f_qs_upper, g, flux=0.0).eigenenergies())

    f_qs_lower = np.asarray(hamiltonian(Ec, Ej, d, flux=0.5).eigenenergies())
    vr_energies_lower = np.asarray(jc_hamiltonian(f_c, f_qs_lower, g, flux=0.5).eigenenergies())
    flux_vec = np.linspace(-5, 5, 1001)

    # qubit energy levels
    energies = np.asarray([hamiltonian(Ec, Ej, d, flux).eigenenergies() for flux in flux_vec])

    # vacuum rabi energy levels
    vr_energies = np.asarray(
        [jc_hamiltonian(f_c, energies[ii], g, flux).eigenenergies() for (ii, flux) in enumerate(flux_vec)])

    #     ng_vec_old = Q_flux_scale*(flux_vec+Q_flux_offset_old/Q_flux_scale)
    ng_vec = Q_flux_scale * (flux_vec + Q_flux_offset / Q_flux_scale)
    energies = vr_energies

    for n in range(1, 2):
        omegavsV = scipy.interpolate.interp1d(ng_vec, (energies[:, n] - energies[:, 0]) / (2 * pi), kind='cubic', )

    energylist = (energies[:, 1] - energies[:, 0]) / (2 * np.pi)
    voltlist = Q_flux_scale * (flux_vec + Q_flux_offset / Q_flux_scale)
    flxquantalist = voltlist / Q_flux_scale
    startpt = np.argmin(np.abs(voltlist))

    energylistQ = energylist
    voltlistQ = voltlist
    flxquantalistQ = flxquantalist

    return [energylistQ, voltlistQ, flxquantalistQ]