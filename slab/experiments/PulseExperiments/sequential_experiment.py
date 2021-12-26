from slab.experiments.PulseExperiments.sequences import PulseSequences
from slab.experiments.PulseExperiments.pulse_experiment import Experiment
import numpy as np
import os
import time
from tqdm import tqdm
import json
from slab.dataanalysis import get_next_filename
from slab.dataanalysis import get_current_filename
from slab.datamanagement import SlabFile
from slab.dsfit import fitdecaysin

from skopt import Optimizer

from slab.experiments.PulseExperiments.get_data import get_singleshot_data_two_qubits_4_calibration_v2,\
    get_singleshot_data_two_qubits, data_to_correlators, two_qubit_quantum_state_tomography,\
    density_matrix_maximum_likelihood

import pickle


def get_iq(expt_data, expt_pts, td=0):
    data_cos_list = []
    data_sin_list = []

    for data, pt in zip(expt_data, expt_pts):
        cos = np.cos(2 * np.pi * pt * (alazar_time_pts - td))
        sin = np.sin(2 * np.pi * pt * (alazar_time_pts - td))
        # td controls the phases. Try different td in get_iq to mitigate phase fringes.

        data_cos = np.dot(data, cos) / len(cos)
        data_sin = np.dot(data, sin) / len(sin)

        data_cos_list.append(data_cos)
        data_sin_list.append(data_sin)

    plt.figure(figsize=(10, 4))
    plt.plot(expt_pts, data_cos_list, label='I')
    plt.plot(expt_pts, data_sin_list, label='Q')

    #     plt.xlim(-0.2,-0.05)
    #     plt.ylim(-0.005, 0.005)

    plt.legend()


def get_iq_data(expt_data, het_freq=0.148, td=0, pi_cal=False):
    data_cos_list = []
    data_sin_list = []

    alazar_time_pts = np.arange(len(np.array(expt_data)[0]))
    #     alazar_time_pts = np.arange(len(np.array(expt_data))) # Quick hack, needs to be fixed

    for data in expt_data:
        cos = np.cos(2 * np.pi * het_freq * (alazar_time_pts - td))
        sin = np.sin(2 * np.pi * het_freq * (alazar_time_pts - td))

        data_cos = np.dot(data, cos) / len(cos)
        data_sin = np.dot(data, sin) / len(sin)

        data_cos_list.append(data_cos)
        data_sin_list.append(data_sin)

    data_cos_list = np.array(data_cos_list)
    data_sin_list = np.array(data_sin_list)

    if pi_cal:

        ge_cos = data_cos_list[-1] - data_cos_list[-2]
        ge_sin = data_sin_list[-1] - data_sin_list[-2]

        ge_mean_vec = np.array([ge_cos, ge_sin])

        data_cos_sin_list = np.array([data_cos_list[:-2] - data_cos_list[-2], data_sin_list[:-2] - data_sin_list[-2]])

        data_list = np.dot(ge_mean_vec, data_cos_sin_list) / np.dot(ge_mean_vec, ge_mean_vec)


    else:
        cos_contrast = np.abs(np.max(data_cos_list) - np.min(data_cos_list))
        sin_contrast = np.abs(np.max(data_sin_list) - np.min(data_sin_list))

        if cos_contrast > sin_contrast:
            data_list = data_cos_list
        else:
            data_list = data_sin_list

    return data_cos_list, data_sin_list, data_list


def get_singleshot_data(expt_data, het_ind, pi_cal=False):
    data_cos_list = expt_data[het_ind][0]
    data_sin_list = expt_data[het_ind][1]

    if pi_cal:

        ge_cos = np.mean(data_cos_list[-1]) - np.mean(data_cos_list[-2])
        ge_sin = np.mean(data_sin_list[-1]) - np.mean(data_sin_list[-2])

        ge_mean_vec = np.array([ge_cos, ge_sin])

        data_cos_sin_list = np.array([data_cos_list[:-2] - np.mean(data_cos_list[-2]),
                                      data_sin_list[:-2] - np.mean(data_sin_list[-2])])

        data_cos_sin_list = np.transpose(data_cos_sin_list, (1, 0, 2))

        data_list = np.dot(ge_mean_vec, data_cos_sin_list) / np.dot(ge_mean_vec, ge_mean_vec)


    else:
        cos_contrast = np.abs(np.max(data_cos_list) - np.min(data_cos_list))
        sin_contrast = np.abs(np.max(data_sin_list) - np.min(data_sin_list))

        if cos_contrast > sin_contrast:
            data_list = data_cos_list
        else:
            data_list = data_sin_list

    return data_cos_list, data_sin_list, data_list


def subtract_mean(data):
    data1 = data.T
    data1 = (data1 - np.mean(data1, axis=0))
    return (data1.T)


def calibrate_ramsey(a, pi_length=100, t2=1000):
    quantum_device_cfg = json.loads(a.attrs['quantum_device_cfg'])
    experiment_cfg = json.loads(a.attrs['experiment_cfg'])
    hardware_cfg = json.loads(a.attrs['hardware_cfg'])

    expt_cfg = experiment_cfg['ramsey_while_flux']
    expt_pts = np.arange(expt_cfg['start'], expt_cfg['stop'], expt_cfg['step'])
    on_qubits = expt_cfg['on_qubits']

    for qubit_id in on_qubits:

        expt_avg_data = np.array(a['expt_avg_data_ch%s' % qubit_id])

        fitguess = [max(expt_avg_data) / 2 - min(expt_avg_data) / 2, 1 / (2 * pi_length), 0, t2, \
                    max(expt_avg_data) / 2 + min(expt_avg_data) / 2]
        fitdata = fitdecaysin(expt_pts, expt_avg_data, fitparams=fitguess, showfit=True)

        if expt_cfg['use_freq_amp_halfpi'][0]:
            qubit_freq = expt_cfg['use_freq_amp_halfpi'][1]
        else:
            qubit_freq = quantum_device_cfg['qubit']['%s' % qubit_id]['freq']
        ramsey_freq = experiment_cfg['ramsey_while_flux']['ramsey_freq']

        real_qubit_freq = qubit_freq + ramsey_freq - fitdata[1]
        possible_qubit_freq = qubit_freq + ramsey_freq + fitdata[1]

        if abs(real_qubit_freq-qubit_freq)<abs(possible_qubit_freq-qubit_freq):
            freq_guess = real_qubit_freq
        else:
            freq_guess = possible_qubit_freq

        return freq_guess

def calibrate_rabi_while_flux(a, pi_length=100, t1=1000):
    quantum_device_cfg = json.loads(a.attrs['quantum_device_cfg'])
    experiment_cfg = json.loads(a.attrs['experiment_cfg'])
    hardware_cfg = json.loads(a.attrs['hardware_cfg'])

    expt_cfg = experiment_cfg['rabi_while_flux']
    expt_pts = np.arange(expt_cfg['start'], expt_cfg['stop'], expt_cfg['step'])

    on_cavity = expt_cfg['on_cavity']
    ii = 0

    for cavity_id in on_cavity:

        expt_avg_data = np.array(a['expt_avg_data_ch%s' % cavity_id])

        y = expt_avg_data
        fitguess = [max(y) / 2 - min(y) / 2, 1 / (2 * pi_length), 0, t1, max(y) / 2 + min(y) / 2]
        fitdata = fitdecaysin(expt_pts[:], expt_avg_data[:], fitparams=fitguess, showfit=True)

        pi_length = (90.0 - fitdata[2]) / (360.0 * fitdata[1])
        pi_length1 = pi_length
        if pi_length1 > 0:
            while pi_length1 > 0:
                pi_length1 -= abs(180 / 360.0 / fitdata[1])
            pi_length1 += abs(180 / 360.0 / fitdata[1])
        else:
            while pi_length1 < 0:
                pi_length1 += abs(180 / 360.0 / fitdata[1])

        pi_length11 = pi_length1 + abs(180 / 360.0 / fitdata[1])
        comparea = fitdata[0] * np.sin(2 * np.pi * fitdata[1] * pi_length1 + fitdata[2] * np.pi / 180) * np.exp(
            -(pi_length1 - expt_pts[0]) / fitdata[3]) + fitdata[4]
        compareb = fitdata[0] * np.sin(2 * np.pi * fitdata[1] * pi_length11 + fitdata[2] * np.pi / 180) * np.exp(
            -(pi_length11 - expt_pts[0]) / fitdata[3]) + fitdata[4]

        if abs(compareb) > abs(comparea): pi_length1 = pi_length11
        hpi_length = pi_length1 - abs(180 / 360.0 / fitdata[1]) / 2
        ii = ii + 1

        return pi_length1, hpi_length


def calibration_auto(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    # Author Ziqian 19th OCT 2021
    # automatically calibrating qubit frequency and pi, pi/2 gate length
    # Initializing qubit frequency and gate length
    expt_cfg = experiment_cfg['calibration_auto']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'calibration_auto', suffix='.h5'))
    ram_acq_no = expt_cfg['ramsey_acq_num']
    fq = {}
    pi_gate = {}
    pi_amp = {}
    hpi_gate = {}
    hpi_amp = {}
    string_list = ['gg->eg','gg->ge','eg->fg','ge->gf','ge->ee','eg->ee','gf->ef','fg->fe','ee->fe','ee->ef','ef->ff','fe->ff']
    fq['gg->eg'] = quantum_device_cfg['qubit']['1']['freq']
    fq['gg->ge'] = quantum_device_cfg['qubit']['2']['freq']

    fq['eg->fg'] = quantum_device_cfg['qubit']['1']['freq']+quantum_device_cfg['qubit']['1']['anharmonicity']
    fq['ge->gf'] = quantum_device_cfg['qubit']['2']['freq']+quantum_device_cfg['qubit']['2']['anharmonicity']

    fq['ge->ee'] = quantum_device_cfg['qubit']['1']['freq']+quantum_device_cfg['qubit']['qq_disp']
    fq['eg->ee'] = quantum_device_cfg['qubit']['2']['freq']+quantum_device_cfg['qubit']['qq_disp']

    fq['gf->ef'] = quantum_device_cfg['qubit']['1']['freq'] + quantum_device_cfg['qubit']['gf1_disp']
    fq['fg->fe'] = quantum_device_cfg['qubit']['2']['freq'] + quantum_device_cfg['qubit']['fg2_disp']

    fq['ee->fe'] = quantum_device_cfg['qubit']['1']['freq']+quantum_device_cfg['qubit']['1']['anharmonicity'] + quantum_device_cfg['qubit']['ef1_disp']
    fq['ee->ef'] = quantum_device_cfg['qubit']['2']['freq']+quantum_device_cfg['qubit']['2']['anharmonicity'] + quantum_device_cfg['qubit']['fe2_disp']

    fq['ef->ff'] = quantum_device_cfg['qubit']['1']['freq'] + quantum_device_cfg['qubit']['1']['anharmonicity'] + \
                   quantum_device_cfg['qubit']['ff1_disp']
    fq['fe->ff'] = quantum_device_cfg['qubit']['2']['freq'] + quantum_device_cfg['qubit']['2']['anharmonicity'] + \
                   quantum_device_cfg['qubit']['ff2_disp']
    
    pi_gate['gg->eg'] = quantum_device_cfg['pulse_info']['1']['pi_len']
    pi_gate['eg->fg'] = quantum_device_cfg['pulse_info']['1']['pi_ef_len']
    pi_gate['ge->ee'] = quantum_device_cfg['pulse_info']['1']['pi_ee_len']
    pi_gate['gf->ef'] = quantum_device_cfg['pulse_info']['1']['pi_gf_len']
    pi_gate['ee->fe'] = quantum_device_cfg['pulse_info']['1']['pi_ef_e_len']
    pi_gate['ef->ff'] = quantum_device_cfg['pulse_info']['1']['pi_ff_len']

    pi_amp['gg->eg'] = quantum_device_cfg['pulse_info']['1']['pi_amp']
    pi_amp['eg->fg'] = quantum_device_cfg['pulse_info']['1']['pi_ef_amp']
    pi_amp['ge->ee'] = quantum_device_cfg['pulse_info']['1']['pi_ee_amp']
    pi_amp['gf->ef'] = quantum_device_cfg['pulse_info']['1']['pi_gf_amp']
    pi_amp['ee->fe'] = quantum_device_cfg['pulse_info']['1']['pi_ef_e_amp']
    pi_amp['ef->ff'] = quantum_device_cfg['pulse_info']['1']['pi_ff_amp']

    hpi_gate['gg->eg'] = quantum_device_cfg['pulse_info']['1']['half_pi_len']
    hpi_gate['eg->fg'] = quantum_device_cfg['pulse_info']['1']['half_pi_ef_len']
    hpi_gate['ge->ee'] = quantum_device_cfg['pulse_info']['1']['half_pi_ee_len']
    hpi_gate['gf->ef'] = quantum_device_cfg['pulse_info']['1']['half_pi_gf_len']
    hpi_gate['ee->fe'] = quantum_device_cfg['pulse_info']['1']['half_pi_ef_e_len']
    hpi_gate['ef->ff'] = quantum_device_cfg['pulse_info']['1']['half_pi_ff_len']

    hpi_amp['gg->eg'] = quantum_device_cfg['pulse_info']['1']['half_pi_amp']
    hpi_amp['eg->fg'] = quantum_device_cfg['pulse_info']['1']['half_pi_ef_amp']
    hpi_amp['ge->ee'] = quantum_device_cfg['pulse_info']['1']['half_pi_ee_amp']
    hpi_amp['gf->ef'] = quantum_device_cfg['pulse_info']['1']['half_pi_gf_amp']
    hpi_amp['ee->fe'] = quantum_device_cfg['pulse_info']['1']['half_pi_ef_e_amp']
    hpi_amp['ef->ff'] = quantum_device_cfg['pulse_info']['1']['half_pi_ff_amp']
########################################################################################
    pi_gate['gg->ge'] = quantum_device_cfg['pulse_info']['2']['pi_len']
    pi_gate['ge->gf'] = quantum_device_cfg['pulse_info']['2']['pi_ef_len']
    pi_gate['eg->ee'] = quantum_device_cfg['pulse_info']['2']['pi_ee_len']
    pi_gate['fg->fe'] = quantum_device_cfg['pulse_info']['2']['pi_gf_len']
    pi_gate['ee->ef'] = quantum_device_cfg['pulse_info']['2']['pi_ef_e_len']
    pi_gate['fe->ff'] = quantum_device_cfg['pulse_info']['2']['pi_ff_len']

    pi_amp['gg->ge'] = quantum_device_cfg['pulse_info']['2']['pi_amp']
    pi_amp['ge->gf'] = quantum_device_cfg['pulse_info']['2']['pi_ef_amp']
    pi_amp['eg->ee'] = quantum_device_cfg['pulse_info']['2']['pi_ee_amp']
    pi_amp['fg->fe'] = quantum_device_cfg['pulse_info']['2']['pi_gf_amp']
    pi_amp['ee->ef'] = quantum_device_cfg['pulse_info']['2']['pi_ef_e_amp']
    pi_amp['fe->ff'] = quantum_device_cfg['pulse_info']['2']['pi_ff_amp']

    hpi_gate['gg->ge'] = quantum_device_cfg['pulse_info']['2']['half_pi_len']
    hpi_gate['ge->gf'] = quantum_device_cfg['pulse_info']['2']['half_pi_ef_len']
    hpi_gate['eg->ee'] = quantum_device_cfg['pulse_info']['2']['half_pi_ee_len']
    hpi_gate['fg->fe'] = quantum_device_cfg['pulse_info']['2']['half_pi_gf_len']
    hpi_gate['ee->ef'] = quantum_device_cfg['pulse_info']['2']['half_pi_ef_e_len']
    hpi_gate['fe->ff'] = quantum_device_cfg['pulse_info']['2']['half_pi_ff_len']

    hpi_amp['gg->ge'] = quantum_device_cfg['pulse_info']['2']['half_pi_amp']
    hpi_amp['ge->gf'] = quantum_device_cfg['pulse_info']['2']['half_pi_ef_amp']
    hpi_amp['eg->ee'] = quantum_device_cfg['pulse_info']['2']['half_pi_ee_amp']
    hpi_amp['fg->fe'] = quantum_device_cfg['pulse_info']['2']['half_pi_gf_amp']
    hpi_amp['ee->ef'] = quantum_device_cfg['pulse_info']['2']['half_pi_ef_e_amp']
    hpi_amp['fe->ff'] = quantum_device_cfg['pulse_info']['2']['half_pi_ff_amp']

    ## calibrating gg->eg
    print('Calibrating |gg>-->|eg> transition')
    for rround in range(expt_cfg['iterno']):
        print('############## Calibration Round No: ', rround+1)
        ##################################### rabi
        print('Calibrating |gg>-->|eg> Rabi')
        experiment_cfg['rabi_while_flux']['amp'] = pi_amp['gg->eg']
        experiment_cfg['rabi_while_flux']['flux_amp'] = []
        experiment_cfg['rabi_while_flux']['ge_pi'] = []
        experiment_cfg['rabi_while_flux']['ef_pi'] = []
        experiment_cfg['rabi_while_flux']['ge_pi2'] = []
        experiment_cfg['rabi_while_flux']['pre_pulse'] = False
        experiment_cfg['rabi_while_flux']['qubit_freq'] = fq['gg->eg']
        experiment_cfg['rabi_while_flux']['pi_calibration'] = expt_cfg['pi_calibration']
        experiment_cfg['rabi_while_flux']['flux_pi_calibration'] = False
        experiment_cfg['rabi_while_flux']['flux_probe'] = False

        experiment_cfg['rabi_while_flux']['start'] = 0.0
        experiment_cfg['rabi_while_flux']['stop'] = pi_gate['gg->eg']*4.0
        experiment_cfg['rabi_while_flux']['step'] = np.round(pi_gate['gg->eg']*4.0/100.0, 1)

        experiment_cfg['rabi_while_flux']['acquisition_num'] = expt_cfg['acquisition_num']
        experiment_cfg['rabi_while_flux']['on_qubits'] = ['1']
        experiment_cfg['rabi_while_flux']['on_cavity'] = ['1']
        experiment_cfg['rabi_while_flux']['calibration_qubit'] = '1'
        experiment_cfg['rabi_while_flux']['flux_line'] = []
        experiment_cfg['rabi_while_flux']['flux_freq'] = 1.0
        experiment_cfg['rabi_while_flux']['phase'] = [0]

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('rabi_while_flux')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'rabi_while_flux')

        update_awg = False
        ########################################### Fitting Rabi
        print('Fitting Rabi data...')
        data_path_now = os.path.join(data_path, get_current_filename(data_path, 'rabi_while_flux', suffix='.h5'))
        with SlabFile(data_path_now) as a:
            pil, hpil = calibrate_rabi_while_flux(a, pi_length=pi_gate['gg->eg'], t1=1000)
        print('Calibrated pi length: %.2f ' %(pil))
        print('Calibrated pi/2 length: %.2f ' % (hpil))
        pi_gate['gg->eg'] = pil
        hpi_gate['gg->eg'] = hpil
        quantum_device_cfg['pulse_info']['1']['pi_len'] = pil
        quantum_device_cfg['pulse_info']['1']['half_pi_len'] = hpil

        ########################################### ramsey
        print('Calibrating |gg>-->|eg> Ramsey')
        experiment_cfg['ramsey_while_flux']['use_freq_amp_halfpi'] = [True, fq['gg->eg'], pi_amp['gg->eg'], hpi_gate['gg->eg'], 'charge1']
        experiment_cfg['ramsey_while_flux']['flux_amp'] = []
        experiment_cfg['ramsey_while_flux']['flux_probe'] = False
        experiment_cfg['ramsey_while_flux']['singleshot'] = False
        experiment_cfg['ramsey_while_flux']['ge_pi'] = []
        experiment_cfg['ramsey_while_flux']['ef_pi'] = []
        experiment_cfg['ramsey_while_flux']['ge_pi2'] = []
        experiment_cfg['ramsey_while_flux']['pre_pulse'] = False
        experiment_cfg['ramsey_while_flux']['pi_calibration'] = expt_cfg['pi_calibration']
        experiment_cfg['ramsey_while_flux']['flux_pi_calibration'] = False

        experiment_cfg['ramsey_while_flux']['start'] = 0.0
        experiment_cfg['ramsey_while_flux']['stop'] = 1500.0
        experiment_cfg['ramsey_while_flux']['step'] = 5.0
        experiment_cfg['ramsey_while_flux']['ramsey_freq'] = 0.005

        experiment_cfg['ramsey_while_flux']['acquisition_num'] = ram_acq_no
        experiment_cfg['ramsey_while_flux']['on_qubits'] = ['1']
        experiment_cfg['ramsey_while_flux']['on_cavity'] = ['1']
        experiment_cfg['ramsey_while_flux']['flux_line'] = []
        experiment_cfg['ramsey_while_flux']['flux_freq'] = 1.0
        experiment_cfg['ramsey_while_flux']['phase'] = [0]

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('ramsey_while_flux')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'ramsey_while_flux')

        update_awg = False
        ########################################### Fitting Ramsey
        print('Fitting Ramsey data...')
        data_path_now = os.path.join(data_path, get_current_filename(data_path, 'ramsey_while_flux', suffix='.h5'))
        with SlabFile(data_path_now) as a:
            freq_new = calibrate_ramsey(a, pi_length=100, t2=1000)
        print('Calibrated |gg>-->|eg> transition: %s GHz' % (freq_new))
        fq['gg->eg'] = freq_new
        quantum_device_cfg['qubit']['1']['freq'] = freq_new

    print('Calibrating |gg>-->|eg> Rabi')
    experiment_cfg['rabi_while_flux']['amp'] = pi_amp['gg->eg']
    experiment_cfg['rabi_while_flux']['flux_amp'] = []
    experiment_cfg['rabi_while_flux']['ge_pi'] = []
    experiment_cfg['rabi_while_flux']['ef_pi'] = []
    experiment_cfg['rabi_while_flux']['ge_pi2'] = []
    experiment_cfg['rabi_while_flux']['pre_pulse'] = False
    experiment_cfg['rabi_while_flux']['qubit_freq'] = fq['gg->eg']
    experiment_cfg['rabi_while_flux']['pi_calibration'] = expt_cfg['pi_calibration']
    experiment_cfg['rabi_while_flux']['flux_pi_calibration'] = False
    experiment_cfg['rabi_while_flux']['flux_probe'] = False

    experiment_cfg['rabi_while_flux']['start'] = 0.0
    experiment_cfg['rabi_while_flux']['stop'] = pi_gate['gg->eg'] * 4.0
    experiment_cfg['rabi_while_flux']['step'] = np.round(pi_gate['gg->eg'] * 4 / 100.0 ,1)

    experiment_cfg['rabi_while_flux']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['rabi_while_flux']['on_qubits'] = ['1']
    experiment_cfg['rabi_while_flux']['on_cavity'] = ['1']
    experiment_cfg['rabi_while_flux']['calibration_qubit'] = '1'
    experiment_cfg['rabi_while_flux']['flux_line'] = []
    experiment_cfg['rabi_while_flux']['flux_freq'] = 1.0
    experiment_cfg['rabi_while_flux']['phase'] = [0]

    ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
    sequences = ps.get_experiment_sequences('rabi_while_flux')
    update_awg = True

    exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
    exp.run_experiment(sequences, path, 'rabi_while_flux')

    update_awg = False
    ########################################### Fitting Rabi
    print('Fitting Rabi data...')
    data_path_now = os.path.join(data_path, get_current_filename(data_path, 'rabi_while_flux', suffix='.h5'))
    with SlabFile(data_path_now) as a:
        pil, hpil = calibrate_rabi_while_flux(a, pi_length=pi_gate['gg->eg'], t1=1000)
    print('Calibrated pi length: %.2f ' % (pil))
    print('Calibrated pi/2 length: %.2f ' % (hpil))
    pi_gate['gg->eg'] = pil
    hpi_gate['gg->eg'] = hpil
    quantum_device_cfg['pulse_info']['1']['pi_len'] = pil
    quantum_device_cfg['pulse_info']['1']['half_pi_len'] = hpil

    print('################################')
    print('current results:')
    for sss in string_list:
        print(sss,'  Freq:',fq[sss],'  pi:',pi_gate[sss],'  hpi:',hpi_gate[sss])
    print('qq_disp: ', fq['ge->ee'] - fq['gg->eg'])
    print('gf1_disp: ', fq['gf->ef'] - fq['gg->eg'])
    print('fg2_disp: ', fq['fg->fe'] - fq['gg->ge'])
    print('ef1_disp: ', fq['ee->fe'] - fq['eg->fg'])
    print('fe2_disp: ', fq['ee->ef'] - fq['ge->gf'])
    print('ff1_disp: ', fq['ef->ff'] - fq['eg->fg'])
    print('ff2_disp: ', fq['fe->ff'] - fq['ge->gf'])



#########################################################################################
    ## calibrating gg->ge
    print('Calibrating |gg>-->|ge> transition')
    for rround in range(expt_cfg['iterno']):
        print('############## Calibration Round No: ', rround + 1)
        ##################################### rabi
        print('Calibrating |gg>-->|ge> Rabi')
        experiment_cfg['rabi_while_flux']['amp'] = pi_amp['gg->ge']
        experiment_cfg['rabi_while_flux']['flux_amp'] = []
        experiment_cfg['rabi_while_flux']['ge_pi'] = []
        experiment_cfg['rabi_while_flux']['ef_pi'] = []
        experiment_cfg['rabi_while_flux']['ge_pi2'] = []
        experiment_cfg['rabi_while_flux']['pre_pulse'] = False
        experiment_cfg['rabi_while_flux']['qubit_freq'] = fq['gg->ge']
        experiment_cfg['rabi_while_flux']['pi_calibration'] = expt_cfg['pi_calibration']
        experiment_cfg['rabi_while_flux']['flux_pi_calibration'] = False
        experiment_cfg['rabi_while_flux']['flux_probe'] = False

        experiment_cfg['rabi_while_flux']['start'] = 0.0
        experiment_cfg['rabi_while_flux']['stop'] = pi_gate['gg->ge'] * 4.0
        experiment_cfg['rabi_while_flux']['step'] = np.round(pi_gate['gg->ge'] * 4 / 100.0 ,1)

        experiment_cfg['rabi_while_flux']['acquisition_num'] = expt_cfg['acquisition_num']
        experiment_cfg['rabi_while_flux']['on_qubits'] = ['2']
        experiment_cfg['rabi_while_flux']['on_cavity'] = ['2']
        experiment_cfg['rabi_while_flux']['calibration_qubit'] = '2'
        experiment_cfg['rabi_while_flux']['flux_line'] = []
        experiment_cfg['rabi_while_flux']['flux_freq'] = 1.0
        experiment_cfg['rabi_while_flux']['phase'] = [0]

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('rabi_while_flux')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'rabi_while_flux')

        update_awg = False
        ########################################### Fitting Rabi
        print('Fitting Rabi data...')
        data_path_now = os.path.join(data_path, get_current_filename(data_path, 'rabi_while_flux', suffix='.h5'))
        with SlabFile(data_path_now) as a:
            pil, hpil = calibrate_rabi_while_flux(a, pi_length=pi_gate['gg->ge'], t1=1000)
        print('Calibrated pi length: %.2f ' % (pil))
        print('Calibrated pi/2 length: %.2f ' % (hpil))
        pi_gate['gg->ge'] = pil
        hpi_gate['gg->ge'] = hpil
        quantum_device_cfg['pulse_info']['2']['pi_len'] = pil
        quantum_device_cfg['pulse_info']['2']['half_pi_len'] = hpil

        ########################################### ramsey
        print('Calibrating |gg>-->|ge> Ramsey')
        experiment_cfg['ramsey_while_flux']['use_freq_amp_halfpi'] = [True, fq['gg->ge'], pi_amp['gg->ge'],
                                                                      hpi_gate['gg->ge'], 'charge2']
        experiment_cfg['ramsey_while_flux']['flux_amp'] = []
        experiment_cfg['ramsey_while_flux']['flux_probe'] = False
        experiment_cfg['ramsey_while_flux']['singleshot'] = False
        experiment_cfg['ramsey_while_flux']['ge_pi'] = []
        experiment_cfg['ramsey_while_flux']['ef_pi'] = []
        experiment_cfg['ramsey_while_flux']['ge_pi2'] = []
        experiment_cfg['ramsey_while_flux']['pre_pulse'] = False
        experiment_cfg['ramsey_while_flux']['pi_calibration'] = expt_cfg['pi_calibration']
        experiment_cfg['ramsey_while_flux']['flux_pi_calibration'] = False

        experiment_cfg['ramsey_while_flux']['start'] = 0.0
        experiment_cfg['ramsey_while_flux']['stop'] = 1500.0
        experiment_cfg['ramsey_while_flux']['step'] = 5.0
        experiment_cfg['ramsey_while_flux']['ramsey_freq'] = 0.005

        experiment_cfg['ramsey_while_flux']['acquisition_num'] = ram_acq_no
        experiment_cfg['ramsey_while_flux']['on_qubits'] = ['2']
        experiment_cfg['ramsey_while_flux']['on_cavity'] = ['2']
        experiment_cfg['ramsey_while_flux']['flux_line'] = []
        experiment_cfg['ramsey_while_flux']['flux_freq'] = 1.0
        experiment_cfg['ramsey_while_flux']['phase'] = [0]

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('ramsey_while_flux')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'ramsey_while_flux')

        update_awg = False
        ########################################### Fitting Ramsey
        print('Fitting Ramsey data...')
        data_path_now = os.path.join(data_path,
                                     get_current_filename(data_path, 'ramsey_while_flux', suffix='.h5'))
        with SlabFile(data_path_now) as a:
            freq_new = calibrate_ramsey(a, pi_length=100, t2=1000)
        print('Calibrated |gg>-->|ge> transition: %s GHz' % (freq_new))
        fq['gg->ge'] = freq_new
        quantum_device_cfg['qubit']['2']['freq'] = freq_new

    print('Calibrating |gg>-->|ge> Rabi')
    experiment_cfg['rabi_while_flux']['amp'] = pi_amp['gg->ge']
    experiment_cfg['rabi_while_flux']['flux_amp'] = []
    experiment_cfg['rabi_while_flux']['ge_pi'] = []
    experiment_cfg['rabi_while_flux']['ef_pi'] = []
    experiment_cfg['rabi_while_flux']['ge_pi2'] = []
    experiment_cfg['rabi_while_flux']['pre_pulse'] = False
    experiment_cfg['rabi_while_flux']['qubit_freq'] = fq['gg->ge']
    experiment_cfg['rabi_while_flux']['pi_calibration'] = expt_cfg['pi_calibration']
    experiment_cfg['rabi_while_flux']['flux_pi_calibration'] = False
    experiment_cfg['rabi_while_flux']['flux_probe'] = False

    experiment_cfg['rabi_while_flux']['start'] = 0.0
    experiment_cfg['rabi_while_flux']['stop'] = pi_gate['gg->ge'] * 4.0
    experiment_cfg['rabi_while_flux']['step'] = np.round(pi_gate['gg->ge'] * 4 / 100.0 ,1)

    experiment_cfg['rabi_while_flux']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['rabi_while_flux']['on_qubits'] = ['2']
    experiment_cfg['rabi_while_flux']['on_cavity'] = ['2']
    experiment_cfg['rabi_while_flux']['calibration_qubit'] = '2'
    experiment_cfg['rabi_while_flux']['flux_line'] = []
    experiment_cfg['rabi_while_flux']['flux_freq'] = 1.0
    experiment_cfg['rabi_while_flux']['phase'] = [0]

    ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
    sequences = ps.get_experiment_sequences('rabi_while_flux')
    update_awg = True

    exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
    exp.run_experiment(sequences, path, 'rabi_while_flux')

    update_awg = False
    ########################################### Fitting Rabi
    print('Fitting Rabi data...')
    data_path_now = os.path.join(data_path, get_current_filename(data_path, 'rabi_while_flux', suffix='.h5'))
    with SlabFile(data_path_now) as a:
        pil, hpil = calibrate_rabi_while_flux(a, pi_length=pi_gate['gg->ge'], t1=1000)
    print('Calibrated pi length: %.2f ' % (pil))
    print('Calibrated pi/2 length: %.2f ' % (hpil))
    pi_gate['gg->ge'] = pil
    hpi_gate['gg->ge'] = hpil
    quantum_device_cfg['pulse_info']['2']['pi_len'] = pil
    quantum_device_cfg['pulse_info']['2']['half_pi_len'] = hpil
    print('################################')
    print('current results:')
    for sss in string_list:
        print(sss, '  Freq:', fq[sss], '  pi:', pi_gate[sss], '  hpi:', hpi_gate[sss])
    print('qq_disp: ', fq['ge->ee'] - fq['gg->eg'])
    print('gf1_disp: ', fq['gf->ef'] - fq['gg->eg'])
    print('fg2_disp: ', fq['fg->fe'] - fq['gg->ge'])
    print('ef1_disp: ', fq['ee->fe'] - fq['eg->fg'])
    print('fe2_disp: ', fq['ee->ef'] - fq['ge->gf'])
    print('ff1_disp: ', fq['ef->ff'] - fq['eg->fg'])
    print('ff2_disp: ', fq['fe->ff'] - fq['ge->gf'])


