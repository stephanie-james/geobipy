
import numpy as np
from ...classes.core import StatArray
from scipy.stats import (multivariate_normal, norm)
from scipy.special import beta
import matplotlib.pyplot as plt
from .Mixture import Mixture
from sklearn.mixture import GaussianMixture
from lmfit.models import Pearson7Model

class mixPearson(Mixture):

    def __init__(self, amplitudes=None, means=None, sigmas=None, exponents=None):

        if np.all([means, sigmas, exponents] is None):
            return

        self.params = np.zeros(self.n_solvable_parameters * np.size(means))


        self.means = means
        self.sigmas = sigmas
        self.exponents = exponents
        self.amplitudes = amplitudes


    @property
    def amplitudes(self):
        return self._params[0::self.n_solvable_parameters]


    @amplitudes.setter
    def amplitudes(self, values):
        assert np.size(values) == self.n_components, ValueError("Must provide {} amplitudes".format(self.n_components))
        self._params[0::self.n_solvable_parameters] = values


    @property
    def means(self):
        return self._params[1::self.n_solvable_parameters]


    @means.setter
    def means(self, values):
        assert np.size(values) == self.n_components, ValueError("Must provide {} means".format(self.n_components))
        self._params[1::self.n_solvable_parameters] = values


    @property
    def moments(self):
        return [self.means, self.variances]


    @property
    def sigmas(self):
        return self._params[2::self.n_solvable_parameters]


    @property
    def variances(self):
        return StatArray.StatArray(self.sigmas**2.0, 'Variance')


    @sigmas.setter
    def sigmas(self, values):
        assert np.size(values) == self.n_components, ValueError("Must provide {} sigmas".format(self.n_components))
        self._params[2::self.n_solvable_parameters] = values


    @property
    def exponents(self):
        return self._params[3::self.n_solvable_parameters]


    @exponents.setter
    def exponents(self, values):
        assert np.size(values) == self.n_components, ValueError("Must provide {} exponents".format(self.n_components))
        self._params[3::self.n_solvable_parameters] = values


    @property
    def model(self):
        return Pearson7Model


    @property
    def mixture_model_class(self):
        return GaussianMixture

    @property
    def n_solvable_parameters(self):
        return 4

    @property
    def n_components(self):
        return self.means.size


    def fit_to_curve(self, *args, **kwargs):
        fit, pars = super().fit_to_curve(*args, **kwargs)
        self.params = np.asarray(list(fit.best_values.values()))
        return self


    def plot_components(self, x, log, ax=None, **kwargs):

        if not ax is None:
            plt.sca(ax)

        probability = self.amplitudes * self.probability(x, log)

        p = probability.plot(x=x, **kwargs)

        return p


    def probability(self, x, log, component=None):

        if component is None:
            out = StatArray.StatArray(np.empty([np.size(x), self.n_components]), "Probability Density")
            for i in range(self.n_components):
                out[:, i] = self.amplitudes[i] * self._probability(x, log, self.means[i], self.variances[i], self.exponents[i])
            return out
        else:
            return self.amplitudes[component] * self._probability(x, log, self.means[component], self.variances[component], self.exponents[component])


    def _probability(self, x, log, mean, sigma, exponent):
        """ For a realization x, compute the probability """

        p = (1.0 / (sigma * beta(exponent - 0.5, 0.5))) * (1 + ((x - mean)**2.0)/(sigma**2.0))**-exponent

        if log:
            return StatArray.StatArray(np.log(p), "Probability Density")
        else:
            return StatArray.StatArray(p, "Probability Density")




