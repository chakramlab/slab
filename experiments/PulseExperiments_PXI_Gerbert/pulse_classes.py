import visdom
import numpy as np
import scipy
from scipy import interpolate
from scipy import integrate


class Pulse:
    def __init__(self):
        pass

    def plot_pulse(self):
        vis = visdom.Visdom()
        win = vis.line(
            X=np.arange(0, len(self.pulse_array)) * self.dt,
            Y=self.pulse_array
        )

    def generate_pulse_array(self, t0=0, dt=None):
        if dt is not None:
            self.dt = dt
        if self.dt is None:
            raise ValueError('dt is not specified.')

        self.t0 = t0

        total_length = self.get_length()
        self.t_array = self.get_t_array(total_length)

        self.pulse_array = self.get_pulse_array()

        if self.plot:
            self.plot_pulse()

    def get_t_array(self, total_length):
        return np.arange(0, total_length, self.dt) + self.t0

    def get_area(self):
        area = np.trapz(self.pulse_array, self.t_array)
        return area


class Gauss(Pulse):
    def __init__(self, max_amp, sigma_len, cutoff_sigma, freq, phase, dt=None, plot=False):
        self.max_amp = max_amp
        self.sigma_len = sigma_len
        self.cutoff_sigma = cutoff_sigma
        self.freq = freq
        self.phase = phase
        self.dt = dt
        self.plot = plot

        self.t0 = 0


    def get_pulse_array(self):

        pulse_array = self.max_amp * np.exp(
            -1.0 * (self.t_array - (self.t0 + 2 * self.sigma_len)) ** 2 / (2 * self.sigma_len ** 2))
        pulse_array = pulse_array * np.cos(2 * np.pi * self.freq * self.t_array + self.phase)

        return pulse_array

    def get_length(self):
        return 2 * self.cutoff_sigma * self.sigma_len

class Gauss_2freq(Pulse):
    def __init__(self, max_amp1, max_amp2, sigma_len, cutoff_sigma, freq1, freq2, phase, dt=None, plot=False):
        self.max_amp1 = max_amp1
        self.max_amp2 = max_amp2
        self.sigma_len = sigma_len
        self.cutoff_sigma = cutoff_sigma
        self.freq1 = freq1
        self.freq2 = freq2
        self.phase = phase
        self.dt = dt
        self.plot = plot

        self.t0 = 0


    def get_pulse_array(self):

        pulse_array1 = self.max_amp1 * np.exp(
            -1.0 * (self.t_array - (self.t0 + 2 * self.sigma_len)) ** 2 / (2 * self.sigma_len ** 2))
        pulse_array1 = pulse_array1 * np.cos(2 * np.pi * self.freq1 * self.t_array + self.phase)

        pulse_array2 = self.max_amp2 * np.exp(
            -1.0 * (self.t_array - (self.t0 + 2 * self.sigma_len)) ** 2 / (2 * self.sigma_len ** 2))
        pulse_array2 = pulse_array2 * np.cos(2 * np.pi * self.freq2 * self.t_array + self.phase)

        return pulse_array1 +pulse_array2

    def get_length(self):
        return 2 * self.cutoff_sigma * self.sigma_len

class Square(Pulse):
    def __init__(self, max_amp, flat_len, ramp_sigma_len, cutoff_sigma, freq, phase, phase_t0 = 0, dt=None, plot=False):
        self.max_amp = max_amp
        self.flat_len = flat_len
        self.ramp_sigma_len = ramp_sigma_len
        self.cutoff_sigma = cutoff_sigma
        self.freq = freq
        self.phase = phase
        self.phase_t0 = phase_t0
        self.dt = dt
        self.plot = plot

        self.t0 = 0

    def get_pulse_array(self):

        t_flat_start = self.t0 + self.cutoff_sigma * self.ramp_sigma_len
        t_flat_end = self.t0 + self.cutoff_sigma * self.ramp_sigma_len + self.flat_len

        t_end = self.t0 + 2 * self.cutoff_sigma * self.ramp_sigma_len + self.flat_len

        pulse_array = self.max_amp * (
            (self.t_array >= t_flat_start) * (
                self.t_array < t_flat_end) +  # Normal square pulse
            (self.t_array >= self.t0) * (self.t_array < t_flat_start) * np.exp(
                -1.0 * (self.t_array - (t_flat_start)) ** 2 / (
                    2 * self.ramp_sigma_len ** 2)) +  # leading gaussian edge
            (self.t_array >= t_flat_end) * (
                self.t_array <= t_end) * np.exp(
                -1.0 * (self.t_array - (t_flat_end)) ** 2 / (
                    2 * self.ramp_sigma_len ** 2))  # trailing edge
        )

        pulse_array = pulse_array * np.cos(2 * np.pi * self.freq * (self.t_array - self.phase_t0) + self.phase)

        return pulse_array

    def get_length(self):
        return self.flat_len + 2 * self.cutoff_sigma * self.ramp_sigma_len


class FreqSquare(Pulse):
    def __init__(self, max_amp, flat_freq_Ghz, pulse_len, conv_gauss_sig_Ghz, freq, phase, phase_t0=0, dt=None,
                 plot=False):
        self.max_amp = max_amp
        self.flat_freq_Ghz = flat_freq_Ghz
        self.pulse_len = pulse_len
        self.conv_gauss_sig_Ghz = conv_gauss_sig_Ghz
        self.freq = freq
        self.phase = phase
        self.phase_t0 = phase_t0
        self.dt = dt
        self.plot = plot

        self.t0 = 0

    def get_pulse_array(self):
        t_center = self.t0 + np.round(self.pulse_len / 2)
        gauss_sigma = 1 / (2 * self.conv_gauss_sig_Ghz * np.pi)

        pulse_array = self.max_amp * \
                      np.sinc((self.t_array - t_center) * self.flat_freq_Ghz) * \
                      np.exp(-1.0 * (self.t_array - t_center) ** 2 / (2 * gauss_sigma ** 2))

        pulse_array = pulse_array * np.cos(2 * np.pi * self.freq * (self.t_array - self.phase_t0) + self.phase)

        return pulse_array

    def get_length(self):
        return self.pulse_len