#########################################################################################
    ## calibrating ge->gf
    print('Calibrating |ge>-->|gf> transition')
    for rround in range(expt_cfg['iterno']):
        print('############## Calibration Round No: ', rround + 1)
        ##################################### rabi
        print('Calibrating |ge>-->|gf> Rabi')
        experiment_cfg['rabi_while_flux']['amp'] = pi_amp['ge->gf']
        experiment_cfg['rabi_while_flux']['flux_amp'] = []
        experiment_cfg['rabi_while_flux']['ge_pi'] = ['2']
        experiment_cfg['rabi_while_flux']['ef_pi'] = []
        experiment_cfg['rabi_while_flux']['ge_pi2'] = []
        experiment_cfg['rabi_while_flux']['pre_pulse'] = False
        experiment_cfg['rabi_while_flux']['qubit_freq'] = fq['ge->gf']
        experiment_cfg['rabi_while_flux']['pi_calibration'] = expt_cfg['pi_calibration']
        experiment_cfg['rabi_while_flux']['flux_pi_calibration'] = False
        experiment_cfg['rabi_while_flux']['flux_probe'] = False

        experiment_cfg['rabi_while_flux']['start'] = 0.0
        experiment_cfg['rabi_while_flux']['stop'] = pi_gate['ge->gf'] * 4.0
        experiment_cfg['rabi_while_flux']['step'] = np.round(pi_gate['ge->gf'] * 4 / 100.0 ,1)

        experiment_cfg['rabi_while_flux']['acquisition_num'] = expt_cfg['acquisition_num']
        experiment_cfg['rabi_while_flux']['on_qubits'] = ['2']
        experiment_cfg['rabi_while_flux']['on_cavity'] = ['2']
        experiment_cfg['rabi_while_flux']['calibration_qubit'] = '2'
        experiment_cfg['rabi_while_flux']['flux_line'] = []
        experiment_cfg['rabi_while_flux']['flux_freq'] = 1.0
        experiment_cfg['rabi_while_flux']['phase'] = [0]

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('rabi_while_flux')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'rabi_while_flux')

        update_awg = False
        ########################################### Fitting Rabi
        print('Fitting Rabi data...')
        data_path_now = os.path.join(data_path, get_current_filename(data_path, 'rabi_while_flux', suffix='.h5'))
        with SlabFile(data_path_now) as a:
            pil, hpil = calibrate_rabi_while_flux(a, pi_length=pi_gate['ge->gf'], t1=1000)
        print('Calibrated pi length: %.2f ' % (pil))
        print('Calibrated pi/2 length: %.2f ' % (hpil))
        pi_gate['ge->gf'] = pil
        hpi_gate['ge->gf'] = hpil
        quantum_device_cfg['pulse_info']['2']['pi_ef_len'] = pil
        quantum_device_cfg['pulse_info']['2']['half_pi_ef_len'] = hpil

        ########################################### ramsey
        print('Calibrating |ge>-->|gf> Ramsey')
        experiment_cfg['ramsey_while_flux']['use_freq_amp_halfpi'] = [True, fq['ge->gf'], pi_amp['ge->gf'],
                                                                      hpi_gate['ge->gf'], 'charge2']
        experiment_cfg['ramsey_while_flux']['flux_amp'] = []
        experiment_cfg['ramsey_while_flux']['flux_probe'] = False
        experiment_cfg['ramsey_while_flux']['singleshot'] = False
        experiment_cfg['ramsey_while_flux']['ge_pi'] = ['2']
        experiment_cfg['ramsey_while_flux']['ef_pi'] = []
        experiment_cfg['ramsey_while_flux']['ge_pi2'] = []
        experiment_cfg['ramsey_while_flux']['pre_pulse'] = False
        experiment_cfg['ramsey_while_flux']['pi_calibration'] = expt_cfg['pi_calibration']
        experiment_cfg['ramsey_while_flux']['flux_pi_calibration'] = False

        experiment_cfg['ramsey_while_flux']['start'] = 0.0
        experiment_cfg['ramsey_while_flux']['stop'] = 1500.0
        experiment_cfg['ramsey_while_flux']['step'] = 5.0
        experiment_cfg['ramsey_while_flux']['ramsey_freq'] = 0.005

        experiment_cfg['ramsey_while_flux']['acquisition_num'] = ram_acq_no
        experiment_cfg['ramsey_while_flux']['on_qubits'] = ['2']
        experiment_cfg['ramsey_while_flux']['on_cavity'] = ['2']
        experiment_cfg['ramsey_while_flux']['flux_line'] = []
        experiment_cfg['ramsey_while_flux']['flux_freq'] = 1.0
        experiment_cfg['ramsey_while_flux']['phase'] = [0]

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('ramsey_while_flux')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'ramsey_while_flux')

        update_awg = False
        ########################################### Fitting Ramsey
        print('Fitting Ramsey data...')
        data_path_now = os.path.join(data_path,
                                     get_current_filename(data_path, 'ramsey_while_flux', suffix='.h5'))
        with SlabFile(data_path_now) as a:
            freq_new = calibrate_ramsey(a, pi_length=100, t2=1000)
        print('Calibrated |ge>-->|gf> transition: %s GHz' % (freq_new))
        fq['ge->gf'] = freq_new
        quantum_device_cfg['qubit']['2']['anharmonicity'] = freq_new-quantum_device_cfg['qubit']['2']['freq']

    print('Calibrating |ge>-->|gf> Rabi')
    experiment_cfg['rabi_while_flux']['amp'] = pi_amp['ge->gf']
    experiment_cfg['rabi_while_flux']['flux_amp'] = []
    experiment_cfg['rabi_while_flux']['ge_pi'] = ['2']
    experiment_cfg['rabi_while_flux']['ef_pi'] = []
    experiment_cfg['rabi_while_flux']['ge_pi2'] = []
    experiment_cfg['rabi_while_flux']['pre_pulse'] = False
    experiment_cfg['rabi_while_flux']['qubit_freq'] = fq['ge->gf']
    experiment_cfg['rabi_while_flux']['pi_calibration'] = expt_cfg['pi_calibration']
    experiment_cfg['rabi_while_flux']['flux_pi_calibration'] = False
    experiment_cfg['rabi_while_flux']['flux_probe'] = False

    experiment_cfg['rabi_while_flux']['start'] = 0.0
    experiment_cfg['rabi_while_flux']['stop'] = pi_gate['ge->gf'] * 4.0
    experiment_cfg['rabi_while_flux']['step'] = np.round(pi_gate['ge->gf'] * 4 / 100.0 ,1)

    experiment_cfg['rabi_while_flux']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['rabi_while_flux']['on_qubits'] = ['2']
    experiment_cfg['rabi_while_flux']['on_cavity'] = ['2']
    experiment_cfg['rabi_while_flux']['calibration_qubit'] = '2'
    experiment_cfg['rabi_while_flux']['flux_line'] = []
    experiment_cfg['rabi_while_flux']['flux_freq'] = 1.0
    experiment_cfg['rabi_while_flux']['phase'] = [0]

    ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
    sequences = ps.get_experiment_sequences('rabi_while_flux')
    update_awg = True

    exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
    exp.run_experiment(sequences, path, 'rabi_while_flux')

    update_awg = False
    ########################################### Fitting Rabi
    print('Fitting Rabi data...')
    data_path_now = os.path.join(data_path, get_current_filename(data_path, 'rabi_while_flux', suffix='.h5'))
    with SlabFile(data_path_now) as a:
        pil, hpil = calibrate_rabi_while_flux(a, pi_length=pi_gate['ge->gf'], t1=1000)
    print('Calibrated pi length: %.2f ' % (pil))
    print('Calibrated pi/2 length: %.2f ' % (hpil))
    pi_gate['ge->gf'] = pil
    hpi_gate['ge->gf'] = hpil
    quantum_device_cfg['pulse_info']['2']['pi_ef_len'] = pil
    quantum_device_cfg['pulse_info']['2']['half_pi_ef_len'] = hpil
    print('################################')
    print('current results:')
    for sss in string_list:
        print(sss, '  Freq:', fq[sss], '  pi:', pi_gate[sss], '  hpi:', hpi_gate[sss])
    print('qq_disp: ', fq['ge->ee'] - fq['gg->eg'])
    print('gf1_disp: ', fq['gf->ef'] - fq['gg->eg'])
    print('fg2_disp: ', fq['fg->fe'] - fq['gg->ge'])
    print('ef1_disp: ', fq['ee->fe'] - fq['eg->fg'])
    print('fe2_disp: ', fq['ee->ef'] - fq['ge->gf'])
    print('ff1_disp: ', fq['ef->ff'] - fq['eg->fg'])
    print('ff2_disp: ', fq['fe->ff'] - fq['ge->gf'])



    #########################################################################################
    ## calibrating eg->fg
    print('Calibrating |eg>-->|fg> transition')
    for rround in range(expt_cfg['iterno']):
        print('############## Calibration Round No: ', rround + 1)
        ##################################### rabi
        print('Calibrating |eg>-->|fg> Rabi')
        experiment_cfg['rabi_while_flux']['amp'] = pi_amp['eg->fg']
        experiment_cfg['rabi_while_flux']['flux_amp'] = []
        experiment_cfg['rabi_while_flux']['ge_pi'] = ['1']
        experiment_cfg['rabi_while_flux']['ef_pi'] = []
        experiment_cfg['rabi_while_flux']['ge_pi2'] = []
        experiment_cfg['rabi_while_flux']['pre_pulse'] = False
        experiment_cfg['rabi_while_flux']['qubit_freq'] = fq['eg->fg']
        experiment_cfg['rabi_while_flux']['pi_calibration'] = expt_cfg['pi_calibration']
        experiment_cfg['rabi_while_flux']['flux_pi_calibration'] = False
        experiment_cfg['rabi_while_flux']['flux_probe'] = False

        experiment_cfg['rabi_while_flux']['start'] = 0.0
        experiment_cfg['rabi_while_flux']['stop'] = pi_gate['eg->fg'] * 4.0
        experiment_cfg['rabi_while_flux']['step'] = np.round(pi_gate['eg->fg'] * 4 / 100.0 ,1)

        experiment_cfg['rabi_while_flux']['acquisition_num'] = expt_cfg['acquisition_num']
        experiment_cfg['rabi_while_flux']['on_qubits'] = ['1']
        experiment_cfg['rabi_while_flux']['on_cavity'] = ['1']
        experiment_cfg['rabi_while_flux']['calibration_qubit'] = '1'
        experiment_cfg['rabi_while_flux']['flux_line'] = []
        experiment_cfg['rabi_while_flux']['flux_freq'] = 1.0
        experiment_cfg['rabi_while_flux']['phase'] = [0]

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('rabi_while_flux')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'rabi_while_flux')

        update_awg = False
        ########################################### Fitting Rabi
        print('Fitting Rabi data...')
        data_path_now = os.path.join(data_path, get_current_filename(data_path, 'rabi_while_flux', suffix='.h5'))
        with SlabFile(data_path_now) as a:
            pil, hpil = calibrate_rabi_while_flux(a, pi_length=pi_gate['eg->fg'], t1=1000)
        print('Calibrated pi length: %.2f ' % (pil))
        print('Calibrated pi/2 length: %.2f ' % (hpil))
        pi_gate['eg->fg'] = pil
        hpi_gate['eg->fg'] = hpil
        quantum_device_cfg['pulse_info']['1']['pi_ef_len'] = pil
        quantum_device_cfg['pulse_info']['1']['half_pi_ef_len'] = hpil

        ########################################### ramsey
        print('Calibrating |eg>-->|fg> Ramsey')
        experiment_cfg['ramsey_while_flux']['use_freq_amp_halfpi'] = [True, fq['eg->fg'], pi_amp['eg->fg'],
                                                                      hpi_gate['eg->fg'], 'charge1']
        experiment_cfg['ramsey_while_flux']['flux_amp'] = []
        experiment_cfg['ramsey_while_flux']['flux_probe'] = False
        experiment_cfg['ramsey_while_flux']['singleshot'] = False
        experiment_cfg['ramsey_while_flux']['ge_pi'] = ['1']
        experiment_cfg['ramsey_while_flux']['ef_pi'] = []
        experiment_cfg['ramsey_while_flux']['ge_pi2'] = []
        experiment_cfg['ramsey_while_flux']['pre_pulse'] = False
        experiment_cfg['ramsey_while_flux']['pi_calibration'] = expt_cfg['pi_calibration']
        experiment_cfg['ramsey_while_flux']['flux_pi_calibration'] = False

        experiment_cfg['ramsey_while_flux']['start'] = 0.0
        experiment_cfg['ramsey_while_flux']['stop'] = 1500.0
        experiment_cfg['ramsey_while_flux']['step'] = 5.0
        experiment_cfg['ramsey_while_flux']['ramsey_freq'] = 0.005

        experiment_cfg['ramsey_while_flux']['acquisition_num'] = ram_acq_no
        experiment_cfg['ramsey_while_flux']['on_qubits'] = ['1']
        experiment_cfg['ramsey_while_flux']['on_cavity'] = ['1']
        experiment_cfg['ramsey_while_flux']['flux_line'] = []
        experiment_cfg['ramsey_while_flux']['flux_freq'] = 1.0
        experiment_cfg['ramsey_while_flux']['phase'] = [0]

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('ramsey_while_flux')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'ramsey_while_flux')

        update_awg = False
        ########################################### Fitting Ramsey
        print('Fitting Ramsey data...')
        data_path_now = os.path.join(data_path,
                                     get_current_filename(data_path, 'ramsey_while_flux', suffix='.h5'))
        with SlabFile(data_path_now) as a:
            freq_new = calibrate_ramsey(a, pi_length=100, t2=1000)
        print('Calibrated |eg>-->|fg> transition: %s GHz' % (freq_new))
        fq['eg->fg'] = freq_new
        quantum_device_cfg['qubit']['1']['anharmonicity'] = freq_new - quantum_device_cfg['qubit']['1']['freq']

    print('Calibrating |eg>-->|fg> Rabi')
    experiment_cfg['rabi_while_flux']['amp'] = pi_amp['eg->fg']
    experiment_cfg['rabi_while_flux']['flux_amp'] = []
    experiment_cfg['rabi_while_flux']['ge_pi'] = ['1']
    experiment_cfg['rabi_while_flux']['ef_pi'] = []
    experiment_cfg['rabi_while_flux']['ge_pi2'] = []
    experiment_cfg['rabi_while_flux']['pre_pulse'] = False
    experiment_cfg['rabi_while_flux']['qubit_freq'] = fq['eg->fg']
    experiment_cfg['rabi_while_flux']['pi_calibration'] = expt_cfg['pi_calibration']
    experiment_cfg['rabi_while_flux']['flux_pi_calibration'] = False
    experiment_cfg['rabi_while_flux']['flux_probe'] = False

    experiment_cfg['rabi_while_flux']['start'] = 0.0
    experiment_cfg['rabi_while_flux']['stop'] = pi_gate['eg->fg'] * 4.0
    experiment_cfg['rabi_while_flux']['step'] = np.round(pi_gate['eg->fg'] * 4 / 100.0 ,1)

    experiment_cfg['rabi_while_flux']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['rabi_while_flux']['on_qubits'] = ['1']
    experiment_cfg['rabi_while_flux']['on_cavity'] = ['1']
    experiment_cfg['rabi_while_flux']['calibration_qubit'] = '1'
    experiment_cfg['rabi_while_flux']['flux_line'] = []
    experiment_cfg['rabi_while_flux']['flux_freq'] = 1.0
    experiment_cfg['rabi_while_flux']['phase'] = [0]

    ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
    sequences = ps.get_experiment_sequences('rabi_while_flux')
    update_awg = True

    exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
    exp.run_experiment(sequences, path, 'rabi_while_flux')

    update_awg = False
    ########################################### Fitting Rabi
    print('Fitting Rabi data...')
    data_path_now = os.path.join(data_path, get_current_filename(data_path, 'rabi_while_flux', suffix='.h5'))
    with SlabFile(data_path_now) as a:
        pil, hpil = calibrate_rabi_while_flux(a, pi_length=pi_gate['eg->fg'], t1=1000)
    print('Calibrated pi length: %.2f ' % (pil))
    print('Calibrated pi/2 length: %.2f ' % (hpil))
    pi_gate['eg->fg'] = pil
    hpi_gate['eg->fg'] = hpil
    quantum_device_cfg['pulse_info']['1']['pi_ef_len'] = pil
    quantum_device_cfg['pulse_info']['1']['half_pi_ef_len'] = hpil
    print('################################')
    print('current results:')
    for sss in string_list:
        print(sss, '  Freq:', fq[sss], '  pi:', pi_gate[sss], '  hpi:', hpi_gate[sss])
    print('qq_disp: ', fq['ge->ee'] - fq['gg->eg'])
    print('gf1_disp: ', fq['gf->ef'] - fq['gg->eg'])
    print('fg2_disp: ', fq['fg->fe'] - fq['gg->ge'])
    print('ef1_disp: ', fq['ee->fe'] - fq['eg->fg'])
    print('fe2_disp: ', fq['ee->ef'] - fq['ge->gf'])
    print('ff1_disp: ', fq['ef->ff'] - fq['eg->fg'])
    print('ff2_disp: ', fq['fe->ff'] - fq['ge->gf'])



    #########################################################################################
    ## calibrating ge->ee
    print('Calibrating |ge>-->|ee> transition')
    for rround in range(expt_cfg['iterno']):
        print('############## Calibration Round No: ', rround + 1)
        ##################################### rabi
        print('Calibrating |ge>-->|ee> Rabi')
        experiment_cfg['rabi_while_flux']['amp'] = pi_amp['ge->ee']
        experiment_cfg['rabi_while_flux']['flux_amp'] = []
        experiment_cfg['rabi_while_flux']['ge_pi'] = ['2']
        experiment_cfg['rabi_while_flux']['ef_pi'] = []
        experiment_cfg['rabi_while_flux']['ge_pi2'] = []
        experiment_cfg['rabi_while_flux']['pre_pulse'] = False
        experiment_cfg['rabi_while_flux']['qubit_freq'] = fq['ge->ee']
        experiment_cfg['rabi_while_flux']['pi_calibration'] = expt_cfg['pi_calibration']
        experiment_cfg['rabi_while_flux']['flux_pi_calibration'] = False
        experiment_cfg['rabi_while_flux']['flux_probe'] = False

        experiment_cfg['rabi_while_flux']['start'] = 0.0
        experiment_cfg['rabi_while_flux']['stop'] = pi_gate['ge->ee'] * 4.0
        experiment_cfg['rabi_while_flux']['step'] = np.round(pi_gate['ge->ee'] * 4 / 100.0 ,1)

        experiment_cfg['rabi_while_flux']['acquisition_num'] = expt_cfg['acquisition_num']
        experiment_cfg['rabi_while_flux']['on_qubits'] = ['1']
        experiment_cfg['rabi_while_flux']['on_cavity'] = ['1']
        experiment_cfg['rabi_while_flux']['calibration_qubit'] = '1'
        experiment_cfg['rabi_while_flux']['flux_line'] = []
        experiment_cfg['rabi_while_flux']['flux_freq'] = 1.0
        experiment_cfg['rabi_while_flux']['phase'] = [0]

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('rabi_while_flux')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'rabi_while_flux')

        update_awg = False
        ########################################### Fitting Rabi
        print('Fitting Rabi data...')
        data_path_now = os.path.join(data_path, get_current_filename(data_path, 'rabi_while_flux', suffix='.h5'))
        with SlabFile(data_path_now) as a:
            pil, hpil = calibrate_rabi_while_flux(a, pi_length=pi_gate['ge->ee'], t1=1000)
        print('Calibrated pi length: %.2f ' % (pil))
        print('Calibrated pi/2 length: %.2f ' % (hpil))
        pi_gate['ge->ee'] = pil
        hpi_gate['ge->ee'] = hpil
        quantum_device_cfg['pulse_info']['1']['pi_ee_len'] = pil
        quantum_device_cfg['pulse_info']['1']['half_pi_ee_len'] = hpil

        ########################################### ramsey
        print('Calibrating |ge>-->|ee> Ramsey')
        experiment_cfg['ramsey_while_flux']['use_freq_amp_halfpi'] = [True, fq['ge->ee'], pi_amp['ge->ee'],
                                                                      hpi_gate['ge->ee'], 'charge1']
        experiment_cfg['ramsey_while_flux']['flux_amp'] = []
        experiment_cfg['ramsey_while_flux']['flux_probe'] = False
        experiment_cfg['ramsey_while_flux']['singleshot'] = False
        experiment_cfg['ramsey_while_flux']['ge_pi'] = ['2']
        experiment_cfg['ramsey_while_flux']['ef_pi'] = []
        experiment_cfg['ramsey_while_flux']['ge_pi2'] = []
        experiment_cfg['ramsey_while_flux']['pre_pulse'] = False
        experiment_cfg['ramsey_while_flux']['pi_calibration'] = expt_cfg['pi_calibration']
        experiment_cfg['ramsey_while_flux']['flux_pi_calibration'] = False

        experiment_cfg['ramsey_while_flux']['start'] = 0.0
        experiment_cfg['ramsey_while_flux']['stop'] = 1500.0
        experiment_cfg['ramsey_while_flux']['step'] = 5.0
        experiment_cfg['ramsey_while_flux']['ramsey_freq'] = 0.005

        experiment_cfg['ramsey_while_flux']['acquisition_num'] = ram_acq_no
        experiment_cfg['ramsey_while_flux']['on_qubits'] = ['1']
        experiment_cfg['ramsey_while_flux']['on_cavity'] = ['1']
        experiment_cfg['ramsey_while_flux']['flux_line'] = []
        experiment_cfg['ramsey_while_flux']['flux_freq'] = 1.0
        experiment_cfg['ramsey_while_flux']['phase'] = [0]

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('ramsey_while_flux')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'ramsey_while_flux')

        update_awg = False
        ########################################### Fitting Ramsey
        print('Fitting Ramsey data...')
        data_path_now = os.path.join(data_path,
                                     get_current_filename(data_path, 'ramsey_while_flux', suffix='.h5'))
        with SlabFile(data_path_now) as a:
            freq_new = calibrate_ramsey(a, pi_length=100, t2=1000)
        print('Calibrated |ge>-->|ee> transition: %s GHz' % (freq_new))
        fq['ge->ee'] = freq_new
        quantum_device_cfg['qubit']['qq_disp'] = freq_new - quantum_device_cfg['qubit']['1']['freq']

    print('Calibrating |ge>-->|ee> Rabi')
    experiment_cfg['rabi_while_flux']['amp'] = pi_amp['ge->ee']
    experiment_cfg['rabi_while_flux']['flux_amp'] = []
    experiment_cfg['rabi_while_flux']['ge_pi'] = ['2']
    experiment_cfg['rabi_while_flux']['ef_pi'] = []
    experiment_cfg['rabi_while_flux']['ge_pi2'] = []
    experiment_cfg['rabi_while_flux']['pre_pulse'] = False
    experiment_cfg['rabi_while_flux']['qubit_freq'] = fq['ge->ee']
    experiment_cfg['rabi_while_flux']['pi_calibration'] = expt_cfg['pi_calibration']
    experiment_cfg['rabi_while_flux']['flux_pi_calibration'] = False
    experiment_cfg['rabi_while_flux']['flux_probe'] = False

    experiment_cfg['rabi_while_flux']['start'] = 0.0
    experiment_cfg['rabi_while_flux']['stop'] = pi_gate['ge->ee'] * 4.0
    experiment_cfg['rabi_while_flux']['step'] = np.round(pi_gate['ge->ee'] * 4 / 100.0 ,1)

    experiment_cfg['rabi_while_flux']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['rabi_while_flux']['on_qubits'] = ['1']
    experiment_cfg['rabi_while_flux']['on_cavity'] = ['1']
    experiment_cfg['rabi_while_flux']['calibration_qubit'] = '1'
    experiment_cfg['rabi_while_flux']['flux_line'] = []
    experiment_cfg['rabi_while_flux']['flux_freq'] = 1.0
    experiment_cfg['rabi_while_flux']['phase'] = [0]

    ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
    sequences = ps.get_experiment_sequences('rabi_while_flux')
    update_awg = True

    exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
    exp.run_experiment(sequences, path, 'rabi_while_flux')

    update_awg = False
    ########################################### Fitting Rabi
    print('Fitting Rabi data...')
    data_path_now = os.path.join(data_path, get_current_filename(data_path, 'rabi_while_flux', suffix='.h5'))
    with SlabFile(data_path_now) as a:
        pil, hpil = calibrate_rabi_while_flux(a, pi_length=pi_gate['ge->ee'], t1=1000)
    print('Calibrated pi length: %.2f ' % (pil))
    print('Calibrated pi/2 length: %.2f ' % (hpil))
    pi_gate['ge->ee'] = pil
    hpi_gate['ge->ee'] = hpil
    quantum_device_cfg['pulse_info']['1']['pi_ee_len'] = pil
    quantum_device_cfg['pulse_info']['1']['half_pi_ee_len'] = hpil
    print('################################')
    print('current results:')
    for sss in string_list:
        print(sss, '  Freq:', fq[sss], '  pi:', pi_gate[sss], '  hpi:', hpi_gate[sss])
    print('qq_disp: ', fq['ge->ee'] - fq['gg->eg'])
    print('gf1_disp: ', fq['gf->ef'] - fq['gg->eg'])
    print('fg2_disp: ', fq['fg->fe'] - fq['gg->ge'])
    print('ef1_disp: ', fq['ee->fe'] - fq['eg->fg'])
    print('fe2_disp: ', fq['ee->ef'] - fq['ge->gf'])
    print('ff1_disp: ', fq['ef->ff'] - fq['eg->fg'])
    print('ff2_disp: ', fq['fe->ff'] - fq['ge->gf'])


