from configuration_IQ import config, storage_IF, storage_LO
from qm.QuantumMachinesManager import QuantumMachinesManager
from qm.qua import *
from qm import SimulationConfig
import matplotlib.pyplot as plt
import numpy as np
from slab import*
from slab.instruments import instrumentmanager
# im = InstrumentManager()
# spec = im['SA']
# LO_s  = im['sccav']
#
# LO_s.set_frequency(storage_LO)
# LO_s.set_power(13.0)

with program() as mixer_calibration:
    with infinite_loop_():
        play("CW"*amp(0.0), "storage")

qmm = QuantumMachinesManager()
qm = qmm.open_qm(config)

job = qm.execute(mixer_calibration, duration_limit=0, data_limit=0)

# delta_F = 300e6
# spec.set_center_frequency(storage_LO)
# spec.set_span(delta_F)
# spec.set_resbw(100e3)
# tr = spec.take_one()
# freq, amp = tr[0], tr[1]
# plt.plot(freq, amp)
# a1 = amp[np.argmin(abs(freq-storage_LO+storage_IF))]
# a2 = amp[np.argmin(abs(freq-storage_LO))]
# a3 = amp[np.argmin(abs(freq-storage_LO-storage_IF))]
#
# print([a1, a2, a3])
# plt.axvline(x=storage_LO, linestyle='--', color='k')
# plt.axvline(x=storage_LO - storage_IF, linestyle='--', color='k')
# plt.axvline(x=storage_LO + storage_IF, linestyle='--', color='k')

# qm.set_dc_offset_by_qe("storage", "I", -0.018)
# qm.set_dc_offset_by_qe("storage", "Q", -0.014)


# print([a1, a2, a3])

def IQ_imbalance_corr(g, phi):
    c = np.cos(phi)
    s = np.sin(phi)
    N = 1 / ((1 - g ** 2) * (2 * c ** 2 - 1))
    return [float(N * x) for x in [(1 - g) * c, (1 + g) * s,
                                   (1 - g) * s, (1 + g) * c]]

# qm.set_mixer_correction("mixer_storage", int(storage_IF), int(storage_LO), IQ_imbalance_corr(0.008,0.037*np.pi))