class adb_ramp(Pulse):
    def __init__(self, max_amp, flat_len, adb_ramp1_sig, ramp2_sigma_len, cutoff_sigma, freq, phase, phase_t0 = 0,
                 dt=None,
                 plot=False):
        self.max_amp = max_amp

        self.flat_len = flat_len
        self.ramp2_sigma_len = ramp2_sigma_len
        self.adb_ramp1_sig = adb_ramp1_sig
        self.cutoff_sigma = cutoff_sigma
        self.freq = freq
        self.phase = phase
        self.phase_t0 = phase_t0
        self.dt = dt
        self.plot = plot

        self.t0 = 0

    def get_pulse_array(self):
        """
        width of adb ramp is 4 sigma"""

        t_flat_start = self.t0 + self.adb_ramp1_sig * self.cutoff_sigma * 2 #error function is
        # 4sigma
        t_flat_end = self.t0 + self.adb_ramp1_sig * self.cutoff_sigma * 2  + self.flat_len

        t_end = self.t0 + self.adb_ramp1_sig * self.cutoff_sigma * 2  + self.flat_len + self.ramp2_sigma_len * self.cutoff_sigma

        pulse_array = self.max_amp * (
            (self.t_array >= t_flat_start) * (
                self.t_array < t_flat_end) +  # Normal square pulse

            (self.t_array >= self.t0) * (self.t_array < t_flat_start) * (
                    0.5 + 0.5 * scipy.special.erf(np.sqrt(2)/self.adb_ramp1_sig *
                                            (self.t_array - (self.t0+self.adb_ramp1_sig*self.cutoff_sigma))
                                            )) +  # leading erf edge

            (self.t_array >= t_flat_end) * (
                self.t_array <= t_end) * np.exp(
                -1.0 * (self.t_array - (t_flat_end)) ** 2 / (
                    2 * self.ramp2_sigma_len ** 2))  # trailing gaussian edge
        )

        pulse_array = pulse_array * np.cos(2 * np.pi * self.freq * (self.t_array - self.phase_t0) + self.phase)

        return pulse_array

    def get_length(self):
        return self.adb_ramp1_sig * self.cutoff_sigma * 2  + self.flat_len + self.ramp2_sigma_len * self.cutoff_sigma

class exp_ramp(Pulse):
    def __init__(self, max_amp, exp_ramp_len,flat_len,tau_ramp,ramp2_sigma_len,cutoff_sigma, freq, phase, phase_t0 = 0,dt=None,plot=False):
        self.max_amp = max_amp
        self.exp_ramp_len = exp_ramp_len
        self.flat_len = flat_len
        self.tau = tau_ramp
        self.fastfluxlength = flat_len
        self.ramp2_sigma_len = ramp2_sigma_len
        self.cutoff_sigma = cutoff_sigma
        self.freq = freq
        self.phase = phase
        self.phase_t0 = phase_t0
        self.dt = dt
        self.plot = plot
        self.t0 = 0

    def get_pulse_array(self):

        t_flat_start = self.t0 + self.exp_ramp_len

        t_flat_end = self.t0 + self.exp_ramp_len  + self.flat_len

        t_end = self.t0 + self.exp_ramp_len  + self.flat_len + self.ramp2_sigma_len * self.cutoff_sigma

        ## Exp Ramp Coefficients
        A = 1/(np.exp(-1*self.exp_ramp_len/self.tau)-1)
        B = -1*A

        pulse_array = \
            self.max_amp * (
                (self.t_array >= t_flat_start) * (
                self.t_array < t_flat_end) +  # Normal square pulse

                (self.t_array >= self.t0) * (self.t_array < t_flat_start) * (
                        A*np.exp(-1*(self.t_array-self.t0)/self.tau) + B) +  # leading Exp Edge

                (self.t_array >= t_flat_end) * (
                        self.t_array <= t_end) * np.exp(
            -1.0 * (self.t_array - (t_flat_end)) ** 2 / (
                    2 * self.ramp2_sigma_len ** 2))  # trailing gaussian edge
        )

        pulse_array = pulse_array * np.cos(2 * np.pi * self.freq * (self.t_array - self.phase_t0) + self.phase)

        return pulse_array

    def get_length(self):
        return self.exp_ramp_len  + self.flat_len + self.ramp2_sigma_len * self.cutoff_sigma

class exp_ramp_and_modulate(Pulse):
    def __init__(self, max_amp, exp_ramp_len,flat_len,tau_ramp,ramp2_sigma_len,cutoff_sigma,amp, freq, phase, phase_t0 = 0,dt=None,plot=False):
        self.max_amp = max_amp
        self.exp_ramp_len = exp_ramp_len
        self.flat_len = flat_len
        self.tau = tau_ramp
        self.fastfluxlength = flat_len
        self.ramp2_sigma_len = ramp2_sigma_len
        self.cutoff_sigma = cutoff_sigma
        self.amp = amp
        self.freq = freq
        self.phase = phase
        self.phase_t0 = phase_t0
        self.dt = dt
        self.plot = plot
        self.t0 = 0

    def get_pulse_array(self):

        t_flat_start = self.t0 + self.exp_ramp_len

        t_flat_end = self.t0 + self.exp_ramp_len  + self.flat_len

        t_end = self.t0 + self.exp_ramp_len  + self.flat_len + self.ramp2_sigma_len * self.cutoff_sigma

        ## Exp Ramp Coefficients
        A = 1/(np.exp(-1*self.exp_ramp_len/self.tau)-1)
        B = -1*A

        pulse_array = \
            self.max_amp * (
                (self.t_array >= t_flat_start) * (
                self.t_array < t_flat_end) +  # Normal square pulse

                (self.t_array >= self.t0) * (self.t_array < t_flat_start) * (
                        A*np.exp(-1*(self.t_array-self.t0)/self.tau) + B) +  # leading Exp Edge

                (self.t_array >= t_flat_end) * (
                        self.t_array <= t_end) * np.exp(
            -1.0 * (self.t_array - (t_flat_end)) ** 2 / (
                    2 * self.ramp2_sigma_len ** 2))  # trailing gaussian edge
        )

        pulselen = self.exp_ramp_len  + self.flat_len + self.ramp2_sigma_len * self.cutoff_sigma

        # Cutting pulse off before the end doesn't seem to work as expected?
        # pulse_array = pulse_array + np.heaviside(-1*(self.t_array - (self.t_array)[0] - pulselen + 30),0)*(self.amp * np.cos(2 * np.pi * self.freq * (self.t_array - self.phase_t0) + self.phase))
        # pulselen = 100
        ## Try exponential damping - also not working?
        # pulse_array = pulse_array + (1/(1+np.exp((self.t_array-pulselen/2)/(pulselen/4)))) * (self.amp * np.cos(2 * np.pi * self.freq * (self.t_array - self.phase_t0) + self.phase))
        pulse_array = pulse_array + ((self.t_array >=self.t0) * (self.t_array <= t_flat_start) ) * (self.amp * np.cos(2 * np.pi * self.freq * (self.t_array - self.phase_t0) + self.phase))

        return pulse_array

    def get_length(self):
        return self.exp_ramp_len  + self.flat_len + self.ramp2_sigma_len * self.cutoff_sigma