#########################################################################
    #########################################################################################
    ## calibrating eg->ee
    print('Calibrating |eg>-->|ee> transition')
    for rround in range(expt_cfg['iterno']):
        print('############## Calibration Round No: ', rround + 1)
        ##################################### rabi
        print('Calibrating |eg>-->|ee> Rabi')
        experiment_cfg['rabi_while_flux']['amp'] = pi_amp['eg->ee']
        experiment_cfg['rabi_while_flux']['flux_amp'] = []
        experiment_cfg['rabi_while_flux']['ge_pi'] = ['1']
        experiment_cfg['rabi_while_flux']['ef_pi'] = []
        experiment_cfg['rabi_while_flux']['ge_pi2'] = []
        experiment_cfg['rabi_while_flux']['pre_pulse'] = False
        experiment_cfg['rabi_while_flux']['qubit_freq'] = fq['eg->ee']
        experiment_cfg['rabi_while_flux']['pi_calibration'] = expt_cfg['pi_calibration']
        experiment_cfg['rabi_while_flux']['flux_pi_calibration'] = False
        experiment_cfg['rabi_while_flux']['flux_probe'] = False

        experiment_cfg['rabi_while_flux']['start'] = 0.0
        experiment_cfg['rabi_while_flux']['stop'] = pi_gate['eg->ee'] * 4.0
        experiment_cfg['rabi_while_flux']['step'] = np.round(pi_gate['eg->ee'] * 4 / 100.0 ,1)

        experiment_cfg['rabi_while_flux']['acquisition_num'] = expt_cfg['acquisition_num']
        experiment_cfg['rabi_while_flux']['on_qubits'] = ['2']
        experiment_cfg['rabi_while_flux']['on_cavity'] = ['2']
        experiment_cfg['rabi_while_flux']['calibration_qubit'] = '2'
        experiment_cfg['rabi_while_flux']['flux_line'] = []
        experiment_cfg['rabi_while_flux']['flux_freq'] = 1.0
        experiment_cfg['rabi_while_flux']['phase'] = [0]

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('rabi_while_flux')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'rabi_while_flux')

        update_awg = False
        ########################################### Fitting Rabi
        print('Fitting Rabi data...')
        data_path_now = os.path.join(data_path, get_current_filename(data_path, 'rabi_while_flux', suffix='.h5'))
        with SlabFile(data_path_now) as a:
            pil, hpil = calibrate_rabi_while_flux(a, pi_length=pi_gate['eg->ee'], t1=1000)
        print('Calibrated pi length: %.2f ' % (pil))
        print('Calibrated pi/2 length: %.2f ' % (hpil))
        pi_gate['eg->ee'] = pil
        hpi_gate['eg->ee'] = hpil
        quantum_device_cfg['pulse_info']['2']['pi_ee_len'] = pil
        quantum_device_cfg['pulse_info']['2']['half_pi_ee_len'] = hpil

        ########################################### ramsey
        print('Calibrating |eg>-->|ee> Ramsey')
        experiment_cfg['ramsey_while_flux']['use_freq_amp_halfpi'] = [True, fq['eg->ee'], pi_amp['eg->ee'],
                                                                      hpi_gate['eg->ee'], 'charge2']
        experiment_cfg['ramsey_while_flux']['flux_amp'] = []
        experiment_cfg['ramsey_while_flux']['flux_probe'] = False
        experiment_cfg['ramsey_while_flux']['singleshot'] = False
        experiment_cfg['ramsey_while_flux']['ge_pi'] = ['1']
        experiment_cfg['ramsey_while_flux']['ef_pi'] = []
        experiment_cfg['ramsey_while_flux']['ge_pi2'] = []
        experiment_cfg['ramsey_while_flux']['pre_pulse'] = False
        experiment_cfg['ramsey_while_flux']['pi_calibration'] = expt_cfg['pi_calibration']
        experiment_cfg['ramsey_while_flux']['flux_pi_calibration'] = False

        experiment_cfg['ramsey_while_flux']['start'] = 0.0
        experiment_cfg['ramsey_while_flux']['stop'] = 1500.0
        experiment_cfg['ramsey_while_flux']['step'] = 5.0
        experiment_cfg['ramsey_while_flux']['ramsey_freq'] = 0.005

        experiment_cfg['ramsey_while_flux']['acquisition_num'] = ram_acq_no
        experiment_cfg['ramsey_while_flux']['on_qubits'] = ['2']
        experiment_cfg['ramsey_while_flux']['on_cavity'] = ['2']
        experiment_cfg['ramsey_while_flux']['flux_line'] = []
        experiment_cfg['ramsey_while_flux']['flux_freq'] = 1.0
        experiment_cfg['ramsey_while_flux']['phase'] = [0]

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('ramsey_while_flux')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'ramsey_while_flux')

        update_awg = False
        ########################################### Fitting Ramsey
        print('Fitting Ramsey data...')
        data_path_now = os.path.join(data_path,
                                     get_current_filename(data_path, 'ramsey_while_flux', suffix='.h5'))
        with SlabFile(data_path_now) as a:
            freq_new = calibrate_ramsey(a, pi_length=100, t2=1000)
        print('Calibrated |eg>-->|ee> transition: %s GHz' % (freq_new))
        fq['eg->ee'] = freq_new
        # quantum_device_cfg['qubit']['qq_disp'] = freq_new - quantum_device_cfg['qubit']['1']['freq']

    print('Calibrating |eg>-->|ee> Rabi')
    experiment_cfg['rabi_while_flux']['amp'] = pi_amp['eg->ee']
    experiment_cfg['rabi_while_flux']['flux_amp'] = []
    experiment_cfg['rabi_while_flux']['ge_pi'] = ['1']
    experiment_cfg['rabi_while_flux']['ef_pi'] = []
    experiment_cfg['rabi_while_flux']['ge_pi2'] = []
    experiment_cfg['rabi_while_flux']['pre_pulse'] = False
    experiment_cfg['rabi_while_flux']['qubit_freq'] = fq['eg->ee']
    experiment_cfg['rabi_while_flux']['pi_calibration'] = expt_cfg['pi_calibration']
    experiment_cfg['rabi_while_flux']['flux_pi_calibration'] = False
    experiment_cfg['rabi_while_flux']['flux_probe'] = False

    experiment_cfg['rabi_while_flux']['start'] = 0.0
    experiment_cfg['rabi_while_flux']['stop'] = pi_gate['eg->ee'] * 4.0
    experiment_cfg['rabi_while_flux']['step'] = np.round(pi_gate['eg->ee'] * 4 / 100.0 ,1)

    experiment_cfg['rabi_while_flux']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['rabi_while_flux']['on_qubits'] = ['2']
    experiment_cfg['rabi_while_flux']['on_cavity'] = ['2']
    experiment_cfg['rabi_while_flux']['calibration_qubit'] = '2'
    experiment_cfg['rabi_while_flux']['flux_line'] = []
    experiment_cfg['rabi_while_flux']['flux_freq'] = 1.0
    experiment_cfg['rabi_while_flux']['phase'] = [0]

    ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
    sequences = ps.get_experiment_sequences('rabi_while_flux')
    update_awg = True

    exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
    exp.run_experiment(sequences, path, 'rabi_while_flux')

    update_awg = False
    ########################################### Fitting Rabi
    print('Fitting Rabi data...')
    data_path_now = os.path.join(data_path, get_current_filename(data_path, 'rabi_while_flux', suffix='.h5'))
    with SlabFile(data_path_now) as a:
        pil, hpil = calibrate_rabi_while_flux(a, pi_length=pi_gate['eg->ee'], t1=1000)
    print('Calibrated pi length: %.2f ' % (pil))
    print('Calibrated pi/2 length: %.2f ' % (hpil))
    pi_gate['eg->ee'] = pil
    hpi_gate['eg->ee'] = hpil
    quantum_device_cfg['pulse_info']['2']['pi_ee_len'] = pil
    quantum_device_cfg['pulse_info']['2']['half_pi_ee_len'] = hpil
    print('################################')
    print('current results:')
    for sss in string_list:
        print(sss, '  Freq:', fq[sss], '  pi:', pi_gate[sss], '  hpi:', hpi_gate[sss])
    print('qq_disp: ', fq['ge->ee'] - fq['gg->eg'])
    print('gf1_disp: ', fq['gf->ef'] - fq['gg->eg'])
    print('fg2_disp: ', fq['fg->fe'] - fq['gg->ge'])
    print('ef1_disp: ', fq['ee->fe'] - fq['eg->fg'])
    print('fe2_disp: ', fq['ee->ef'] - fq['ge->gf'])
    print('ff1_disp: ', fq['ef->ff'] - fq['eg->fg'])
    print('ff2_disp: ', fq['fe->ff'] - fq['ge->gf'])



    ########################################################################################
    ## calibrating gf->ef
    print('Calibrating |gf>-->|ef> transition')
    for rround in range(expt_cfg['iterno']):
        print('############## Calibration Round No: ', rround + 1)
        ##################################### rabi
        print('Calibrating |gf>-->|ef> Rabi')
        experiment_cfg['rabi_while_flux']['amp'] = pi_amp['gf->ef']
        experiment_cfg['rabi_while_flux']['flux_amp'] = []
        experiment_cfg['rabi_while_flux']['ge_pi'] = []
        experiment_cfg['rabi_while_flux']['ef_pi'] = []
        experiment_cfg['rabi_while_flux']['ge_pi2'] = []
        experiment_cfg['rabi_while_flux']['pre_pulse'] = True
        quantum_device_cfg['pre_pulse_info']['times_prep']=[[pi_gate['gg->ge'], 0.0], [pi_gate['ge->gf'], 0.0]]
        quantum_device_cfg['pre_pulse_info']['charge1_amps_prep'] = [[0.0, 0.0], [0.0, 0.0]]
        quantum_device_cfg['pre_pulse_info']['charge1_freqs_prep'] = [[0.0, 0.0], [0.0, 0.0]]
        quantum_device_cfg['pre_pulse_info']['charge1_phases_prep'] = [[0.0, 0.0], [0.0, 0.0]]

        quantum_device_cfg['pre_pulse_info']['charge2_amps_prep'] = [[pi_amp['gg->ge'], 0.0], [pi_amp['ge->gf'], 0.0]]
        quantum_device_cfg['pre_pulse_info']['charge2_freqs_prep'] = [[fq['gg->ge'], 0.0], [fq['ge->gf'], 0.0]]
        quantum_device_cfg['pre_pulse_info']['charge2_phases_prep'] = [[0.0, 0.0], [0.0, 0.0]]

        quantum_device_cfg['pre_pulse_info']['flux1_amps_prep'] = [[0.0, 0.0], [0.0, 0.0]]
        quantum_device_cfg['pre_pulse_info']['flux1_freqs_prep'] = [[0.0, 0.0], [0.0, 0.0]]
        quantum_device_cfg['pre_pulse_info']['flux1_phases_prep'] = [[0.0, 0.0], [0.0, 0.0]]

        quantum_device_cfg['pre_pulse_info']['flux2_amps_prep'] = [[0.0, 0.0], [0.0, 0.0]]
        quantum_device_cfg['pre_pulse_info']['flux2_freqs_prep'] = [[0.0, 0.0], [0.0, 0.0]]
        quantum_device_cfg['pre_pulse_info']['flux2_phases_prep'] = [[0.0, 0.0], [0.0, 0.0]]
        
        
        experiment_cfg['rabi_while_flux']['qubit_freq'] = fq['gf->ef']
        experiment_cfg['rabi_while_flux']['pi_calibration'] = expt_cfg['pi_calibration']
        experiment_cfg['rabi_while_flux']['flux_pi_calibration'] = False
        experiment_cfg['rabi_while_flux']['flux_probe'] = False

        experiment_cfg['rabi_while_flux']['start'] = 0.0
        experiment_cfg['rabi_while_flux']['stop'] = pi_gate['gf->ef'] * 4.0
        experiment_cfg['rabi_while_flux']['step'] = np.round(pi_gate['gf->ef'] * 4 / 100.0 ,1)

        experiment_cfg['rabi_while_flux']['acquisition_num'] = expt_cfg['acquisition_num']
        experiment_cfg['rabi_while_flux']['on_qubits'] = ['1']
        experiment_cfg['rabi_while_flux']['on_cavity'] = ['1']
        experiment_cfg['rabi_while_flux']['calibration_qubit'] = '1'
        experiment_cfg['rabi_while_flux']['flux_line'] = []
        experiment_cfg['rabi_while_flux']['flux_freq'] = 1.0
        experiment_cfg['rabi_while_flux']['phase'] = [0]

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('rabi_while_flux')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'rabi_while_flux')

        update_awg = False
        ########################################### Fitting Rabi
        print('Fitting Rabi data...')
        data_path_now = os.path.join(data_path, get_current_filename(data_path, 'rabi_while_flux', suffix='.h5'))
        with SlabFile(data_path_now) as a:
            pil, hpil = calibrate_rabi_while_flux(a, pi_length=pi_gate['gf->ef'], t1=1000)
        print('Calibrated pi length: %.2f ' % (pil))
        print('Calibrated pi/2 length: %.2f ' % (hpil))
        pi_gate['gf->ef'] = pil
        hpi_gate['gf->ef'] = hpil
        quantum_device_cfg['pulse_info']['1']['pi_gf_len'] = pil
        quantum_device_cfg['pulse_info']['1']['half_pi_gf_len'] = hpil

        ########################################### ramsey
        print('Calibrating |gf>-->|ef> Ramsey')
        experiment_cfg['ramsey_while_flux']['use_freq_amp_halfpi'] = [True, fq['gf->ef'], pi_amp['gf->ef'],
                                                                      hpi_gate['gf->ef'], 'charge1']
        experiment_cfg['ramsey_while_flux']['flux_amp'] = []
        experiment_cfg['ramsey_while_flux']['flux_probe'] = False
        experiment_cfg['ramsey_while_flux']['singleshot'] = False
        experiment_cfg['ramsey_while_flux']['ge_pi'] = []
        experiment_cfg['ramsey_while_flux']['ef_pi'] = []
        experiment_cfg['ramsey_while_flux']['ge_pi2'] = []
        experiment_cfg['ramsey_while_flux']['pre_pulse'] = True
        experiment_cfg['ramsey_while_flux']['pi_calibration'] = expt_cfg['pi_calibration']
        experiment_cfg['ramsey_while_flux']['flux_pi_calibration'] = False

        experiment_cfg['ramsey_while_flux']['start'] = 0.0
        experiment_cfg['ramsey_while_flux']['stop'] = 1500.0
        experiment_cfg['ramsey_while_flux']['step'] = 5.0
        experiment_cfg['ramsey_while_flux']['ramsey_freq'] = 0.005

        experiment_cfg['ramsey_while_flux']['acquisition_num'] = ram_acq_no
        experiment_cfg['ramsey_while_flux']['on_qubits'] = ['1']
        experiment_cfg['ramsey_while_flux']['on_cavity'] = ['1']
        experiment_cfg['ramsey_while_flux']['flux_line'] = []
        experiment_cfg['ramsey_while_flux']['flux_freq'] = 1.0
        experiment_cfg['ramsey_while_flux']['phase'] = [0]

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('ramsey_while_flux')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'ramsey_while_flux')

        update_awg = False
        ########################################### Fitting Ramsey
        print('Fitting Ramsey data...')
        data_path_now = os.path.join(data_path,
                                     get_current_filename(data_path, 'ramsey_while_flux', suffix='.h5'))
        with SlabFile(data_path_now) as a:
            freq_new = calibrate_ramsey(a, pi_length=100, t2=1000)
        print('Calibrated |gf>-->|ef> transition: %s GHz' % (freq_new))
        fq['gf->ef'] = freq_new
        quantum_device_cfg['qubit']['gf1_disp'] = freq_new - quantum_device_cfg['qubit']['1']['freq']

    print('Calibrating |gf>-->|ef> Rabi')
    experiment_cfg['rabi_while_flux']['amp'] = pi_amp['gf->ef']
    experiment_cfg['rabi_while_flux']['flux_amp'] = []
    experiment_cfg['rabi_while_flux']['ge_pi'] = []
    experiment_cfg['rabi_while_flux']['ef_pi'] = []
    experiment_cfg['rabi_while_flux']['ge_pi2'] = []
    experiment_cfg['rabi_while_flux']['pre_pulse'] = True
    experiment_cfg['rabi_while_flux']['qubit_freq'] = fq['gf->ef']
    experiment_cfg['rabi_while_flux']['pi_calibration'] = expt_cfg['pi_calibration']
    experiment_cfg['rabi_while_flux']['flux_pi_calibration'] = False
    experiment_cfg['rabi_while_flux']['flux_probe'] = False

    experiment_cfg['rabi_while_flux']['start'] = 0.0
    experiment_cfg['rabi_while_flux']['stop'] = pi_gate['gf->ef'] * 4.0
    experiment_cfg['rabi_while_flux']['step'] = np.round(pi_gate['gf->ef'] * 4 / 100.0 ,1)

    experiment_cfg['rabi_while_flux']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['rabi_while_flux']['on_qubits'] = ['1']
    experiment_cfg['rabi_while_flux']['on_cavity'] = ['1']
    experiment_cfg['rabi_while_flux']['calibration_qubit'] = '1'
    experiment_cfg['rabi_while_flux']['flux_line'] = []
    experiment_cfg['rabi_while_flux']['flux_freq'] = 1.0
    experiment_cfg['rabi_while_flux']['phase'] = [0]

    ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
    sequences = ps.get_experiment_sequences('rabi_while_flux')
    update_awg = True

    exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
    exp.run_experiment(sequences, path, 'rabi_while_flux')

    update_awg = False
    ########################################### Fitting Rabi
    print('Fitting Rabi data...')
    data_path_now = os.path.join(data_path, get_current_filename(data_path, 'rabi_while_flux', suffix='.h5'))
    with SlabFile(data_path_now) as a:
        pil, hpil = calibrate_rabi_while_flux(a, pi_length=pi_gate['gf->ef'], t1=1000)
    print('Calibrated pi length: %.2f ' % (pil))
    print('Calibrated pi/2 length: %.2f ' % (hpil))
    pi_gate['gf->ef'] = pil
    hpi_gate['gf->ef'] = hpil
    quantum_device_cfg['pulse_info']['1']['pi_gf_len'] = pil
    quantum_device_cfg['pulse_info']['1']['half_pi_gf_len'] = hpil
    print('################################')
    print('current results:')
    for sss in string_list:
        print(sss, '  Freq:', fq[sss], '  pi:', pi_gate[sss], '  hpi:', hpi_gate[sss])
    print('qq_disp: ', fq['ge->ee'] - fq['gg->eg'])
    print('gf1_disp: ', fq['gf->ef'] - fq['gg->eg'])
    print('fg2_disp: ', fq['fg->fe'] - fq['gg->ge'])
    print('ef1_disp: ', fq['ee->fe'] - fq['eg->fg'])
    print('fe2_disp: ', fq['ee->ef'] - fq['ge->gf'])
    print('ff1_disp: ', fq['ef->ff'] - fq['eg->fg'])
    print('ff2_disp: ', fq['fe->ff'] - fq['ge->gf'])


    ########################################################################################
    ## calibrating fg->fe
    print('Calibrating |fg>-->|fe> transition')
    for rround in range(expt_cfg['iterno']):
        print('############## Calibration Round No: ', rround + 1)
        ##################################### rabi
        print('Calibrating |fg>-->|fe> Rabi')
        experiment_cfg['rabi_while_flux']['amp'] = pi_amp['fg->fe']
        experiment_cfg['rabi_while_flux']['flux_amp'] = []
        experiment_cfg['rabi_while_flux']['ge_pi'] = []
        experiment_cfg['rabi_while_flux']['ef_pi'] = []
        experiment_cfg['rabi_while_flux']['ge_pi2'] = []
        experiment_cfg['rabi_while_flux']['pre_pulse'] = True
        quantum_device_cfg['pre_pulse_info']['times_prep'] = [[pi_gate['gg->eg'], 0.0], [pi_gate['eg->fg'], 0.0]]

        quantum_device_cfg['pre_pulse_info']['charge1_amps_prep'] = [[pi_amp['gg->eg'], 0.0], [pi_amp['eg->fg'], 0.0]]
        quantum_device_cfg['pre_pulse_info']['charge1_freqs_prep'] = [[fq['gg->eg'], 0.0], [fq['eg->fg'], 0.0]]
        quantum_device_cfg['pre_pulse_info']['charge1_phases_prep'] = [[0.0, 0.0], [0.0, 0.0]]

        quantum_device_cfg['pre_pulse_info']['charge2_amps_prep'] = [[0.0, 0.0], [0.0, 0.0]]
        quantum_device_cfg['pre_pulse_info']['charge2_freqs_prep'] = [[0.0, 0.0], [0.0, 0.0]]
        quantum_device_cfg['pre_pulse_info']['charge2_phases_prep'] = [[0.0, 0.0], [0.0, 0.0]]



        quantum_device_cfg['pre_pulse_info']['flux1_amps_prep'] = [[0.0, 0.0], [0.0, 0.0]]
        quantum_device_cfg['pre_pulse_info']['flux1_freqs_prep'] = [[0.0, 0.0], [0.0, 0.0]]
        quantum_device_cfg['pre_pulse_info']['flux1_phases_prep'] = [[0.0, 0.0], [0.0, 0.0]]

        quantum_device_cfg['pre_pulse_info']['flux2_amps_prep'] = [[0.0, 0.0], [0.0, 0.0]]
        quantum_device_cfg['pre_pulse_info']['flux2_freqs_prep'] = [[0.0, 0.0], [0.0, 0.0]]
        quantum_device_cfg['pre_pulse_info']['flux2_phases_prep'] = [[0.0, 0.0], [0.0, 0.0]]

        experiment_cfg['rabi_while_flux']['qubit_freq'] = fq['fg->fe']
        experiment_cfg['rabi_while_flux']['pi_calibration'] = expt_cfg['pi_calibration']
        experiment_cfg['rabi_while_flux']['flux_pi_calibration'] = False
        experiment_cfg['rabi_while_flux']['flux_probe'] = False

        experiment_cfg['rabi_while_flux']['start'] = 0.0
        experiment_cfg['rabi_while_flux']['stop'] = pi_gate['fg->fe'] * 4.0
        experiment_cfg['rabi_while_flux']['step'] = np.round(pi_gate['fg->fe'] * 4 / 100.0 ,1)

        experiment_cfg['rabi_while_flux']['acquisition_num'] = expt_cfg['acquisition_num']
        experiment_cfg['rabi_while_flux']['on_qubits'] = ['2']
        experiment_cfg['rabi_while_flux']['on_cavity'] = ['2']
        experiment_cfg['rabi_while_flux']['calibration_qubit'] = '2'
        experiment_cfg['rabi_while_flux']['flux_line'] = []
        experiment_cfg['rabi_while_flux']['flux_freq'] = 1.0
        experiment_cfg['rabi_while_flux']['phase'] = [0]

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('rabi_while_flux')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'rabi_while_flux')

        update_awg = False
        ########################################### Fitting Rabi
        print('Fitting Rabi data...')
        data_path_now = os.path.join(data_path, get_current_filename(data_path, 'rabi_while_flux', suffix='.h5'))
        with SlabFile(data_path_now) as a:
            pil, hpil = calibrate_rabi_while_flux(a, pi_length=pi_gate['fg->fe'], t1=1000)
        print('Calibrated pi length: %.2f ' % (pil))
        print('Calibrated pi/2 length: %.2f ' % (hpil))
        pi_gate['fg->fe'] = pil
        hpi_gate['fg->fe'] = hpil
        quantum_device_cfg['pulse_info']['2']['pi_gf_len'] = pil
        quantum_device_cfg['pulse_info']['2']['half_pi_gf_len'] = hpil

        ########################################### ramsey
        print('Calibrating |fg>-->|fe Ramsey')
        experiment_cfg['ramsey_while_flux']['use_freq_amp_halfpi'] = [True, fq['fg->fe'], pi_amp['fg->fe'],
                                                                      hpi_gate['fg->fe'], 'charge2']
        experiment_cfg['ramsey_while_flux']['flux_amp'] = []
        experiment_cfg['ramsey_while_flux']['flux_probe'] = False
        experiment_cfg['ramsey_while_flux']['singleshot'] = False
        experiment_cfg['ramsey_while_flux']['ge_pi'] = []
        experiment_cfg['ramsey_while_flux']['ef_pi'] = []
        experiment_cfg['ramsey_while_flux']['ge_pi2'] = []
        experiment_cfg['ramsey_while_flux']['pre_pulse'] = True
        experiment_cfg['ramsey_while_flux']['pi_calibration'] = expt_cfg['pi_calibration']
        experiment_cfg['ramsey_while_flux']['flux_pi_calibration'] = False

        experiment_cfg['ramsey_while_flux']['start'] = 0.0
        experiment_cfg['ramsey_while_flux']['stop'] = 1500.0
        experiment_cfg['ramsey_while_flux']['step'] = 5.0
        experiment_cfg['ramsey_while_flux']['ramsey_freq'] = 0.005

        experiment_cfg['ramsey_while_flux']['acquisition_num'] = ram_acq_no
        experiment_cfg['ramsey_while_flux']['on_qubits'] = ['2']
        experiment_cfg['ramsey_while_flux']['on_cavity'] = ['2']
        experiment_cfg['ramsey_while_flux']['flux_line'] = []
        experiment_cfg['ramsey_while_flux']['flux_freq'] = 1.0
        experiment_cfg['ramsey_while_flux']['phase'] = [0]

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('ramsey_while_flux')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'ramsey_while_flux')

        update_awg = False
        ########################################### Fitting Ramsey
        print('Fitting Ramsey data...')
        data_path_now = os.path.join(data_path,
                                     get_current_filename(data_path, 'ramsey_while_flux', suffix='.h5'))
        with SlabFile(data_path_now) as a:
            freq_new = calibrate_ramsey(a, pi_length=100, t2=1000)
        print('Calibrated |fg>-->|fe> transition: %s GHz' % (freq_new))
        fq['fg->fe'] = freq_new
        quantum_device_cfg['qubit']['fg2_disp'] = freq_new - quantum_device_cfg['qubit']['2']['freq']

    print('Calibrating |fg>-->|fe> Rabi')
    experiment_cfg['rabi_while_flux']['amp'] = pi_amp['fg->fe']
    experiment_cfg['rabi_while_flux']['flux_amp'] = []
    experiment_cfg['rabi_while_flux']['ge_pi'] = []
    experiment_cfg['rabi_while_flux']['ef_pi'] = []
    experiment_cfg['rabi_while_flux']['ge_pi2'] = []
    experiment_cfg['rabi_while_flux']['pre_pulse'] = True
    experiment_cfg['rabi_while_flux']['qubit_freq'] = fq['fg->fe']
    experiment_cfg['rabi_while_flux']['pi_calibration'] = expt_cfg['pi_calibration']
    experiment_cfg['rabi_while_flux']['flux_pi_calibration'] = False
    experiment_cfg['rabi_while_flux']['flux_probe'] = False

    experiment_cfg['rabi_while_flux']['start'] = 0.0
    experiment_cfg['rabi_while_flux']['stop'] = pi_gate['fg->fe'] * 4.0
    experiment_cfg['rabi_while_flux']['step'] = np.round(pi_gate['fg->fe'] * 4 / 100.0 ,1)

    experiment_cfg['rabi_while_flux']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['rabi_while_flux']['on_qubits'] = ['2']
    experiment_cfg['rabi_while_flux']['on_cavity'] = ['2']
    experiment_cfg['rabi_while_flux']['calibration_qubit'] = '2'
    experiment_cfg['rabi_while_flux']['flux_line'] = []
    experiment_cfg['rabi_while_flux']['flux_freq'] = 1.0
    experiment_cfg['rabi_while_flux']['phase'] = [0]

    ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
    sequences = ps.get_experiment_sequences('rabi_while_flux')
    update_awg = True

    exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
    exp.run_experiment(sequences, path, 'rabi_while_flux')

    update_awg = False
    ########################################### Fitting Rabi
    print('Fitting Rabi data...')
    data_path_now = os.path.join(data_path, get_current_filename(data_path, 'rabi_while_flux', suffix='.h5'))
    with SlabFile(data_path_now) as a:
        pil, hpil = calibrate_rabi_while_flux(a, pi_length=pi_gate['fg->fe'], t1=1000)
    print('Calibrated pi length: %.2f ' % (pil))
    print('Calibrated pi/2 length: %.2f ' % (hpil))
    pi_gate['fg->fe'] = pil
    hpi_gate['fg->fe'] = hpil
    quantum_device_cfg['pulse_info']['2']['pi_gf_len'] = pil
    quantum_device_cfg['pulse_info']['2']['half_pi_gf_len'] = hpil
    print('################################')
    print('current results:')
    for sss in string_list:
        print(sss, '  Freq:', fq[sss], '  pi:', pi_gate[sss], '  hpi:', hpi_gate[sss])
    print('qq_disp: ', fq['ge->ee'] - fq['gg->eg'])
    print('gf1_disp: ', fq['gf->ef'] - fq['gg->eg'])
    print('fg2_disp: ', fq['fg->fe'] - fq['gg->ge'])
    print('ef1_disp: ', fq['ee->fe'] - fq['eg->fg'])
    print('fe2_disp: ', fq['ee->ef'] - fq['ge->gf'])
    print('ff1_disp: ', fq['ef->ff'] - fq['eg->fg'])
    print('ff2_disp: ', fq['fe->ff'] - fq['ge->gf'])



    ########################################################################################
    ## calibrating ee->fe
    print('Calibrating |ee>-->|fe> transition')
    for rround in range(expt_cfg['iterno']):
        print('############## Calibration Round No: ', rround + 1)
        ##################################### rabi
        print('Calibrating |ee>-->|fe> Rabi')
        experiment_cfg['rabi_while_flux']['amp'] = pi_amp['ee->fe']
        experiment_cfg['rabi_while_flux']['flux_amp'] = []
        experiment_cfg['rabi_while_flux']['ge_pi'] = []
        experiment_cfg['rabi_while_flux']['ef_pi'] = []
        experiment_cfg['rabi_while_flux']['ge_pi2'] = []
        experiment_cfg['rabi_while_flux']['pre_pulse'] = True
        quantum_device_cfg['pre_pulse_info']['times_prep'] = [[pi_gate['gg->eg'], 0.0], [pi_gate['eg->ee'], 0.0]]

        quantum_device_cfg['pre_pulse_info']['charge1_amps_prep'] = [[pi_amp['gg->eg'], 0.0], [0.0, 0.0]]
        quantum_device_cfg['pre_pulse_info']['charge1_freqs_prep'] = [[fq['gg->eg'], 0.0], [0.0, 0.0]]
        quantum_device_cfg['pre_pulse_info']['charge1_phases_prep'] = [[0.0, 0.0], [0.0, 0.0]]

        quantum_device_cfg['pre_pulse_info']['charge2_amps_prep'] = [[0.0, 0.0], [pi_amp['eg->ee'], 0.0]]
        quantum_device_cfg['pre_pulse_info']['charge2_freqs_prep'] = [[0.0, 0.0], [fq['eg->ee'], 0.0]]
        quantum_device_cfg['pre_pulse_info']['charge2_phases_prep'] = [[0.0, 0.0], [0.0, 0.0]]

        quantum_device_cfg['pre_pulse_info']['flux1_amps_prep'] = [[0.0, 0.0], [0.0, 0.0]]
        quantum_device_cfg['pre_pulse_info']['flux1_freqs_prep'] = [[0.0, 0.0], [0.0, 0.0]]
        quantum_device_cfg['pre_pulse_info']['flux1_phases_prep'] = [[0.0, 0.0], [0.0, 0.0]]

        quantum_device_cfg['pre_pulse_info']['flux2_amps_prep'] = [[0.0, 0.0], [0.0, 0.0]]
        quantum_device_cfg['pre_pulse_info']['flux2_freqs_prep'] = [[0.0, 0.0], [0.0, 0.0]]
        quantum_device_cfg['pre_pulse_info']['flux2_phases_prep'] = [[0.0, 0.0], [0.0, 0.0]]

        experiment_cfg['rabi_while_flux']['qubit_freq'] = fq['ee->fe']
        experiment_cfg['rabi_while_flux']['pi_calibration'] = expt_cfg['pi_calibration']
        experiment_cfg['rabi_while_flux']['flux_pi_calibration'] = False
        experiment_cfg['rabi_while_flux']['flux_probe'] = False

        experiment_cfg['rabi_while_flux']['start'] = 0.0
        experiment_cfg['rabi_while_flux']['stop'] = pi_gate['ee->fe'] * 4.0
        experiment_cfg['rabi_while_flux']['step'] = np.round(pi_gate['ee->fe'] * 4 / 100.0 ,1)

        experiment_cfg['rabi_while_flux']['acquisition_num'] = expt_cfg['acquisition_num']
        experiment_cfg['rabi_while_flux']['on_qubits'] = ['1']
        experiment_cfg['rabi_while_flux']['on_cavity'] = ['1']
        experiment_cfg['rabi_while_flux']['calibration_qubit'] = '1'
        experiment_cfg['rabi_while_flux']['flux_line'] = []
        experiment_cfg['rabi_while_flux']['flux_freq'] = 1.0
        experiment_cfg['rabi_while_flux']['phase'] = [0]

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('rabi_while_flux')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'rabi_while_flux')

        update_awg = False
        ########################################### Fitting Rabi
        print('Fitting Rabi data...')
        data_path_now = os.path.join(data_path, get_current_filename(data_path, 'rabi_while_flux', suffix='.h5'))
        with SlabFile(data_path_now) as a:
            pil, hpil = calibrate_rabi_while_flux(a, pi_length=pi_gate['ee->fe'], t1=1000)
        print('Calibrated pi length: %.2f ' % (pil))
        print('Calibrated pi/2 length: %.2f ' % (hpil))
        pi_gate['ee->fe'] = pil
        hpi_gate['ee->fe'] = hpil
        quantum_device_cfg['pulse_info']['1']['pi_ef_e_len'] = pil
        quantum_device_cfg['pulse_info']['1']['half_pi_ef_e_len'] = hpil

        ########################################### ramsey
        print('Calibrating |ee>-->|fe> Ramsey')
        experiment_cfg['ramsey_while_flux']['use_freq_amp_halfpi'] = [True, fq['ee->fe'], pi_amp['ee->fe'],
                                                                      hpi_gate['ee->fe'], 'charge1']
        experiment_cfg['ramsey_while_flux']['flux_amp'] = []
        experiment_cfg['ramsey_while_flux']['flux_probe'] = False
        experiment_cfg['ramsey_while_flux']['singleshot'] = False
        experiment_cfg['ramsey_while_flux']['ge_pi'] = []
        experiment_cfg['ramsey_while_flux']['ef_pi'] = []
        experiment_cfg['ramsey_while_flux']['ge_pi2'] = []
        experiment_cfg['ramsey_while_flux']['pre_pulse'] = True
        experiment_cfg['ramsey_while_flux']['pi_calibration'] = expt_cfg['pi_calibration']
        experiment_cfg['ramsey_while_flux']['flux_pi_calibration'] = False

        experiment_cfg['ramsey_while_flux']['start'] = 0.0
        experiment_cfg['ramsey_while_flux']['stop'] = 1500.0
        experiment_cfg['ramsey_while_flux']['step'] = 5.0
        experiment_cfg['ramsey_while_flux']['ramsey_freq'] = 0.005

        experiment_cfg['ramsey_while_flux']['acquisition_num'] = ram_acq_no
        experiment_cfg['ramsey_while_flux']['on_qubits'] = ['1']
        experiment_cfg['ramsey_while_flux']['on_cavity'] = ['1']
        experiment_cfg['ramsey_while_flux']['flux_line'] = []
        experiment_cfg['ramsey_while_flux']['flux_freq'] = 1.0
        experiment_cfg['ramsey_while_flux']['phase'] = [0]

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('ramsey_while_flux')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'ramsey_while_flux')

        update_awg = False
        ########################################### Fitting Ramsey
        print('Fitting Ramsey data...')
        data_path_now = os.path.join(data_path,
                                     get_current_filename(data_path, 'ramsey_while_flux', suffix='.h5'))
        with SlabFile(data_path_now) as a:
            freq_new = calibrate_ramsey(a, pi_length=100, t2=1000)
        print('Calibrated |ee>-->|fe> transition: %s GHz' % (freq_new))
        fq['ee->fe'] = freq_new
        quantum_device_cfg['qubit']['ef1_disp'] = freq_new - quantum_device_cfg['qubit']['1']['freq']

    print('Calibrating |ee>-->|fe> Rabi')
    experiment_cfg['rabi_while_flux']['amp'] = pi_amp['ee->fe']
    experiment_cfg['rabi_while_flux']['flux_amp'] = []
    experiment_cfg['rabi_while_flux']['ge_pi'] = []
    experiment_cfg['rabi_while_flux']['ef_pi'] = []
    experiment_cfg['rabi_while_flux']['ge_pi2'] = []
    experiment_cfg['rabi_while_flux']['pre_pulse'] = True
    experiment_cfg['rabi_while_flux']['qubit_freq'] = fq['ee->fe']
    experiment_cfg['rabi_while_flux']['pi_calibration'] = expt_cfg['pi_calibration']
    experiment_cfg['rabi_while_flux']['flux_pi_calibration'] = False
    experiment_cfg['rabi_while_flux']['flux_probe'] = False

    experiment_cfg['rabi_while_flux']['start'] = 0.0
    experiment_cfg['rabi_while_flux']['stop'] = pi_gate['ee->fe'] * 4.0
    experiment_cfg['rabi_while_flux']['step'] = np.round(pi_gate['ee->fe'] * 4 / 100.0 ,1)

    experiment_cfg['rabi_while_flux']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['rabi_while_flux']['on_qubits'] = ['1']
    experiment_cfg['rabi_while_flux']['on_cavity'] = ['1']
    experiment_cfg['rabi_while_flux']['calibration_qubit'] = '1'
    experiment_cfg['rabi_while_flux']['flux_line'] = []
    experiment_cfg['rabi_while_flux']['flux_freq'] = 1.0
    experiment_cfg['rabi_while_flux']['phase'] = [0]

    ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
    sequences = ps.get_experiment_sequences('rabi_while_flux')
    update_awg = True

    exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
    exp.run_experiment(sequences, path, 'rabi_while_flux')

    update_awg = False
    ########################################### Fitting Rabi
    print('Fitting Rabi data...')
    data_path_now = os.path.join(data_path, get_current_filename(data_path, 'rabi_while_flux', suffix='.h5'))
    with SlabFile(data_path_now) as a:
        pil, hpil = calibrate_rabi_while_flux(a, pi_length=pi_gate['ee->fe'], t1=1000)
    print('Calibrated pi length: %.2f ' % (pil))
    print('Calibrated pi/2 length: %.2f ' % (hpil))
    pi_gate['ee->fe'] = pil
    hpi_gate['ee->fe'] = hpil
    quantum_device_cfg['pulse_info']['1']['pi_ef_e_len'] = pil
    quantum_device_cfg['pulse_info']['1']['half_pi_ef_e_len'] = hpil

    print('################################')
    print('current results:')
    for sss in string_list:
        print(sss, '  Freq:', fq[sss], '  pi:', pi_gate[sss], '  hpi:', hpi_gate[sss])
    print('qq_disp: ', fq['ge->ee'] - fq['gg->eg'])
    print('gf1_disp: ', fq['gf->ef'] - fq['gg->eg'])
    print('fg2_disp: ', fq['fg->fe'] - fq['gg->ge'])
    print('ef1_disp: ', fq['ee->fe'] - fq['eg->fg'])
    print('fe2_disp: ', fq['ee->ef'] - fq['ge->gf'])
    print('ff1_disp: ', fq['ef->ff'] - fq['eg->fg'])
    print('ff2_disp: ', fq['fe->ff'] - fq['ge->gf'])

    ########################################################################################
    ## calibrating ee->ef
    print('Calibrating |ee>-->|ef> transition')
    for rround in range(expt_cfg['iterno']):
        print('############## Calibration Round No: ', rround + 1)
        ##################################### rabi
        print('Calibrating |ee>-->|ef> Rabi')
        experiment_cfg['rabi_while_flux']['amp'] = pi_amp['ee->ef']
        experiment_cfg['rabi_while_flux']['flux_amp'] = []
        experiment_cfg['rabi_while_flux']['ge_pi'] = []
        experiment_cfg['rabi_while_flux']['ef_pi'] = []
        experiment_cfg['rabi_while_flux']['ge_pi2'] = []
        experiment_cfg['rabi_while_flux']['pre_pulse'] = True
        quantum_device_cfg['pre_pulse_info']['times_prep'] = [[pi_gate['gg->eg'], 0.0], [pi_gate['eg->ee'], 0.0]]

        quantum_device_cfg['pre_pulse_info']['charge1_amps_prep'] = [[pi_amp['gg->eg'], 0.0], [0.0, 0.0]]
        quantum_device_cfg['pre_pulse_info']['charge1_freqs_prep'] = [[fq['gg->eg'], 0.0], [0.0, 0.0]]
        quantum_device_cfg['pre_pulse_info']['charge1_phases_prep'] = [[0.0, 0.0], [0.0, 0.0]]

        quantum_device_cfg['pre_pulse_info']['charge2_amps_prep'] = [[0.0, 0.0], [pi_amp['eg->ee'], 0.0]]
        quantum_device_cfg['pre_pulse_info']['charge2_freqs_prep'] = [[0.0, 0.0], [fq['eg->ee'], 0.0]]
        quantum_device_cfg['pre_pulse_info']['charge2_phases_prep'] = [[0.0, 0.0], [0.0, 0.0]]

        quantum_device_cfg['pre_pulse_info']['flux1_amps_prep'] = [[0.0, 0.0], [0.0, 0.0]]
        quantum_device_cfg['pre_pulse_info']['flux1_freqs_prep'] = [[0.0, 0.0], [0.0, 0.0]]
        quantum_device_cfg['pre_pulse_info']['flux1_phases_prep'] = [[0.0, 0.0], [0.0, 0.0]]

        quantum_device_cfg['pre_pulse_info']['flux2_amps_prep'] = [[0.0, 0.0], [0.0, 0.0]]
        quantum_device_cfg['pre_pulse_info']['flux2_freqs_prep'] = [[0.0, 0.0], [0.0, 0.0]]
        quantum_device_cfg['pre_pulse_info']['flux2_phases_prep'] = [[0.0, 0.0], [0.0, 0.0]]

        experiment_cfg['rabi_while_flux']['qubit_freq'] = fq['ee->ef']
        experiment_cfg['rabi_while_flux']['pi_calibration'] = expt_cfg['pi_calibration']
        experiment_cfg['rabi_while_flux']['flux_pi_calibration'] = False
        experiment_cfg['rabi_while_flux']['flux_probe'] = False

        experiment_cfg['rabi_while_flux']['start'] = 0.0
        experiment_cfg['rabi_while_flux']['stop'] = pi_gate['ee->ef'] * 4.0
        experiment_cfg['rabi_while_flux']['step'] = np.round(pi_gate['ee->ef'] * 4 / 100.0)

        experiment_cfg['rabi_while_flux']['acquisition_num'] = expt_cfg['acquisition_num']
        experiment_cfg['rabi_while_flux']['on_qubits'] = ['2']
        experiment_cfg['rabi_while_flux']['on_cavity'] = ['2']
        experiment_cfg['rabi_while_flux']['calibration_qubit'] = '2'
        experiment_cfg['rabi_while_flux']['flux_line'] = []
        experiment_cfg['rabi_while_flux']['flux_freq'] = 1.0
        experiment_cfg['rabi_while_flux']['phase'] = [0]

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('rabi_while_flux')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'rabi_while_flux')

        update_awg = False
        ########################################### Fitting Rabi
        print('Fitting Rabi data...')
        data_path_now = os.path.join(data_path, get_current_filename(data_path, 'rabi_while_flux', suffix='.h5'))
        with SlabFile(data_path_now) as a:
            pil, hpil = calibrate_rabi_while_flux(a, pi_length=pi_gate['ee->ef'], t1=1000)
        print('Calibrated pi length: %.2f ' % (pil))
        print('Calibrated pi/2 length: %.2f ' % (hpil))
        pi_gate['ee->ef'] = pil
        hpi_gate['ee->ef'] = hpil
        quantum_device_cfg['pulse_info']['2']['pi_ef_e_len'] = pil
        quantum_device_cfg['pulse_info']['2']['half_pi_ef_e_len'] = hpil

        ########################################### ramsey
        print('Calibrating |ee>-->|ef> Ramsey')
        experiment_cfg['ramsey_while_flux']['use_freq_amp_halfpi'] = [True, fq['ee->ef'], pi_amp['ee->ef'],
                                                                      hpi_gate['ee->ef'], 'charge2']
        experiment_cfg['ramsey_while_flux']['flux_amp'] = []
        experiment_cfg['ramsey_while_flux']['flux_probe'] = False
        experiment_cfg['ramsey_while_flux']['singleshot'] = False
        experiment_cfg['ramsey_while_flux']['ge_pi'] = []
        experiment_cfg['ramsey_while_flux']['ef_pi'] = []
        experiment_cfg['ramsey_while_flux']['ge_pi2'] = []
        experiment_cfg['ramsey_while_flux']['pre_pulse'] = True
        experiment_cfg['ramsey_while_flux']['pi_calibration'] = expt_cfg['pi_calibration']
        experiment_cfg['ramsey_while_flux']['flux_pi_calibration'] = False

        experiment_cfg['ramsey_while_flux']['start'] = 0.0
        experiment_cfg['ramsey_while_flux']['stop'] = 1500.0
        experiment_cfg['ramsey_while_flux']['step'] = 5.0
        experiment_cfg['ramsey_while_flux']['ramsey_freq'] = 0.005

        experiment_cfg['ramsey_while_flux']['acquisition_num'] = ram_acq_no
        experiment_cfg['ramsey_while_flux']['on_qubits'] = ['2']
        experiment_cfg['ramsey_while_flux']['on_cavity'] = ['2']
        experiment_cfg['ramsey_while_flux']['flux_line'] = []
        experiment_cfg['ramsey_while_flux']['flux_freq'] = 1.0
        experiment_cfg['ramsey_while_flux']['phase'] = [0]

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('ramsey_while_flux')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'ramsey_while_flux')

        update_awg = False
        ########################################### Fitting Ramsey
        print('Fitting Ramsey data...')
        data_path_now = os.path.join(data_path,
                                     get_current_filename(data_path, 'ramsey_while_flux', suffix='.h5'))
        with SlabFile(data_path_now) as a:
            freq_new = calibrate_ramsey(a, pi_length=100, t2=1000)
        print('Calibrated |ee>-->|ef> transition: %s GHz' % (freq_new))
        fq['ee->ef'] = freq_new
        quantum_device_cfg['qubit']['fe2_disp'] = freq_new - quantum_device_cfg['qubit']['2']['freq']

    print('Calibrating |ee>-->|ef> Rabi')
    experiment_cfg['rabi_while_flux']['amp'] = pi_amp['ee->ef']
    experiment_cfg['rabi_while_flux']['flux_amp'] = []
    experiment_cfg['rabi_while_flux']['ge_pi'] = []
    experiment_cfg['rabi_while_flux']['ef_pi'] = []
    experiment_cfg['rabi_while_flux']['ge_pi2'] = []
    experiment_cfg['rabi_while_flux']['pre_pulse'] = True
    experiment_cfg['rabi_while_flux']['qubit_freq'] = fq['ee->ef']
    experiment_cfg['rabi_while_flux']['pi_calibration'] = expt_cfg['pi_calibration']
    experiment_cfg['rabi_while_flux']['flux_pi_calibration'] = False
    experiment_cfg['rabi_while_flux']['flux_probe'] = False

    experiment_cfg['rabi_while_flux']['start'] = 0.0
    experiment_cfg['rabi_while_flux']['stop'] = pi_gate['ee->ef'] * 4.0
    experiment_cfg['rabi_while_flux']['step'] = np.round(pi_gate['ee->ef'] * 4 / 100.0 ,1)

    experiment_cfg['rabi_while_flux']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['rabi_while_flux']['on_qubits'] = ['2']
    experiment_cfg['rabi_while_flux']['on_cavity'] = ['2']
    experiment_cfg['rabi_while_flux']['calibration_qubit'] = '2'
    experiment_cfg['rabi_while_flux']['flux_line'] = []
    experiment_cfg['rabi_while_flux']['flux_freq'] = 1.0
    experiment_cfg['rabi_while_flux']['phase'] = [0]

    ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
    sequences = ps.get_experiment_sequences('rabi_while_flux')
    update_awg = True

    exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
    exp.run_experiment(sequences, path, 'rabi_while_flux')

    update_awg = False
    ########################################### Fitting Rabi
    print('Fitting Rabi data...')
    data_path_now = os.path.join(data_path, get_current_filename(data_path, 'rabi_while_flux', suffix='.h5'))
    with SlabFile(data_path_now) as a:
        pil, hpil = calibrate_rabi_while_flux(a, pi_length=pi_gate['ee->ef'], t1=1000)
    print('Calibrated pi length: %.2f ' % (pil))
    print('Calibrated pi/2 length: %.2f ' % (hpil))
    pi_gate['ee->ef'] = pil
    hpi_gate['ee->ef'] = hpil
    quantum_device_cfg['pulse_info']['2']['pi_ef_e_len'] = pil
    quantum_device_cfg['pulse_info']['2']['half_pi_ef_e_len'] = hpil
    print('################################')
    print('current results:')
    for sss in string_list:
        print(sss, '  Freq:', fq[sss], '  pi:', pi_gate[sss], '  hpi:', hpi_gate[sss])
    print('qq_disp: ', fq['ge->ee'] - fq['gg->eg'])
    print('gf1_disp: ', fq['gf->ef'] - fq['gg->eg'])
    print('fg2_disp: ', fq['fg->fe'] - fq['gg->ge'])
    print('ef1_disp: ', fq['ee->fe'] - fq['eg->fg'])
    print('fe2_disp: ', fq['ee->ef'] - fq['ge->gf'])
    print('ff1_disp: ', fq['ef->ff'] - fq['eg->fg'])
    print('ff2_disp: ', fq['fe->ff'] - fq['ge->gf'])


    ########################################################################################
    ## calibrating ef->ff
    print('Calibrating |ef>-->|ff> transition')
    for rround in range(expt_cfg['iterno']):
        print('############## Calibration Round No: ', rround + 1)
        ##################################### rabi
        print('Calibrating |ef>-->|ff> Rabi')
        experiment_cfg['rabi_while_flux']['amp'] = pi_amp['ef->ff']
        experiment_cfg['rabi_while_flux']['flux_amp'] = []
        experiment_cfg['rabi_while_flux']['ge_pi'] = []
        experiment_cfg['rabi_while_flux']['ef_pi'] = []
        experiment_cfg['rabi_while_flux']['ge_pi2'] = []
        experiment_cfg['rabi_while_flux']['pre_pulse'] = True
        quantum_device_cfg['pre_pulse_info']['times_prep'] = [[pi_gate['gg->eg'], 0.0], [pi_gate['eg->ee'], 0.0], [pi_gate['ee->ef'], 0.0]]

        quantum_device_cfg['pre_pulse_info']['charge1_amps_prep'] = [[pi_amp['gg->eg'], 0.0], [0.0, 0.0], [0.0, 0.0]]
        quantum_device_cfg['pre_pulse_info']['charge1_freqs_prep'] = [[fq['gg->eg'], 0.0], [0.0, 0.0], [0.0, 0.0]]
        quantum_device_cfg['pre_pulse_info']['charge1_phases_prep'] = [[0.0, 0.0], [0.0, 0.0], [0.0, 0.0]]

        quantum_device_cfg['pre_pulse_info']['charge2_amps_prep'] = [[0.0, 0.0], [pi_amp['eg->ee'], 0.0], [pi_amp['ee->ef'], 0.0]]
        quantum_device_cfg['pre_pulse_info']['charge2_freqs_prep'] = [[0.0, 0.0], [fq['eg->ee'], 0.0], [fq['ee->ef'], 0.0]]
        quantum_device_cfg['pre_pulse_info']['charge2_phases_prep'] = [[0.0, 0.0], [0.0, 0.0], [0.0, 0.0]]

        quantum_device_cfg['pre_pulse_info']['flux1_amps_prep'] = [[0.0, 0.0], [0.0, 0.0], [0.0, 0.0]]
        quantum_device_cfg['pre_pulse_info']['flux1_freqs_prep'] = [[0.0, 0.0], [0.0, 0.0], [0.0, 0.0]]
        quantum_device_cfg['pre_pulse_info']['flux1_phases_prep'] = [[0.0, 0.0], [0.0, 0.0], [0.0, 0.0]]

        quantum_device_cfg['pre_pulse_info']['flux2_amps_prep'] = [[0.0, 0.0], [0.0, 0.0], [0.0, 0.0]]
        quantum_device_cfg['pre_pulse_info']['flux2_freqs_prep'] = [[0.0, 0.0], [0.0, 0.0], [0.0, 0.0]]
        quantum_device_cfg['pre_pulse_info']['flux2_phases_prep'] = [[0.0, 0.0], [0.0, 0.0], [0.0, 0.0]]

        experiment_cfg['rabi_while_flux']['qubit_freq'] = fq['ef->ff']
        experiment_cfg['rabi_while_flux']['pi_calibration'] = expt_cfg['pi_calibration']
        experiment_cfg['rabi_while_flux']['flux_pi_calibration'] = False
        experiment_cfg['rabi_while_flux']['flux_probe'] = False

        experiment_cfg['rabi_while_flux']['start'] = 0.0
        experiment_cfg['rabi_while_flux']['stop'] = pi_gate['ef->ff'] * 4.0
        experiment_cfg['rabi_while_flux']['step'] = np.round(pi_gate['ef->ff'] * 4 / 100.0 ,1)

        experiment_cfg['rabi_while_flux']['acquisition_num'] = expt_cfg['acquisition_num']
        experiment_cfg['rabi_while_flux']['on_qubits'] = ['1']
        experiment_cfg['rabi_while_flux']['on_cavity'] = ['1']
        experiment_cfg['rabi_while_flux']['calibration_qubit'] = '1'
        experiment_cfg['rabi_while_flux']['flux_line'] = []
        experiment_cfg['rabi_while_flux']['flux_freq'] = 1.0
        experiment_cfg['rabi_while_flux']['phase'] = [0]

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('rabi_while_flux')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'rabi_while_flux')

        update_awg = False
        ########################################### Fitting Rabi
        print('Fitting Rabi data...')
        data_path_now = os.path.join(data_path, get_current_filename(data_path, 'rabi_while_flux', suffix='.h5'))
        with SlabFile(data_path_now) as a:
            pil, hpil = calibrate_rabi_while_flux(a, pi_length=pi_gate['ef->ff'], t1=1000)
        print('Calibrated pi length: %.2f ' % (pil))
        print('Calibrated pi/2 length: %.2f ' % (hpil))
        pi_gate['ef->ff'] = pil
        hpi_gate['ef->ff'] = hpil
        quantum_device_cfg['pulse_info']['1']['pi_ff_len'] = pil
        quantum_device_cfg['pulse_info']['1']['half_pi_ff_len'] = hpil

        ########################################### ramsey
        print('Calibrating |ef>-->|ff> Ramsey')
        experiment_cfg['ramsey_while_flux']['use_freq_amp_halfpi'] = [True, fq['ef->ff'], pi_amp['ef->ff'],
                                                                      hpi_gate['ef->ff'], 'charge1']
        experiment_cfg['ramsey_while_flux']['flux_amp'] = []
        experiment_cfg['ramsey_while_flux']['flux_probe'] = False
        experiment_cfg['ramsey_while_flux']['singleshot'] = False
        experiment_cfg['ramsey_while_flux']['ge_pi'] = []
        experiment_cfg['ramsey_while_flux']['ef_pi'] = []
        experiment_cfg['ramsey_while_flux']['ge_pi2'] = []
        experiment_cfg['ramsey_while_flux']['pre_pulse'] = True
        experiment_cfg['ramsey_while_flux']['pi_calibration'] = expt_cfg['pi_calibration']
        experiment_cfg['ramsey_while_flux']['flux_pi_calibration'] = False

        experiment_cfg['ramsey_while_flux']['start'] = 0.0
        experiment_cfg['ramsey_while_flux']['stop'] = 1500.0
        experiment_cfg['ramsey_while_flux']['step'] = 5.0
        experiment_cfg['ramsey_while_flux']['ramsey_freq'] = 0.005

        experiment_cfg['ramsey_while_flux']['acquisition_num'] = ram_acq_no
        experiment_cfg['ramsey_while_flux']['on_qubits'] = ['1']
        experiment_cfg['ramsey_while_flux']['on_cavity'] = ['1']
        experiment_cfg['ramsey_while_flux']['flux_line'] = []
        experiment_cfg['ramsey_while_flux']['flux_freq'] = 1.0
        experiment_cfg['ramsey_while_flux']['phase'] = [0]

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('ramsey_while_flux')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'ramsey_while_flux')

        update_awg = False
        ########################################### Fitting Ramsey
        print('Fitting Ramsey data...')
        data_path_now = os.path.join(data_path,
                                     get_current_filename(data_path, 'ramsey_while_flux', suffix='.h5'))
        with SlabFile(data_path_now) as a:
            freq_new = calibrate_ramsey(a, pi_length=100, t2=1000)
        print('Calibrated |ef>-->|ff> transition: %s GHz' % (freq_new))
        fq['ef->ff'] = freq_new
        quantum_device_cfg['qubit']['ff1_disp'] = freq_new - quantum_device_cfg['qubit']['1']['freq']+quantum_device_cfg['qubit']['1']['anharmonicity']

    print('Calibrating |ef>-->|ff> Rabi')
    experiment_cfg['rabi_while_flux']['amp'] = pi_amp['ef->ff']
    experiment_cfg['rabi_while_flux']['flux_amp'] = []
    experiment_cfg['rabi_while_flux']['ge_pi'] = []
    experiment_cfg['rabi_while_flux']['ef_pi'] = []
    experiment_cfg['rabi_while_flux']['ge_pi2'] = []
    experiment_cfg['rabi_while_flux']['pre_pulse'] = True
    experiment_cfg['rabi_while_flux']['qubit_freq'] = fq['ef->ff']
    experiment_cfg['rabi_while_flux']['pi_calibration'] = expt_cfg['pi_calibration']
    experiment_cfg['rabi_while_flux']['flux_pi_calibration'] = False
    experiment_cfg['rabi_while_flux']['flux_probe'] = False

    experiment_cfg['rabi_while_flux']['start'] = 0.0
    experiment_cfg['rabi_while_flux']['stop'] = pi_gate['ef->ff'] * 4.0
    experiment_cfg['rabi_while_flux']['step'] = np.round(pi_gate['ef->ff'] * 4 / 100.0 ,1)

    experiment_cfg['rabi_while_flux']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['rabi_while_flux']['on_qubits'] = ['1']
    experiment_cfg['rabi_while_flux']['on_cavity'] = ['1']
    experiment_cfg['rabi_while_flux']['calibration_qubit'] = '1'
    experiment_cfg['rabi_while_flux']['flux_line'] = []
    experiment_cfg['rabi_while_flux']['flux_freq'] = 1.0
    experiment_cfg['rabi_while_flux']['phase'] = [0]

    ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
    sequences = ps.get_experiment_sequences('rabi_while_flux')
    update_awg = True

    exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
    exp.run_experiment(sequences, path, 'rabi_while_flux')

    update_awg = False
    ########################################### Fitting Rabi
    print('Fitting Rabi data...')
    data_path_now = os.path.join(data_path, get_current_filename(data_path, 'rabi_while_flux', suffix='.h5'))
    with SlabFile(data_path_now) as a:
        pil, hpil = calibrate_rabi_while_flux(a, pi_length=pi_gate['ef->ff'], t1=1000)
    print('Calibrated pi length: %.2f ' % (pil))
    print('Calibrated pi/2 length: %.2f ' % (hpil))
    pi_gate['ef->ff'] = pil
    hpi_gate['ef->ff'] = hpil
    quantum_device_cfg['pulse_info']['1']['pi_ff_len'] = pil
    quantum_device_cfg['pulse_info']['1']['half_pi_ff_len'] = hpil
    print('################################')
    print('current results:')
    for sss in string_list:
        print(sss, '  Freq:', fq[sss], '  pi:', pi_gate[sss], '  hpi:', hpi_gate[sss])
    print('qq_disp: ', fq['ge->ee'] - fq['gg->eg'])
    print('gf1_disp: ', fq['gf->ef'] - fq['gg->eg'])
    print('fg2_disp: ', fq['fg->fe'] - fq['gg->ge'])
    print('ef1_disp: ', fq['ee->fe'] - fq['eg->fg'])
    print('fe2_disp: ', fq['ee->ef'] - fq['ge->gf'])
    print('ff1_disp: ', fq['ef->ff'] - fq['eg->fg'])
    print('ff2_disp: ', fq['fe->ff'] - fq['ge->gf'])


    ########################################################################################
    ## calibrating fe->ff
    print('Calibrating |fe>-->|ff> transition')
    for rround in range(expt_cfg['iterno']):
        print('############## Calibration Round No: ', rround + 1)
        ##################################### rabi
        print('Calibrating |fe>-->|ff> Rabi')
        experiment_cfg['rabi_while_flux']['amp'] = pi_amp['fe->ff']
        experiment_cfg['rabi_while_flux']['flux_amp'] = []
        experiment_cfg['rabi_while_flux']['ge_pi'] = []
        experiment_cfg['rabi_while_flux']['ef_pi'] = []
        experiment_cfg['rabi_while_flux']['ge_pi2'] = []
        experiment_cfg['rabi_while_flux']['pre_pulse'] = True
        quantum_device_cfg['pulse_info']['times_prep'] = [[pi_gate['gg->eg'], 0.0], [pi_gate['eg->ee'], 0.0],
                                                          [pi_gate['ee->fe'], 0.0]]

        quantum_device_cfg['pre_pulse_info']['charge1_amps_prep'] = [[pi_amp['gg->eg'], 0.0], [0.0, 0.0], [pi_amp['ee->fe'], 0.0]]
        quantum_device_cfg['pre_pulse_info']['charge1_freqs_prep'] = [[fq['gg->eg'], 0.0], [0.0, 0.0], [fq['ee->fe'], 0.0]]
        quantum_device_cfg['pre_pulse_info']['charge1_phases_prep'] = [[0.0, 0.0], [0.0, 0.0], [0.0, 0.0]]

        quantum_device_cfg['pre_pulse_info']['charge2_amps_prep'] = [[0.0, 0.0], [pi_amp['eg->ee'], 0.0],
                                                                 [0.0, 0.0]]
        quantum_device_cfg['pre_pulse_info']['charge2_freqs_prep'] = [[0.0, 0.0], [fq['eg->ee'], 0.0], [0.0, 0.0]]
        quantum_device_cfg['pre_pulse_info']['charge2_phases_prep'] = [[0.0, 0.0], [0.0, 0.0], [0.0, 0.0]]

        quantum_device_cfg['pre_pulse_info']['flux1_amps_prep'] = [[0.0, 0.0], [0.0, 0.0], [0.0, 0.0]]
        quantum_device_cfg['pre_pulse_info']['flux1_freqs_prep'] = [[0.0, 0.0], [0.0, 0.0], [0.0, 0.0]]
        quantum_device_cfg['pre_pulse_info']['flux1_phases_prep'] = [[0.0, 0.0], [0.0, 0.0], [0.0, 0.0]]

        quantum_device_cfg['pre_pulse_info']['flux2_amps_prep'] = [[0.0, 0.0], [0.0, 0.0], [0.0, 0.0]]
        quantum_device_cfg['pre_pulse_info']['flux2_freqs_prep'] = [[0.0, 0.0], [0.0, 0.0], [0.0, 0.0]]
        quantum_device_cfg['pre_pulse_info']['flux2_phases_prep'] = [[0.0, 0.0], [0.0, 0.0], [0.0, 0.0]]

        experiment_cfg['rabi_while_flux']['qubit_freq'] = fq['fe->ff']
        experiment_cfg['rabi_while_flux']['pi_calibration'] = expt_cfg['pi_calibration']
        experiment_cfg['rabi_while_flux']['flux_pi_calibration'] = False
        experiment_cfg['rabi_while_flux']['flux_probe'] = False

        experiment_cfg['rabi_while_flux']['start'] = 0.0
        experiment_cfg['rabi_while_flux']['stop'] = pi_gate['fe->ff'] * 4.0
        experiment_cfg['rabi_while_flux']['step'] = np.round(pi_gate['fe->ff'] * 4 / 100.0 ,1)

        experiment_cfg['rabi_while_flux']['acquisition_num'] = expt_cfg['acquisition_num']
        experiment_cfg['rabi_while_flux']['on_qubits'] = ['2']
        experiment_cfg['rabi_while_flux']['on_cavity'] = ['2']
        experiment_cfg['rabi_while_flux']['calibration_qubit'] = '2'
        experiment_cfg['rabi_while_flux']['flux_line'] = []
        experiment_cfg['rabi_while_flux']['flux_freq'] = 1.0
        experiment_cfg['rabi_while_flux']['phase'] = [0]

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('rabi_while_flux')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'rabi_while_flux')

        update_awg = False
        ########################################### Fitting Rabi
        print('Fitting Rabi data...')
        data_path_now = os.path.join(data_path, get_current_filename(data_path, 'rabi_while_flux', suffix='.h5'))
        with SlabFile(data_path_now) as a:
            pil, hpil = calibrate_rabi_while_flux(a, pi_length=pi_gate['fe->ff'], t1=1000)
        print('Calibrated pi length: %.2f ' % (pil))
        print('Calibrated pi/2 length: %.2f ' % (hpil))
        pi_gate['fe->ff'] = pil
        hpi_gate['fe->ff'] = hpil
        quantum_device_cfg['pulse_info']['2']['pi_ff_len'] = pil
        quantum_device_cfg['pulse_info']['2']['half_pi_ff_len'] = hpil

        ########################################### ramsey
        print('Calibrating |fe>-->|ff> Ramsey')
        experiment_cfg['ramsey_while_flux']['use_freq_amp_halfpi'] = [True, fq['fe->ff'], pi_amp['fe->ff'],
                                                                      hpi_gate['fe->ff'], 'charge2']
        experiment_cfg['ramsey_while_flux']['flux_amp'] = []
        experiment_cfg['ramsey_while_flux']['flux_probe'] = False
        experiment_cfg['ramsey_while_flux']['singleshot'] = False
        experiment_cfg['ramsey_while_flux']['ge_pi'] = []
        experiment_cfg['ramsey_while_flux']['ef_pi'] = []
        experiment_cfg['ramsey_while_flux']['ge_pi2'] = []
        experiment_cfg['ramsey_while_flux']['pre_pulse'] = True
        experiment_cfg['ramsey_while_flux']['pi_calibration'] = expt_cfg['pi_calibration']
        experiment_cfg['ramsey_while_flux']['flux_pi_calibration'] = False

        experiment_cfg['ramsey_while_flux']['start'] = 0.0
        experiment_cfg['ramsey_while_flux']['stop'] = 1500.0
        experiment_cfg['ramsey_while_flux']['step'] = 5.0
        experiment_cfg['ramsey_while_flux']['ramsey_freq'] = 0.005

        experiment_cfg['ramsey_while_flux']['acquisition_num'] = ram_acq_no
        experiment_cfg['ramsey_while_flux']['on_qubits'] = ['2']
        experiment_cfg['ramsey_while_flux']['on_cavity'] = ['2']
        experiment_cfg['ramsey_while_flux']['flux_line'] = []
        experiment_cfg['ramsey_while_flux']['flux_freq'] = 1.0
        experiment_cfg['ramsey_while_flux']['phase'] = [0]

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('ramsey_while_flux')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'ramsey_while_flux')

        update_awg = False
        ########################################### Fitting Ramsey
        print('Fitting Ramsey data...')
        data_path_now = os.path.join(data_path,
                                     get_current_filename(data_path, 'ramsey_while_flux', suffix='.h5'))
        with SlabFile(data_path_now) as a:
            freq_new = calibrate_ramsey(a, pi_length=100, t2=1000)
        print('Calibrated |fe>-->|ff> transition: %s GHz' % (freq_new))
        fq['fe->ff'] = freq_new
        quantum_device_cfg['qubit']['ff2_disp'] = freq_new - quantum_device_cfg['qubit']['2']['freq'] + \
                                                  quantum_device_cfg['qubit']['2']['anharmonicity']

    print('Calibrating |fe>-->|ff> Rabi')
    experiment_cfg['rabi_while_flux']['amp'] = pi_amp['fe->ff']
    experiment_cfg['rabi_while_flux']['flux_amp'] = []
    experiment_cfg['rabi_while_flux']['ge_pi'] = []
    experiment_cfg['rabi_while_flux']['ef_pi'] = []
    experiment_cfg['rabi_while_flux']['ge_pi2'] = []
    experiment_cfg['rabi_while_flux']['pre_pulse'] = True
    experiment_cfg['rabi_while_flux']['qubit_freq'] = fq['fe->ff']
    experiment_cfg['rabi_while_flux']['pi_calibration'] = expt_cfg['pi_calibration']
    experiment_cfg['rabi_while_flux']['flux_pi_calibration'] = False
    experiment_cfg['rabi_while_flux']['flux_probe'] = False

    experiment_cfg['rabi_while_flux']['start'] = 0.0
    experiment_cfg['rabi_while_flux']['stop'] = pi_gate['fe->ff'] * 4.0
    experiment_cfg['rabi_while_flux']['step'] = np.round(pi_gate['fe->ff'] * 4 / 100.0 ,1)

    experiment_cfg['rabi_while_flux']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['rabi_while_flux']['on_qubits'] = ['2']
    experiment_cfg['rabi_while_flux']['on_cavity'] = ['2']
    experiment_cfg['rabi_while_flux']['calibration_qubit'] = '2'
    experiment_cfg['rabi_while_flux']['flux_line'] = []
    experiment_cfg['rabi_while_flux']['flux_freq'] = 1.0
    experiment_cfg['rabi_while_flux']['phase'] = [0]

    ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
    sequences = ps.get_experiment_sequences('rabi_while_flux')
    update_awg = True

    exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
    exp.run_experiment(sequences, path, 'rabi_while_flux')

    update_awg = False
    ########################################### Fitting Rabi
    print('Fitting Rabi data...')
    data_path_now = os.path.join(data_path, get_current_filename(data_path, 'rabi_while_flux', suffix='.h5'))
    with SlabFile(data_path_now) as a:
        pil, hpil = calibrate_rabi_while_flux(a, pi_length=pi_gate['fe->ff'], t1=1000)
    print('Calibrated pi length: %.2f ' % (pil))
    print('Calibrated pi/2 length: %.2f ' % (hpil))
    pi_gate['fe->ff'] = pil
    hpi_gate['fe->ff'] = hpil
    quantum_device_cfg['pulse_info']['2']['pi_ff_len'] = pil
    quantum_device_cfg['pulse_info']['2']['half_pi_ff_len'] = hpil

    ### save results
    print('################################')
    print('Final results:')
    for sss in string_list:
        print(sss, '  Freq:', fq[sss], '  pi:', pi_gate[sss], '  hpi:', hpi_gate[sss])
    print('alpha1: ',fq['eg->fg']-fq['gg->eg'])
    print('alpha2: ',fq['ge->gf']-fq['gg->ge'])
    print('qq_disp: ',fq['ge->ee']-fq['gg->eg'])
    print('gf1_disp: ',fq['gf->ef']-fq['gg->eg'])
    print('fg2_disp: ',fq['fg->fe']-fq['gg->ge'])
    print('ef1_disp: ',fq['ee->fe']-fq['eg->fg'])
    print('fe2_disp: ',fq['ee->ef']-fq['ge->gf'])
    print('ff1_disp: ',fq['ef->ff']-fq['eg->fg'])
    print('ff2_disp: ',fq['fe->ff']-fq['ge->gf'])

def histogram_time_idle_sweep(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['histogram_time_idle_sweep']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'histogram_time_idle_sweep', suffix='.h5'))
    on_qubits = expt_cfg['on_qubits']

    experiment_cfg['histogram_while_flux']['states'] = expt_cfg['states']
    experiment_cfg['histogram_while_flux']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['histogram_while_flux']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['histogram_while_flux']['singleshot'] = expt_cfg['singleshot']
    experiment_cfg['histogram_while_flux']['flux_probe'] = expt_cfg['flux_probe']
    experiment_cfg['histogram_while_flux']['flux_line'] = expt_cfg['flux_line']

    experiment_cfg['histogram_while_flux']['amps'] = expt_cfg['amps']
    experiment_cfg['histogram_while_flux']['freqs'] = expt_cfg['freqs']
    experiment_cfg['histogram_while_flux']['phases'] = expt_cfg['phases']
    experiment_cfg['histogram_while_flux']['sideband_on'] = expt_cfg['sideband_on']
    
    if on_qubits[0]=='1':
        sweep_states = ['gg','eg','fg']
    else:
        sweep_states = ['gg','ge','gf']
    for ss in sweep_states:
        experiment_cfg['histogram_while_flux']['states'].append(ss)

    for time in np.arange(expt_cfg['start'], expt_cfg['stop'], expt_cfg['step']):

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        experiment_cfg['histogram_while_flux']['time'] = time
        sequences = ps.get_experiment_sequences('histogram_while_flux')
        update_awg = True
        print('Sweep time: ',time,' ns')

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'histogram_while_flux', seq_data_file, update_awg)

        update_awg = False


def histogram_time_idle_sweep_phase_sweep(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['histogram_time_idle_sweep_phase_sweep']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'histogram_time_idle_sweep_phase_sweep', suffix='.h5'))
    on_qubits = expt_cfg['on_qubits']

    experiment_cfg['histogram_while_flux']['states'] = expt_cfg['states']
    experiment_cfg['histogram_while_flux']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['histogram_while_flux']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['histogram_while_flux']['singleshot'] = expt_cfg['singleshot']
    experiment_cfg['histogram_while_flux']['flux_probe'] = expt_cfg['flux_probe']
    experiment_cfg['histogram_while_flux']['flux_line'] = expt_cfg['flux_line']

    experiment_cfg['histogram_while_flux']['amps'] = expt_cfg['amps']
    experiment_cfg['histogram_while_flux']['freqs'] = expt_cfg['freqs']
    experiment_cfg['histogram_while_flux']['phases'] = expt_cfg['phases']
    experiment_cfg['histogram_while_flux']['sideband_on'] = expt_cfg['sideband_on']

    if on_qubits[0] == '1':
        sweep_states = ['gg', 'eg', 'fg']
    else:
        sweep_states = ['gg', 'ge', 'gf']
    for ss in sweep_states:
        experiment_cfg['histogram_while_flux']['states'].append(ss)

    for phase_p in np.arange(expt_cfg['phase_start'], expt_cfg['phase_stop'], expt_cfg['phase_step']):

        quantum_device_cfg['pre_pulse_info']['flux2_phases_prep'][-2][0] = phase_p
        print('Sweep Phase: ', phase_p)

        print(quantum_device_cfg['pre_pulse_info']['flux2_phases_prep'])

        for time in np.arange(expt_cfg['start'], expt_cfg['stop'], expt_cfg['step']):
            ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
            experiment_cfg['histogram_while_flux']['time'] = time
            sequences = ps.get_experiment_sequences('histogram_while_flux')
            update_awg = True
            print('Sweep time: ', time, ' ns')

            exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
            exp.run_experiment(sequences, path, 'histogram_while_flux', seq_data_file, update_awg)

            update_awg = False

def histogram(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['histogram']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'histogram', suffix='.h5'))
    on_qubits = expt_cfg['on_qubits']

    lo_freq = {"1": quantum_device_cfg['heterodyne']['1']['lo_freq'],
               "2": quantum_device_cfg['heterodyne']['2']['lo_freq']}

    for amp in np.arange(expt_cfg['amp_start'], expt_cfg['amp_stop'], expt_cfg['amp_step']):
        for qubit_id in on_qubits:
            quantum_device_cfg['heterodyne'][qubit_id]['amp'] = amp
        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('histogram')
        update_awg = True
        for lo_freq_delta in np.arange(expt_cfg['lo_freq_delta_start'], expt_cfg['lo_freq_delta_stop'], expt_cfg['lo_freq_delta_step']):
            for qubit_id in on_qubits:
                quantum_device_cfg['heterodyne'][qubit_id]['lo_freq'] = lo_freq[qubit_id] + lo_freq_delta
                print('lo_freq_delta: ',lo_freq_delta,' GHz, amp: ',amp)

            exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
            exp.run_experiment(sequences, path, 'histogram', seq_data_file, update_awg)

            update_awg = False

def histogram_three_level(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['histogram']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'histogram', suffix='.h5'))
    on_qubits = expt_cfg['on_qubits']

    lo_freq = {"1": quantum_device_cfg['heterodyne']['1']['lo_freq'],
               "2": quantum_device_cfg['heterodyne']['2']['lo_freq']}

    for amp in np.arange(expt_cfg['amp_start'], expt_cfg['amp_stop'], expt_cfg['amp_step']):
        for qubit_id in on_qubits:
            quantum_device_cfg['heterodyne'][qubit_id]['amp'] = amp
        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('histogram')
        update_awg = True
        for lo_freq_delta in np.arange(expt_cfg['lo_freq_delta_start'], expt_cfg['lo_freq_delta_stop'], expt_cfg['lo_freq_delta_step']):
            for qubit_id in on_qubits:
                quantum_device_cfg['heterodyne'][qubit_id]['lo_freq'] = lo_freq[qubit_id] + lo_freq_delta
                print('lo_freq_delta: ',lo_freq_delta,' GHz, amp: ',amp)

            exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
            exp.run_experiment(sequences, path, 'histogram', seq_data_file, update_awg)

            update_awg = False

def readout_time_optimization(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['readout_time_optimization']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'readout_time_optimization', suffix='.h5'))
    on_qubits = expt_cfg['on_qubits']

    experiment_cfg['histogram']['states'] = expt_cfg['states']
    experiment_cfg['histogram']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['histogram']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['histogram']['singleshot'] = expt_cfg['singleshot']
    experiment_cfg['histogram']['flux_probe'] = expt_cfg['flux_probe']

    for readout_time in np.arange(expt_cfg['start'], expt_cfg['stop'], expt_cfg['step']):
        print('readout time is',readout_time)
        quantum_device_cfg['alazar_readout']['width'] = int(readout_time)
        quantum_device_cfg['alazar_readout']['window'] = [0,int(readout_time)]
        for qubit_id in on_qubits:
            quantum_device_cfg['heterodyne'][qubit_id]['length'] = readout_time
        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('histogram')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'readout_time_optimization', seq_data_file, update_awg)

        update_awg = False

def readout_iq_freq_optimization(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['readout_iq_freq_optimization']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'readout_iq_freq_optimization', suffix='.h5'))
    on_qubits = expt_cfg['on_qubits']

    lo_freq = {"1": quantum_device_cfg['heterodyne']['1']['lo_freq'],
               "2": quantum_device_cfg['heterodyne']['2']['lo_freq']}

    iq_freq = {"1": quantum_device_cfg['heterodyne']['1']['freq'],
               "2": quantum_device_cfg['heterodyne']['2']['freq']}

    experiment_cfg['histogram']['states'] = expt_cfg['states']
    experiment_cfg['histogram']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['histogram']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['histogram']['singleshot'] = expt_cfg['singleshot']
    experiment_cfg['histogram']['flux_probe'] = expt_cfg['flux_probe']

    for iq_freq_delta in np.arange(expt_cfg['iq_freq_delta_start'], expt_cfg['iq_freq_delta_stop'], expt_cfg['iq_freq_delta_step']):
        print('iq_freq_delta is',iq_freq_delta)
        for qubit_id in on_qubits:
            quantum_device_cfg['heterodyne'][qubit_id]['freq'] = iq_freq[qubit_id]+iq_freq_delta
            quantum_device_cfg['heterodyne'][qubit_id]['lo_freq'] = lo_freq[qubit_id]+iq_freq_delta
            print('readout freq is', quantum_device_cfg['heterodyne'][qubit_id]['lo_freq']-quantum_device_cfg['heterodyne'][qubit_id]['freq'])
        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('histogram')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'readout_iq_freq_optimization', seq_data_file, update_awg)

        update_awg = False

def readout_lo_power_optimization(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['readout_lo_power_optimization']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'readout_lo_power_optimization', suffix='.h5'))
    on_qubits = expt_cfg['on_qubits']

    lo_power = {"1": quantum_device_cfg['heterodyne']['1']['lo_power'],
               "2": quantum_device_cfg['heterodyne']['2']['lo_power']}


    experiment_cfg['histogram']['states'] = expt_cfg['states']
    experiment_cfg['histogram']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['histogram']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['histogram']['singleshot'] = expt_cfg['singleshot']
    experiment_cfg['histogram']['flux_probe'] = expt_cfg['flux_probe']

    for lo_power_delta in np.arange(expt_cfg['lo_power_delta_start'], expt_cfg['lo_power_delta_stop'], expt_cfg['lo_power_delta_step']):
        print('lo_power_delta is',lo_power_delta)
        for qubit_id in on_qubits:
            quantum_device_cfg['heterodyne'][qubit_id]['lo_power'] = lo_power[qubit_id]+lo_power_delta
        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('histogram')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'readout_lo_power_optimization', seq_data_file, update_awg)

        update_awg = False

def qubit_frequency_flux_calibration(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
    sequences = ps.get_experiment_sequences('ramsey')
    expt_cfg = experiment_cfg['ramsey']
    uncalibrated_qubits = list(expt_cfg['on_qubits'])
    for ii in range(3):
        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        data_file = exp.run_experiment(sequences, path, 'ramsey')
        expt_cfg = experiment_cfg['ramsey']
        on_qubits = expt_cfg['on_qubits']
        expt_pts = np.arange(expt_cfg['start'], expt_cfg['stop'], expt_cfg['step'])
        with SlabFile(data_file) as a:
            for qubit_id in on_qubits:
                data_list = np.array(a['expt_avg_data_ch%s' % qubit_id])
                fitdata = fitdecaysin(expt_pts, data_list, showfit=False)
                qubit_freq = quantum_device_cfg['qubit']['%s' % qubit_id]['freq']
                ramsey_freq = experiment_cfg['ramsey']['ramsey_freq']
                real_qubit_freq = qubit_freq + ramsey_freq - fitdata[1]
                possible_qubit_freq = qubit_freq + ramsey_freq + fitdata[1]
                flux_offset = -(real_qubit_freq - qubit_freq) / quantum_device_cfg['freq_flux'][qubit_id][
                    'freq_flux_slope']
                suggested_flux = round(quantum_device_cfg['freq_flux'][qubit_id]['current_mA'] + flux_offset, 4)
                print('qubit %s' %qubit_id)
                print('original qubit frequency:' + str(qubit_freq) + " GHz")
                print('Decay Time: %s ns' % (fitdata[3]))
                print("Oscillation frequency: %s GHz" % str(fitdata[1]))
                print("Suggested qubit frequency: %s GHz" % str(real_qubit_freq))
                print("possible qubit frequency: %s GHz" % str(possible_qubit_freq))
                print("Suggested flux: %s mA" % str(suggested_flux))
                print("Max contrast: %s" % str(max(data_list)-min(data_list)))

                freq_offset = ramsey_freq - fitdata[1]

                if (abs(freq_offset) < 100e-6):
                    print("Frequency is within expected value. No further calibration required.")
                    if qubit_id in uncalibrated_qubits: uncalibrated_qubits.remove(qubit_id)
                elif (abs(flux_offset) < 0.01):
                    print("Changing flux to the suggested flux: %s mA" % str(suggested_flux))
                    quantum_device_cfg['freq_flux'][qubit_id]['current_mA'] = suggested_flux
                else:
                    print("Large change in flux is required; please do so manually")
                    return

                if uncalibrated_qubits == []:
                    print("All qubits frequency calibrated.")
                    with open(os.path.join(path, 'quantum_device_config.json'), 'w') as f:
                        json.dump(quantum_device_cfg, f)
                    return

def pulse_probe_flux_sweep(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['pulse_probe_flux_sweep']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'pulse_probe_flux_sweep', suffix='.h5'))
    on_qubits = expt_cfg['on_qubits']

    experiment_cfg['pulse_probe']['pulse_amp'] = expt_cfg['pulse_amp']
    experiment_cfg['pulse_probe']['pulse_length'] = expt_cfg['pulse_length']
    experiment_cfg['pulse_probe']['start'] = expt_cfg['freq_start']
    experiment_cfg['pulse_probe']['stop'] = expt_cfg['freq_stop']
    experiment_cfg['pulse_probe']['step'] = expt_cfg['freq_step']
    experiment_cfg['pulse_probe']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['pulse_probe']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['pulse_probe']['ge_pi'] = expt_cfg['ge_pi']
    experiment_cfg['pulse_probe']['singleshot'] = expt_cfg['singleshot']
    experiment_cfg['pulse_probe']['flux_probe'] = expt_cfg['flux_probe']
    experiment_cfg['pulse_probe']['pi_calibration'] = expt_cfg['pi_calibration']
    experiment_cfg['pulse_probe']['calibration_qubit'] = expt_cfg['calibration_qubit']
    experiment_cfg['pulse_probe']['flux_pi_calibration'] = expt_cfg['flux_pi_calibration']

    if expt_cfg['use_qubit_spec'][0]:
        for qubit_id in on_qubits:
            p5 = np.poly1d(np.polyfit(quantum_device_cfg['qubit_spec'][qubit_id]['current_mA'], quantum_device_cfg['qubit_spec'][qubit_id]['freq'], 5))

    for flux2 in np.arange(expt_cfg['flux2_start'], expt_cfg['flux2_stop'], expt_cfg['flux2_step']):
        for flux1 in np.arange(expt_cfg['flux1_start'], expt_cfg['flux1_stop'], expt_cfg['flux1_step']):

            if expt_cfg['use_qubit_spec'][0]:
                qubit_freq = p5(flux1)
                experiment_cfg['pulse_probe']['start'] = qubit_freq - expt_cfg['use_qubit_spec'][1]/2
                experiment_cfg['pulse_probe']['stop'] = qubit_freq + expt_cfg['use_qubit_spec'][1]/2

            quantum_device_cfg['freq_flux']['1']['current_mA'] = flux1
            quantum_device_cfg['freq_flux']['2']['current_mA'] = flux2

            print('flux is', [flux1, flux2])
            print('freq range is', [experiment_cfg['pulse_probe']['start'], experiment_cfg['pulse_probe']['stop']])

            ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
            sequences = ps.get_experiment_sequences('pulse_probe')
            update_awg = True

            exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
            exp.run_experiment(sequences, path, 'pulse_probe_flux_sweep', seq_data_file, update_awg)

            update_awg = False

def pulse_probe_power_sweep(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['pulse_probe_power_sweep']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'pulse_probe_power_sweep', suffix='.h5'))
    on_qubits = expt_cfg['on_qubits']

    for amp in np.arange(expt_cfg['amp_start'], expt_cfg['amp_stop'], expt_cfg['amp_step']):
        experiment_cfg['pulse_probe']['pulse_amp'] = amp
        experiment_cfg['pulse_probe']['pulse_length'] = expt_cfg['pulse_length']
        experiment_cfg['pulse_probe']['start'] = expt_cfg['freq_start']
        experiment_cfg['pulse_probe']['stop'] = expt_cfg['freq_stop']
        experiment_cfg['pulse_probe']['step'] = expt_cfg['freq_step']
        experiment_cfg['pulse_probe']['acquisition_num'] = expt_cfg['acquisition_num']
        experiment_cfg['pulse_probe']['on_qubits'] = expt_cfg['on_qubits']
        experiment_cfg['pulse_probe']['ge_pi'] = expt_cfg['ge_pi']
        experiment_cfg['pulse_probe']['singleshot'] = expt_cfg['singleshot']
        experiment_cfg['pulse_probe']['flux_probe'] = expt_cfg['flux_probe']
        experiment_cfg['pulse_probe']['pi_calibration'] = expt_cfg['pi_calibration']
        experiment_cfg['pulse_probe']['calibration_qubit'] = expt_cfg['calibration_qubit']
        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('pulse_probe')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'pulse_probe_power_sweep', seq_data_file, update_awg)

        update_awg = False


def pulse_probe_through_flux_dc_flux_sweep(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['pulse_probe_through_flux_dc_flux_sweep']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'pulse_probe_through_flux_dc_flux_sweep', suffix='.h5'))
    on_qubits = expt_cfg['on_qubits']

    experiment_cfg['pulse_probe_through_flux']['pulse_length'] = expt_cfg['pulse_length']
    experiment_cfg['pulse_probe_through_flux']['start'] = expt_cfg['freq_start']
    experiment_cfg['pulse_probe_through_flux']['stop'] = expt_cfg['freq_stop']
    experiment_cfg['pulse_probe_through_flux']['step'] = expt_cfg['freq_step']
    experiment_cfg['pulse_probe_through_flux']['ge_pi'] = expt_cfg['ge_pi']
    experiment_cfg['pulse_probe_through_flux']['ef_pi'] = expt_cfg['ef_pi']
    experiment_cfg['pulse_probe_through_flux']['singleshot'] = expt_cfg['singleshot']
    experiment_cfg['pulse_probe_through_flux']['flux_pi_calibration'] = expt_cfg['flux_pi_calibration']
    experiment_cfg['pulse_probe_through_flux']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['pulse_probe_through_flux']['time_bin_data'] = expt_cfg['time_bin_data']
    experiment_cfg['pulse_probe_through_flux']['flux_amp'] = expt_cfg['flux_amp']
    experiment_cfg['pulse_probe_through_flux']['phase'] = expt_cfg['phase']
    experiment_cfg['pulse_probe_through_flux']['flux_line'] = expt_cfg['flux_line']
    experiment_cfg['pulse_probe_through_flux']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['pulse_probe_through_flux']['flux_pulse'] = expt_cfg['flux_pulse']
    experiment_cfg['pulse_probe_through_flux']['pi_calibration'] = expt_cfg['pi_calibration']

    for index, dc_flux in enumerate(np.arange(expt_cfg['dc_flux_start'], expt_cfg['dc_flux_stop'], expt_cfg['dc_flux_step'])):

        print('Index: %s dc_flux. = %s mA' %(index, dc_flux))
        quantum_device_cfg['freq_flux'][expt_cfg['dc_flux_line']]['current_mA'] = dc_flux

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('pulse_probe_through_flux')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'pulse_probe_through_flux_dc_flux_sweep', seq_data_file, update_awg)

        update_awg = False


def pulse_probe_through_flux_amp_sweep(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['pulse_probe_through_flux_amp_sweep']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'pulse_probe_through_flux_amp_sweep', suffix='.h5'))

    experiment_cfg['pulse_probe_through_flux']['pulse_length'] = expt_cfg['pulse_length']
    experiment_cfg['pulse_probe_through_flux']['start'] = expt_cfg['freq_start']
    experiment_cfg['pulse_probe_through_flux']['stop'] = expt_cfg['freq_stop']
    experiment_cfg['pulse_probe_through_flux']['step'] = expt_cfg['freq_step']
    experiment_cfg['pulse_probe_through_flux']['ge_pi'] = expt_cfg['ge_pi']
    experiment_cfg['pulse_probe_through_flux']['ef_pi'] = expt_cfg['ef_pi']
    experiment_cfg['pulse_probe_through_flux']['singleshot'] = expt_cfg['singleshot']
    experiment_cfg['pulse_probe_through_flux']['flux_pi_calibration'] = expt_cfg['flux_pi_calibration']
    experiment_cfg['pulse_probe_through_flux']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['pulse_probe_through_flux']['time_bin_data'] = expt_cfg['time_bin_data']
    experiment_cfg['pulse_probe_through_flux']['phase'] = expt_cfg['phase']
    experiment_cfg['pulse_probe_through_flux']['flux_line'] = expt_cfg['flux_line']
    experiment_cfg['pulse_probe_through_flux']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['pulse_probe_through_flux']['flux_pulse'] = expt_cfg['flux_pulse']
    experiment_cfg['pulse_probe_through_flux']['pi_calibration'] = expt_cfg['pi_calibration']

    no_of_step = expt_cfg['no_of_step']
    step1 = (expt_cfg['flux_amp_stop'][0] - expt_cfg['flux_amp_start'][0])/(no_of_step-1)
    step2 = (expt_cfg['flux_amp_stop'][1] - expt_cfg['flux_amp_start'][1])/(no_of_step-1)

    for index in range(no_of_step):

        amp1 = expt_cfg['flux_amp_start'][0] + step1*index
        amp2 = expt_cfg['flux_amp_start'][1] + step2*index
        print('Index: %s flux_amp = [%s, %s]' %(index, amp1, amp2))
        experiment_cfg['pulse_probe_through_flux']['flux_amp'] = [amp1, amp2]

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('pulse_probe_through_flux')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'pulse_probe_through_flux_amp_sweep', seq_data_file, update_awg)

        update_awg = False


def sideband_rabi_sweep(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['sideband_rabi_sweep']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'sideband_rabi_sweep', suffix='.h5'))
    on_qubits = expt_cfg['on_qubits']

    experiment_cfg['sideband_rabi']['amp'] = expt_cfg['amp']
    experiment_cfg['sideband_rabi']['start'] = expt_cfg['time_start']
    experiment_cfg['sideband_rabi']['stop'] = expt_cfg['time_stop']
    experiment_cfg['sideband_rabi']['step'] = expt_cfg['time_step']
    experiment_cfg['sideband_rabi']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['sideband_rabi']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['sideband_rabi']['calibration_qubit'] = expt_cfg['calibration_qubit']
    experiment_cfg['sideband_rabi']['pi_calibration'] = expt_cfg['pi_calibration']
    experiment_cfg['sideband_rabi']['flux_pi_calibration'] = expt_cfg['flux_pi_calibration']
    experiment_cfg['sideband_rabi']['ge_pi'] = expt_cfg['ge_pi']
    experiment_cfg['sideband_rabi']['ef_pi'] = expt_cfg['ef_pi']
    experiment_cfg['sideband_rabi']['flux_line'] = expt_cfg['flux_line']

    for freq in np.arange(expt_cfg['freq_start'], expt_cfg['freq_stop'], expt_cfg['freq_step']):

        experiment_cfg['sideband_rabi']['freq'] = freq

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('sideband_rabi')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'sideband_rabi_sweep', seq_data_file, update_awg)

        update_awg = False


def sideband_rabi_drive_both_flux_freq_sweep(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['sideband_rabi_drive_both_flux_freq_sweep']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'sideband_rabi_drive_both_flux_freq_sweep', suffix='.h5'))
    on_qubits = expt_cfg['on_qubits']

    experiment_cfg['sideband_rabi_drive_both_flux']['amp'] = expt_cfg['amp']
    experiment_cfg['sideband_rabi_drive_both_flux']['start'] = expt_cfg['time_start']
    experiment_cfg['sideband_rabi_drive_both_flux']['stop'] = expt_cfg['time_stop']
    experiment_cfg['sideband_rabi_drive_both_flux']['step'] = expt_cfg['time_step']
    experiment_cfg['sideband_rabi_drive_both_flux']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['sideband_rabi_drive_both_flux']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['sideband_rabi_drive_both_flux']['calibration_qubit'] = expt_cfg['calibration_qubit']
    experiment_cfg['sideband_rabi_drive_both_flux']['pi_calibration'] = expt_cfg['pi_calibration']
    experiment_cfg['sideband_rabi_drive_both_flux']['flux_pi_calibration'] = expt_cfg['flux_pi_calibration']
    experiment_cfg['sideband_rabi_drive_both_flux']['ge_pi'] = expt_cfg['ge_pi']
    experiment_cfg['sideband_rabi_drive_both_flux']['ef_pi'] = expt_cfg['ef_pi']
    experiment_cfg['sideband_rabi_drive_both_flux']['ge_both_pi'] = expt_cfg['ge_both_pi']
    experiment_cfg['sideband_rabi_drive_both_flux']['flux_line'] = expt_cfg['flux_line']
    experiment_cfg['sideband_rabi_drive_both_flux']['flux_pulse'] = expt_cfg['flux_pulse']
    experiment_cfg['sideband_rabi_drive_both_flux']['phase'] = expt_cfg['phase']
    experiment_cfg['sideband_rabi_drive_both_flux']['flux_LO'] = expt_cfg['flux_LO']
    experiment_cfg['sideband_rabi_drive_both_flux']['pre_pulse'] = expt_cfg['pre_pulse']

    for index, freq in enumerate(np.arange(expt_cfg['freq_start'], expt_cfg['freq_stop'], expt_cfg['freq_step'])):

        print('Index: %s Freq. = %s GHz' %(index, freq))
        experiment_cfg['sideband_rabi_drive_both_flux']['freq'] = freq

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('sideband_rabi_drive_both_flux')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'sideband_rabi_drive_both_flux_freq_sweep', seq_data_file, update_awg)

        update_awg = False