class multiexponential_ramp(Pulse):
    def __init__(self, max_amp, exp_ramp_len,flat_len,tau_ramp,ramp2_sigma_len,cutoff_sigma, freq, phase,multiples = 2, phase_t0 = 0,dt=None,plot=False):
        self.max_amp = max_amp
        self.exp_ramp_len = exp_ramp_len
        self.flat_len = flat_len
        self.tau = tau_ramp
        self.fastfluxlength = flat_len
        self.ramp2_sigma_len = ramp2_sigma_len
        self.cutoff_sigma = cutoff_sigma
        self.freq = freq
        self.phase = phase
        self.multiples = multiples # number of ramp away + ramp backs
        self.phase_t0 = phase_t0
        self.dt = dt
        self.plot = plot
        self.t0 = 0

    def get_pulse_array(self):

        ## use functions instead for repeat ramps

        def tempfun(t, ramplen, tau):
            A = 1 / (np.exp(-1 * ramplen / tau) - 1)
            B = -1 * A
            return A * np.exp(-t / tau) + B

        def tempfun2(tlist, ramplen, tau):
            return np.heaviside(tlist, 0) * np.heaviside(-1 * tlist + ramplen, tempfun(ramplen , ramplen,tau)/2) * tempfun(tlist, ramplen,tau) + \
                   np.heaviside(tlist - ramplen, tempfun(ramplen, ramplen, tau)/2) * np.heaviside(-1 * tlist + 2 * ramplen, 0) * (tempfun(-tlist + 2 * ramplen, ramplen, tau))

        def tempfun3(tlist, ramplen, tau, multiples):
            valholder = 0
            for ii in range(multiples):
                valholder += tempfun2(tlist - 2 * ii * ramplen, ramplen, tau)
            return valholder

        # t_flat_start = self.t0 + self.exp_ramp_len*2*self.multiples
        #
        # t_flat_end = self.t0 + self.exp_ramp_len*2*self.multiples  + self.flat_len
        #
        # t_end = self.t0 + self.exp_ramp_len*2*self.multiples  + self.flat_len + self.ramp2_sigma_len * self.cutoff_sigma

        ## Exp Ramp Coefficients
        A = 1/(np.exp(-1*self.exp_ramp_len/self.tau)-1)
        B = -1*A

        pulse_array = self.max_amp * tempfun3(np.array(self.t_array) - self.t0,self.exp_ramp_len,self.tau,self.multiples)

        pulse_array = pulse_array * np.cos(2 * np.pi * self.freq * (self.t_array - self.phase_t0) + self.phase)

        return pulse_array

    def get_length(self):
        return self.exp_ramp_len  + self.flat_len + self.ramp2_sigma_len * self.cutoff_sigma

class multiexponential_ramp_new(Pulse):
    def __init__(self, max_amp, exp_ramp_len,flat_len,tau_ramp,ramp2_sigma_len,cutoff_sigma, freq, phase,multiples = 2, phase_t0 = 0,dt=None,plot=False):
        self.max_amp = max_amp
        self.exp_ramp_len = exp_ramp_len
        self.flat_len = flat_len
        self.tau = tau_ramp
        self.fastfluxlength = flat_len
        self.ramp2_sigma_len = ramp2_sigma_len
        self.cutoff_sigma = cutoff_sigma
        self.freq = freq
        self.phase = phase
        self.multiples = multiples # number of ramp away + ramp backs
        self.phase_t0 = phase_t0
        self.dt = dt
        self.plot = plot
        self.t0 = 0

    def get_pulse_array(self):

        ## use functions instead for repeat ramps

        def tempfun(t, ramplen, tau):
            A = 1 / (np.exp(-1 * ramplen / tau) - 1)
            B = -1 * A
            return A * np.exp(-t / tau) + B

        def tempfun2(tlist, ramplen, tau):
            # return np.heaviside(tlist, 0) * np.heaviside(-1 * tlist + ramplen, tempfun(ramplen , ramplen,tau)/2) * tempfun(tlist, ramplen,tau) + \
            #        np.heaviside(tlist - ramplen, tempfun(ramplen, ramplen, tau)/2) * np.heaviside(-1 * tlist + 2 * ramplen, 0) * (tempfun(-tlist + 2 * ramplen, ramplen, tau))
            temparray = []
            for t in tlist:
                temp = 0
                if (np.heaviside(t, 0) * np.heaviside(-1 * t + ramplen, tempfun(ramplen , ramplen,tau)/4) != 0):
                    temp +=  tempfun(t, ramplen,tau)
                if (np.heaviside(t - ramplen, tempfun(ramplen, ramplen, tau)/2) * np.heaviside(-1 * t + 2 * ramplen, 0) != 0):
                    temp += tempfun(-t + 2 * ramplen, ramplen, tau)
                # else:

                temparray.append(temp)
            return temparray

        def tempfun3(tlist, ramplen, tau, multiples):
            valholder = 0
            for ii in range(multiples):
                valholder += np.asarray(tempfun2(tlist - 2 * ii * ramplen, ramplen, tau))
            return valholder

        # t_flat_start = self.t0 + self.exp_ramp_len*2*self.multiples
        #
        # t_flat_end = self.t0 + self.exp_ramp_len*2*self.multiples  + self.flat_len
        #
        # t_end = self.t0 + self.exp_ramp_len*2*self.multiples  + self.flat_len + self.ramp2_sigma_len * self.cutoff_sigma

        ## Exp Ramp Coefficients
        A = 1/(np.exp(-1*self.exp_ramp_len/self.tau)-1)
        B = -1*A

        pulse_array = self.max_amp * tempfun3(np.array(self.t_array) - self.t0,self.exp_ramp_len,self.tau,self.multiples)

        pulse_array = pulse_array * np.cos(2 * np.pi * self.freq * (self.t_array - self.phase_t0) + self.phase)

        return pulse_array

    def get_length(self):
        # return self.exp_ramp_len  + self.flat_len + self.ramp2_sigma_len * self.cutoff_sigma
        return self.exp_ramp_len*self.multiples + self.flat_len + self.ramp2_sigma_len * self.cutoff_sigma