def sideband_rabi_drive_both_flux_phase_sweep(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['sideband_rabi_drive_both_flux_phase_sweep']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'sideband_rabi_drive_both_flux_phase_sweep', suffix='.h5'))
    on_qubits = expt_cfg['on_qubits']

    experiment_cfg['sideband_rabi_drive_both_flux']['amp'] = expt_cfg['amp']
    experiment_cfg['sideband_rabi_drive_both_flux']['start'] = expt_cfg['time_start']
    experiment_cfg['sideband_rabi_drive_both_flux']['stop'] = expt_cfg['time_stop']
    experiment_cfg['sideband_rabi_drive_both_flux']['step'] = expt_cfg['time_step']
    experiment_cfg['sideband_rabi_drive_both_flux']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['sideband_rabi_drive_both_flux']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['sideband_rabi_drive_both_flux']['calibration_qubit'] = expt_cfg['calibration_qubit']
    experiment_cfg['sideband_rabi_drive_both_flux']['pi_calibration'] = expt_cfg['pi_calibration']
    experiment_cfg['sideband_rabi_drive_both_flux']['flux_pi_calibration'] = expt_cfg['flux_pi_calibration']
    experiment_cfg['sideband_rabi_drive_both_flux']['ge_pi'] = expt_cfg['ge_pi']
    experiment_cfg['sideband_rabi_drive_both_flux']['ef_pi'] = expt_cfg['ef_pi']
    experiment_cfg['sideband_rabi_drive_both_flux']['ge_both_pi'] = expt_cfg['ge_both_pi']
    experiment_cfg['sideband_rabi_drive_both_flux']['flux_line'] = expt_cfg['flux_line']
    experiment_cfg['sideband_rabi_drive_both_flux']['flux_pulse'] = expt_cfg['flux_pulse']
    experiment_cfg['sideband_rabi_drive_both_flux']['freq'] = expt_cfg['freq']
    experiment_cfg['sideband_rabi_drive_both_flux']['pre_pulse'] = expt_cfg['pre_pulse']

    for index, phase in enumerate(np.arange(expt_cfg['phase_start'], expt_cfg['phase_stop'], expt_cfg['phase_step'])):

        phase1 = quantum_device_cfg['flux_pulse_info']['1']['pulse_phase'] + phase
        phase2 = quantum_device_cfg['flux_pulse_info']['2']['pulse_phase'] + phase*0
        experiment_cfg['sideband_rabi_drive_both_flux']['phase'][0] = phase1
        experiment_cfg['sideband_rabi_drive_both_flux']['phase'][1] = phase2
        print('Index: %s Phase1: %s' %(index, phase1))
        print('Index: %s Phase2: %s' %(index, phase2))

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('sideband_rabi_drive_both_flux')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'sideband_rabi_drive_both_flux_phase_sweep', seq_data_file, update_awg)

        update_awg = False

def sideband_rabi_drive_both_flux_amp1_sweep(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['sideband_rabi_drive_both_flux_amp1_sweep']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'sideband_rabi_drive_both_flux_amp1_sweep', suffix='.h5'))
    on_qubits = expt_cfg['on_qubits']

    experiment_cfg['sideband_rabi_drive_both_flux']['phase'] = expt_cfg['phase']
    experiment_cfg['sideband_rabi_drive_both_flux']['start'] = expt_cfg['time_start']
    experiment_cfg['sideband_rabi_drive_both_flux']['stop'] = expt_cfg['time_stop']
    experiment_cfg['sideband_rabi_drive_both_flux']['step'] = expt_cfg['time_step']
    experiment_cfg['sideband_rabi_drive_both_flux']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['sideband_rabi_drive_both_flux']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['sideband_rabi_drive_both_flux']['calibration_qubit'] = expt_cfg['calibration_qubit']
    experiment_cfg['sideband_rabi_drive_both_flux']['pi_calibration'] = expt_cfg['pi_calibration']
    experiment_cfg['sideband_rabi_drive_both_flux']['flux_pi_calibration'] = expt_cfg['flux_pi_calibration']
    experiment_cfg['sideband_rabi_drive_both_flux']['ge_pi'] = expt_cfg['ge_pi']
    experiment_cfg['sideband_rabi_drive_both_flux']['ef_pi'] = expt_cfg['ef_pi']
    experiment_cfg['sideband_rabi_drive_both_flux']['ge_both_pi'] = expt_cfg['ge_both_pi']
    experiment_cfg['sideband_rabi_drive_both_flux']['flux_line'] = expt_cfg['flux_line']
    experiment_cfg['sideband_rabi_drive_both_flux']['flux_pulse'] = expt_cfg['flux_pulse']
    experiment_cfg['sideband_rabi_drive_both_flux']['freq'] = expt_cfg['freq']
    experiment_cfg['sideband_rabi_drive_both_flux']['pre_pulse'] = expt_cfg['pre_pulse']

    for index, amplitude in enumerate(np.arange(expt_cfg['amp_start'], expt_cfg['amp_stop'], expt_cfg['amp_step'])):

        experiment_cfg['sideband_rabi_drive_both_flux']['amp'][0] = amplitude
        experiment_cfg['sideband_rabi_drive_both_flux']['amp'][1] = expt_cfg['amp2']
        print('Index: %s amp1: %s' %(index, amplitude))

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('sideband_rabi_drive_both_flux')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'sideband_rabi_drive_both_flux_amp1_sweep', seq_data_file, update_awg)

        update_awg = False

def sideband_rabi_drive_both_flux_amp2_sweep(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['sideband_rabi_drive_both_flux_amp2_sweep']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'sideband_rabi_drive_both_flux_amp2_sweep', suffix='.h5'))
    on_qubits = expt_cfg['on_qubits']

    experiment_cfg['sideband_rabi_drive_both_flux']['phase'] = expt_cfg['phase']
    experiment_cfg['sideband_rabi_drive_both_flux']['start'] = expt_cfg['time_start']
    experiment_cfg['sideband_rabi_drive_both_flux']['stop'] = expt_cfg['time_stop']
    experiment_cfg['sideband_rabi_drive_both_flux']['step'] = expt_cfg['time_step']
    experiment_cfg['sideband_rabi_drive_both_flux']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['sideband_rabi_drive_both_flux']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['sideband_rabi_drive_both_flux']['calibration_qubit'] = expt_cfg['calibration_qubit']
    experiment_cfg['sideband_rabi_drive_both_flux']['pi_calibration'] = expt_cfg['pi_calibration']
    experiment_cfg['sideband_rabi_drive_both_flux']['flux_pi_calibration'] = expt_cfg['flux_pi_calibration']
    experiment_cfg['sideband_rabi_drive_both_flux']['ge_pi'] = expt_cfg['ge_pi']
    experiment_cfg['sideband_rabi_drive_both_flux']['ef_pi'] = expt_cfg['ef_pi']
    experiment_cfg['sideband_rabi_drive_both_flux']['ge_both_pi'] = expt_cfg['ge_both_pi']
    experiment_cfg['sideband_rabi_drive_both_flux']['flux_line'] = expt_cfg['flux_line']
    experiment_cfg['sideband_rabi_drive_both_flux']['flux_pulse'] = expt_cfg['flux_pulse']
    experiment_cfg['sideband_rabi_drive_both_flux']['freq'] = expt_cfg['freq']
    experiment_cfg['sideband_rabi_drive_both_flux']['pre_pulse'] = expt_cfg['pre_pulse']

    for index, amplitude in enumerate(np.arange(expt_cfg['amp_start'], expt_cfg['amp_stop'], expt_cfg['amp_step'])):

        experiment_cfg['sideband_rabi_drive_both_flux']['amp'][1] = amplitude
        experiment_cfg['sideband_rabi_drive_both_flux']['amp'][0] = expt_cfg['amp1']
        print('Index: %s amp2: %s' %(index, amplitude))

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('sideband_rabi_drive_both_flux')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'sideband_rabi_drive_both_flux_amp2_sweep', seq_data_file, update_awg)

        update_awg = False

def half_pi_both_freq_and_length_sweep(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['half_pi_both_freq_and_length_sweep']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'half_pi_both_freq_and_length_sweep', suffix='.h5'))
    on_qubits = expt_cfg['on_qubits']

    experiment_cfg['half_pi_sweep']['amp'] = expt_cfg['amp']
    experiment_cfg['half_pi_sweep']['pulse_phase'] = expt_cfg['pulse_phase']
    experiment_cfg['half_pi_sweep']['start_pi_length'] = expt_cfg['start_pi_length']
    experiment_cfg['half_pi_sweep']['stop_pi_length'] = expt_cfg['stop_pi_length']
    experiment_cfg['half_pi_sweep']['step_pi_length'] = expt_cfg['step_pi_length']
    experiment_cfg['half_pi_sweep']['ge_pi'] = expt_cfg['ge_pi']
    experiment_cfg['half_pi_sweep']['pi_calibration'] = expt_cfg['pi_calibration']
    experiment_cfg['half_pi_sweep']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['half_pi_sweep']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['half_pi_sweep']['on_cavity'] = expt_cfg['on_cavity']
    experiment_cfg['half_pi_sweep']['calibration_qubit'] = expt_cfg['calibration_qubit']


    for index, qubit_freq in enumerate(np.arange(expt_cfg['qubit_freq_start'], expt_cfg['qubit_freq_stop'], expt_cfg['qubit_freq_step'])):

        experiment_cfg['half_pi_sweep']['qubit_freq'][0] = qubit_freq
        experiment_cfg['half_pi_sweep']['qubit_freq'][1] = qubit_freq
        print('Index: %s Freq: %s' %(index, qubit_freq))

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('half_pi_sweep')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'half_pi_both_freq_and_length_sweep', seq_data_file, update_awg)

        update_awg = False


def half_pi_both_phase_and_length_sweep(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['half_pi_both_phase_and_length_sweep']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'half_pi_both_phase_and_length_sweep', suffix='.h5'))
    on_qubits = expt_cfg['on_qubits']

    experiment_cfg['half_pi_sweep_phase']['amp'] = expt_cfg['amp']
    experiment_cfg['half_pi_sweep_phase']['qubit_freq'] = expt_cfg['pulse_freq']
    experiment_cfg['half_pi_sweep_phase']['start_pi_phase'] = expt_cfg['start_pi_phase']
    experiment_cfg['half_pi_sweep_phase']['stop_pi_phase'] = expt_cfg['stop_pi_phase']
    experiment_cfg['half_pi_sweep_phase']['step_pi_phase'] = expt_cfg['step_pi_phase']
    experiment_cfg['half_pi_sweep_phase']['ge_pi'] = expt_cfg['ge_pi']
    experiment_cfg['half_pi_sweep_phase']['pi_calibration'] = expt_cfg['pi_calibration']
    experiment_cfg['half_pi_sweep_phase']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['half_pi_sweep_phase']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['half_pi_sweep_phase']['on_cavity'] = expt_cfg['on_cavity']
    experiment_cfg['half_pi_sweep_phase']['calibration_qubit'] = expt_cfg['calibration_qubit']


    for index, gate_length in enumerate(np.arange(expt_cfg['start_pi_length'], expt_cfg['stop_pi_length'], expt_cfg['step_pi_length'])):

        experiment_cfg['half_pi_sweep_phase']['pulse_length'][0] = gate_length
        experiment_cfg['half_pi_sweep_phase']['pulse_length'][1] = expt_cfg['half_pi_length']
        print('Index: %s Pulse_length: %s' %(index, gate_length))

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('half_pi_sweep_phase')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'half_pi_both_phase_and_length_sweep', seq_data_file, update_awg)

        update_awg = False


def half_pi_both_phase_and_freq_sweep(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['half_pi_both_phase_and_freq_sweep']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'half_pi_both_phase_and_freq_sweep', suffix='.h5'))
    on_qubits = expt_cfg['on_qubits']

    experiment_cfg['half_pi_sweep_phase']['amp'] = expt_cfg['amp']
    experiment_cfg['half_pi_sweep_phase']['pulse_length'] = expt_cfg['pulse_length']
    experiment_cfg['half_pi_sweep_phase']['start_pi_phase'] = expt_cfg['start_pi_phase']
    experiment_cfg['half_pi_sweep_phase']['stop_pi_phase'] = expt_cfg['stop_pi_phase']
    experiment_cfg['half_pi_sweep_phase']['step_pi_phase'] = expt_cfg['step_pi_phase']
    experiment_cfg['half_pi_sweep_phase']['ge_pi'] = expt_cfg['ge_pi']
    experiment_cfg['half_pi_sweep_phase']['pi_calibration'] = expt_cfg['pi_calibration']
    experiment_cfg['half_pi_sweep_phase']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['half_pi_sweep_phase']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['half_pi_sweep_phase']['on_cavity'] = expt_cfg['on_cavity']
    experiment_cfg['half_pi_sweep_phase']['calibration_qubit'] = expt_cfg['calibration_qubit']


    for index, qubit_freq in enumerate(np.arange(expt_cfg['start_pi_freq'], expt_cfg['stop_pi_freq'], expt_cfg['step_pi_freq'])):

        experiment_cfg['half_pi_sweep_phase']['qubit_freq'][0] = qubit_freq
        experiment_cfg['half_pi_sweep_phase']['qubit_freq'][1] = qubit_freq
        print('Index: %s Qubit_freq: %s' %(index, qubit_freq))

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('half_pi_sweep_phase')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'half_pi_both_phase_and_freq_sweep', seq_data_file, update_awg)

        update_awg = False


def sideband_rabi_drive_both_flux_LO_freq_sweep(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['sideband_rabi_drive_both_flux_LO_freq_sweep']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'sideband_rabi_drive_both_flux_LO_freq_sweep', suffix='.h5'))
    on_qubits = expt_cfg['on_qubits']

    experiment_cfg['sideband_rabi_drive_both_flux_LO']['amp'] = expt_cfg['amp']
    experiment_cfg['sideband_rabi_drive_both_flux_LO']['start'] = expt_cfg['time_start']
    experiment_cfg['sideband_rabi_drive_both_flux_LO']['stop'] = expt_cfg['time_stop']
    experiment_cfg['sideband_rabi_drive_both_flux_LO']['step'] = expt_cfg['time_step']
    experiment_cfg['sideband_rabi_drive_both_flux_LO']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['sideband_rabi_drive_both_flux_LO']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['sideband_rabi_drive_both_flux_LO']['calibration_qubit'] = expt_cfg['calibration_qubit']
    experiment_cfg['sideband_rabi_drive_both_flux_LO']['pi_calibration'] = expt_cfg['pi_calibration']
    experiment_cfg['sideband_rabi_drive_both_flux_LO']['flux_pi_calibration'] = expt_cfg['flux_pi_calibration']
    experiment_cfg['sideband_rabi_drive_both_flux_LO']['ge_pi'] = expt_cfg['ge_pi']
    experiment_cfg['sideband_rabi_drive_both_flux_LO']['ef_pi'] = expt_cfg['ef_pi']
    experiment_cfg['sideband_rabi_drive_both_flux_LO']['flux_line'] = expt_cfg['flux_line']
    experiment_cfg['sideband_rabi_drive_both_flux_LO']['flux_pulse'] = expt_cfg['flux_pulse']
    experiment_cfg['sideband_rabi_drive_both_flux_LO']['phase'] = expt_cfg['phase']

    for index, freq in enumerate(np.arange(expt_cfg['freq_start'], expt_cfg['freq_stop'], expt_cfg['freq_step'])):

        print('Index: %s LO freq. = %s GHz' %(index, freq))
        experiment_cfg['sideband_rabi_drive_both_flux_LO']['flux_LO'] = freq
        experiment_cfg['sideband_rabi_drive_both_flux_LO_freq_sweep']['flux_LO'] = freq # it's a quick hack

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('sideband_rabi_drive_both_flux_LO')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'sideband_rabi_drive_both_flux_LO_freq_sweep', seq_data_file, update_awg)

        update_awg = False


def multitone_error_divisible_gate_tg_sweep(quantum_device_cfg, experiment_cfg, hardware_cfg, path): ## UNCHECKED
    expt_cfg = experiment_cfg['multitone_error_divisible_gate_tg_sweep']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'multitone_error_divisible_gate_tg_sweep', suffix='.h5'))

    experiment_cfg['multitone_error_divisible_gate']['amps'] = expt_cfg['amps']
    experiment_cfg['multitone_error_divisible_gate']['freqs'] = expt_cfg['freqs']
    experiment_cfg['multitone_error_divisible_gate']['time_length'] = expt_cfg['time_length']
    experiment_cfg['multitone_error_divisible_gate']['ge_pi'] = expt_cfg['ge_pi']
    experiment_cfg['multitone_error_divisible_gate']['ef_pi'] = expt_cfg['ef_pi']
    experiment_cfg['multitone_error_divisible_gate']['phases'] = expt_cfg['phases']
    experiment_cfg['multitone_error_divisible_gate']['stop_no'] = expt_cfg['stop_no']
    experiment_cfg['multitone_error_divisible_gate']['step_no'] = expt_cfg['step_no']
    experiment_cfg['multitone_error_divisible_gate']['start_no'] = expt_cfg['start_no']
    experiment_cfg['multitone_error_divisible_gate']['shape'] = expt_cfg['shape']
    experiment_cfg['multitone_error_divisible_gate']['pi_calibration'] = expt_cfg['pi_calibration']
    experiment_cfg['multitone_error_divisible_gate']['flux_pi_calibration'] = expt_cfg['flux_pi_calibration']
    experiment_cfg['multitone_error_divisible_gate']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['multitone_error_divisible_gate']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['multitone_error_divisible_gate']['flux_pulse'] = expt_cfg['flux_pulse']
    experiment_cfg['multitone_error_divisible_gate']['flux_line'] = expt_cfg['flux_line']
    experiment_cfg['multitone_error_divisible_gate']['calibration_qubit'] = expt_cfg['calibration_qubit']
    experiment_cfg['multitone_error_divisible_gate']['pre_pulse'] = expt_cfg['pre_pulse']
    experiment_cfg['multitone_error_divisible_gate']['inverse_rotation'] = expt_cfg['inverse_rotation']
    experiment_cfg['multitone_error_divisible_gate']['edg_line'] = expt_cfg['edg_line']
    experiment_cfg['multitone_error_divisible_gate']['edg_no'] = expt_cfg['edg_no']

    tgs_arr = np.arange(expt_cfg['tg_start'], expt_cfg['tg_stop'], expt_cfg['tg_step'])


    for ii, tgs in enumerate(tgs_arr):

        print('Index %s: Single Gate tg: %s' %(ii, tgs))
        experiment_cfg['multitone_error_divisible_gate']['shape'][4] = tgs
        print(experiment_cfg['multitone_error_divisible_gate'])

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('multitone_error_divisible_gate')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'multitone_error_divisible_gate_tg_sweep', seq_data_file, update_awg)

        update_awg = False



def multitone_error_divisible_gate_f_sweep(quantum_device_cfg, experiment_cfg, hardware_cfg, path): ## UNCHECKED
    expt_cfg = experiment_cfg['multitone_error_divisible_gate_f_sweep']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'multitone_error_divisible_gate_f_sweep', suffix='.h5'))

    experiment_cfg['multitone_error_divisible_gate']['amps'] = expt_cfg['amps']
    experiment_cfg['multitone_error_divisible_gate']['freqs'] = expt_cfg['freqs']
    experiment_cfg['multitone_error_divisible_gate']['time_length'] = expt_cfg['time_length']
    experiment_cfg['multitone_error_divisible_gate']['ge_pi'] = expt_cfg['ge_pi']
    experiment_cfg['multitone_error_divisible_gate']['ef_pi'] = expt_cfg['ef_pi']
    experiment_cfg['multitone_error_divisible_gate']['phases'] = expt_cfg['phases']
    experiment_cfg['multitone_error_divisible_gate']['stop_no'] = expt_cfg['stop_no']
    experiment_cfg['multitone_error_divisible_gate']['step_no'] = expt_cfg['step_no']
    experiment_cfg['multitone_error_divisible_gate']['start_no'] = expt_cfg['start_no']
    experiment_cfg['multitone_error_divisible_gate']['shape'] = expt_cfg['shape']
    experiment_cfg['multitone_error_divisible_gate']['pi_calibration'] = expt_cfg['pi_calibration']
    experiment_cfg['multitone_error_divisible_gate']['flux_pi_calibration'] = expt_cfg['flux_pi_calibration']
    experiment_cfg['multitone_error_divisible_gate']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['multitone_error_divisible_gate']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['multitone_error_divisible_gate']['flux_pulse'] = expt_cfg['flux_pulse']
    experiment_cfg['multitone_error_divisible_gate']['flux_line'] = expt_cfg['flux_line']
    experiment_cfg['multitone_error_divisible_gate']['calibration_qubit'] = expt_cfg['calibration_qubit']
    experiment_cfg['multitone_error_divisible_gate']['pre_pulse'] = expt_cfg['pre_pulse']
    experiment_cfg['multitone_error_divisible_gate']['inverse_rotation'] = expt_cfg['inverse_rotation']
    experiment_cfg['multitone_error_divisible_gate']['edg_line'] = expt_cfg['edg_line']
    experiment_cfg['multitone_error_divisible_gate']['edg_no'] = expt_cfg['edg_no']

    freqs_arr = np.arange(expt_cfg['freq_start'], expt_cfg['freq_stop'], expt_cfg['freq_step'])


    for ii, freqs in enumerate(freqs_arr):

        print('Index %s: EDG frequency: %s' %(ii, freqs))
        experiment_cfg['multitone_error_divisible_gate']['shape'][2] = freqs
        print(experiment_cfg['multitone_error_divisible_gate'])

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('multitone_error_divisible_gate')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'multitone_error_divisible_gate_f_sweep', seq_data_file, update_awg)

        update_awg = False


def multitone_error_divisible_gate_freq_sweep(quantum_device_cfg, experiment_cfg, hardware_cfg, path): ## UNCHECKED
    expt_cfg = experiment_cfg['multitone_error_divisible_gate_freq_sweep']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'multitone_error_divisible_gate_freq_sweep', suffix='.h5'))

    experiment_cfg['multitone_error_divisible_gate']['amps'] = expt_cfg['amps']
    experiment_cfg['multitone_error_divisible_gate']['freqs'] = expt_cfg['freqs']
    experiment_cfg['multitone_error_divisible_gate']['time_length'] = expt_cfg['time_length']
    experiment_cfg['multitone_error_divisible_gate']['ge_pi'] = expt_cfg['ge_pi']
    experiment_cfg['multitone_error_divisible_gate']['ef_pi'] = expt_cfg['ef_pi']
    experiment_cfg['multitone_error_divisible_gate']['phases'] = expt_cfg['phases']
    experiment_cfg['multitone_error_divisible_gate']['stop_no'] = expt_cfg['stop_no']
    experiment_cfg['multitone_error_divisible_gate']['step_no'] = expt_cfg['step_no']
    experiment_cfg['multitone_error_divisible_gate']['start_no'] = expt_cfg['start_no']
    experiment_cfg['multitone_error_divisible_gate']['shape'] = expt_cfg['shape']
    experiment_cfg['multitone_error_divisible_gate']['pi_calibration'] = expt_cfg['pi_calibration']
    experiment_cfg['multitone_error_divisible_gate']['flux_pi_calibration'] = expt_cfg['flux_pi_calibration']
    experiment_cfg['multitone_error_divisible_gate']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['multitone_error_divisible_gate']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['multitone_error_divisible_gate']['flux_pulse'] = expt_cfg['flux_pulse']
    experiment_cfg['multitone_error_divisible_gate']['flux_line'] = expt_cfg['flux_line']
    experiment_cfg['multitone_error_divisible_gate']['calibration_qubit'] = expt_cfg['calibration_qubit']
    experiment_cfg['multitone_error_divisible_gate']['pre_pulse'] = expt_cfg['pre_pulse']
    experiment_cfg['multitone_error_divisible_gate']['inverse_rotation'] = expt_cfg['inverse_rotation']
    experiment_cfg['multitone_error_divisible_gate']['edg_line'] = expt_cfg['edg_line']
    experiment_cfg['multitone_error_divisible_gate']['edg_no'] = expt_cfg['edg_no']

    freqs_arr = np.arange(expt_cfg['freq_start'], expt_cfg['freq_stop'], expt_cfg['freq_step'])
    edg_line = int(expt_cfg['edg_line'])
    edg_no = int(expt_cfg['edg_no'])


    for ii, freqs in enumerate(freqs_arr):

        print('Index %s: Carrier frequency: %s' %(ii, freqs))
        experiment_cfg['multitone_error_divisible_gate']['freqs'][edg_line-1][edg_no] = freqs
        print(experiment_cfg['multitone_error_divisible_gate'])

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('multitone_error_divisible_gate')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'multitone_error_divisible_gate_freq_sweep', seq_data_file, update_awg)

        update_awg = False


def multitone_sideband_rabi_drive_both_flux_freq_sweep_old(quantum_device_cfg, experiment_cfg, hardware_cfg, path): ## UNCHECKED
    expt_cfg = experiment_cfg['multitone_sideband_rabi_drive_both_flux_freq_sweep']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'multitone_sideband_rabi_drive_both_flux_freq_sweep', suffix='.h5'))

    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['amps'] = expt_cfg['amps']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['pre_pulse'] = expt_cfg['pre_pulse']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['post_pulse'] = expt_cfg['post_pulse']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['phases'] = expt_cfg['phases']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['start'] = expt_cfg['time_start']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['stop'] = expt_cfg['time_stop']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['step'] = expt_cfg['time_step']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['ge_pi'] = expt_cfg['ge_pi']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['ef_pi'] = expt_cfg['ef_pi']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['Gaussian'] = expt_cfg['Gaussian']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['pi_calibration'] = expt_cfg['pi_calibration']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['flux_pi_calibration'] = expt_cfg['flux_pi_calibration']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['flux_pulse'] = expt_cfg['flux_pulse']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['flux_line'] = expt_cfg['flux_line']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['calibration_qubit'] = expt_cfg['calibration_qubit']

    # Sweep strategy: sweeping two tones together, the tones are picked up according to the 'sweep_tone_no'
    flag = []
    for i, no in enumerate(expt_cfg['sweep_lines']):
        flag.append(no-1)
    freq_start = expt_cfg['freqs_start'][flag[0]][expt_cfg['sweep_tone_no'][0][0] - 1]
    freq_stop = expt_cfg['freqs_stop'][flag[0]][expt_cfg['sweep_tone_no'][0][0] - 1]

    freqs_arr = np.arange(freq_start, freq_stop, expt_cfg['freq_steps'])
    freqs_list = []
    freqs_list.append(expt_cfg['freqs_start'][0][:])
    freqs_list.append(expt_cfg['freqs_start'][1][:])
    print(freqs_list)

    for ii, freqs in enumerate(freqs_arr):
        for jj, no in enumerate(flag):
            for kk in range(len(expt_cfg['sweep_tone_no'][jj])):
                freqs_list[no][expt_cfg['sweep_tone_no'][jj][kk] - 1] = freqs

        print('Index %s: Flux_drive_freqs: %s' %(ii, freqs_list))
        experiment_cfg['multitone_sideband_rabi_drive_both_flux']['freqs'] = freqs_list
        # print(experiment_cfg['multitone_sideband_rabi_drive_both_flux'])

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('multitone_sideband_rabi_drive_both_flux')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'multitone_sideband_rabi_drive_both_flux_freq_sweep', seq_data_file, update_awg)

        update_awg = False
        # print('Now value is:',expt_cfg['freqs_start'])


def multitone_sideband_rabi_drive_both_flux_freq_sweep(quantum_device_cfg, experiment_cfg, hardware_cfg, path): ## UNCHECKED
    expt_cfg = experiment_cfg['multitone_sideband_rabi_drive_both_flux_freq_sweep']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'multitone_sideband_rabi_drive_both_flux_freq_sweep', suffix='.h5'))

    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['amps'] = expt_cfg['amps']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['pre_pulse'] = expt_cfg['pre_pulse']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['post_pulse'] = expt_cfg['post_pulse']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['phases'] = expt_cfg['phases']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['start'] = expt_cfg['time_start']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['stop'] = expt_cfg['time_stop']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['step'] = expt_cfg['time_step']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['ge_pi'] = expt_cfg['ge_pi']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['ef_pi'] = expt_cfg['ef_pi']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['Gaussian'] = expt_cfg['Gaussian']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['pi_calibration'] = expt_cfg['pi_calibration']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['flux_pi_calibration'] = expt_cfg['flux_pi_calibration']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['flux_pulse'] = expt_cfg['flux_pulse']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['flux_line'] = expt_cfg['flux_line']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['calibration_qubit'] = expt_cfg['calibration_qubit']

    freqs_arr = np.linspace(expt_cfg['freqs_start'], expt_cfg['freqs_stop'], expt_cfg['no_points'])
    # Simultaneously sweeping both freq. array

    for ii, freqs in enumerate(freqs_arr):
        print('Index %s: rabi_drive_freqs: %s' % (ii, freqs.tolist()))
        experiment_cfg['multitone_sideband_rabi_drive_both_flux']['freqs'] = freqs.tolist()

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('multitone_sideband_rabi_drive_both_flux')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'multitone_sideband_rabi_drive_both_flux_freq_sweep', seq_data_file, update_awg)

        update_awg = False


def multitone_sideband_rabi_drive_both_flux_amp_sweep(quantum_device_cfg, experiment_cfg, hardware_cfg, path): ## UNCHECKED
    expt_cfg = experiment_cfg['multitone_sideband_rabi_drive_both_flux_amp_sweep']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'multitone_sideband_rabi_drive_both_flux_amp_sweep', suffix='.h5'))

    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['freqs'] = expt_cfg['freqs']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['phases'] = expt_cfg['phases']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['time_start'] = expt_cfg['time_start']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['time_stop'] = expt_cfg['time_stop']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['time_step'] = expt_cfg['time_step']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['Gaussian'] = expt_cfg['Gaussian']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['pi_calibration'] = expt_cfg['pi_calibration']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['flux_pi_calibration'] = expt_cfg['flux_pi_calibration']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['flux_pulse'] = expt_cfg['flux_pulse']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['flux_line'] = expt_cfg['flux_line']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['calibration_qubit'] = expt_cfg['calibration_qubit']

    # Sweep strategy: sweeping two tones together, the tones are picked up according to the 'sweep_tone_no'
    flag = []
    for i, no in enumerate(expt_cfg['sweep_lines']):
        flag.append(no-1)
    amp_start = expt_cfg['amps_start'][flag[0]][expt_cfg['sweep_tone_no'][0][0] - 1]
    amp_stop = expt_cfg['amps_stop'][flag[0]][expt_cfg['sweep_tone_no'][0][0] - 1]

    amps_arr = np.arange(amp_start, amp_stop, expt_cfg['amp_steps'])
    amps_list = []
    amps_list.append(expt_cfg['amps_start'][0][:])
    amps_list.append(expt_cfg['amps_start'][1][:])


    for ii, amps in enumerate(amps_arr):
        first = False
        for jj, no in enumerate(flag):
            for kk in range(len(expt_cfg['sweep_tone_no'][jj])):
                if (expt_cfg['fixed_ratio'])and(first):
                    ratio = expt_cfg['ratio']
                    amps_list[jj][expt_cfg['sweep_tone_no'][jj][kk] - 1] = amps*ratio
                else:
                    amps_list[jj][expt_cfg['sweep_tone_no'][jj][kk] - 1] = amps
                    first = True

        print('Index %s: Flux_drive_amps: %s' %(ii, amps_list))
        experiment_cfg['multitone_sideband_rabi_drive_both_flux']['amps'] = amps_list

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('multitone_sideband_rabi_drive_both_flux')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'multitone_sideband_rabi_drive_both_flux_amp_sweep', seq_data_file, update_awg)

        update_awg = False

def multitone_sideband_rabi_drive_both_flux_pre_phase_sweep(quantum_device_cfg, experiment_cfg, hardware_cfg, path): ## UNCHECKED
    expt_cfg = experiment_cfg['multitone_sideband_rabi_drive_both_flux_pre_phase_sweep']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'multitone_sideband_rabi_drive_both_flux_pre_phase_sweep', suffix='.h5'))

    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['amp_factor'] = expt_cfg['amp_factor']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['amps'] = expt_cfg['amps']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['phases'] = expt_cfg['phases']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['freqs'] = expt_cfg['freqs']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['ge_pi'] = expt_cfg['ge_pi']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['ef_pi'] = expt_cfg['ef_pi']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['start'] = expt_cfg['start']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['stop'] = expt_cfg['stop']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['step'] = expt_cfg['step']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['Gaussian'] = expt_cfg['Gaussian']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['pi_calibration'] = expt_cfg['pi_calibration']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['flux_pi_calibration'] = expt_cfg['flux_pi_calibration']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['flux_pulse'] = expt_cfg['flux_pulse']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['flux_line'] = expt_cfg['flux_line']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['phase_offset'] = expt_cfg['phase_offset']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['calibration_qubit'] = expt_cfg['calibration_qubit']
    experiment_cfg['multitone_sideband_rabi_drive_both_flux']['pre_pulse'] = expt_cfg['pre_pulse']



    for ii, phase in enumerate(np.arange(expt_cfg['phase_start'], expt_cfg['phase_stop'], expt_cfg['phase_step'])):

        print('Index %s: Pre_pulse_pahse: %s' %(ii, phase))
        experiment_cfg['multitone_sideband_rabi_drive_both_flux']['pre_phase'] = [[0,0],[phase,0]]

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('multitone_sideband_rabi_drive_both_flux')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'multitone_sideband_rabi_drive_both_flux_pre_phase_sweep', seq_data_file, update_awg)

        update_awg = False


def t1rho_amp_sweep(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['t1rho_amp_sweep']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 't1rho_amp_sweep', suffix='.h5'))
    on_qubits = expt_cfg['on_qubits']

    experiment_cfg['t1rho']['start'] = expt_cfg['time_start']
    experiment_cfg['t1rho']['stop'] = expt_cfg['time_stop']
    experiment_cfg['t1rho']['step'] = expt_cfg['time_step']
    experiment_cfg['t1rho']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['t1rho']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['t1rho']['calibration_qubit'] = expt_cfg['calibration_qubit']
    experiment_cfg['t1rho']['pi_calibration'] = expt_cfg['pi_calibration']
    experiment_cfg['t1rho']['ge_pi'] = expt_cfg['ge_pi']
    experiment_cfg['t1rho']['ef_pi'] = expt_cfg['ef_pi']
    experiment_cfg['t1rho']['flux_pi'] = expt_cfg['flux_pi']
    experiment_cfg['t1rho']['use_freq_amp_halfpi'] = expt_cfg['use_freq_amp_halfpi']
    experiment_cfg['t1rho']['mid_phase'] = expt_cfg['mid_phase']

    if expt_cfg['log_spacing']:
        num_pts = (expt_cfg['amp_stop']-expt_cfg['amp_start'])/expt_cfg['amp_step']  + 1
        amp_arr = np.linspace(np.log10(expt_cfg['amp_start']), np.log10(expt_cfg['amp_stop']), num_pts)
        amp_arr = 10**amp_arr
    else:
        amp_arr = np.arange(expt_cfg['amp_start'], expt_cfg['amp_stop'], expt_cfg['amp_step'])

    for index, amp in enumerate(amp_arr):

        experiment_cfg['t1rho']['amp'] = amp
        print('Index: %s amp: %s' %(index,amp))

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('t1rho')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 't1rho_amp_sweep', seq_data_file, update_awg)

        update_awg = False


def t1rho_mid_phase_sweep(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['t1rho_mid_phase_sweep']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 't1rho_mid_phase_sweep', suffix='.h5'))
    on_qubits = expt_cfg['on_qubits']

    experiment_cfg['t1rho']['amp'] = expt_cfg['amp']
    experiment_cfg['t1rho']['start'] = expt_cfg['time_start']
    experiment_cfg['t1rho']['stop'] = expt_cfg['time_stop']
    experiment_cfg['t1rho']['step'] = expt_cfg['time_step']
    experiment_cfg['t1rho']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['t1rho']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['t1rho']['calibration_qubit'] = expt_cfg['calibration_qubit']
    experiment_cfg['t1rho']['pi_calibration'] = expt_cfg['pi_calibration']
    experiment_cfg['t1rho']['ge_pi'] = expt_cfg['ge_pi']
    experiment_cfg['t1rho']['ef_pi'] = expt_cfg['ef_pi']
    experiment_cfg['t1rho']['flux_pi'] = expt_cfg['flux_pi']
    experiment_cfg['t1rho']['use_freq_amp_halfpi'] = expt_cfg['use_freq_amp_halfpi']

    for index, phase in enumerate(np.arange(expt_cfg['phase_start'], expt_cfg['phase_stop'], expt_cfg['phase_step'])):

        experiment_cfg['t1rho']['mid_phase'] = phase
        print('Index: %s amp: %s' %(index,phase))

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('t1rho')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 't1rho_mid_phase_sweep', seq_data_file, update_awg)

        update_awg = False


def tomo_2q_multitone_charge_flux_drive_Qubit_sweep(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['tomo_2q_multitone_charge_flux_drive_Qubit_sweep']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'tomo_2q_multitone_charge_flux_drive_Qubit_sweep', suffix='.h5'))
    on_qubits = expt_cfg['on_qubits']

    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['times_prep'] = expt_cfg['times_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['charge1_amps_prep'] = [[0.0,0.0],[0.0,0.0]]
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['charge1_freqs_prep'] = expt_cfg['charge1_freqs_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['charge1_phases_prep'] = expt_cfg['charge1_phases_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['charge2_amps_prep'] = [[0.0,0.0],[0.0,0.0]]
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['charge2_freqs_prep'] = expt_cfg['charge2_freqs_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['charge2_phases_prep'] = expt_cfg['charge2_phases_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux1_amps_prep'] = expt_cfg['flux1_amps_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux1_freqs_prep'] = expt_cfg['flux1_freqs_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux1_phases_prep'] = expt_cfg['flux1_phases_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux2_amps_prep'] = expt_cfg['flux2_amps_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux2_freqs_prep'] = expt_cfg['flux2_freqs_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux2_phases_prep'] = expt_cfg['flux2_phases_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux1_amps_tomo'] = expt_cfg['flux1_amps_tomo']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux1_freqs_tomo'] = expt_cfg['flux1_freqs_tomo']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux1_phases_tomo'] = expt_cfg['flux1_phases_tomo']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux2_amps_tomo'] = expt_cfg['flux2_amps_tomo']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux2_freqs_tomo'] = expt_cfg['flux2_freqs_tomo']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux2_phases_tomo'] = expt_cfg['flux2_phases_tomo']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['singleshot'] = expt_cfg['singleshot']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux_LO'] = expt_cfg['flux_LO']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['use_tomo_pulse_info'] = expt_cfg['use_tomo_pulse_info']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['sequential_tomo_pulse'] = expt_cfg['sequential_tomo_pulse']

    if expt_cfg['sweep_qubit'] == 1:
        experiment_cfg['tomo_2q_multitone_charge_flux_drive']['charge1_amps_prep'] = expt_cfg['charge1_amps_prep']
    if expt_cfg['sweep_qubit'] == 2:
        experiment_cfg['tomo_2q_multitone_charge_flux_drive']['charge2_amps_prep'] = expt_cfg['charge2_amps_prep']

    for ii, gate_length in enumerate(np.arange(expt_cfg['time_start'], expt_cfg['time_stop'], expt_cfg['time_step'])):

        print('Index %s: gate_length: %s' %(ii, gate_length))
        experiment_cfg['tomo_2q_multitone_charge_flux_drive']['times_prep'][0][0] = gate_length

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('tomo_2q_multitone_charge_flux_drive')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'tomo_2q_multitone_charge_flux_drive_Qubit_sweep', seq_data_file, update_awg)

        update_awg = False


def tomo_2q_multitone_charge_flux_drive_gef_sweep(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['tomo_2q_multitone_charge_flux_drive_gef_sweep']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'tomo_2q_multitone_charge_flux_drive_gef_sweep', suffix='.h5'))
    on_qubits = expt_cfg['on_qubits']

    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gef']['default'] = expt_cfg['default']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gef']['default_state'] = expt_cfg['default_state']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gef']['times_prep'] = expt_cfg['times_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gef']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gef']['charge1_amps_prep'] = expt_cfg['charge1_amps_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gef']['charge1_freqs_prep'] = expt_cfg['charge1_freqs_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gef']['charge1_phases_prep'] = expt_cfg['charge1_phases_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gef']['charge2_amps_prep'] = expt_cfg['charge2_amps_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gef']['charge2_freqs_prep'] = expt_cfg['charge2_freqs_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gef']['charge2_phases_prep'] = expt_cfg['charge2_phases_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gef']['flux1_amps_prep'] = expt_cfg['flux1_amps_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gef']['flux1_freqs_prep'] = expt_cfg['flux1_freqs_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gef']['flux1_phases_prep'] = expt_cfg['flux1_phases_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gef']['flux2_amps_prep'] = expt_cfg['flux2_amps_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gef']['flux2_freqs_prep'] = expt_cfg['flux2_freqs_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gef']['flux2_phases_prep'] = expt_cfg['flux2_phases_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gef']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gef']['singleshot'] = expt_cfg['singleshot']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gef']['flux_LO'] = expt_cfg['flux_LO']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gef']['use_tomo_pulse_info'] = expt_cfg['use_tomo_pulse_info']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gef']['sequential_tomo_pulse'] = expt_cfg['sequential_tomo_pulse']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gef']['defined'] = expt_cfg['defined']
    ll = len(experiment_cfg['tomo_2q_multitone_charge_flux_drive_gef_sweep']['times_prep'][-1])

    for ii, idle_time in enumerate(np.arange(expt_cfg['time_start'], expt_cfg['time_stop'], expt_cfg['time_step'])):

        print('Index %s: gate_length: %s' %(ii, idle_time))
        add_slot = []
        for jj in range(ll):
            add_slot.append(idle_time)
        experiment_cfg['tomo_2q_multitone_charge_flux_drive_gef']['times_prep'][-1] = add_slot
        print(experiment_cfg['tomo_2q_multitone_charge_flux_drive_gef'])

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('tomo_2q_multitone_charge_flux_drive_gef')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'tomo_2q_multitone_charge_flux_drive_gef_sweep', seq_data_file, update_awg)

        update_awg = False


def tomo_2q_multitone_bell_state_sweep(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['tomo_2q_multitone_bell_state_sweep']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'tomo_2q_multitone_bell_state_sweep', suffix='.h5'))
    on_qubits = expt_cfg['on_qubits']

    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['times_prep'] = expt_cfg['times_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['charge1_amps_prep'] = expt_cfg['charge1_amps_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['charge1_freqs_prep'] = expt_cfg['charge1_freqs_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['charge1_phases_prep'] = expt_cfg['charge1_phases_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['charge2_amps_prep'] = expt_cfg['charge2_amps_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['charge2_freqs_prep'] = expt_cfg['charge2_freqs_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['charge2_phases_prep'] = expt_cfg['charge2_phases_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux1_amps_prep'] = expt_cfg['flux1_amps_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux1_freqs_prep'] = expt_cfg['flux1_freqs_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux1_phases_prep'] = expt_cfg['flux1_phases_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux2_amps_prep'] = expt_cfg['flux2_amps_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux2_freqs_prep'] = expt_cfg['flux2_freqs_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux2_phases_prep'] = expt_cfg['flux2_phases_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux1_amps_tomo'] = expt_cfg['flux1_amps_tomo']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux1_freqs_tomo'] = expt_cfg['flux1_freqs_tomo']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux1_phases_tomo'] = expt_cfg['flux1_phases_tomo']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux2_amps_tomo'] = expt_cfg['flux2_amps_tomo']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux2_freqs_tomo'] = expt_cfg['flux2_freqs_tomo']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux2_phases_tomo'] = expt_cfg['flux2_phases_tomo']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['singleshot'] = expt_cfg['singleshot']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux_LO'] = expt_cfg['flux_LO']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['use_tomo_pulse_info'] = expt_cfg['use_tomo_pulse_info']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['sequential_tomo_pulse'] = expt_cfg['sequential_tomo_pulse']

    for ii, idle_time in enumerate(np.arange(expt_cfg['time_start'], expt_cfg['time_stop'], expt_cfg['time_step'])):

        print('Index %s: gate_length: %s' %(ii, idle_time))
        experiment_cfg['tomo_2q_multitone_charge_flux_drive']['times_prep'][-1] = [idle_time,idle_time]
        print(experiment_cfg['tomo_2q_multitone_bell_state_sweep'])

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('tomo_2q_multitone_charge_flux_drive')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'tomo_2q_multitone_bell_state_sweep', seq_data_file, update_awg)

        update_awg = False

def tomo_2q_multitone_flux_phase_sweep(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['tomo_2q_multitone_flux_phase_sweep']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'tomo_2q_multitone_flux_phase_sweep', suffix='.h5'))
    on_qubits = expt_cfg['on_qubits']

    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['times_prep'] = expt_cfg['times_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['charge1_amps_prep'] = expt_cfg['charge1_amps_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['charge1_freqs_prep'] = expt_cfg['charge1_freqs_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['charge1_phases_prep'] = expt_cfg['charge1_phases_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['charge2_amps_prep'] = expt_cfg['charge2_amps_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['charge2_freqs_prep'] = expt_cfg['charge2_freqs_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['charge2_phases_prep'] = expt_cfg['charge2_phases_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux1_amps_prep'] = expt_cfg['flux1_amps_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux1_freqs_prep'] = expt_cfg['flux1_freqs_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux1_phases_prep'] = expt_cfg['flux1_phases_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux2_amps_prep'] = expt_cfg['flux2_amps_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux2_freqs_prep'] = expt_cfg['flux2_freqs_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux2_phases_prep'] = expt_cfg['flux2_phases_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux1_amps_tomo'] = expt_cfg['flux1_amps_tomo']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux1_freqs_tomo'] = expt_cfg['flux1_freqs_tomo']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux1_phases_tomo'] = expt_cfg['flux1_phases_tomo']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux2_amps_tomo'] = expt_cfg['flux2_amps_tomo']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux2_freqs_tomo'] = expt_cfg['flux2_freqs_tomo']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux2_phases_tomo'] = expt_cfg['flux2_phases_tomo']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['singleshot'] = expt_cfg['singleshot']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux_LO'] = expt_cfg['flux_LO']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['use_tomo_pulse_info'] = expt_cfg['use_tomo_pulse_info']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['sequential_tomo_pulse'] = expt_cfg['sequential_tomo_pulse']

    for ii, psweep in enumerate(np.arange(expt_cfg['pstart'], expt_cfg['pstop'], expt_cfg['pstep'])):

        print('Index %s: flux phase: %s' %(ii, psweep))
        if expt_cfg['sweep_line']==1:
            experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux1_phases_prep'][1] = [psweep,psweep]
        else:
            experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux2_phases_prep'][1] = [psweep, psweep]
        # print(experiment_cfg['tomo_2q_multitone_charge_flux_drive'])

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('tomo_2q_multitone_charge_flux_drive')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'tomo_2q_multitone_flux_phase_sweep', seq_data_file, update_awg)

        update_awg = False



def tomo_2q_multitone_charge_flux_drive_for_edg_rb(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['tomo_2q_multitone_charge_flux_drive_for_edg_rb']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'tomo_2q_multitone_charge_flux_drive_for_edg_rb', suffix='.h5'))
    on_qubits = expt_cfg['on_qubits']

    experiment_cfg['tomo_2q_multitone_charge_flux_drive_for_edg']['times_prep'] = expt_cfg['times_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_for_edg']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_for_edg']['charge1_amps_prep'] = expt_cfg['charge1_amps_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_for_edg']['charge1_freqs_prep'] = expt_cfg['charge1_freqs_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_for_edg']['charge1_phases_prep'] = expt_cfg['charge1_phases_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_for_edg']['charge2_amps_prep'] = expt_cfg['charge2_amps_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_for_edg']['charge2_freqs_prep'] = expt_cfg['charge2_freqs_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_for_edg']['charge2_phases_prep'] = expt_cfg['charge2_phases_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_for_edg']['flux1_amps_prep'] = expt_cfg['flux1_amps_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_for_edg']['flux1_freqs_prep'] = expt_cfg['flux1_freqs_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_for_edg']['flux1_phases_prep'] = expt_cfg['flux1_phases_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_for_edg']['flux2_amps_prep'] = expt_cfg['flux2_amps_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_for_edg']['flux2_freqs_prep'] = expt_cfg['flux2_freqs_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_for_edg']['flux2_phases_prep'] = expt_cfg['flux2_phases_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_for_edg']['flux1_amps_tomo'] = expt_cfg['flux1_amps_tomo']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_for_edg']['flux1_freqs_tomo'] = expt_cfg['flux1_freqs_tomo']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_for_edg']['flux1_phases_tomo'] = expt_cfg['flux1_phases_tomo']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_for_edg']['flux2_amps_tomo'] = expt_cfg['flux2_amps_tomo']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_for_edg']['flux2_freqs_tomo'] = expt_cfg['flux2_freqs_tomo']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_for_edg']['flux2_phases_tomo'] = expt_cfg['flux2_phases_tomo']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_for_edg']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_for_edg']['singleshot'] = expt_cfg['singleshot']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_for_edg']['flux_LO'] = expt_cfg['flux_LO']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_for_edg']['use_tomo_pulse_info'] = expt_cfg['use_tomo_pulse_info']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_for_edg']['sequential_tomo_pulse'] = expt_cfg['sequential_tomo_pulse']

    experiment_cfg['tomo_2q_multitone_charge_flux_drive_for_edg']['amps'] = expt_cfg['amps']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_for_edg']['freqs'] = expt_cfg['freqs']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_for_edg']['time_length'] = expt_cfg['time_length']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_for_edg']['phases'] = expt_cfg['phases']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_for_edg']['shape'] = expt_cfg['shape']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_for_edg']['flux_pi_calibration'] = expt_cfg[
        'flux_pi_calibration']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_for_edg']['flux_pulse'] = expt_cfg[
        'flux_pulse']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_for_edg']['flux_line'] = expt_cfg['flux_line']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_for_edg']['edg_line'] = expt_cfg[
        'edg_line']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_for_edg']['edg_no'] = expt_cfg[
        'edg_no']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_for_edg']['calibration_qubit'] = expt_cfg[
        'calibration_qubit']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_for_edg']['inverse_rotation'] = expt_cfg[
        'inverse_rotation']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_for_edg']['edg_on'] = expt_cfg[
        'edg_on']

    for ii, gate_sweep in enumerate(np.arange(expt_cfg['repeat_start'], expt_cfg['repeat_stop'], expt_cfg['repeat_step'])):

        print('Index %s: Sweeping gate numbers: %s' %(ii, gate_sweep))
        experiment_cfg['tomo_2q_multitone_charge_flux_drive_for_edg']['repeat'] = int(gate_sweep)
        print(experiment_cfg['tomo_2q_multitone_charge_flux_drive_for_edg'])

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('tomo_2q_multitone_charge_flux_drive_for_edg')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'tomo_2q_multitone_charge_flux_drive_for_edg_rb', seq_data_file, update_awg)

        update_awg = False



def tomo_2q_multitone_charge_phase_sweep(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['tomo_2q_multitone_charge_phase_sweep']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'tomo_2q_multitone_charge_phase_sweep', suffix='.h5'))
    on_qubits = expt_cfg['on_qubits']

    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['times_prep'] = expt_cfg['times_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['charge1_amps_prep'] = expt_cfg['charge1_amps_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['charge1_freqs_prep'] = expt_cfg['charge1_freqs_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['charge1_phases_prep'] = expt_cfg['charge1_phases_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['charge2_amps_prep'] = expt_cfg['charge2_amps_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['charge2_freqs_prep'] = expt_cfg['charge2_freqs_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['charge2_phases_prep'] = expt_cfg['charge2_phases_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux1_amps_prep'] = expt_cfg['flux1_amps_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux1_freqs_prep'] = expt_cfg['flux1_freqs_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux1_phases_prep'] = expt_cfg['flux1_phases_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux2_amps_prep'] = expt_cfg['flux2_amps_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux2_freqs_prep'] = expt_cfg['flux2_freqs_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux2_phases_prep'] = expt_cfg['flux2_phases_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux1_amps_tomo'] = expt_cfg['flux1_amps_tomo']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux1_freqs_tomo'] = expt_cfg['flux1_freqs_tomo']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux1_phases_tomo'] = expt_cfg['flux1_phases_tomo']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux2_amps_tomo'] = expt_cfg['flux2_amps_tomo']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux2_freqs_tomo'] = expt_cfg['flux2_freqs_tomo']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux2_phases_tomo'] = expt_cfg['flux2_phases_tomo']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['singleshot'] = expt_cfg['singleshot']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['flux_LO'] = expt_cfg['flux_LO']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['use_tomo_pulse_info'] = expt_cfg['use_tomo_pulse_info']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive']['sequential_tomo_pulse'] = expt_cfg['sequential_tomo_pulse']

    for ii, psweep in enumerate(np.arange(expt_cfg['pstart'], expt_cfg['pstop'], expt_cfg['pstep'])):

        print('Index %s: charge phase: %s' %(ii, psweep))
        if expt_cfg['sweep_line']==1:
            experiment_cfg['tomo_2q_multitone_charge_flux_drive']['charge1_phases_prep'][-1] = [psweep,psweep]
        else:
            experiment_cfg['tomo_2q_multitone_charge_flux_drive']['charge2_phases_prep'][-1] = [psweep, psweep]
        print(experiment_cfg['tomo_2q_multitone_charge_flux_drive'])

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('tomo_2q_multitone_charge_flux_drive')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'tomo_2q_multitone_charge_phase_sweep', seq_data_file, update_awg)

        update_awg = False


def tomo_2q_multitone_charge_flux_drive_gate_sweep(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['tomo_2q_multitone_charge_flux_drive_gate_sweep']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'tomo_2q_multitone_charge_flux_drive_gate_sweep', suffix='.h5'))
    on_qubits = expt_cfg['on_qubits']

    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gate']['times_prep'] = expt_cfg['times_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gate']['tomo_qubit'] = expt_cfg['tomo_qubit']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gate']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gate']['charge1_amps_prep'] = expt_cfg['charge1_amps_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gate']['charge1_freqs_prep'] = expt_cfg['charge1_freqs_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gate']['charge1_phases_prep'] = expt_cfg['charge1_phases_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gate']['charge2_amps_prep'] = expt_cfg['charge2_amps_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gate']['charge2_freqs_prep'] = expt_cfg['charge2_freqs_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gate']['charge2_phases_prep'] = expt_cfg['charge2_phases_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gate']['flux1_amps_prep'] = expt_cfg['flux1_amps_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gate']['flux1_freqs_prep'] = expt_cfg['flux1_freqs_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gate']['flux1_phases_prep'] = expt_cfg['flux1_phases_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gate']['flux2_amps_prep'] = expt_cfg['flux2_amps_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gate']['flux2_freqs_prep'] = expt_cfg['flux2_freqs_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gate']['flux2_phases_prep'] = expt_cfg['flux2_phases_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gate']['flux1_amps_tomo'] = expt_cfg['flux1_amps_tomo']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gate']['flux1_freqs_tomo'] = expt_cfg['flux1_freqs_tomo']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gate']['flux1_phases_tomo'] = expt_cfg['flux1_phases_tomo']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gate']['flux2_amps_tomo'] = expt_cfg['flux2_amps_tomo']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gate']['flux2_freqs_tomo'] = expt_cfg['flux2_freqs_tomo']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gate']['flux2_phases_tomo'] = expt_cfg['flux2_phases_tomo']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gate']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gate']['singleshot'] = expt_cfg['singleshot']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gate']['flux_LO'] = expt_cfg['flux_LO']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gate']['use_tomo_pulse_info'] = expt_cfg['use_tomo_pulse_info']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_gate']['sequential_tomo_pulse'] = expt_cfg['sequential_tomo_pulse']

    for ii, gate_length in enumerate(np.arange(expt_cfg['time_start'], expt_cfg['time_stop'], expt_cfg['time_step'])):

        print('Index %s: gate_length: %s' %(ii, gate_length))
        experiment_cfg['tomo_2q_multitone_charge_flux_drive_gate']['tomo_gate'] = gate_length

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('tomo_2q_multitone_charge_flux_drive_gate')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'tomo_2q_multitone_charge_flux_drive_gate_sweep', seq_data_file, update_awg)

        update_awg = False


def tomo_2q_multitone_charge_flux_drive_tomo_angle_sweep(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['tomo_2q_multitone_charge_flux_drive_tomo_angle_sweep']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'tomo_2q_multitone_charge_flux_drive_tomo_angle_sweep', suffix='.h5'))
    on_qubits = expt_cfg['on_qubits']

    experiment_cfg['tomo_2q_multitone_charge_flux_drive_tomo_angle']['times_prep'] = expt_cfg['times_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_tomo_angle']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_tomo_angle']['charge1_amps_prep'] = expt_cfg['charge1_amps_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_tomo_angle']['charge1_freqs_prep'] = expt_cfg['charge1_freqs_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_tomo_angle']['charge1_phases_prep'] = expt_cfg['charge1_phases_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_tomo_angle']['charge2_amps_prep'] = expt_cfg['charge2_amps_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_tomo_angle']['charge2_freqs_prep'] = expt_cfg['charge2_freqs_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_tomo_angle']['charge2_phases_prep'] = expt_cfg['charge2_phases_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_tomo_angle']['flux1_amps_prep'] = expt_cfg['flux1_amps_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_tomo_angle']['flux1_freqs_prep'] = expt_cfg['flux1_freqs_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_tomo_angle']['flux1_phases_prep'] = expt_cfg['flux1_phases_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_tomo_angle']['flux2_amps_prep'] = expt_cfg['flux2_amps_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_tomo_angle']['flux2_freqs_prep'] = expt_cfg['flux2_freqs_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_tomo_angle']['flux2_phases_prep'] = expt_cfg['flux2_phases_prep']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_tomo_angle']['flux1_amps_tomo'] = expt_cfg['flux1_amps_tomo']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_tomo_angle']['flux1_freqs_tomo'] = expt_cfg['flux1_freqs_tomo']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_tomo_angle']['flux1_phases_tomo'] = expt_cfg['flux1_phases_tomo']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_tomo_angle']['flux2_amps_tomo'] = expt_cfg['flux2_amps_tomo']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_tomo_angle']['flux2_freqs_tomo'] = expt_cfg['flux2_freqs_tomo']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_tomo_angle']['flux2_phases_tomo'] = expt_cfg['flux2_phases_tomo']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_tomo_angle']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_tomo_angle']['singleshot'] = expt_cfg['singleshot']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_tomo_angle']['flux_LO'] = expt_cfg['flux_LO']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_tomo_angle']['use_tomo_pulse_info'] = expt_cfg['use_tomo_pulse_info']
    experiment_cfg['tomo_2q_multitone_charge_flux_drive_tomo_angle']['sequential_tomo_pulse'] = expt_cfg['sequential_tomo_pulse']
    rel_y_angle

    for ii, rel_y_angle in enumerate(np.arange(expt_cfg['rel_y_angle_start'], expt_cfg['rel_y_angle_stop'], expt_cfg['rel_y_angle_step'])):

        print('Index %s: rel_y_angle: %s' %(ii, rel_y_angle))
        experiment_cfg['tomo_2q_multitone_charge_flux_drive_tomo_angle']['rel_y_angle'] = rel_y_angle

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('tomo_2q_multitone_charge_flux_drive_tomo_angle')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'tomo_2q_multitone_charge_flux_drive_tomo_angle_sweep', seq_data_file, update_awg)

        update_awg = False

def tomo_1q_multitone_charge_flux_drive_sweep_halfpi_gate(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['tomo_1q_multitone_charge_flux_drive_sweep_halfpi_gate']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'tomo_1q_multitone_charge_flux_drive_sweep_halfpi_gate', suffix='.h5'))
    on_qubits = expt_cfg['on_qubits']

    experiment_cfg['tomo_1q_multitone_charge_flux_drive_gate']['times_prep'] = expt_cfg['times_prep']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive_gate']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive_gate']['charge1_amps_prep'] = expt_cfg['charge1_amps_prep']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive_gate']['charge1_freqs_prep'] = expt_cfg['charge1_freqs_prep']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive_gate']['charge1_phases_prep'] = expt_cfg['charge1_phases_prep']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive_gate']['charge2_amps_prep'] = expt_cfg['charge2_amps_prep']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive_gate']['charge2_freqs_prep'] = expt_cfg['charge2_freqs_prep']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive_gate']['charge2_phases_prep'] = expt_cfg['charge2_phases_prep']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive_gate']['flux1_amps_prep'] = expt_cfg['flux1_amps_prep']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive_gate']['flux1_freqs_prep'] = expt_cfg['flux1_freqs_prep']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive_gate']['flux1_phases_prep'] = expt_cfg['flux1_phases_prep']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive_gate']['flux2_amps_prep'] = expt_cfg['flux2_amps_prep']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive_gate']['flux2_freqs_prep'] = expt_cfg['flux2_freqs_prep']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive_gate']['flux2_phases_prep'] = expt_cfg['flux2_phases_prep']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive_gate']['flux1_amps_tomo'] = expt_cfg['flux1_amps_tomo']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive_gate']['flux1_freqs_tomo'] = expt_cfg['flux1_freqs_tomo']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive_gate']['flux1_phases_tomo'] = expt_cfg['flux1_phases_tomo']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive_gate']['flux2_amps_tomo'] = expt_cfg['flux2_amps_tomo']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive_gate']['flux2_freqs_tomo'] = expt_cfg['flux2_freqs_tomo']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive_gate']['flux2_phases_tomo'] = expt_cfg['flux2_phases_tomo']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive_gate']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive_gate']['singleshot'] = expt_cfg['singleshot']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive_gate']['flux_LO'] = expt_cfg['flux_LO']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive_gate']['use_tomo_pulse_info'] = expt_cfg['use_tomo_pulse_info']

    for ii, gate_length in enumerate(np.arange(expt_cfg['halfpi_start'], expt_cfg['halfpi_stop'], expt_cfg['halfpi_step'])):

        print('Index %s: half_pi_gate: %s' %(ii, gate_length))
        experiment_cfg['tomo_1q_multitone_charge_flux_drive_gate']['half_pi_len'] = gate_length

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('tomo_1q_multitone_charge_flux_drive_gate')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'tomo_1q_multitone_charge_flux_drive_sweep_halfpi_gate', seq_data_file, update_awg)

        update_awg = False



def tomo_1q_multitone_charge_flux_drive_sweep_pi_gate(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['tomo_1q_multitone_charge_flux_drive_sweep_pi_gate']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'tomo_1q_multitone_charge_flux_drive_sweep_pi_gate', suffix='.h5'))
    on_qubits = expt_cfg['on_qubits']

    experiment_cfg['tomo_1q_multitone_charge_flux_drive']['times_prep'] = expt_cfg['times_prep']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive']['charge1_amps_prep'] = expt_cfg['charge1_amps_prep']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive']['charge1_freqs_prep'] = expt_cfg['charge1_freqs_prep']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive']['charge1_phases_prep'] = expt_cfg['charge1_phases_prep']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive']['charge2_amps_prep'] = expt_cfg['charge2_amps_prep']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive']['charge2_freqs_prep'] = expt_cfg['charge2_freqs_prep']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive']['charge2_phases_prep'] = expt_cfg['charge2_phases_prep']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive']['flux1_amps_prep'] = expt_cfg['flux1_amps_prep']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive']['flux1_freqs_prep'] = expt_cfg['flux1_freqs_prep']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive']['flux1_phases_prep'] = expt_cfg['flux1_phases_prep']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive']['flux2_amps_prep'] = expt_cfg['flux2_amps_prep']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive']['flux2_freqs_prep'] = expt_cfg['flux2_freqs_prep']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive']['flux2_phases_prep'] = expt_cfg['flux2_phases_prep']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive']['flux1_amps_tomo'] = expt_cfg['flux1_amps_tomo']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive']['flux1_freqs_tomo'] = expt_cfg['flux1_freqs_tomo']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive']['flux1_phases_tomo'] = expt_cfg['flux1_phases_tomo']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive']['flux2_amps_tomo'] = expt_cfg['flux2_amps_tomo']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive']['flux2_freqs_tomo'] = expt_cfg['flux2_freqs_tomo']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive']['flux2_phases_tomo'] = expt_cfg['flux2_phases_tomo']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive']['singleshot'] = expt_cfg['singleshot']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive']['flux_LO'] = expt_cfg['flux_LO']
    experiment_cfg['tomo_1q_multitone_charge_flux_drive']['use_tomo_pulse_info'] = expt_cfg['use_tomo_pulse_info']

    for ii, gate_length in enumerate(np.arange(expt_cfg['pi_start'], expt_cfg['pi_stop'], expt_cfg['pi_step'])):

        print('Index %s: pi_gate: %s' %(ii, gate_length))
        experiment_cfg['tomo_1q_multitone_charge_flux_drive']['times_prep'][0][0] = gate_length

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('tomo_1q_multitone_charge_flux_drive')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'tomo_1q_multitone_charge_flux_drive_sweep_pi_gate', seq_data_file, update_awg)

        update_awg = False


def ramsey_while_flux_sweep(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['ramsey_while_flux_sweep']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'ramsey_while_flux_sweep', suffix='.h5'))
    on_qubits = expt_cfg['on_qubits']

    experiment_cfg['ramsey_while_flux']['stop'] = expt_cfg['stop']
    experiment_cfg['ramsey_while_flux']['step'] = expt_cfg['step']
    experiment_cfg['ramsey_while_flux']['use_freq_amp_halfpi'] = expt_cfg['use_freq_amp_halfpi']
    experiment_cfg['ramsey_while_flux']['singleshot'] = expt_cfg['singleshot']
    experiment_cfg['ramsey_while_flux']['flux_pi_calibration'] = expt_cfg['flux_pi_calibration']
    experiment_cfg['ramsey_while_flux']['flux_probe'] = expt_cfg['flux_probe']
    experiment_cfg['ramsey_while_flux']['ge_pi'] = expt_cfg['ge_pi']
    experiment_cfg['ramsey_while_flux']['ef_pi'] = expt_cfg['ef_pi']
    experiment_cfg['ramsey_while_flux']['ge_pi2'] = expt_cfg['ge_pi2']
    experiment_cfg['ramsey_while_flux']['start'] = expt_cfg['start']
    experiment_cfg['ramsey_while_flux']['ramsey_freq'] = expt_cfg['ramsey_freq']
    experiment_cfg['ramsey_while_flux']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['ramsey_while_flux']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['ramsey_while_flux']['on_cavity'] = expt_cfg['on_cavity']
    experiment_cfg['ramsey_while_flux']['pi_calibration'] = expt_cfg['pi_calibration']
    experiment_cfg['ramsey_while_flux']['flux_amp'] = expt_cfg['flux_amp']
    experiment_cfg['ramsey_while_flux']['flux_line'] = expt_cfg['flux_line']
    experiment_cfg['ramsey_while_flux']['flux_freq'] = expt_cfg['flux_freq']
    experiment_cfg['ramsey_while_flux']['phase'] = expt_cfg['phase']
    experiment_cfg['ramsey_while_flux']['pre_pulse'] = expt_cfg['pre_pulse']

    for ii, time_add in enumerate(range(expt_cfg['section'])):

        print('Index %s: ramsey_while_flux time section: %s' %(ii, time_add))
        experiment_cfg['ramsey_while_flux']['start'] = expt_cfg['start']+time_add*expt_cfg['stop']
        experiment_cfg['ramsey_while_flux']['stop'] = expt_cfg['stop']+time_add*expt_cfg['stop']
        experiment_cfg['ramsey_while_flux']['step'] = expt_cfg['step']

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('ramsey_while_flux')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'ramsey_while_flux_sweep', seq_data_file, update_awg)

        update_awg = False

def rabi_while_flux_freq_sweep(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['rabi_while_flux_freq_sweep']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'rabi_while_flux_freq_sweep', suffix='.h5'))
    on_qubits = expt_cfg['on_qubits']

    experiment_cfg['rabi_while_flux']['amp'] = expt_cfg['amp']
    experiment_cfg['rabi_while_flux']['start'] = expt_cfg['time_start']
    experiment_cfg['rabi_while_flux']['stop'] = expt_cfg['time_stop']
    experiment_cfg['rabi_while_flux']['step'] = expt_cfg['time_step']
    experiment_cfg['rabi_while_flux']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['rabi_while_flux']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['rabi_while_flux']['pi_calibration'] = expt_cfg['pi_calibration']
    experiment_cfg['rabi_while_flux']['flux_probe'] = expt_cfg['flux_probe']
    experiment_cfg['rabi_while_flux']['flux_pi_calibration'] = expt_cfg['flux_pi_calibration']
    experiment_cfg['rabi_while_flux']['calibration_qubit'] = expt_cfg['calibration_qubit']
    experiment_cfg['rabi_while_flux']['ge_pi'] = expt_cfg['ge_pi']
    experiment_cfg['rabi_while_flux']['ef_pi'] = expt_cfg['ef_pi']
    experiment_cfg['rabi_while_flux']['ge_pi2'] = expt_cfg['ge_pi2']
    experiment_cfg['rabi_while_flux']['flux_line'] = expt_cfg['flux_line']
    experiment_cfg['rabi_while_flux']['flux_freq'] = expt_cfg['flux_freq']
    experiment_cfg['rabi_while_flux']['phase'] = expt_cfg['phase']
    experiment_cfg['rabi_while_flux']['on_cavity'] = expt_cfg['on_cavity']
    experiment_cfg['rabi_while_flux']['pre_pulse'] = expt_cfg['pre_pulse']

    for ii, freq in enumerate(np.arange(expt_cfg['freq_start'], expt_cfg['freq_stop'], expt_cfg['freq_step'])):

        print('Index %s: rabi_drive_freq: %s' %(ii, freq))
        experiment_cfg['rabi_while_flux']['qubit_freq'] = freq

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('rabi_while_flux')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'rabi_while_flux_freq_sweep', seq_data_file, update_awg)

        update_awg = False


def vacuum_rabi_pre_sweep(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['vacuum_rabi_pre_sweep']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'vacuum_rabi_pre_sweep', suffix='.h5'))
    on_qubits = expt_cfg['on_qubits']

    experiment_cfg['vacuum_rabi']['stop'] = expt_cfg['stop']
    experiment_cfg['vacuum_rabi']['step'] = expt_cfg['step']
    experiment_cfg['vacuum_rabi']['pre_pulse'] = expt_cfg['pre_pulse']
    experiment_cfg['vacuum_rabi']['start'] = expt_cfg['start']
    experiment_cfg['vacuum_rabi']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['vacuum_rabi']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['vacuum_rabi']['singleshot'] = expt_cfg['singleshot']
    experiment_cfg['vacuum_rabi']['time_bin_data'] = expt_cfg['time_bin_data']
    lines = expt_cfg['sweep_lines']+'_freqs_prep'


    for ii, freq in enumerate(np.arange(expt_cfg['start_freq'], expt_cfg['stop_freq'], expt_cfg['step_freq'])):

        print('Index %s: vacuum_rabi_pre_freq: %s' %(ii, freq))
        quantum_device_cfg['pre_pulse_info'][lines][-1] = [freq, freq]
        print(quantum_device_cfg['pre_pulse_info'])

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('vacuum_rabi')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'vacuum_rabi_pre_sweep', seq_data_file, update_awg)

        update_awg = False


def vacuum_rabi_amp_sweep(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['vacuum_rabi_amp_sweep']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'vacuum_rabi_amp_sweep', suffix='.h5'))
    on_qubits = expt_cfg['on_qubits']

    experiment_cfg['vacuum_rabi']['stop'] = expt_cfg['stop']
    experiment_cfg['vacuum_rabi']['step'] = expt_cfg['step']
    experiment_cfg['vacuum_rabi']['pre_pulse'] = expt_cfg['pre_pulse']
    experiment_cfg['vacuum_rabi']['start'] = expt_cfg['start']
    experiment_cfg['vacuum_rabi']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['vacuum_rabi']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['vacuum_rabi']['singleshot'] = expt_cfg['singleshot']
    experiment_cfg['vacuum_rabi']['time_bin_data'] = expt_cfg['time_bin_data']
    lines = expt_cfg['sweep_lines']


    for ii, amp in enumerate(np.arange(expt_cfg['start_amp'], expt_cfg['stop_amp'], expt_cfg['step_amp'])):

        print('Index %s: vacuum_rabi_amp_sweep: %s' %(ii, amp))
        quantum_device_cfg['heterodyne'][lines]['amp'] = amp
        print(quantum_device_cfg['heterodyne'])

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('vacuum_rabi')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'vacuum_rabi_amp_sweep', seq_data_file, update_awg)

        update_awg = False


def halfpi_calibration(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['halfpi_calibration']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'halfpi_calibration', suffix='.h5'))
    on_qubits = expt_cfg['on_qubits']

    experiment_cfg['rabi_while_flux']['amp'] = 0
    experiment_cfg['rabi_while_flux']['start'] = expt_cfg['time_start']
    experiment_cfg['rabi_while_flux']['stop'] = expt_cfg['time_stop']
    experiment_cfg['rabi_while_flux']['step'] = expt_cfg['time_step']
    experiment_cfg['rabi_while_flux']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['rabi_while_flux']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['rabi_while_flux']['pi_calibration'] = expt_cfg['pi_calibration']
    experiment_cfg['rabi_while_flux']['flux_probe'] = expt_cfg['flux_probe']
    experiment_cfg['rabi_while_flux']['flux_pi_calibration'] = expt_cfg['flux_pi_calibration']
    experiment_cfg['rabi_while_flux']['calibration_qubit'] = expt_cfg['calibration_qubit']
    experiment_cfg['rabi_while_flux']['ge_pi'] = expt_cfg['ge_pi']
    experiment_cfg['rabi_while_flux']['ef_pi'] = expt_cfg['ef_pi']
    experiment_cfg['rabi_while_flux']['ge_pi2'] = expt_cfg['ge_pi2']
    experiment_cfg['rabi_while_flux']['flux_line'] = expt_cfg['flux_line']
    experiment_cfg['rabi_while_flux']['flux_freq'] = expt_cfg['flux_freq']
    experiment_cfg['rabi_while_flux']['phase'] = expt_cfg['phase']
    experiment_cfg['rabi_while_flux']['on_cavity'] = expt_cfg['on_cavity']
    experiment_cfg['rabi_while_flux']['pre_pulse'] = expt_cfg['pre_pulse']
    if expt_cfg['on_qubits']==["1"]:
        amp_change = 'charge1_amps_prep'
        quantum_device_cfg['pre_pulse_info']['charge1_freqs_prep'] = [[expt_cfg['freq']]]
        quantum_device_cfg['pre_pulse_info']['charge2_freqs_prep'] = [[0.0]]
    else:
        amp_change = 'charge2_amps_prep'
        quantum_device_cfg['pre_pulse_info']['charge2_freqs_prep'] = [[expt_cfg['freq']]]
        quantum_device_cfg['pre_pulse_info']['charge1_freqs_prep'] = [[0.0]]

    quantum_device_cfg['pre_pulse_info']['times_prep'] = [[0.0]]
    quantum_device_cfg['pre_pulse_info']['charge1_amps_prep'] = [[0.0]]
    quantum_device_cfg['pre_pulse_info']['charge1_phases_prep'] = [[0.0]]
    quantum_device_cfg['pre_pulse_info']['charge2_amps_prep'] = [[0.0]]
    quantum_device_cfg['pre_pulse_info']['charge2_freqs_prep'] = [[0.0]]
    quantum_device_cfg['pre_pulse_info']['charge2_phases_prep'] = [[0.0]]
    quantum_device_cfg['pre_pulse_info']['flux1_amps_prep'] = [[0.0]]
    quantum_device_cfg['pre_pulse_info']['flux1_freqs_prep'] = [[0.0]]
    quantum_device_cfg['pre_pulse_info']['flux1_phases_prep'] = [[0.0]]
    quantum_device_cfg['pre_pulse_info']['flux2_amps_prep'] = [[0.0]]
    quantum_device_cfg['pre_pulse_info']['flux2_freqs_prep'] = [[0.0]]
    quantum_device_cfg['pre_pulse_info']['flux2_phases_prep'] = [[0.0]]
    quantum_device_cfg['pre_pulse_info']['repeat'] = expt_cfg['repeat']

    for ii, amp in enumerate(np.arange(expt_cfg['amp_start'], expt_cfg['amp_stop'], expt_cfg['amp_step'])):

        print('Index %s: halfpi_gate_amplitude: %s' %(ii, amp))
        quantum_device_cfg['pre_pulse_info'][amp_change] = [[amp]]

        for jj, gate in enumerate(np.arange(expt_cfg['halfpi_start'], expt_cfg['halfpi_stop'], expt_cfg['halfpi_step'])):
            print('Index %s: halfpi_gate_length: %s' % (jj, gate))
            quantum_device_cfg['pre_pulse_info']['times_prep'] = [[gate]]
            # print(quantum_device_cfg['pre_pulse_info'])
            # print(experiment_cfg['rabi_while_flux'])


            ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
            sequences = ps.get_experiment_sequences('rabi_while_flux')
            update_awg = True

            exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
            exp.run_experiment(sequences, path, 'halfpi_calibration', seq_data_file, update_awg)

            update_awg = False