class reversability_ramp(Pulse):
    def __init__(self, max_amp, exp_ramp_len,flat_len,tau_ramp,ramp2_sigma_len,cutoff_sigma, freq, phase,evolutiontime = 200, phase_t0 = 0,dt=None,plot=False):
        self.max_amp = max_amp
        self.exp_ramp_len = exp_ramp_len
        self.flat_len = flat_len
        self.tau = tau_ramp
        self.fastfluxlength = flat_len
        self.ramp2_sigma_len = ramp2_sigma_len
        self.cutoff_sigma = cutoff_sigma
        self.freq = freq
        self.phase = phase
        self.evolutiontime = evolutiontime
        self.phase_t0 = phase_t0
        self.dt = dt
        self.plot = plot
        self.t0 = 0

    def get_pulse_array(self):

        ## use functions instead for repeat ramps

        def tempfun(t, ramplen, tau):
            A = 1 / (np.exp(-1 * ramplen / tau) - 1)
            B = -1 * A
            return A * np.exp(-t / tau) + B

        def tempfunrev(tlist, evolutiontime, ramplen, tau):
            if evolutiontime == 0:
                return np.heaviside(tlist, 0) * np.heaviside(-1 * tlist + ramplen, 1/2) * tempfun(tlist, ramplen, tau) + \
               np.heaviside((tlist - ramplen), 1/2) * np.heaviside(-1 * (tlist - evolutiontime - ramplen), 0) + \
               np.heaviside((tlist - evolutiontime) - ramplen, 1/2) * np.heaviside(-1 * (tlist - evolutiontime) + 2 * ramplen, 0) * (tempfun(-(tlist - evolutiontime) + 2 * ramplen, ramplen, tau))
            else:
                return np.heaviside(tlist, 0) * np.heaviside(-1 * tlist + ramplen, 1/2) * tempfun(tlist, ramplen, tau) + \
               np.heaviside((tlist - ramplen), 1/2) * np.heaviside(-1 * (tlist - evolutiontime - ramplen), 1/2) + \
               np.heaviside((tlist - evolutiontime) - ramplen, 1/2) * np.heaviside(-1 * (tlist - evolutiontime) + 2 * ramplen, 0) * (tempfun(-(tlist - evolutiontime) + 2 * ramplen, ramplen, tau))

        ## Exp Ramp Coefficients
        A = 1/(np.exp(-1*self.exp_ramp_len/self.tau)-1)
        B = -1*A

        pulse_array = self.max_amp * tempfunrev(np.array(self.t_array) - self.t0,self.flat_len,self.exp_ramp_len,self.tau)

        pulse_array = pulse_array * np.cos(2 * np.pi * self.freq * (self.t_array - self.phase_t0) + self.phase)

        return pulse_array

    def get_length(self):
        return self.exp_ramp_len*2  + self.flat_len

class reversability_ramp_modulate(Pulse):
    def __init__(self, max_amp, exp_ramp_len,flat_len,tau_ramp,ramp2_sigma_len,cutoff_sigma, freq, phase,
                 evolutiontime = 200, phase_t0 = 0, modulate_freq = 0, modulate_amp = 0, modulate_phase = 0, dt=None,
                 plot=False):
        self.max_amp = max_amp
        self.exp_ramp_len = exp_ramp_len
        self.flat_len = flat_len
        self.tau = tau_ramp
        self.fastfluxlength = flat_len
        self.ramp2_sigma_len = ramp2_sigma_len
        self.cutoff_sigma = cutoff_sigma
        self.freq = freq
        self.phase = phase
        self.evolutiontime = evolutiontime
        self.phase_t0 = phase_t0
        self.dt = dt
        self.plot = plot
        self.t0 = 0

        self.modulate_freq = modulate_freq
        self.modulate_amp = modulate_amp
        self.modulate_phase = modulate_phase

    def get_pulse_array(self):

        ## use functions instead for repeat ramps

        def tempfun(t, ramplen, tau):
            A = 1 / (np.exp(-1 * ramplen / tau) - 1)
            B = -1 * A
            return A * np.exp(-t / tau) + B

        def tempfunrev(max_amp, tlist, evolutiontime, ramplen, tau, modulate_freq, modulate_amp, modulate_phase):
            if evolutiontime == 0:
                return max_amp * (np.heaviside(tlist, 0) * np.heaviside(-1 * tlist + ramplen, 1/2) * tempfun(
                    tlist, ramplen, tau) + \
               np.heaviside((tlist - ramplen), 1/2) * np.heaviside(-1 * (tlist - evolutiontime - ramplen), 0) + \
               np.heaviside((tlist - evolutiontime) - ramplen, 1/2) * np.heaviside(-1 * (tlist - evolutiontime) + 2 *
                                                                                   ramplen, 0) * (tempfun(-(tlist - evolutiontime) + 2 * ramplen, ramplen, tau)))

            else:
                return max_amp* (np.heaviside(tlist, 0) * np.heaviside(-1 * tlist + ramplen, 1/2) * tempfun(tlist,
                                                                                                          ramplen,
                                                                                                            tau)) + \
                       max_amp*(np.heaviside((tlist - ramplen), 1/2) * np.heaviside(-1 * (tlist - evolutiontime -
                                                                                          ramplen), 1/2)) + \
                       modulate_amp * np.cos(tlist*2*np.pi*modulate_freq + modulate_phase) * (np.heaviside((
                        tlist-ramplen), 1 / 2) * np.heaviside(-1 * (tlist - evolutiontime - ramplen), 1 / 2)) + \
                       max_amp * (np.heaviside((tlist - evolutiontime) - ramplen, 1/2) * np.heaviside(-1 * (
                        tlist-evolutiontime) + 2 * ramplen, 0) * (tempfun(-(tlist - evolutiontime) + 2 * ramplen,
                                                                          ramplen, tau)))

        ## Exp Ramp Coefficients
        A = 1/(np.exp(-1*self.exp_ramp_len/self.tau)-1)
        B = -1*A

        pulse_array = tempfunrev(self.max_amp, np.array(self.t_array) - self.t0,self.flat_len,
                                                self.exp_ramp_len,self.tau, self.modulate_freq, self.modulate_amp, self.modulate_phase)

        pulse_array = pulse_array * np.cos(2 * np.pi * self.freq * (self.t_array - self.phase_t0) + self.phase)

        return pulse_array

    def get_length(self):
        return self.exp_ramp_len*2  + self.flat_len