def rabi_while_flux_phase_sweep(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['rabi_while_flux_phase_sweep']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'rabi_while_flux_phase_sweep', suffix='.h5'))

    experiment_cfg['rabi_while_flux']['amp'] = expt_cfg['amp']
    experiment_cfg['rabi_while_flux']['flux_amp'] = expt_cfg['flux_amp']
    experiment_cfg['rabi_while_flux']['pre_pulse'] = expt_cfg['pre_pulse']
    experiment_cfg['rabi_while_flux']['start'] = expt_cfg['time_start']
    experiment_cfg['rabi_while_flux']['stop'] = expt_cfg['time_stop']
    experiment_cfg['rabi_while_flux']['step'] = expt_cfg['time_step']
    experiment_cfg['rabi_while_flux']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['rabi_while_flux']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['rabi_while_flux']['pi_calibration'] = expt_cfg['pi_calibration']
    experiment_cfg['rabi_while_flux']['flux_probe'] = expt_cfg['flux_probe']
    experiment_cfg['rabi_while_flux']['flux_pi_calibration'] = expt_cfg['flux_pi_calibration']
    experiment_cfg['rabi_while_flux']['calibration_qubit'] = expt_cfg['calibration_qubit']
    experiment_cfg['rabi_while_flux']['ge_pi'] = expt_cfg['ge_pi']
    experiment_cfg['rabi_while_flux']['flux_line'] = expt_cfg['flux_line']
    experiment_cfg['rabi_while_flux']['flux_freq'] = expt_cfg['flux_freq']
    experiment_cfg['rabi_while_flux']['qubit_freq'] = expt_cfg['qubit_freq']
    experiment_cfg['rabi_while_flux']['on_cavity'] = expt_cfg['on_cavity']

    for ii, phase_sweep in enumerate(np.arange(expt_cfg['phase_start'], expt_cfg['phase_stop'], expt_cfg['phase_step'])):

        print('Index %s: Phase: %s' %(ii, phase_sweep))
        experiment_cfg['rabi_while_flux']['phase'] = [phase_sweep, 180+phase_sweep]

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('rabi_while_flux')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'rabi_while_flux_phase_sweep', seq_data_file, update_awg)

        update_awg = False


def rabi_while_flux_charge_phase_sweep(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['rabi_while_flux_charge_phase_sweep']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'rabi_while_flux_charge_phase_sweep', suffix='.h5'))

    experiment_cfg['rabi_while_flux_charge_phase']['amp'] = expt_cfg['amp']
    experiment_cfg['rabi_while_flux_charge_phase']['phase'] = expt_cfg['phase']
    experiment_cfg['rabi_while_flux_charge_phase']['flux_amp'] = expt_cfg['flux_amp']
    experiment_cfg['rabi_while_flux_charge_phase']['pre_pulse'] = expt_cfg['pre_pulse']
    experiment_cfg['rabi_while_flux_charge_phase']['start'] = expt_cfg['start']
    experiment_cfg['rabi_while_flux_charge_phase']['stop'] = expt_cfg['stop']
    experiment_cfg['rabi_while_flux_charge_phase']['step'] = expt_cfg['step']
    experiment_cfg['rabi_while_flux_charge_phase']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['rabi_while_flux_charge_phase']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['rabi_while_flux_charge_phase']['pi_calibration'] = expt_cfg['pi_calibration']
    experiment_cfg['rabi_while_flux_charge_phase']['flux_probe'] = expt_cfg['flux_probe']
    experiment_cfg['rabi_while_flux_charge_phase']['flux_pi_calibration'] = expt_cfg['flux_pi_calibration']
    experiment_cfg['rabi_while_flux_charge_phase']['calibration_qubit'] = expt_cfg['calibration_qubit']
    experiment_cfg['rabi_while_flux_charge_phase']['ge_pi'] = expt_cfg['ge_pi']
    experiment_cfg['rabi_while_flux_charge_phase']['flux_line'] = expt_cfg['flux_line']
    experiment_cfg['rabi_while_flux_charge_phase']['flux_freq'] = expt_cfg['flux_freq']
    experiment_cfg['rabi_while_flux_charge_phase']['qubit_freq'] = expt_cfg['qubit_freq']
    experiment_cfg['rabi_while_flux_charge_phase']['on_cavity'] = expt_cfg['on_cavity']

    for ii, phase_sweep in enumerate(np.arange(expt_cfg['charge_phase_start'], expt_cfg['charge_phase_stop'], expt_cfg['charge_phase_step'])):

        print('Index %s: Phase: %s' %(ii, phase_sweep))
        experiment_cfg['rabi_while_flux_charge_phase']['charge_phase'] = phase_sweep

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('rabi_while_flux_charge_phase')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'rabi_while_flux_charge_phase_sweep', seq_data_file, update_awg)

        update_awg = False


def rabi_while_flux_charge_amp_sweep(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['rabi_while_flux_charge_amp_sweep']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'rabi_while_flux_charge_amp_sweep', suffix='.h5'))

    experiment_cfg['rabi_while_flux']['phase'] = expt_cfg['phase']
    experiment_cfg['rabi_while_flux']['flux_amp'] = expt_cfg['flux_amp']
    experiment_cfg['rabi_while_flux']['pre_pulse'] = expt_cfg['pre_pulse']
    experiment_cfg['rabi_while_flux']['start'] = expt_cfg['time_start']
    experiment_cfg['rabi_while_flux']['stop'] = expt_cfg['time_stop']
    experiment_cfg['rabi_while_flux']['step'] = expt_cfg['time_step']
    experiment_cfg['rabi_while_flux']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['rabi_while_flux']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['rabi_while_flux']['pi_calibration'] = expt_cfg['pi_calibration']
    experiment_cfg['rabi_while_flux']['flux_probe'] = expt_cfg['flux_probe']
    experiment_cfg['rabi_while_flux']['flux_pi_calibration'] = expt_cfg['flux_pi_calibration']
    experiment_cfg['rabi_while_flux']['calibration_qubit'] = expt_cfg['calibration_qubit']
    experiment_cfg['rabi_while_flux']['ge_pi'] = expt_cfg['ge_pi']
    experiment_cfg['rabi_while_flux']['ef_pi'] = expt_cfg['ef_pi']
    experiment_cfg['rabi_while_flux']['ge_pi2'] = expt_cfg['ge_pi2']
    experiment_cfg['rabi_while_flux']['flux_line'] = expt_cfg['flux_line']
    experiment_cfg['rabi_while_flux']['flux_freq'] = expt_cfg['flux_freq']
    experiment_cfg['rabi_while_flux']['qubit_freq'] = expt_cfg['qubit_freq']
    experiment_cfg['rabi_while_flux']['on_cavity'] = expt_cfg['on_cavity']

    for ii, amp in enumerate(np.arange(expt_cfg['amp_start'], expt_cfg['amp_stop'], expt_cfg['amp_step'])):

        print('Index %s: Amp: %s' %(ii, amp))
        experiment_cfg['rabi_while_flux']['amp'] = amp

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('rabi_while_flux')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'rabi_while_flux_charge_amp_sweep', seq_data_file, update_awg)

        update_awg = False


def edg_xeb_repeat(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['edg_xeb_repeat']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'edg_xeb_repeat', suffix='.h5'))

    experiment_cfg['edg_xeb']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['edg_xeb']['singleshot'] = expt_cfg['singleshot']
    experiment_cfg['edg_xeb']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['edg_xeb']['edg_on'] = expt_cfg['edg_on']
    experiment_cfg['edg_xeb']['repeat'] = expt_cfg['repeat']
    experiment_cfg['edg_xeb']['use_tomo_pulse_info'] = expt_cfg['use_tomo_pulse_info']
    experiment_cfg['edg_xeb']['sequential_single_gate'] = expt_cfg['sequential_single_gate']


    for ii in range(int(expt_cfg['sequence_number'])):

        print('Index %s: ' %(ii))

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('edg_xeb')
        update_awg = True
        # print(quantum_device_cfg['rb_gate']['gate_list_q1'])

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'edg_xeb_repeat', seq_data_file, update_awg)

        update_awg = False


def xeb_single_repeat(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    # Author Tanay 17 Sep 2021
    # Repeat is the number of different sequences with same depth
    expt_cfg = experiment_cfg['xeb_single_repeat']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'xeb_single_repeat', suffix='.h5'))

    experiment_cfg['xeb_single']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['xeb_single']['singleshot'] = expt_cfg['singleshot']
    experiment_cfg['xeb_single']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['xeb_single']['edg_on'] = expt_cfg['edg_on']
    experiment_cfg['xeb_single']['depth'] = expt_cfg['depth']
    experiment_cfg['xeb_single']['use_tomo_pulse_info'] = expt_cfg['use_tomo_pulse_info']
    experiment_cfg['xeb_single']['sequential_single_gate'] = expt_cfg['sequential_single_gate']


    for ii in range(int(expt_cfg['repeat'])):

        print('Index %s: ' %(ii))

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('xeb_single')
        update_awg = True
        # print(quantum_device_cfg['rb_gate']['gate_list_q1'])

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'xeb_single_repeat', seq_data_file, update_awg)

        update_awg = False

def edg_xeb_repeat_rb(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['edg_xeb_repeat_rb']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'edg_xeb_repeat_rb', suffix='.h5'))

    experiment_cfg['edg_xeb']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['edg_xeb']['singleshot'] = expt_cfg['singleshot']
    experiment_cfg['edg_xeb']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['edg_xeb']['edg_on'] = expt_cfg['edg_on']
    experiment_cfg['edg_xeb']['use_tomo_pulse_info'] = expt_cfg['use_tomo_pulse_info']
    experiment_cfg['edg_xeb']['sequential_single_gate'] = expt_cfg['sequential_single_gate']

    circuit = np.arange(expt_cfg['circuit_depth_start'],expt_cfg['circuit_depth_stop'],expt_cfg['circuit_depth_step'])
    for jj in circuit:
        print('Circuit_depth: ',jj)
        print('#####################################')
        experiment_cfg['edg_xeb']['repeat'] = int(jj)
        for ii in range(int(expt_cfg['sequence_number'])):

            print('Index %s: ' %(ii))

            ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
            sequences = ps.get_experiment_sequences('edg_xeb')
            update_awg = True
            # print(quantum_device_cfg['rb_gate']['gate_list_q1'])

            exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
            exp.run_experiment(sequences, path, 'edg_xeb_repeat_rb', seq_data_file, update_awg)

            update_awg = False


def xeb_single_repeat_rb(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['xeb_single_repeat_rb']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'xeb_single_repeat_rb', suffix='.h5'))

    experiment_cfg['xeb_single']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['xeb_single']['singleshot'] = expt_cfg['singleshot']
    experiment_cfg['xeb_single']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['xeb_single']['edg_on'] = expt_cfg['edg_on']
    experiment_cfg['xeb_single']['use_tomo_pulse_info'] = expt_cfg['use_tomo_pulse_info']
    experiment_cfg['xeb_single']['sequential_single_gate'] = expt_cfg['sequential_single_gate']

    circuit = np.arange(expt_cfg['circuit_depth_start'],expt_cfg['circuit_depth_stop'],expt_cfg['circuit_depth_step'])
    for jj in circuit:
        print('Circuit_depth: ',jj)
        print('#####################################')
        experiment_cfg['xeb_single']['depth'] = int(jj)
        for ii in range(int(expt_cfg['repeat'])):

            print('Index %s: ' %(ii))

            ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
            sequences = ps.get_experiment_sequences('xeb_single')
            update_awg = True
            # print(quantum_device_cfg['rb_gate']['gate_list_q1'])

            exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
            exp.run_experiment(sequences, path, 'xeb_single_repeat_rb', seq_data_file, update_awg)

            update_awg = False


def rb_full(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['rb_full']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'rb_full', suffix='.h5'))

    experiment_cfg['rb']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['rb']['singleshot'] = expt_cfg['singleshot']
    experiment_cfg['rb']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['rb']['use_tomo_pulse_info'] = expt_cfg['use_tomo_pulse_info']
    experiment_cfg['rb']['sequential_single_gate'] = expt_cfg['sequential_single_gate']

    circuit = expt_cfg['depth']
    for jj in circuit:
        print('Circuit_depth: ',jj)
        print('#####################################')
        experiment_cfg['rb']['depth'] = int(jj)
        for ii in range(int(expt_cfg['repeat'])):

            print('Index %s: ' %(ii))

            ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
            sequences = ps.get_experiment_sequences('rb')
            update_awg = True
            # print(quantum_device_cfg['rb_gate']['gate_list_q1'])

            exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
            exp.run_experiment(sequences, path, 'rb_full', seq_data_file, update_awg)

            update_awg = False


def rb_interleaved_full(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['rb_interleaved_full']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'rb_interleaved_full', suffix='.h5'))

    experiment_cfg['rb_interleaved']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['rb_interleaved']['singleshot'] = expt_cfg['singleshot']
    experiment_cfg['rb_interleaved']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['rb_interleaved']['use_tomo_pulse_info'] = expt_cfg['use_tomo_pulse_info']
    experiment_cfg['rb_interleaved']['sequential_single_gate'] = expt_cfg['sequential_single_gate']
    experiment_cfg['rb_interleaved']['interleaved'] = expt_cfg['interleaved']

    circuit = expt_cfg['depth']
    for jj in circuit:
        print('Circuit_depth: ',jj)
        print('#####################################')
        experiment_cfg['rb_interleaved']['depth'] = int(jj)
        for ii in range(int(expt_cfg['repeat'])):

            print('Index %s: ' %(ii))

            ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
            sequences = ps.get_experiment_sequences('rb_interleaved')
            update_awg = True
            # print(quantum_device_cfg['rb_gate']['gate_list_q1'])

            exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
            exp.run_experiment(sequences, path, 'rb_interleaved_full', seq_data_file, update_awg)

            update_awg = False

def rb_both_full(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['rb_both_full']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'rb_both_full', suffix='.h5'))

    experiment_cfg['rb_both']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['rb_both']['singleshot'] = expt_cfg['singleshot']
    experiment_cfg['rb_both']['use_tomo_pulse_info'] = expt_cfg['use_tomo_pulse_info']
    experiment_cfg['rb_both']['sequential_single_gate'] = expt_cfg['sequential_single_gate']

    circuit = expt_cfg['depth']
    for jj in circuit:
        print('Circuit_depth: ',jj)
        print('#####################################')
        experiment_cfg['rb_both']['depth'] = int(jj)
        for ii in range(int(expt_cfg['repeat'])):

            print('Index %s: ' %(ii))

            ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
            sequences = ps.get_experiment_sequences('rb_both')
            update_awg = True
            # print(quantum_device_cfg['rb_gate']['gate_list_q1'])

            exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
            exp.run_experiment(sequences, path, 'rb_both_full', seq_data_file, update_awg)

            update_awg = False


def rabi_while_flux_flux_freq_sweep(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['rabi_while_flux_flux_freq_sweep']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'rabi_while_flux_flux_freq_sweep', suffix='.h5'))

    experiment_cfg['rabi_while_flux']['amp'] = expt_cfg['amp']
    experiment_cfg['rabi_while_flux']['flux_amp'] = expt_cfg['flux_amp']
    experiment_cfg['rabi_while_flux']['pre_pulse'] = expt_cfg['pre_pulse']
    experiment_cfg['rabi_while_flux']['start'] = expt_cfg['time_start']
    experiment_cfg['rabi_while_flux']['stop'] = expt_cfg['time_stop']
    experiment_cfg['rabi_while_flux']['step'] = expt_cfg['time_step']
    experiment_cfg['rabi_while_flux']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['rabi_while_flux']['on_qubits'] = expt_cfg['on_qubits']
    experiment_cfg['rabi_while_flux']['pi_calibration'] = expt_cfg['pi_calibration']
    experiment_cfg['rabi_while_flux']['flux_probe'] = expt_cfg['flux_probe']
    experiment_cfg['rabi_while_flux']['flux_pi_calibration'] = expt_cfg['flux_pi_calibration']
    experiment_cfg['rabi_while_flux']['calibration_qubit'] = expt_cfg['calibration_qubit']
    experiment_cfg['rabi_while_flux']['ge_pi'] = expt_cfg['ge_pi']
    experiment_cfg['rabi_while_flux']['flux_line'] = expt_cfg['flux_line']
    experiment_cfg['rabi_while_flux']['phase'] = expt_cfg['phase']
    experiment_cfg['rabi_while_flux']['on_cavity'] = expt_cfg['on_cavity']

    for ii, freq in enumerate(np.arange(expt_cfg['freq_start'], expt_cfg['freq_stop'], expt_cfg['freq_step'])):

        print('Index %s: Freq: %s' %(ii, freq/2))
        experiment_cfg['rabi_while_flux']['flux_freq'] = freq/2
        experiment_cfg['rabi_while_flux']['qubit_freq'] = freq

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('rabi_while_flux')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'rabi_while_flux_flux_freq_sweep', seq_data_file, update_awg)

        update_awg = False

def multitone_rabi_while_flux_freq_sweep(quantum_device_cfg, experiment_cfg, hardware_cfg, path): ## UNCHECKED
    expt_cfg = experiment_cfg['multitone_rabi_while_flux_freq_sweep']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'multitone_rabi_while_flux_freq_sweep', suffix='.h5'))

    experiment_cfg['multitone_rabi_while_flux']['amps'] = expt_cfg['amps']
    experiment_cfg['multitone_rabi_while_flux']['phases'] = expt_cfg['phases']
    experiment_cfg['multitone_rabi_while_flux']['start'] = expt_cfg['time_start']
    experiment_cfg['multitone_rabi_while_flux']['stop'] = expt_cfg['time_stop']
    experiment_cfg['multitone_rabi_while_flux']['step'] = expt_cfg['time_step']
    experiment_cfg['multitone_rabi_while_flux']['acquisition_num'] = expt_cfg['acquisition_num']
    experiment_cfg['multitone_rabi_while_flux']['pi_calibration'] = expt_cfg['pi_calibration']
    experiment_cfg['multitone_rabi_while_flux']['calibration_qubit'] = expt_cfg['calibration_qubit']
    experiment_cfg['multitone_rabi_while_flux']['flux_pi_calibration'] = expt_cfg['flux_pi_calibration']
    experiment_cfg['multitone_rabi_while_flux']['ge_pi'] = expt_cfg['ge_pi']
    experiment_cfg['multitone_rabi_while_flux']['flux_line'] = expt_cfg['flux_line']
    experiment_cfg['multitone_rabi_while_flux']['flux_amp'] = expt_cfg['flux_amp']
    experiment_cfg['multitone_rabi_while_flux']['flux_freq'] = expt_cfg['flux_freq']
    experiment_cfg['multitone_rabi_while_flux']['flux_phase'] = expt_cfg['flux_phase']
    experiment_cfg['multitone_rabi_while_flux']['on_cavity'] = expt_cfg['on_cavity']
    experiment_cfg['multitone_rabi_while_flux']['on_qubits'] = expt_cfg['on_qubits']

    freqs_arr = np.linspace(expt_cfg['freqs_start'],expt_cfg['freqs_stop'],expt_cfg['no_points'])
    # Simultaneously sweeping both freq. array

    for ii, freqs in enumerate(freqs_arr):

        print('Index %s: rabi_drive_freqs: %s' %(ii, freqs.tolist()))
        experiment_cfg['multitone_rabi_while_flux']['freqs'] = freqs.tolist()

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('multitone_rabi_while_flux')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'multitone_rabi_while_flux_freq_sweep', seq_data_file, update_awg)

        update_awg = False



def sideband_rabi_around_mm(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['sideband_rabi_around_mm']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'sideband_rabi_around_mm', suffix='.h5'))
    on_qubits = expt_cfg['on_qubits']

    mm_freq_list_1 = [quantum_device_cfg['multimodes']['1']['freq'][-1]]
    freq_list_all_1 = []
    for mm_freq in mm_freq_list_1:
        freq_list_all_1 += [np.arange(mm_freq-expt_cfg['freq_range'],mm_freq+expt_cfg['freq_range'],expt_cfg['step'])]

    freq_array_1 = np.hstack(np.array(freq_list_all_1))


    mm_freq_list_2 = [quantum_device_cfg['multimodes']['2']['freq'][-1]]
    freq_list_all_2 = []
    for mm_freq in mm_freq_list_2:
        freq_list_all_2 += [np.arange(mm_freq-expt_cfg['freq_range'],mm_freq+expt_cfg['freq_range'],expt_cfg['step'])]

    freq_array_2 = np.hstack(np.array(freq_list_all_2))
    print(freq_array_2)
    last_freq_1 = 0

    for freq_1, freq_2 in zip(freq_array_1,freq_array_2):

        # calibrate qubit frequency everytime changing target mm
        if freq_1 - last_freq_1 > 2*expt_cfg['step']:
            qubit_frequency_flux_calibration(quantum_device_cfg, experiment_cfg, hardware_cfg, path)

        last_freq_1 = freq_1

        experiment_cfg['sideband_rabi_2_freq']['freq_1'] = freq_1
        experiment_cfg['sideband_rabi_2_freq']['freq_2'] = freq_2
        experiment_cfg['sideband_rabi_2_freq']['amp'] = expt_cfg['amp']
        experiment_cfg['sideband_rabi_2_freq']['start'] = expt_cfg['time_start']
        experiment_cfg['sideband_rabi_2_freq']['stop'] = expt_cfg['time_stop']
        experiment_cfg['sideband_rabi_2_freq']['step'] = expt_cfg['time_step']
        experiment_cfg['sideband_rabi_2_freq']['acquisition_num'] = expt_cfg['acquisition_num']
        experiment_cfg['sideband_rabi_2_freq']['on_qubits'] = expt_cfg['on_qubits']
        experiment_cfg['sideband_rabi_2_freq']['pi_calibration'] = expt_cfg['pi_calibration']
        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('sideband_rabi_2_freq')
        update_awg = True

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'sideband_rabi_around_mm', seq_data_file, update_awg)

        update_awg = False


def multimode_rabi_pi_calibrate(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['multimode_rabi']
    data_path = os.path.join(path, 'data/')
    on_qubits = expt_cfg['on_qubits']

    on_mms_list = np.arange(1,9)

    for on_mms in on_mms_list:

        for qubit_id in expt_cfg['on_qubits']:
            experiment_cfg['multimode_rabi']['on_mms'][qubit_id] = int(on_mms)

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('multimode_rabi')

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        data_file = exp.run_experiment(sequences, path, 'multimode_rabi')
        expt_pts = np.arange(expt_cfg['start'], expt_cfg['stop'], expt_cfg['step'])
        with SlabFile(data_file) as a:
            for qubit_id in on_qubits:
                expt_avg_data = np.array(a['expt_avg_data_ch%s'%qubit_id])

                data_list = np.array(a['expt_avg_data_ch%s'%qubit_id])
                fitdata = fitdecaysin(expt_pts[1:],data_list[1:],showfit=True)

                pi_length = round((-fitdata[2]%180 + 90)/(360*fitdata[1]),5)
                print("Flux pi length ge: %s" %pi_length)

                quantum_device_cfg['multimodes'][qubit_id]['pi_len'][on_mms] = pi_length
                with open(os.path.join(path, 'quantum_device_config.json'), 'w') as f:
                    json.dump(quantum_device_cfg, f)


def multimode_ef_rabi_pi_calibrate(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['multimode_ef_rabi']
    data_path = os.path.join(path, 'data/')
    on_qubits = expt_cfg['on_qubits']

    on_mms_list = np.arange(1,9)

    for on_mms in on_mms_list:

        for qubit_id in expt_cfg['on_qubits']:
            experiment_cfg['multimode_ef_rabi']['on_mms'][qubit_id] = int(on_mms)

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('multimode_ef_rabi')

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        data_file = exp.run_experiment(sequences, path, 'multimode_ef_rabi')
        expt_pts = np.arange(expt_cfg['start'], expt_cfg['stop'], expt_cfg['step'])
        with SlabFile(data_file) as a:
            for qubit_id in on_qubits:
                expt_avg_data = np.array(a['expt_avg_data_ch%s'%qubit_id])

                data_list = np.array(a['expt_avg_data_ch%s'%qubit_id])
                fitdata = fitdecaysin(expt_pts[1:],data_list[1:],showfit=True)

                pi_length = round((-fitdata[2]%180 + 90)/(360*fitdata[1]),5)
                print("Flux pi length ge: %s" %pi_length)

                quantum_device_cfg['multimodes'][qubit_id]['ef_pi_len'][on_mms] = pi_length
                with open(os.path.join(path, 'quantum_device_config.json'), 'w') as f:
                    json.dump(quantum_device_cfg, f)


def multimode_t1(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['multimode_t1']
    data_path = os.path.join(path, 'data/')
    on_qubits = expt_cfg['on_qubits']

    on_mms_list = np.arange(1,9)

    for on_mms in on_mms_list:

        for qubit_id in expt_cfg['on_qubits']:
            experiment_cfg['multimode_t1']['on_mms'][qubit_id] = int(on_mms)

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('multimode_t1')

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'multimode_t1')


def multimode_dc_offset(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['multimode_ramsey']
    data_path = os.path.join(path, 'data/')
    on_qubits = expt_cfg['on_qubits']

    on_mms_list = np.arange(1,9)

    for on_mms in on_mms_list:

        for qubit_id in expt_cfg['on_qubits']:
            experiment_cfg['multimode_ramsey']['on_mms'][qubit_id] = int(on_mms)
            experiment_cfg['multimode_ramsey']['ramsey_freq'] = 0
            quantum_device_cfg['multimodes'][qubit_id]['dc_offset'][on_mms] = 0

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('multimode_ramsey')

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        data_file = exp.run_experiment(sequences, path, 'multimode_ramsey')
        expt_pts = np.arange(expt_cfg['start'], expt_cfg['stop'], expt_cfg['step'])
        with SlabFile(data_file) as a:
            for qubit_id in on_qubits:
                data_list = np.array(a['expt_avg_data_ch%s' % qubit_id])
                fitdata = fitdecaysin(expt_pts, data_list, showfit=False)
                print("Oscillation frequency: %s GHz" % str(fitdata[1]))

                quantum_device_cfg['multimodes'][qubit_id]['dc_offset'][on_mms] = round(-fitdata[1],5)
                with open(os.path.join(path, 'quantum_device_config.json'), 'w') as f:
                    json.dump(quantum_device_cfg, f)

def multimode_ramsey(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['multimode_ramsey']
    data_path = os.path.join(path, 'data/')
    on_qubits = expt_cfg['on_qubits']

    on_mms_list = np.arange(1,9)

    for on_mms in on_mms_list:

        for qubit_id in expt_cfg['on_qubits']:
            experiment_cfg['multimode_ramsey']['on_mms'][qubit_id] = int(on_mms)

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('multimode_ramsey')

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        data_file = exp.run_experiment(sequences, path, 'multimode_ramsey')


def sideband_cooling_test(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['ef_rabi']
    data_path = os.path.join(path, 'data/')
    on_qubits = expt_cfg['on_qubits']


    on_mms_list = np.arange(1,9)

    for on_mms in on_mms_list:

        for qubit_id in expt_cfg['on_qubits']:
            quantum_device_cfg['sideband_cooling'][qubit_id]['cool'] = True
            quantum_device_cfg['sideband_cooling'][qubit_id]['mode_id'] = int(on_mms)

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('ef_rabi')

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        data_file = exp.run_experiment(sequences, path, 'ef_rabi')


        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('ramsey')

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        data_file = exp.run_experiment(sequences, path, 'ramsey')


def photon_transfer_optimize(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['photon_transfer_arb']
    data_path = os.path.join(path, 'data/')
    filename = get_next_filename(data_path, 'photon_transfer_optimize', suffix='.h5')
    seq_data_file = os.path.join(data_path, filename)

    init_iteration_num = 1

    iteration_num = 20000

    sequence_num = 10
    expt_num = sequence_num*expt_cfg['repeat']

    A_list_len = 10

    max_a = {"1":0.6, "2":0.65}
    max_len = 1000

    limit_list = []
    limit_list += [(0.0, max_a[expt_cfg['sender_id']])]*A_list_len
    limit_list += [(0.0, max_a[expt_cfg['receiver_id']])]*A_list_len
    limit_list += [(10.0,max_len)] * 2

    ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)

    use_prev_model = False

    if use_prev_model:
        with open(os.path.join(path,'optimizer/00041_photon_transfer_optimize.pkl'), 'rb') as f:
            opt = pickle.load(f)
    else:
        opt = Optimizer(limit_list, "GBRT", acq_optimizer="lbfgs")

        gauss_z = np.linspace(-2,2,A_list_len)
        gauss_envelop = np.exp(-gauss_z**2)
        init_send_A_list = list(quantum_device_cfg['communication'][expt_cfg['sender_id']]['pi_amp'] * gauss_envelop)
        init_rece_A_list = list(quantum_device_cfg['communication'][expt_cfg['receiver_id']]['pi_amp'] * gauss_envelop)
        init_send_len = [300]
        init_rece_len = [300]

        init_x = [init_send_A_list + init_rece_A_list + init_send_len + init_rece_len] * sequence_num



        x_array = np.array(init_x)

        send_A_list = x_array[:,:A_list_len]
        rece_A_list = x_array[:,A_list_len:2*A_list_len]
        send_len = x_array[:,-2]
        rece_len = x_array[:,-1]


        sequences = ps.get_experiment_sequences('photon_transfer_arb', sequence_num = sequence_num,
                                                    send_A_list = send_A_list, rece_A_list = rece_A_list,
                                                    send_len = send_len, rece_len = rece_len)

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        data_file = exp.run_experiment(sequences, path, 'photon_transfer_arb', seq_data_file)

        with SlabFile(data_file) as a:
            f_val_list = list(1-np.array(a['expt_avg_data_ch%s'%expt_cfg['receiver_id']])[-1])
            print(f_val_list)
            print(f_val_list[::2])
            print(f_val_list[1::2])

        f_val_all = []

        for ii in range(sequence_num):
            f_val_all += [np.mean(f_val_list[ii::sequence_num])]

        print(f_val_all)
        opt.tell(init_x, f_val_all)

    if use_prev_model:
        init_iteration_num = 0


    for iteration in range(init_iteration_num):

        next_x_list = opt.ask(sequence_num,strategy='cl_max')

        # do the experiment
        x_array = np.array(next_x_list)

        send_A_list = x_array[:,:A_list_len]
        rece_A_list = x_array[:,A_list_len:2*A_list_len]
        send_len = x_array[:,-2]
        rece_len = x_array[:,-1]
        sequences = ps.get_experiment_sequences('photon_transfer_arb', sequence_num = sequence_num,
                                                send_A_list = send_A_list, rece_A_list = rece_A_list,
                                                send_len = send_len, rece_len = rece_len)

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        data_file = exp.run_experiment(sequences, path, 'photon_transfer_arb', seq_data_file)

        with SlabFile(data_file) as a:
            f_val_list = list(1-np.array(a['expt_avg_data_ch%s'%expt_cfg['receiver_id']])[-1])
            print(f_val_list)
            print(f_val_list[::2])
            print(f_val_list[1::2])

        f_val_all = []

        for ii in range(sequence_num):
            f_val_all += [np.mean(f_val_list[ii::sequence_num])]

        print(f_val_all)

        opt.tell(next_x_list, f_val_all)

        with open(os.path.join(path,'optimizer/%s.pkl' %filename.split('.')[0]), 'wb') as f:
            pickle.dump(opt, f)


        frequency_recalibrate_cycle = 20
        if iteration % frequency_recalibrate_cycle == frequency_recalibrate_cycle-1:
            qubit_frequency_flux_calibration(quantum_device_cfg, experiment_cfg, hardware_cfg, path)


    for iteration in range(iteration_num):

        experiment_cfg['photon_transfer_arb']['repeat'] = 1

        X_cand = opt.space.transform(opt.space.rvs(n_samples=1000000))
        X_cand_predict = opt.models[-1].predict(X_cand)
        X_cand_argsort = np.argsort(X_cand_predict)
        X_cand_sort = np.array([X_cand[ii] for ii in X_cand_argsort])
        X_cand_top = X_cand_sort[:expt_num]

        next_x_list = opt.space.inverse_transform(X_cand_top)

        # do the experiment
        x_array = np.array(next_x_list)

        send_A_list = x_array[:,:A_list_len]
        rece_A_list = x_array[:,A_list_len:2*A_list_len]
        send_len = x_array[:,-2]
        rece_len = x_array[:,-1]
        sequences = ps.get_experiment_sequences('photon_transfer_arb', sequence_num = expt_num,
                                                send_A_list = send_A_list, rece_A_list = rece_A_list,
                                                send_len = send_len, rece_len = rece_len)

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        data_file = exp.run_experiment(sequences, path, 'photon_transfer_arb', seq_data_file)

        with SlabFile(data_file) as a:
            f_val_list = list(1-np.array(a['expt_avg_data_ch%s'%expt_cfg['receiver_id']])[-1])
            print(f_val_list)


        opt.tell(next_x_list, f_val_list)

        with open(os.path.join(path,'optimizer/%s.pkl' %filename.split('.')[0]), 'wb') as f:
            pickle.dump(opt, f)


        frequency_recalibrate_cycle = 20
        if iteration % frequency_recalibrate_cycle == frequency_recalibrate_cycle-1:
            qubit_frequency_flux_calibration(quantum_device_cfg, experiment_cfg, hardware_cfg, path)

def photon_transfer_optimize_v2(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['photon_transfer_arb']
    data_path = os.path.join(path, 'data/')
    filename = get_next_filename(data_path, 'photon_transfer_optimize', suffix='.h5')
    seq_data_file = os.path.join(data_path, filename)

    iteration_num = 20000

    sequence_num = 100
    expt_num = sequence_num

    A_list_len = 6

    max_a = {"1":0.5, "2":0.65}
    max_len = 300

    limit_list = []
    limit_list += [(0.0, max_a[expt_cfg['sender_id']])]*A_list_len
    limit_list += [(0.0, max_a[expt_cfg['receiver_id']])]*A_list_len
    limit_list += [(10.0,max_len)] * 2

    ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)

    use_prev_model = True

    if use_prev_model:
        with open(os.path.join(path,'optimizer/00051_photon_transfer_optimize.pkl'), 'rb') as f:
            opt = pickle.load(f)
    else:
        opt = Optimizer(limit_list, "GBRT", acq_optimizer="auto")

        gauss_z = np.linspace(-2,2,A_list_len)
        gauss_envelop = np.exp(-gauss_z**2)
        init_send_A_list = list(quantum_device_cfg['communication'][expt_cfg['sender_id']]['pi_amp'] * gauss_envelop)
        init_rece_A_list = list(quantum_device_cfg['communication'][expt_cfg['receiver_id']]['pi_amp'] * gauss_envelop)
        init_send_len = [300]
        init_rece_len = [300]

        init_x = [init_send_A_list + init_rece_A_list + init_send_len + init_rece_len] * sequence_num



        x_array = np.array(init_x)

        send_A_list = x_array[:,:A_list_len]
        rece_A_list = x_array[:,A_list_len:2*A_list_len]
        send_len = x_array[:,-2]
        rece_len = x_array[:,-1]


        sequences = ps.get_experiment_sequences('photon_transfer_arb', sequence_num = sequence_num,
                                                    send_A_list = send_A_list, rece_A_list = rece_A_list,
                                                    send_len = send_len, rece_len = rece_len)

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        data_file = exp.run_experiment(sequences, path, 'photon_transfer_arb', seq_data_file)

        with SlabFile(data_file) as a:
            f_val_list = list(1-np.array(a['expt_avg_data_ch%s'%expt_cfg['receiver_id']])[-1])
            print(f_val_list)

        opt.tell(init_x, f_val_list)


    for iteration in range(iteration_num):

        next_x_list = opt.ask(sequence_num,strategy='cl_min')

        # do the experiment
        x_array = np.array(next_x_list)

        send_A_list = x_array[:,:A_list_len]
        rece_A_list = x_array[:,A_list_len:2*A_list_len]
        send_len = x_array[:,-2]
        rece_len = x_array[:,-1]
        sequences = ps.get_experiment_sequences('photon_transfer_arb', sequence_num = sequence_num,
                                                send_A_list = send_A_list, rece_A_list = rece_A_list,
                                                send_len = send_len, rece_len = rece_len)

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        data_file = exp.run_experiment(sequences, path, 'photon_transfer_arb', seq_data_file)

        with SlabFile(data_file) as a:
            f_val_list = list(1-np.array(a['expt_avg_data_ch%s'%expt_cfg['receiver_id']])[-1])
            print(f_val_list)

        opt.tell(next_x_list, f_val_list)

        with open(os.path.join(path,'optimizer/%s.pkl' %filename.split('.')[0]), 'wb') as f:
            pickle.dump(opt, f)


        frequency_recalibrate_cycle = 20
        if iteration % frequency_recalibrate_cycle == frequency_recalibrate_cycle-1:
            qubit_frequency_flux_calibration(quantum_device_cfg, experiment_cfg, hardware_cfg, path)


def photon_transfer_optimize_v3(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['photon_transfer_arb']
    data_path = os.path.join(path, 'data/')
    filename = get_next_filename(data_path, 'photon_transfer_optimize', suffix='.h5')
    seq_data_file = os.path.join(data_path, filename)

    iteration_num = 20000

    sequence_num = 100
    expt_num = sequence_num


    max_a = {"1":0.5, "2":0.65}
    max_len = 300
    # max_delta_freq = 0.0005

    limit_list = []
    limit_list += [(0.60, max_a[expt_cfg['sender_id']])]
    limit_list += [(0.3, max_a[expt_cfg['receiver_id']])]
    limit_list += [(100.0,max_len)] * 2
    # limit_list += [(-max_delta_freq,max_delta_freq)] * 2

    ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)

    use_prev_model = False

    if use_prev_model:
        with open(os.path.join(path,'optimizer/00057_photon_transfer_optimize.pkl'), 'rb') as f:
            opt = pickle.load(f)
    else:
        opt = Optimizer(limit_list, "GBRT", acq_optimizer="auto")

        init_send_a = [quantum_device_cfg['communication'][expt_cfg['sender_id']]['pi_amp']]
        init_rece_a = [quantum_device_cfg['communication'][expt_cfg['receiver_id']]['pi_amp']]
        init_send_len = [quantum_device_cfg['communication'][expt_cfg['sender_id']]['pi_len']]
        init_rece_len = [quantum_device_cfg['communication'][expt_cfg['receiver_id']]['pi_len']]
        # init_delta_freq_send = [0.00025]
        # init_delta_freq_rece = [0]

        init_x = [init_send_a + init_rece_a + init_send_len + init_rece_len] * sequence_num



        x_array = np.array(init_x)

        send_a = x_array[:,0]
        rece_a = x_array[:,1]
        send_len = x_array[:,2]
        rece_len = x_array[:,3]
        # delta_freq_send = x_array[:,4]
        # delta_freq_rece = x_array[:,5]

        send_A_list = np.outer(send_a, np.ones(10))
        rece_A_list = np.outer(rece_a, np.ones(10))


        sequences = ps.get_experiment_sequences('photon_transfer_arb', sequence_num = sequence_num,
                                                    send_A_list = send_A_list, rece_A_list = rece_A_list,
                                                    send_len = send_len, rece_len = rece_len)

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        data_file = exp.run_experiment(sequences, path, 'photon_transfer_arb', seq_data_file)

        with SlabFile(data_file) as a:
            f_val_list = list(1-np.array(a['expt_avg_data_ch%s'%expt_cfg['receiver_id']])[-1])
            print(f_val_list)

        opt.tell(init_x, f_val_list)


    for iteration in range(iteration_num):

        next_x_list = opt.ask(sequence_num,strategy='cl_max')

        # do the experiment
        x_array = np.array(next_x_list)

        send_a = x_array[:,0]
        rece_a = x_array[:,1]
        send_len = x_array[:,2]
        rece_len = x_array[:,3]
        # delta_freq_send = x_array[:,4]
        # delta_freq_rece = x_array[:,5]

        send_A_list = np.outer(send_a, np.ones(10))
        rece_A_list = np.outer(rece_a, np.ones(10))


        sequences = ps.get_experiment_sequences('photon_transfer_arb', sequence_num = sequence_num,
                                                    send_A_list = send_A_list, rece_A_list = rece_A_list,
                                                    send_len = send_len, rece_len = rece_len)

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        data_file = exp.run_experiment(sequences, path, 'photon_transfer_arb', seq_data_file)

        with SlabFile(data_file) as a:
            f_val_list = list(1-np.array(a['expt_avg_data_ch%s'%expt_cfg['receiver_id']])[-1])
            print(f_val_list)

        opt.tell(next_x_list, f_val_list)

        with open(os.path.join(path,'optimizer/%s.pkl' %filename.split('.')[0]), 'wb') as f:
            pickle.dump(opt, f)


        frequency_recalibrate_cycle = 20
        if iteration % frequency_recalibrate_cycle == frequency_recalibrate_cycle-1:
            qubit_frequency_flux_calibration(quantum_device_cfg, experiment_cfg, hardware_cfg, path)

def photon_transfer_optimize_gp_v4(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['photon_transfer_arb']
    data_path = os.path.join(path, 'data/')
    filename = get_next_filename(data_path, 'photon_transfer_optimize', suffix='.h5')
    seq_data_file = os.path.join(data_path, filename)

    iteration_num = 20000

    sequence_num = 50
    expt_num = sequence_num


    max_a = {"1":0.3, "2":0.7}
    max_len = 400
    # max_delta_freq = 0.0005

    sender_id = quantum_device_cfg['communication']['sender_id']
    receiver_id = quantum_device_cfg['communication']['receiver_id']

    limit_list = []
    limit_list += [(0.10, max_a[sender_id])]
    limit_list += [(0.1, max_a[receiver_id])]
    limit_list += [(100.0,max_len)]
    # limit_list += [(-max_delta_freq,max_delta_freq)] * 2

    ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)

    use_prev_model = False

    for iteration in range(iteration_num):

        if use_prev_model:
            with open(os.path.join(path,'optimizer/00057_photon_transfer_optimize.pkl'), 'rb') as f:
                opt = pickle.load(f)

        if iteration == 0 and not use_prev_model:
            opt = Optimizer(limit_list, "GP", acq_optimizer="lbfgs")

            init_send_a = [quantum_device_cfg['communication'][sender_id]['pi_amp']]
            init_rece_a = [quantum_device_cfg['communication'][receiver_id]['pi_amp']]
            init_send_len = [quantum_device_cfg['communication'][sender_id]['pi_len']]

            next_x_list = [init_send_a + init_rece_a + init_send_len]

            for ii in range(sequence_num-1):
                x_list = []
                for limit in limit_list:
                    sample = np.random.uniform(low=limit[0],high=limit[1])
                    x_list.append(sample)
                next_x_list.append(x_list)

        else:
            next_x_list = []
            gp_best = opt.ask()
            next_x_list.append(gp_best)

            random_sample_num = 10
            x_from_model_num = sequence_num-random_sample_num-1

            X_cand = opt.space.transform(opt.space.rvs(n_samples=100000))
            X_cand_predict = opt.models[-1].predict(X_cand)
            X_cand_argsort = np.argsort(X_cand_predict)
            X_cand_sort = np.array([X_cand[ii] for ii in X_cand_argsort])
            X_cand_top = X_cand_sort[:x_from_model_num]

            gp_sample = opt.space.inverse_transform(X_cand_top)
            next_x_list += gp_sample

            for ii in range(random_sample_num):
                x_list = []
                for limit in limit_list:
                    sample = np.random.uniform(low=limit[0],high=limit[1])
                    x_list.append(sample)
                next_x_list.append(x_list)


        # do the experiment
        print(next_x_list)
        x_array = np.array(next_x_list)

        send_a = x_array[:,0]
        rece_a = x_array[:,1]
        transfer_len = x_array[:,2]

        send_len = transfer_len
        rece_len = transfer_len
        # delta_freq_send = x_array[:,4]
        # delta_freq_rece = x_array[:,5]

        send_A_list = np.outer(send_a, np.ones(10))
        rece_A_list = np.outer(rece_a, np.ones(10))


        sequences = ps.get_experiment_sequences('photon_transfer_arb', sequence_num = sequence_num,
                                                    send_A_list = send_A_list, rece_A_list = rece_A_list,
                                                    send_len = send_len, rece_len = rece_len)

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        data_file = exp.run_experiment(sequences, path, 'photon_transfer_arb', seq_data_file)

        with SlabFile(data_file) as a:
            single_data1 = np.array(a['single_data1'][-1])
            single_data2 = np.array(a['single_data2'][-1])
            single_data_list = [single_data1, single_data2]

            state_norm = get_singleshot_data_two_qubits_4_calibration_v2(single_data_list)
            if receiver_id == 2:
                f_val_list = list(1-state_norm[1])
            else:
                f_val_list = list(1-state_norm[2])
            print(f_val_list)

        opt.tell(next_x_list, f_val_list)

        with open(os.path.join(path,'optimizer/%s.pkl' %filename.split('.')[0]), 'wb') as f:
            pickle.dump(opt, f)


        frequency_recalibrate_cycle = 20
        if iteration % frequency_recalibrate_cycle == frequency_recalibrate_cycle-1:
            qubit_frequency_flux_calibration(quantum_device_cfg, experiment_cfg, hardware_cfg, path)


def bell_entanglement_by_half_sideband_optimize(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['bell_entanglement_by_half_sideband_tomography']
    data_path = os.path.join(path, 'data/')
    filename = get_next_filename(data_path, 'bell_entanglement_by_half_sideband_optimize', suffix='.h5')
    seq_data_file = os.path.join(data_path, filename)

    iteration_num = 20000

    sequence_num = 20
    expt_num = sequence_num


    max_a = {"1":0.6, "2":0.7}
    max_len = 200
    # max_delta_freq = 0.0005

    sender_id = quantum_device_cfg['communication']['sender_id']
    receiver_id = quantum_device_cfg['communication']['receiver_id']

    limit_list = []
    limit_list += [(0.30, max_a[sender_id])]
    limit_list += [(0.3, max_a[receiver_id])]
    limit_list += [(50.0,max_len)] * 2
    # limit_list += [(-max_delta_freq,max_delta_freq)] * 2

    ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)

    use_prev_model = False

    for iteration in range(iteration_num):
        if use_prev_model:
            with open(os.path.join(path,'optimizer/00057_photon_transfer_optimize.pkl'), 'rb') as f:
                opt = pickle.load(f)
            next_x_list = opt.ask(sequence_num,strategy='cl_min')
        else:

            if iteration == 0:
                opt = Optimizer(limit_list, "GBRT", acq_optimizer="auto")

                init_send_a = [quantum_device_cfg['communication'][sender_id]['half_transfer_amp']]
                init_rece_a = [quantum_device_cfg['communication'][receiver_id]['half_transfer_amp']]
                init_send_len = [quantum_device_cfg['communication'][sender_id]['half_transfer_len']]
                init_rece_len = [quantum_device_cfg['communication'][receiver_id]['half_transfer_len']]
                # init_delta_freq_send = [0.00025]
                # init_delta_freq_rece = [0]

                next_x_list = [init_send_a + init_rece_a + init_send_len + init_rece_len]

                for ii in range(sequence_num-1):
                    x_list = []
                    for limit in limit_list:
                        sample = np.random.uniform(low=limit[0],high=limit[1])
                        x_list.append(sample)
                    next_x_list.append(x_list)



            else:
                next_x_list = opt.ask(sequence_num,strategy='cl_max')

        # do the experiment
        print(next_x_list)
        x_array = np.array(next_x_list)

        send_a = x_array[:,0]
        rece_a = x_array[:,1]
        send_len = x_array[:,2]
        rece_len = x_array[:,3]
        # delta_freq_send = x_array[:,4]
        # delta_freq_rece = x_array[:,5]

        send_A_list = np.outer(send_a, np.ones(10))
        rece_A_list = np.outer(rece_a, np.ones(10))


        sequences = ps.get_experiment_sequences('bell_entanglement_by_half_sideband_tomography', sequence_num = sequence_num,
                                                    send_A_list = send_A_list, rece_A_list = rece_A_list,
                                                    send_len = send_len, rece_len = rece_len)

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        data_file = exp.run_experiment(sequences, path, 'bell_entanglement_by_half_sideband_tomography', seq_data_file)

        with SlabFile(data_file) as a:
            single_data1 = np.array(a['single_data1'])[-1]
            single_data2 = np.array(a['single_data2'])[-1]

            # single_data_list = [single_data1, single_data2]

            f_val_list = []
            for expt_id in range(sequence_num):
                elem_list = list(range(expt_id*9,(expt_id+1)*9)) + [-2,-1]
                single_data_list = [single_data1[:,:,elem_list,:], single_data2[:,:,elem_list,:]]
                state_norm = get_singleshot_data_two_qubits(single_data_list, expt_cfg['pi_calibration'])
                # print(state_norm.shape)
                state_data = data_to_correlators(state_norm)
                den_mat = two_qubit_quantum_state_tomography(state_data)
                perfect_bell = np.array([0,1/np.sqrt(2),1/np.sqrt(2),0])
                perfect_bell_den_mat = np.outer(perfect_bell, perfect_bell)

                fidelity = np.trace(np.dot(np.transpose(np.conjugate(perfect_bell_den_mat)),np.abs(den_mat) ))

                f_val_list.append(1-fidelity)
            print(f_val_list)

        opt.tell(next_x_list, f_val_list)

        with open(os.path.join(path,'optimizer/%s.pkl' %filename.split('.')[0]), 'wb') as f:
            pickle.dump(opt, f)


        frequency_recalibrate_cycle = 10
        if iteration % frequency_recalibrate_cycle == frequency_recalibrate_cycle-1:
            qubit_frequency_flux_calibration(quantum_device_cfg, experiment_cfg, hardware_cfg, path)



def bell_entanglement_by_half_sideband_optimize_gp_v4(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    # use a * len as a variable, and not use opt.ask
    expt_cfg = experiment_cfg['bell_entanglement_by_half_sideband_tomography']
    data_path = os.path.join(path, 'data/')
    filename = get_next_filename(data_path, 'bell_entanglement_by_half_sideband_optimize', suffix='.h5')
    seq_data_file = os.path.join(data_path, filename)

    iteration_num = 20000

    sequence_num = 10
    expt_num = sequence_num


    max_a = {"1":0.4, "2":0.6}
    max_len_send = 80
    max_len_rece = 200
    # max_delta_freq = 0.0005

    sender_id = quantum_device_cfg['communication']['sender_id']
    receiver_id = quantum_device_cfg['communication']['receiver_id']

    limit_list = []
    limit_list += [(0.35, max_a[sender_id])]
    limit_list += [(0.55, max_a[receiver_id])]
    limit_list += [(60.0*0.35,max_len_send*max_a[sender_id])]
    limit_list += [(170.0*0.55,max_len_rece*max_a[receiver_id])]
    # limit_list += [(-max_delta_freq,max_delta_freq)] * 2

    ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)

    use_prev_model = False

    for iteration in range(iteration_num):
        if iteration == 0 and use_prev_model:
            with open(os.path.join(path,'optimizer/00031_bell_entanglement_by_half_sideband_optimize.pkl'), 'rb') as f:
                opt = pickle.load(f)

        if iteration == 0 and not use_prev_model:
            opt = Optimizer(limit_list, "GP", acq_optimizer="lbfgs")

            init_send_a = [quantum_device_cfg['communication'][sender_id]['half_transfer_amp']]
            init_rece_a = [quantum_device_cfg['communication'][receiver_id]['half_transfer_amp']]
            init_send_len = [quantum_device_cfg['communication'][sender_id]['half_transfer_len']]
            init_rece_len = [quantum_device_cfg['communication'][receiver_id]['half_transfer_len']]

            init_send_area = [quantum_device_cfg['communication'][sender_id]['half_transfer_amp']*quantum_device_cfg['communication'][sender_id]['half_transfer_len']]
            init_rece_area = [quantum_device_cfg['communication'][receiver_id]['half_transfer_amp']*quantum_device_cfg['communication'][receiver_id]['half_transfer_len']]
            # init_delta_freq_send = [0.00025]
            # init_delta_freq_rece = [0]

            next_x_list = [init_send_a + init_rece_a + init_send_area + init_rece_area]

            for ii in range(sequence_num-1):
                x_list = []
                for limit in limit_list:
                    sample = np.random.uniform(low=limit[0],high=limit[1])
                    x_list.append(sample)
                next_x_list.append(x_list)



        else:
            next_x_list = []
            gp_best = opt.ask()
            next_x_list.append(gp_best)

            random_sample_num = 2
            x_from_model_num = sequence_num-random_sample_num-1

            X_cand = opt.space.transform(opt.space.rvs(n_samples=100000))
            X_cand_predict = opt.models[-1].predict(X_cand)
            X_cand_argsort = np.argsort(X_cand_predict)
            X_cand_sort = np.array([X_cand[ii] for ii in X_cand_argsort])
            X_cand_top = X_cand_sort[:x_from_model_num]

            gp_sample = opt.space.inverse_transform(X_cand_top)
            next_x_list += gp_sample

            for ii in range(random_sample_num):
                x_list = []
                for limit in limit_list:
                    sample = np.random.uniform(low=limit[0],high=limit[1])
                    x_list.append(sample)
                next_x_list.append(x_list)

        # do the experiment
        print(next_x_list)
        x_array = np.array(next_x_list)

        send_a = x_array[:,0]
        rece_a = x_array[:,1]
        send_area = x_array[:,2]
        rece_area = x_array[:,3]


        send_len = send_area/send_a
        rece_len = rece_area/rece_a
        # delta_freq_send = x_array[:,4]
        # delta_freq_rece = x_array[:,5]

        send_A_list = np.outer(send_a, np.ones(10))
        rece_A_list = np.outer(rece_a, np.ones(10))


        sequences = ps.get_experiment_sequences('bell_entanglement_by_half_sideband_tomography', sequence_num = sequence_num,
                                                    send_A_list = send_A_list, rece_A_list = rece_A_list,
                                                    send_len = send_len, rece_len = rece_len)

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        data_file = exp.run_experiment(sequences, path, 'bell_entanglement_by_half_sideband_tomography', seq_data_file)

        with SlabFile(data_file) as a:
            single_data1 = np.array(a['single_data1'])[-1]
            single_data2 = np.array(a['single_data2'])[-1]

            # single_data_list = [single_data1, single_data2]

            f_val_list = []
            for expt_id in range(sequence_num):
                elem_list = list(range(expt_id*17,(expt_id+1)*17)) + [-4,-3,-2,-1]
                single_data_list = [single_data1[:,:,elem_list,:], single_data2[:,:,elem_list,:]]
                state_norm = get_singleshot_data_two_qubits_4_calibration_v2(single_data_list)

                state_data = data_to_correlators(state_norm[:9])
                den_mat_guess = two_qubit_quantum_state_tomography(state_data)

                ew, ev = np.linalg.eigh(den_mat_guess)
                pos_ew = [max(w,0) for w in ew]
                pos_D = np.diag(pos_ew)
                inv_ev = np.linalg.inv(ev)
                pos_den_mat_guess = np.dot(np.dot(ev,pos_D),inv_ev)

                den_mat_guess_input = pos_den_mat_guess[::-1,::-1]
                den_mat_guess_input = np.real(den_mat_guess_input) - 1j*np.imag(den_mat_guess_input)

                optimized_rho = density_matrix_maximum_likelihood(state_norm,den_mat_guess_input)

                perfect_bell = np.array([0,1/np.sqrt(2),1/np.sqrt(2),0])
                perfect_bell_den_mat = np.outer(perfect_bell, perfect_bell)
                fidelity = np.trace(np.dot(np.transpose(np.conjugate(perfect_bell_den_mat)),np.abs(optimized_rho).clip(max=0.5) ))

                f_val_list.append(1-fidelity)
            print(f_val_list)

        opt.tell(next_x_list, f_val_list)

        # only save the latest model
        opt.models = [opt.models[-1]]

        with open(os.path.join(path,'optimizer/%s.pkl' %filename.split('.')[0]), 'wb') as f:
            pickle.dump(opt, f)


        frequency_recalibrate_cycle = 10
        if iteration % frequency_recalibrate_cycle == frequency_recalibrate_cycle-1:
            qubit_frequency_flux_calibration(quantum_device_cfg, experiment_cfg, hardware_cfg, path)



def bell_entanglement_by_half_sideband_optimize_v4(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    # use a * len as a variable, and not use opt.ask
    expt_cfg = experiment_cfg['bell_entanglement_by_half_sideband_tomography']
    data_path = os.path.join(path, 'data/')
    filename = get_next_filename(data_path, 'bell_entanglement_by_half_sideband_optimize', suffix='.h5')
    seq_data_file = os.path.join(data_path, filename)

    iteration_num = 20000

    sequence_num = 10
    expt_num = sequence_num


    max_a = {"1":0.6, "2":0.7}
    max_len = 200
    # max_delta_freq = 0.0005

    sender_id = quantum_device_cfg['communication']['sender_id']
    receiver_id = quantum_device_cfg['communication']['receiver_id']

    limit_list = []
    limit_list += [(0.30, max_a[sender_id])]
    limit_list += [(0.3, max_a[receiver_id])]
    limit_list += [(10.0,max_len*max_a[sender_id])]
    limit_list += [(10.0,max_len*max_a[receiver_id])]
    # limit_list += [(-max_delta_freq,max_delta_freq)] * 2

    ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)

    use_prev_model = False

    for iteration in range(iteration_num):
        if iteration == 0 and use_prev_model:
            with open(os.path.join(path,'optimizer/00031_bell_entanglement_by_half_sideband_optimize.pkl'), 'rb') as f:
                opt = pickle.load(f)

        if iteration == 0 and not use_prev_model:
            opt = Optimizer(limit_list, "GBRT", acq_optimizer="auto")

            init_send_a = [quantum_device_cfg['communication'][sender_id]['half_transfer_amp']]
            init_rece_a = [quantum_device_cfg['communication'][receiver_id]['half_transfer_amp']]
            init_send_len = [quantum_device_cfg['communication'][sender_id]['half_transfer_len']]
            init_rece_len = [quantum_device_cfg['communication'][receiver_id]['half_transfer_len']]

            init_send_area = [quantum_device_cfg['communication'][sender_id]['half_transfer_amp']*quantum_device_cfg['communication'][sender_id]['half_transfer_len']]
            init_rece_area = [quantum_device_cfg['communication'][receiver_id]['half_transfer_amp']*quantum_device_cfg['communication'][receiver_id]['half_transfer_len']]
            # init_delta_freq_send = [0.00025]
            # init_delta_freq_rece = [0]

            next_x_list = [init_send_a + init_rece_a + init_send_area + init_rece_area]

            for ii in range(sequence_num-1):
                x_list = []
                for limit in limit_list:
                    sample = np.random.uniform(low=limit[0],high=limit[1])
                    x_list.append(sample)
                next_x_list.append(x_list)



        else:
            x_from_model_num = int(sequence_num/2)

            X_cand = opt.space.transform(opt.space.rvs(n_samples=100000))
            X_cand_predict = opt.models[-1].predict(X_cand)
            X_cand_argsort = np.argsort(X_cand_predict)
            X_cand_sort = np.array([X_cand[ii] for ii in X_cand_argsort])
            X_cand_top = X_cand_sort[:x_from_model_num]

            next_x_list = opt.space.inverse_transform(X_cand_top)

            for ii in range(sequence_num-x_from_model_num):
                x_list = []
                for limit in limit_list:
                    sample = np.random.uniform(low=limit[0],high=limit[1])
                    x_list.append(sample)
                next_x_list.append(x_list)

        # do the experiment
        print(next_x_list)
        x_array = np.array(next_x_list)

        send_a = x_array[:,0]
        rece_a = x_array[:,1]
        send_area = x_array[:,2]
        rece_area = x_array[:,3]


        send_len = send_area/send_a
        rece_len = rece_area/rece_a
        # delta_freq_send = x_array[:,4]
        # delta_freq_rece = x_array[:,5]

        send_A_list = np.outer(send_a, np.ones(10))
        rece_A_list = np.outer(rece_a, np.ones(10))


        sequences = ps.get_experiment_sequences('bell_entanglement_by_half_sideband_tomography', sequence_num = sequence_num,
                                                    send_A_list = send_A_list, rece_A_list = rece_A_list,
                                                    send_len = send_len, rece_len = rece_len)

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        data_file = exp.run_experiment(sequences, path, 'bell_entanglement_by_half_sideband_tomography', seq_data_file)

        with SlabFile(data_file) as a:
            single_data1 = np.array(a['single_data1'])[-1]
            single_data2 = np.array(a['single_data2'])[-1]

            # single_data_list = [single_data1, single_data2]

            f_val_list = []
            for expt_id in range(sequence_num):
                elem_list = list(range(expt_id*17,(expt_id+1)*17)) + [-4,-3,-2,-1]
                single_data_list = [single_data1[:,:,elem_list,:], single_data2[:,:,elem_list,:]]
                state_norm = get_singleshot_data_two_qubits_4_calibration(single_data_list)

                state_data = data_to_correlators(state_norm[:9])
                den_mat_guess = two_qubit_quantum_state_tomography(state_data)

                ew, ev = np.linalg.eigh(den_mat_guess)
                pos_ew = [max(w,0) for w in ew]
                pos_D = np.diag(pos_ew)
                inv_ev = np.linalg.inv(ev)
                pos_den_mat_guess = np.dot(np.dot(ev,pos_D),inv_ev)

                den_mat_guess_input = pos_den_mat_guess[::-1,::-1]
                den_mat_guess_input = np.real(den_mat_guess_input) - 1j*np.imag(den_mat_guess_input)

                optimized_rho = density_matrix_maximum_likelihood(state_norm,den_mat_guess_input)

                perfect_bell = np.array([0,1/np.sqrt(2),1/np.sqrt(2),0])
                perfect_bell_den_mat = np.outer(perfect_bell, perfect_bell)
                fidelity = np.trace(np.dot(np.transpose(np.conjugate(perfect_bell_den_mat)),np.abs(optimized_rho) ))

                f_val_list.append(1-fidelity)
            print(f_val_list)

        opt.tell(next_x_list, f_val_list)

        # only save the latest model
        opt.models = [opt.models[-1]]

        with open(os.path.join(path,'optimizer/%s.pkl' %filename.split('.')[0]), 'wb') as f:
            pickle.dump(opt, f)


        frequency_recalibrate_cycle = 10
        if iteration % frequency_recalibrate_cycle == frequency_recalibrate_cycle-1:
            qubit_frequency_flux_calibration(quantum_device_cfg, experiment_cfg, hardware_cfg, path)



def bell_entanglement_by_half_sideband_optimize_v3(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    # use a * len as a variable
    expt_cfg = experiment_cfg['bell_entanglement_by_half_sideband_tomography']
    data_path = os.path.join(path, 'data/')
    filename = get_next_filename(data_path, 'bell_entanglement_by_half_sideband_optimize', suffix='.h5')
    seq_data_file = os.path.join(data_path, filename)

    iteration_num = 20000

    sequence_num = 20
    expt_num = sequence_num


    max_a = {"1":0.6, "2":0.7}
    max_len = 200
    # max_delta_freq = 0.0005

    sender_id = quantum_device_cfg['communication']['sender_id']
    receiver_id = quantum_device_cfg['communication']['receiver_id']

    limit_list = []
    limit_list += [(0.30, max_a[sender_id])]
    limit_list += [(0.3, max_a[receiver_id])]
    limit_list += [(20.0,max_len*max_a[sender_id])]
    limit_list += [(20.0,max_len*max_a[receiver_id])]
    # limit_list += [(-max_delta_freq,max_delta_freq)] * 2

    ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)

    use_prev_model = False

    for iteration in range(iteration_num):
        if use_prev_model:
            with open(os.path.join(path,'optimizer/00057_photon_transfer_optimize.pkl'), 'rb') as f:
                opt = pickle.load(f)
            next_x_list = opt.ask(sequence_num,strategy='cl_min')
        else:

            if iteration == 0:
                opt = Optimizer(limit_list, "GBRT", acq_optimizer="auto")

                init_send_a = [quantum_device_cfg['communication'][sender_id]['half_transfer_amp']]
                init_rece_a = [quantum_device_cfg['communication'][receiver_id]['half_transfer_amp']]
                init_send_len = [quantum_device_cfg['communication'][sender_id]['half_transfer_len']]
                init_rece_len = [quantum_device_cfg['communication'][receiver_id]['half_transfer_len']]

                init_send_area = [quantum_device_cfg['communication'][sender_id]['half_transfer_amp']*quantum_device_cfg['communication'][sender_id]['half_transfer_len']]
                init_rece_area = [quantum_device_cfg['communication'][receiver_id]['half_transfer_amp']*quantum_device_cfg['communication'][receiver_id]['half_transfer_len']]
                # init_delta_freq_send = [0.00025]
                # init_delta_freq_rece = [0]

                next_x_list = [init_send_a + init_rece_a + init_send_area + init_rece_area]

                for ii in range(sequence_num-1):
                    x_list = []
                    for limit in limit_list:
                        sample = np.random.uniform(low=limit[0],high=limit[1])
                        x_list.append(sample)
                    next_x_list.append(x_list)



            else:
                next_x_list = opt.ask(sequence_num,strategy='cl_max')

        # do the experiment
        print(next_x_list)
        x_array = np.array(next_x_list)

        send_a = x_array[:,0]
        rece_a = x_array[:,1]
        send_area = x_array[:,2]
        rece_area = x_array[:,3]


        send_len = send_area/send_a
        rece_len = rece_area/rece_a
        # delta_freq_send = x_array[:,4]
        # delta_freq_rece = x_array[:,5]

        send_A_list = np.outer(send_a, np.ones(10))
        rece_A_list = np.outer(rece_a, np.ones(10))


        sequences = ps.get_experiment_sequences('bell_entanglement_by_half_sideband_tomography', sequence_num = sequence_num,
                                                    send_A_list = send_A_list, rece_A_list = rece_A_list,
                                                    send_len = send_len, rece_len = rece_len)

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        data_file = exp.run_experiment(sequences, path, 'bell_entanglement_by_half_sideband_tomography', seq_data_file)

        with SlabFile(data_file) as a:
            single_data1 = np.array(a['single_data1'])[-1]
            single_data2 = np.array(a['single_data2'])[-1]

            # single_data_list = [single_data1, single_data2]

            f_val_list = []
            for expt_id in range(sequence_num):
                elem_list = list(range(expt_id*9,(expt_id+1)*9)) + [-2,-1]
                single_data_list = [single_data1[:,:,elem_list,:], single_data2[:,:,elem_list,:]]
                state_norm = get_singleshot_data_two_qubits(single_data_list, expt_cfg['pi_calibration'])
                # print(state_norm.shape)
                state_data = data_to_correlators(state_norm)
                den_mat = two_qubit_quantum_state_tomography(state_data)
                perfect_bell = np.array([0,1/np.sqrt(2),1/np.sqrt(2),0])
                perfect_bell_den_mat = np.outer(perfect_bell, perfect_bell)

                fidelity = np.trace(np.dot(np.transpose(np.conjugate(perfect_bell_den_mat)),np.abs(den_mat) ))

                f_val_list.append(1-fidelity)
            print(f_val_list)

        opt.tell(next_x_list, f_val_list)

        with open(os.path.join(path,'optimizer/%s.pkl' %filename.split('.')[0]), 'wb') as f:
            pickle.dump(opt, f)


        frequency_recalibrate_cycle = 10
        if iteration % frequency_recalibrate_cycle == frequency_recalibrate_cycle-1:
            qubit_frequency_flux_calibration(quantum_device_cfg, experiment_cfg, hardware_cfg, path)

def bell_entanglement_by_half_sideband_optimize_v2(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['bell_entanglement_by_half_sideband_tomography']
    data_path = os.path.join(path, 'data/')
    filename = get_next_filename(data_path, 'bell_entanglement_by_half_sideband_optimize', suffix='.h5')
    seq_data_file = os.path.join(data_path, filename)

    iteration_num = 20000

    sequence_num = 20
    expt_num = sequence_num

    A_list_len = 2

    max_a = {"1":0.6, "2":0.7}
    max_len = 200
    # max_delta_freq = 0.0005

    sender_id = quantum_device_cfg['communication']['sender_id']
    receiver_id = quantum_device_cfg['communication']['receiver_id']

    limit_list = []
    limit_list += [(0.30, max_a[sender_id])]*A_list_len
    limit_list += [(0.2, max_a[receiver_id])]*A_list_len
    limit_list += [(50.0,max_len)] * 2
    # limit_list += [(-max_delta_freq,max_delta_freq)] * 2

    ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)

    use_prev_model = False

    for iteration in range(iteration_num):
        if use_prev_model:
            with open(os.path.join(path,'optimizer/00057_photon_transfer_optimize.pkl'), 'rb') as f:
                opt = pickle.load(f)
            next_x_list = opt.ask(sequence_num,strategy='cl_max')
        else:

            if iteration == 0:
                opt = Optimizer(limit_list, "GBRT", acq_optimizer="auto")

                init_send_a = [quantum_device_cfg['communication'][sender_id]['half_transfer_amp']]*A_list_len
                init_rece_a = [quantum_device_cfg['communication'][receiver_id]['half_transfer_amp']]*A_list_len
                init_send_len = [quantum_device_cfg['communication'][sender_id]['half_transfer_len']]
                init_rece_len = [quantum_device_cfg['communication'][receiver_id]['half_transfer_len']]
                # init_delta_freq_send = [0.00025]
                # init_delta_freq_rece = [0]

                next_x_list = [init_send_a + init_rece_a + init_send_len + init_rece_len]

                for ii in range(sequence_num-1):
                    x_list = []
                    for limit in limit_list:
                        sample = np.random.uniform(low=limit[0],high=limit[1])
                        x_list.append(sample)
                    next_x_list.append(x_list)



            else:
                next_x_list = opt.ask(sequence_num,strategy='cl_max')

        # do the experiment
        print(next_x_list)
        x_array = np.array(next_x_list)

        # send_a = x_array[:,0]
        # rece_a = x_array[:,1]
        # send_len = x_array[:,2]
        # rece_len = x_array[:,3]
        # # delta_freq_send = x_array[:,4]
        # # delta_freq_rece = x_array[:,5]
        #
        # send_A_list = np.outer(send_a, np.ones(10))
        # rece_A_list = np.outer(rece_a, np.ones(10))


        send_A_list = x_array[:,:A_list_len]
        rece_A_list = x_array[:,A_list_len:2*A_list_len]
        send_len = x_array[:,-2]
        rece_len = x_array[:,-1]


        sequences = ps.get_experiment_sequences('bell_entanglement_by_half_sideband_tomography', sequence_num = sequence_num,
                                                    send_A_list = send_A_list, rece_A_list = rece_A_list,
                                                    send_len = send_len, rece_len = rece_len)

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        data_file = exp.run_experiment(sequences, path, 'bell_entanglement_by_half_sideband_tomography', seq_data_file)

        with SlabFile(data_file) as a:
            single_data1 = np.array(a['single_data1'])[-1]
            single_data2 = np.array(a['single_data2'])[-1]

            # single_data_list = [single_data1, single_data2]

            f_val_list = []
            for expt_id in range(sequence_num):
                elem_list = list(range(expt_id*9,(expt_id+1)*9)) + [-2,-1]
                single_data_list = [single_data1[:,:,elem_list,:], single_data2[:,:,elem_list,:]]
                state_norm = get_singleshot_data_two_qubits(single_data_list, expt_cfg['pi_calibration'])
                # print(state_norm.shape)
                state_data = data_to_correlators(state_norm)
                den_mat = two_qubit_quantum_state_tomography(state_data)
                perfect_bell = np.array([0,1/np.sqrt(2),1/np.sqrt(2),0])
                perfect_bell_den_mat = np.outer(perfect_bell, perfect_bell)

                fidelity = np.trace(np.dot(np.transpose(np.conjugate(perfect_bell_den_mat)),np.abs(den_mat) ))

                f_val_list.append(1-fidelity)
            print(f_val_list)

        opt.tell(next_x_list, f_val_list)

        with open(os.path.join(path,'optimizer/%s.pkl' %filename.split('.')[0]), 'wb') as f:
            pickle.dump(opt, f)


        frequency_recalibrate_cycle = 10
        if iteration % frequency_recalibrate_cycle == frequency_recalibrate_cycle-1:
            qubit_frequency_flux_calibration(quantum_device_cfg, experiment_cfg, hardware_cfg, path)



def photon_transfer_sweep(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['photon_transfer']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'photon_transfer_sweep', suffix='.h5'))

    sweep = 'rece_a'

    sender_id = quantum_device_cfg['communication']['sender_id']
    receiver_id = quantum_device_cfg['communication']['receiver_id']

    if sweep == 'delay':
        delay_len_start = -100
        delay_len_stop = 100
        delay_len_step = 4.0

        for delay_len in np.arange(delay_len_start, delay_len_stop,delay_len_step):
            experiment_cfg['photon_transfer']['rece_delay'] = delay_len
            ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
            sequences = ps.get_experiment_sequences('photon_transfer')

            exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
            exp.run_experiment(sequences, path, 'photon_transfer', seq_data_file)

    elif sweep == 'sender_a':
        start = 0.41
        stop = 0.39
        step = -0.002

        for amp in np.arange(start, stop,step):
            quantum_device_cfg['communication'][sender_id]['pi_amp'] = amp
            ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
            sequences = ps.get_experiment_sequences('photon_transfer')

            exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
            exp.run_experiment(sequences, path, 'photon_transfer', seq_data_file)
    elif sweep == 'rece_a':
        start = 0.5
        stop = 0.3
        step = -0.01

        for amp in np.arange(start, stop,step):
            quantum_device_cfg['communication'][receiver_id]['pi_amp'] = amp
            ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
            sequences = ps.get_experiment_sequences('photon_transfer')

            exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
            exp.run_experiment(sequences, path, 'photon_transfer', seq_data_file)


def communication_rabi_amp_sweep(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['communication_rabi']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'communication_rabi_amp_sweep', suffix='.h5'))

    amp_start = 0.7
    amp_stop = 0.0
    amp_step = -0.01

    on_qubit = "2"

    for amp in np.arange(amp_start, amp_stop,amp_step):
        quantum_device_cfg['communication'][on_qubit]['pi_amp'] = amp
        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('communication_rabi')

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'communication_rabi', seq_data_file)


def sideband_rabi_freq_amp_sweep(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['sideband_rabi_freq']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'sideband_rabi_freq_amp_sweep', suffix='.h5'))

    amp_start = 0.70
    amp_stop = 0.0
    amp_step = -0.005

    for amp in np.arange(amp_start, amp_stop,amp_step):
        experiment_cfg['sideband_rabi_freq']['amp'] = amp
        experiment_cfg['sideband_rabi_freq']['pulse_len'] = 90*amp_start/amp
        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('sideband_rabi_freq')

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'sideband_rabi_freq', seq_data_file)

def ef_sideband_rabi_freq_amp_sweep(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['ef_sideband_rabi_freq']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'ef_sideband_rabi_freq_amp_sweep', suffix='.h5'))

    amp_start = 0.4
    amp_stop = 0.0
    amp_step = -0.005

    for amp in np.arange(amp_start, amp_stop,amp_step):
        experiment_cfg['ef_sideband_rabi_freq']['amp'] = amp
        experiment_cfg['ef_sideband_rabi_freq']['pulse_len'] = 50*amp_start/amp
        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('ef_sideband_rabi_freq')

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'ef_sideband_rabi_freq', seq_data_file)


def rabi_repeat(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['rabi']
    data_path = os.path.join(path, 'data/')
    seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'rabi_repeat', suffix='.h5'))

    repeat = 100

    update_awg = True

    for ii in range(repeat):
        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('rabi')

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'rabi', seq_data_file, update_awg = update_awg)

        update_awg = False


def bell_repeat(quantum_device_cfg, experiment_cfg, hardware_cfg, path):
    expt_cfg = experiment_cfg['bell_entanglement_by_half_sideband_tomography']
    data_path = os.path.join(path, 'data/')
    #seq_data_file = os.path.join(data_path, get_next_filename(data_path, 'bell_entanglement_by_half_sideband_tomography_repeat', suffix='.h5'))

    repeat = 10

    update_awg = True

    for iteration in range(repeat):
        qubit_frequency_flux_calibration(quantum_device_cfg, experiment_cfg, hardware_cfg, path)

        ps = PulseSequences(quantum_device_cfg, experiment_cfg, hardware_cfg)
        sequences = ps.get_experiment_sequences('bell_entanglement_by_half_sideband_tomography')

        exp = Experiment(quantum_device_cfg, experiment_cfg, hardware_cfg)
        exp.run_experiment(sequences, path, 'bell_entanglement_by_half_sideband_tomography', update_awg = update_awg)

        # frequency_recalibrate_cycle = 10
        # if iteration % frequency_recalibrate_cycle == frequency_recalibrate_cycle-1:
        #     qubit_frequency_flux_calibration(quantum_device_cfg, experiment_cfg, hardware_cfg, path)