class exp_ramp_modulate(Pulse):
    def __init__(self, max_amp, exp_ramp_len,flat_len,tau_ramp,ramp2_sigma_len,cutoff_sigma, freq, phase,
                 evolutiontime = 200, phase_t0 = 0, modulate_freq = 0, modulate_amp = 0, modulate_phase = 0, dt=None,
                 plot=False):
        self.max_amp = max_amp
        self.exp_ramp_len = exp_ramp_len
        self.flat_len = flat_len
        self.tau = tau_ramp
        self.fastfluxlength = flat_len
        self.ramp2_sigma_len = ramp2_sigma_len
        self.cutoff_sigma = cutoff_sigma
        self.freq = 0 #freq
        self.phase = 0 #phase
        self.evolutiontime = evolutiontime
        self.phase_t0 = phase_t0
        self.dt = dt
        self.plot = plot
        self.t0 = 0

        self.modulate_freq = modulate_freq
        self.modulate_amp = modulate_amp
        self.modulate_phase = modulate_phase

    def get_pulse_array(self):

        t_flat_start = self.t0 + self.exp_ramp_len

        t_flat_end = self.t0 + self.exp_ramp_len + self.flat_len

        t_end = self.t0 + self.exp_ramp_len + self.flat_len + self.ramp2_sigma_len * self.cutoff_sigma

        ## Exp Ramp Coefficients
        A = 1 / (np.exp(-1 * self.exp_ramp_len / self.tau) - 1)
        B = -1 * A

        # previous implementions of the modulated exp ramp
        # pulse_array = \
        #     (self.max_amp + self.modulate_amp * np.cos(self.t_array*2*np.pi*self.modulate_freq + self.modulate_phase))* (
        #             (self.t_array >= t_flat_start) * (
        #             self.t_array < t_flat_end) +  # Normal square pulse
        #
        #             (self.t_array >= self.t0) * (self.t_array < t_flat_start) * (
        #                     A * np.exp(-1 * (self.t_array - self.t0) / self.tau) + B) +  # leading Exp Edge
        #
        #             (self.t_array >= t_flat_end) * (
        #                     self.t_array <= t_end) * np.exp(
        #         -1.0 * (self.t_array - (t_flat_end)) ** 2 / (
        #                 2 * self.ramp2_sigma_len ** 2))  # trailing gaussian edge
        #     )

        pulse_array = \
            (self.max_amp)* (
                    (self.t_array >= t_flat_start) * (
                    self.t_array < t_flat_end) +  # Normal square pulse

                    (self.t_array >= self.t0) * (self.t_array < t_flat_start) * (
                            A * np.exp(-1 * (self.t_array - self.t0) / self.tau) + B) +  # leading Exp Edge

                    (self.t_array >= t_flat_end) * (
                            self.t_array <= t_end) * np.exp(
                -1.0 * (self.t_array - (t_flat_end)) ** 2 / (
                        2 * self.ramp2_sigma_len ** 2))  # trailing gaussian edge
            ) + \
            (self.modulate_amp * np.cos(self.t_array * 2 * np.pi * self.modulate_freq + self.modulate_phase))* \
            (self.t_array >= t_flat_start) * (
                    self.t_array < t_flat_end)  # Normal square pulse

        pulse_array = pulse_array * np.cos(2 * np.pi * self.freq * (self.t_array - self.phase_t0) + self.phase)

        return pulse_array

    def get_length(self):
        return self.exp_ramp_len + self.flat_len + self.ramp2_sigma_len * self.cutoff_sigma

class linear_ramp(Pulse):
    def __init__(self, max_amp, flat_len, ramp1_len, ramp2_sigma_len, cutoff_sigma, freq, phase, phase_t0 = 0,
                 dt=None,
                 plot=False):
        self.max_amp = max_amp
        self.flat_len = flat_len
        self.ramp2_sigma_len = ramp2_sigma_len
        self.ramp1_len = ramp1_len
        self.cutoff_sigma = cutoff_sigma
        self.freq = freq
        self.phase = phase
        self.phase_t0 = phase_t0
        self.dt = dt
        self.plot = plot

        self.t0 = 0

    def get_pulse_array(self):
        t_flat_start = self.t0 + self.ramp1_len

        t_flat_end = self.t0 + self.ramp1_len  + self.flat_len

        t_end = self.t0 + self.ramp1_len  + self.flat_len + self.ramp2_sigma_len * self.cutoff_sigma

        pulse_array = (self.max_amp * (
            (self.t_array >= t_flat_start) * (
                self.t_array < t_flat_end)) +  # Normal square pulse

            (self.t_array >= self.t0) * (self.t_array < t_flat_start) * (
                    self.max_amp/self.ramp1_len * (self.t_array-self.t0)) +  # leading linear edge

            (self.t_array >= t_flat_end) *self.max_amp* (
                self.t_array <= t_end) * np.exp(
                -1.0 * (self.t_array - (t_flat_end)) ** 2 / (
                    2 * self.ramp2_sigma_len ** 2)))  # trailing gaussian edge


        pulse_array = pulse_array * np.cos(2 * np.pi * self.freq * (self.t_array - self.phase_t0) + self.phase)

        return pulse_array

    def get_length(self):
        return self.ramp1_len  + self.flat_len + self.ramp2_sigma_len * self.cutoff_sigma

class WURST20_I(Pulse):
    def __init__(self, max_amp,bandwidth,t_length,freq,phase =0 ,phase_t0 = 0,dt=None,plot=False):
        self.max_amp = max_amp
        self.bandwidth = bandwidth
        self.t_length = t_length
        self.freq = freq
        self.phase = phase
        self.phase_t0 = phase_t0
        self.dt = dt
        self.plot = plot
        self.t0 = 0

    def get_pulse_array(self):

        def phi(t):
            return (-1 * (self.bandwidth*2*np.pi / 2) + self.freq *2*np.pi) * t + (self.bandwidth*2*np.pi * t ** 2) / (2 * self.t_length)
        def Amp(t):
            return 1-np.abs(np.sin(np.pi*((t-self.t_length/2)/self.t_length)))**20

        pulse_array = self.max_amp * Amp(np.array(self.t_array) - self.t0)*np.sin(phi(np.array(self.t_array) - self.t0))

        return pulse_array

    def get_length(self):
        return self.t_length

class WURST20_Q(Pulse):
    def __init__(self, max_amp, bandwidth, t_length, freq, phase=0, phase_t0=0, dt=None, plot=False):
        self.max_amp = max_amp
        self.bandwidth = bandwidth
        self.t_length = t_length
        self.freq = freq
        self.phase = phase
        self.phase_t0 = phase_t0
        self.dt = dt
        self.plot = plot
        self.t0 = 0

    def get_pulse_array(self):
        def phi(t):
            return (-1 * (self.bandwidth*2*np.pi / 2) + self.freq *2*np.pi) * t + (self.bandwidth*2*np.pi * t ** 2) / (2 * self.t_length)
        def Amp(t):
            return 1-np.abs(np.sin(np.pi*((t-self.t_length/2)/self.t_length)))**20

        pulse_array = self.max_amp * Amp(np.array(self.t_array) - self.t0) * np.cos(phi(np.array(self.t_array) - self.t0) + self.phase_t0)

        return pulse_array

    def get_length(self):
        return self.t_length

class WURST20_I_X(Pulse):
    def __init__(self, max_amp,bandwidth,t_length,freq,phase =0 ,phase_t0 = 0,dt=None,plot=False):
        self.max_amp = max_amp
        self.bandwidth = bandwidth
        self.t_length = t_length
        self.freq = freq
        self.phase = phase
        self.phase_t0 = phase_t0
        self.dt = dt
        self.plot = plot
        self.t0 = 0

    def get_pulse_array(self):

        def phi(t):
            return (-1 * (self.bandwidth * 2 * np.pi / 2) + self.freq * 2 * np.pi) * t + (self.bandwidth * 2 * np.pi * t ** 2) / (2 * self.t_length)
        def Amp(t):
            doubler = 2*self.t_length
            return (1-np.abs(np.sin(np.pi*((t-doubler/2)/doubler)))**20) * np.heaviside(self.t_length/2-t,0)


        pulse_array = self.max_amp * Amp(np.array(self.t_array) - self.t0)*np.sin(phi(np.array(self.t_array) - self.t0))

        return pulse_array

    def get_length(self):
        return self.t_length

class WURST20_Q_X(Pulse):
    def __init__(self, max_amp, bandwidth, t_length, freq, phase=0, phase_t0=0, dt=None, plot=False):
        self.max_amp = max_amp
        self.bandwidth = bandwidth
        self.t_length = t_length
        self.freq = freq
        self.phase = phase
        self.phase_t0 = phase_t0
        self.dt = dt
        self.plot = plot
        self.t0 = 0

    def get_pulse_array(self):

        def phi(t):
            return (-1 * (self.bandwidth * 2 * np.pi / 2) + self.freq * 2 * np.pi) * t + (self.bandwidth * 2 * np.pi * t ** 2) / (2 * self.t_length)

        def Amp(t):
            doubler = 2 * self.t_length
            return (1 - np.abs(np.sin(np.pi * ((t - doubler / 2) / doubler))) ** 20) * np.heaviside(self.t_length / 2 - t, 0)


        pulse_array = self.max_amp * Amp(np.array(self.t_array) - self.t0) * np.cos(phi(np.array(self.t_array) - self.t0) + self.phase_t0)

        return pulse_array

    def get_length(self):
        return self.t_length

class BIR_4(Pulse):
    def __init__(self, max_amp, bandwidth, t_length, freq,theta, phase=0, phase_t0=0, dt=None, plot=False):
        self.max_amp = max_amp
        self.bandwidth = bandwidth
        self.t_length = t_length
        self.freq = freq
        self.phase = phase
        self.phase_t0 = phase_t0
        self.theta = theta * (np.pi/180)
        self.dt = dt
        self.plot = plot
        self.t0 = 0
        self.freq_max = self.bandwidth/2
        self.beta = 6

    def get_pulse_array(self):
        def phi(t):
            # Graff et. al.
            def tempphi(t):
                return (np.pi*self.freq_max*self.t_length/(2*self.beta)) * np.log(np.cosh(4*self.beta*t/self.t_length))
            return tempphi(t)*np.heaviside(self.t_length/4-t,0) + \
                   (tempphi(self.t_length/2-t) + np.pi + self.theta/2)* np.heaviside(t-1*self.t_length / 4, 1)* np.heaviside(2*self.t_length / 4 - t, 0) + \
                   (tempphi(t-(self.t_length/2)) + np.pi + self.theta/2)* np.heaviside(t-2*self.t_length / 4, 1)* np.heaviside(3*self.t_length / 4 - t, 0) + \
                   tempphi(self.t_length - t)* np.heaviside(t-3*self.t_length / 4, 1)* np.heaviside(4*self.t_length / 4 - t, 0) + 2*np.pi * self.freq * t

        def Amp(t):
            def tempamp(t):
                return np.cosh(self.beta*(4*(t/self.t_length)))**-1
            return tempamp(t)*np.heaviside(self.t_length/4 - t,0) + \
                   tempamp(self.t_length/2-t) * np.heaviside(t-1*self.t_length / 4, 1)* np.heaviside(2*self.t_length / 4 - t, 0) + \
                   tempamp(t-(self.t_length/2))* np.heaviside(t-2*self.t_length / 4, 1)* np.heaviside(3*self.t_length / 4 - t, 0) + \
                   tempamp(self.t_length - t)* np.heaviside(t-3*self.t_length / 4, 1)* np.heaviside(4*self.t_length / 4 - t, 0)


        pulse_array = self.max_amp * Amp(np.array(self.t_array) - self.t0) * np.cos(phi(np.array(self.t_array) - self.t0) + self.phase_t0)

        return pulse_array

    def get_length(self):
        return self.t_length

class BIR_4_hyp(Pulse):
    def __init__(self, max_amp, bandwidth, t_length, freq,theta, phase=0, phase_t0=0,kappa = np.arctan(0.25),beta = 0.25, dt=None, plot=False):
        self.max_amp = max_amp
        self.bandwidth = bandwidth
        self.t_length = t_length
        self.freq = freq
        self.phase = phase
        self.phase_t0 = phase_t0
        self.theta = theta
        self.dt = dt
        self.plot = plot
        self.t0 = 0
        self.freq_max = self.bandwidth/2
        self.kappa = kappa
        self.beta = beta

    def get_pulse_array(self):
        self.freq_max = self.bandwidth / 2

        def tau(t):
            return t / (self.t_length / 4)

        def freq(t):
            return 2*np.pi*self.freq_max*(np.tan(self.kappa * tau(t)) / np.tan(self.kappa) * np.heaviside(-tau(t) + 1,0) + \
                   np.tan(self.kappa * (tau(t) - 2)) / np.tan(self.kappa) * np.heaviside(
                -tau(t) + 2, 0) * np.heaviside(tau(t) - 1, 0) + \
                   np.tan(self.kappa * (tau(t) - 2)) / np.tan(self.kappa) * np.heaviside(
                -tau(t) + 3, 0) * np.heaviside(tau(t) - 2, 0) + \
                   np.tan(self.kappa * (tau(t) - 4)) / np.tan(self.kappa) * np.heaviside(
                -tau(t) + 4, 0) * np.heaviside(tau(t) - 3, 0))

        deltaphi1 = (np.pi / 180) * (180 + self.theta / 2)
        deltaphi2 = -1 * deltaphi1
        def phi(t):
            return np.cumsum(freq(t)) + \
                   deltaphi1 * np.heaviside(t - self.t_length / 4, 0) + deltaphi2 * np.heaviside(t - 3 * self.t_length / 4,0) + \
                   0  +  2*np.pi * self.freq * t
        def Amp(t):
            return np.tanh(self.beta * (1 - tau(t))) * np.heaviside(-tau(t) + 1, 0) + \
                   np.tanh(self.beta * (tau(t) - 1)) * np.heaviside(tau(t) - 1, 0) * np.heaviside(
                -tau(t) + 2, 0) + \
                   np.tanh(self.beta * (3 - tau(t))) * np.heaviside(tau(t) - 2, 1) * np.heaviside(
                -tau(t) + 3, 0) + \
                   np.tanh(self.beta * (tau(t) - 3)) * np.heaviside(tau(t) - 3, 0) * np.heaviside(
                -tau(t) + 4, 0)


        pulse_array = self.max_amp * Amp(np.array(self.t_array) - self.t0) * np.cos(phi(np.array(self.t_array) - self.t0) + self.phase_t0)
        return pulse_array

    def get_length(self):
        return self.t_length

## 22/1/05 - not currently working
class BIR_4_wurst(Pulse):
    def __init__(self, max_amp, bandwidth, t_length, freq, phase=0, phase_t0=0, dt=None, plot=False):
        self.max_amp = max_amp
        self.bandwidth = bandwidth
        self.t_length = t_length
        self.freq = freq
        self.phase = phase
        self.phase_t0 = phase_t0
        self.dt = dt
        self.plot = plot
        self.t0 = 0
        self.freq_max = self.bandwidth/2
        self.deltaphi = 180 * (np.pi/180)
        self.beta = 3

    def get_pulse_array(self):
        # wurst
        def freq(t):
            return ( 0 + self.bandwidth * 2 * np.pi * t / (2*self.t_length/4) + self.freq * 2 * np.pi ) * np.heaviside(t-0,0) + \
            ( - self.bandwidth * 2 * np.pi )*np.heaviside(1 * self.t_length/4 - t,0) + \
            (- self.bandwidth * 2 * np.pi) * np.heaviside(3 * self.t_length / 4 - t,0)

        def phi(t):
            return (1/self.t_length)*np.cumsum(freq(t)) + \
                   (np.pi + self.deltaphi/2) * np.heaviside(1*self.t_length / 4 - t,0) + \
                   (- np.pi - self.deltaphi/2) * np.heaviside(3*self.t_length / 4-t,0)

        # 1 - np.abs(np.sin(np.pi * ((t - self.t_length / 2) / self.t_length))) ** 20
        def Amp(t):
            return  (1-np.abs(np.sin(np.pi*((t-self.t0 + self.t_length/4)/(self.t_length/2))))**20)*np.heaviside((1*self.t_length/4) - t,0)  + \
                    (1-np.abs(np.sin(np.pi*((t-self.t0 - self.t_length/4)/(self.t_length/2))))**20)*np.heaviside(t-(1*self.t_length/4),0)*np.heaviside((3*self.t_length/4) - t,0) + \
                    (1-np.abs(np.sin(np.pi*((t-self.t0 - 3*self.t_length/4)/(self.t_length/2))))**20)*np.heaviside(t-(3*self.t_length/4),0)*np.heaviside((4*self.t_length/4) - t,0)

        pulse_array = self.max_amp * Amp(np.array(self.t_array) - self.t0) * np.cos(phi(np.array(self.t_array) - self.t0) + self.phase_t0)

        return pulse_array

    def get_length(self):
        return self.t_length

class Square_two_tone(Pulse):
    def __init__(self, max_amp, flat_len, ramp_sigma_len, cutoff_sigma, freq1, freq2, phase1 = 0, phase2 = 0, phase_t0 = 0, dt=None, plot=False):
        self.max_amp = max_amp
        self.flat_len = flat_len
        self.ramp_sigma_len = ramp_sigma_len
        self.cutoff_sigma = cutoff_sigma
        self.freq1 = freq1
        self.freq2 = freq2
        self.phase1 = phase1
        self.phase2 = phase2
        self.phase_t0 = phase_t0
        self.dt = dt
        self.plot = plot
        self.t0 = 0

    def get_pulse_array(self):

        t_flat_start = self.t0 + self.cutoff_sigma * self.ramp_sigma_len
        t_flat_end = self.t0 + self.cutoff_sigma * self.ramp_sigma_len + self.flat_len

        t_end = self.t0 + 2 * self.cutoff_sigma * self.ramp_sigma_len + self.flat_len

        pulse_array = self.max_amp * (
            (self.t_array >= t_flat_start) * (
                self.t_array < t_flat_end) +  # Normal square pulse
            (self.t_array >= self.t0) * (self.t_array < t_flat_start) * np.exp(
                -1.0 * (self.t_array - (t_flat_start)) ** 2 / (
                    2 * self.ramp_sigma_len ** 2)) +  # leading gaussian edge
            (self.t_array >= t_flat_end) * (
                self.t_array <= t_end) * np.exp(
                -1.0 * (self.t_array - (t_flat_end)) ** 2 / (
                    2 * self.ramp_sigma_len ** 2))  # trailing edge
        )

        pulse_array = pulse_array * (np.cos(2 * np.pi * self.freq1 * (self.t_array - self.phase_t0) + self.phase1) + np.cos(2 * np.pi * self.freq2*(self.t_array - self.phase_t0) + self.phase2))/2.0

        return pulse_array

    def get_length(self):
        return self.flat_len + 2 * self.cutoff_sigma * self.ramp_sigma_len


class DRAG(Pulse):
    def __init__(self, A, beta, sigma_len, cutoff_sigma, freq, phase, dt=None, plot=False):
        self.A = A
        self.beta = beta
        self.sigma_len = sigma_len
        self.cutoff_sigma = cutoff_sigma
        self.freq = freq
        self.phase = phase
        self.dt = dt
        self.plot = plot

        self.t0 = 0

    def get_pulse_array(self):

        t_center = self.t0 + 2 * self.sigma_len

        pulse_array_x = self.A * np.exp(
            -1.0 * (self.t_array - t_center) ** 2 / (2 * self.sigma_len ** 2))
        pulse_array_y = self.beta * (-(self.t_array - t_center) / (self.sigma_len ** 2)) * self.A * np.exp(
            -1.0 * (self.t_array - t_center) ** 2 / (2 * self.sigma_len ** 2))

        pulse_array = pulse_array_x * np.cos(2 * np.pi * self.freq * self.t_array + self.phase) + \
                      - pulse_array_y * np.sin(2 * np.pi * self.freq * self.t_array + self.phase)

        return pulse_array

    def get_length(self):
        return 2 * self.cutoff_sigma * self.sigma_len


class ARB(Pulse):
    def __init__(self, A_list, B_list, len, freq, phase, dt=None, plot=False):
        self.A_list = np.pad(A_list, (1, 1), 'constant', constant_values=(0, 0))
        self.B_list = np.pad(B_list, (1, 1), 'constant', constant_values=(0, 0))
        self.len = len
        self.freq = freq
        self.phase = phase
        self.dt = dt
        self.plot = plot

        self.t0 = 0

    def get_pulse_array(self):
        t_array_A_list = np.linspace(self.t_array[0], self.t_array[-1], num=len(self.A_list))
        t_array_B_list = np.linspace(self.t_array[0], self.t_array[-1], num=len(self.B_list))

        tck_A = interpolate.splrep(t_array_A_list, self.A_list)
        tck_B = interpolate.splrep(t_array_B_list, self.B_list)

        pulse_array_x = interpolate.splev(self.t_array, tck_A, der=0)
        pulse_array_y = interpolate.splev(self.t_array, tck_B, der=0)

        pulse_array = pulse_array_x * np.cos(2 * np.pi * self.freq * self.t_array + self.phase) + \
                      - pulse_array_y * np.sin(2 * np.pi * self.freq * self.t_array + self.phase)

        return pulse_array

    def get_length(self):
        return self.len


class ARB_freq_a(Pulse):
    def __init__(self, A_list, B_list, len, freq_a_fit, phase, delta_freq = 0, dt=None, plot=False):
        self.A_list = A_list
        self.B_list = B_list
        self.len = len
        self.freq_a_fit = freq_a_fit
        self.phase = phase
        self.delta_freq = delta_freq
        self.dt = dt
        self.plot = plot

        self.t0 = 0

    def get_pulse_array(self):
        t_array_A_list = np.linspace(self.t_array[0], self.t_array[-1], num=len(self.A_list))
        t_array_B_list = np.linspace(self.t_array[0], self.t_array[-1], num=len(self.B_list))

        # # spline
        # tck_A = interpolate.splrep(t_array_A_list, self.A_list)
        # tck_B = interpolate.splrep(t_array_B_list, self.B_list)
        #
        # pulse_array_x = interpolate.splev(self.t_array, tck_A, der=0)
        # pulse_array_y = interpolate.splev(self.t_array, tck_B, der=0)

        # linear interpolation
        pulse_array_x = np.interp(self.t_array,t_array_A_list,self.A_list)
        pulse_array_y = np.interp(self.t_array,t_array_B_list,self.B_list)

        freq_array_x = self.freq_a_fit(pulse_array_x) + self.delta_freq
        freq_array_y = self.freq_a_fit(pulse_array_y) + self.delta_freq

        # print(freq_array_x)
        # print(freq_array_y)
        # print(self.dt)

        phase_array_x = 2*np.pi*np.cumsum(freq_array_x*self.dt) + self.phase
        phase_array_y = 2*np.pi*np.cumsum(freq_array_y*self.dt) + self.phase

        pulse_array = pulse_array_x * np.cos(phase_array_x) + \
                      - pulse_array_y * np.sin(phase_array_y)

        return pulse_array

    def get_length(self):
        return self.len


class Ones(Pulse):
    def __init__(self, time, dt=None, plot=False):
        self.time = time
        self.dt = dt
        self.plot = plot

        self.t0 = 0

    def get_pulse_array(self):
        pulse_array = np.ones_like(self.t_array)

        return pulse_array

    def get_length(self):
        return self.time


class Idle(Pulse):
    def __init__(self, time, dt=None, plot=False):
        self.time = time
        self.dt = dt
        self.plot = plot

        self.t0 = 0

    def get_pulse_array(self):
        pulse_array = np.zeros_like(self.t_array)

        return pulse_array

    def get_length(self):
        return self.time



if __name__ == "__main__":
    vis = visdom.Visdom()
    vis.close()

    gauss = Gauss(max_amp=0.1, sigma_len=2, cutoff_sigma=2, freq=1, phase=0, dt=0.1, plot=True)
    gauss.generate_pulse_array()
    gauss = Gauss(max_amp=0.1, sigma_len=2, cutoff_sigma=2, freq=1, phase=np.pi / 2, dt=0.1, plot=True)
    gauss.generate_pulse_array()

    # test_pulse = Pulse(np.arange(0,10),0.1)