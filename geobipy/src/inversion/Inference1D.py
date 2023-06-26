""" @Inference1D
Class to store inversion results. Contains plotting and writing to file procedures
"""
from copy import deepcopy
from os.path import join

from numpy import argwhere, asarray, reshape, size, int64, sum, linspace, float64, int32
from numpy import arange, inf, isclose, mod, s_, maximum, any, isnan, sort, nan
from numpy import max, min, log, array, full, longdouble

from numpy.random import RandomState
from numpy.linalg import norm

import matplotlib.pyplot as plt
from matplotlib.pyplot import Figure

from ..base import plotting as cP
from ..base import utilities as cF

import h5py
from ..classes.core import StatArray
from ..classes.statistics.Distribution import Distribution
from ..classes.statistics.Histogram import Histogram
from ..classes.core.myObject import myObject
from ..classes.data.datapoint.DataPoint import DataPoint
# from ..classes.data.datapoint.FdemDataPoint import FdemDataPoint
# from ..classes.data.datapoint.TdemDataPoint import TdemDataPoint
from ..classes.mesh.RectilinearMesh1D import RectilinearMesh1D
from ..classes.model.Model import Model
from ..classes.core.Stopwatch import Stopwatch
from ..base.HDF import hdfRead
from cached_property import cached_property

class Inference1D(myObject):
    """Define the results for the Bayesian MCMC Inversion.

    Contains histograms and inversion related variables that can be updated as the Bayesian inversion progresses.

    Inference1D(saveMe, plotMe, savePNG, dataPoint, model, ID, \*\*kwargs)

    Parameters
    ----------
    saveMe : bool, optional
        Whether to save the results to HDF5 files.
    plotMe : bool, optional
        Whether to plot the results on the fly. Only use this in serial mode.
    savePNG : bool, optional
        Whether to save a png of each single data point results. Don't do this in parallel please.
    dataPoint : geobipy.dataPoint
        Datapoint to use in the inversion.
        The relative error prior must have been set with dataPoint.relative_error.set_prior()
        The additive error prior must have been set with dataPoint.additive_error.set_prior()
        The height prior must have been set with dataPoint.z.set_prior()
    model : geobipy.model
        Model representing the subsurface.
    ID : int, optional

    OtherParameters
    ---------------
    nMarkovChains : int, optional
        Number of markov chains that will be tested.
    plotEvery : int, optional
        When plotMe = True, update the plot when plotEvery iterations have progressed.
    parameterDisplayLimits : sequence of ints, optional
        Limits of the parameter axis in the hitmap plot.
    reciprocateParameters : bool, optional
        Take the reciprocal of the parameters when plotting the hitmap.
    reciprocateName : str, optional
        Name of the parameters if they are reciprocated.
    reciprocateUnits : str, optional
        Units of the parameters if they are reciprocated.

    """

    def __init__(self,
                 ignore_likelihood:bool = False,
                 interactive_plot:bool = True,
                 multiplier:float = 1.0,
                 n_markov_chains = 100000,
                 parameter_limits = None,
                 prng=None,
                 reciprocate_parameters:bool = False,
                 save_hdf5:bool = True,
                 save_png:bool = False,
                 solve_gradient:bool = True,
                 solve_parameter:bool = False,
                 update_plot_every = 5000,
                 world=None,
                 **kwargs):
        """ Initialize the results of the inversion """

        self.fig = None

        self.world = world

        self.prng = prng
        kwargs['prng'] = self.prng

        self.ignore_likelihood = ignore_likelihood
        self.n_markov_chains = n_markov_chains
        self.solve_gradient = solve_gradient
        self.solve_parameter = solve_parameter
        self.save_hdf5 = save_hdf5
        self.interactive_plot = interactive_plot
        self.save_png = save_png
        self.update_plot_every = update_plot_every
        self.limits = parameter_limits
        self.reciprocate_parameter = reciprocate_parameters

        assert self.interactive_plot or self.save_hdf5, Exception('You have chosen to neither view or save the inversion results!')

    @property
    def datapoint(self):
        return self._datapoint

    @datapoint.setter
    def datapoint(self, value):
        assert isinstance(value, DataPoint), TypeError("datapoint must have type geobipy.Datapoint")
        self._datapoint = value

    @cached_property
    def iz(self):
        return arange(self.model.values.posterior.y.nCells.item())

    @property
    def ignore_likelihood(self):
        return self._ignore_likelihood

    @ignore_likelihood.setter
    def ignore_likelihood(self, value:bool):
        assert isinstance(value, bool), ValueError('ignore_likelihood must have type bool')
        self._ignore_likelihood = value

    @property
    def interactive_plot(self):
        return self._interactive_plot

    @interactive_plot.setter
    def interactive_plot(self, value:bool):
        assert isinstance(value, bool), ValueError('interactive_plot must have type bool')
        if self.mpi_enabled:
            value = False
        self._interactive_plot = value

    @property
    def limits(self):
        return self._limits

    @limits.setter
    def limits(self, values):
        self._limits = None
        if values is not None:
            assert size(values) == 2, ValueError("Limits must have length 2")
            self._limits = sort(asarray(values, dtype=float64))

    @property
    def model(self):
        return self._model

    @model.setter
    def model(self, value):
        assert isinstance(value, Model), TypeError("model must have type geobipy.Model")
        self._model = value

    @property
    def mpi_enabled(self):
        return not (self.world is None)

    @property
    def multiplier(self):
        return self._multiplier

    @multiplier.setter
    def multiplier(self, value):
        self._multiplier = float64(value)

    @property
    def n_markov_chains(self):
        return self._n_markov_chains

    @n_markov_chains.setter
    def n_markov_chains(self, value):
        self._n_markov_chains = int64(value)

    @property
    def prng(self):
        return self._prng

    @prng.setter
    def prng(self, value):
        if value is None:
            assert not self.mpi_enabled, TypeError("Must specify a prng when running in parallel")
            self._prng = RandomState()
        else:
            self._prng = value

        self.seed = self.prng.get_state()

    @property
    def rank(self):
        if self.mpi_enabled:
            return self.world.rank
        else:
            return 1

    @property
    def reciprocate_parameters(self):
        return self._reciprocate_parameters

    @reciprocate_parameters.setter
    def reciprocate_parameters(self, value:bool):
        assert isinstance(value, bool), ValueError('reciprocate_parameters must have type bool')
        self._reciprocate_parameters = value

    @property
    def save_hdf5(self):
        return self._save_hdf5

    @save_hdf5.setter
    def save_hdf5(self, value:bool):
        assert isinstance(value, bool), ValueError('save_hdf5 must have type bool')
        self._save_hdf5 = value

    @property
    def save_png(self):
        return self._save_png

    @save_png.setter
    def save_png(self, value:bool):
        assert isinstance(value, bool), ValueError('save_png must have type bool')
        if self.mpi_enabled:
            value = False
        self._save_png = value

    @property
    def solve_parameter(self):
        return self._solve_parameter

    @solve_parameter.setter
    def solve_parameter(self, value:bool):
        assert isinstance(value, bool), ValueError('solve_parameter must have type bool')
        self._solve_parameter = value

    @property
    def solve_gradient(self):
        return self._solve_gradient

    @solve_gradient.setter
    def solve_gradient(self, value:bool):
        assert isinstance(value, bool), ValueError('solve_gradient must have type bool')
        self._solve_gradient = value

    @property
    def update_plot_every(self):
        return self._update_plot_every

    @update_plot_every.setter
    def update_plot_every(self, value):
        self._update_plot_every = int32(value)

    @property
    def world(self):
        return self._world

    @world.setter
    def world(self, value):
        self._world = value


    def initialize(self, datapoint, **kwargs):
        # Get the initial best fitting halfspace and set up
        # priors and posteriors using user parameters
        # ------------------------------------------------
        # Intialize the datapoint with the user parameters
        # ------------------------------------------------
        self.initialize_datapoint(datapoint, **kwargs)

        # # Initialize the calibration parameters
        # if (kwargs.solveCalibration):
        #     datapoint.calibration.set_prior('Normal',
        #                            reshape(kwargs.calMean, size(kwargs.calMean), order='F'),
        #                            reshape(kwargs.calVar, size(kwargs.calVar), order='F'), prng=prng)
        #     datapoint.calibration[:] = datapoint.calibration.prior.mean
        #     # Initialize the calibration proposal
        #     datapoint.calibration.setProposal('Normal', datapoint.calibration, reshape(kwargs.propCal, size(kwargs.propCal), order='F'), prng=prng)

        # ---------------------------------
        # Set the earth model properties
        # ---------------------------------
        self.initialize_model(**kwargs)

        # Compute the data misfit
        self.data_misfit = datapoint.dataMisfit()

        # # Calibrate the response if it is being solved for
        # if (self.kwargs.solveCalibration):
        #     self.datapoint.calibrate()

        # Evaluate the prior for the current model
        self.prior = self.model.probability(self.solve_parameter,
                                            self.solve_gradient)

        self.prior += self.datapoint.probability

        # Initialize the burned in state
        self.burned_in_iteration = self.n_markov_chains
        self.burned_in = True

        # Add the likelihood function to the prior
        self.likelihood = 1.0
        if not self.ignore_likelihood:
            self.likelihood = self.datapoint.likelihood(log=True)
            self.burned_in = False
            self.burned_in_iteration = int64(0)

        self.posterior = self.likelihood + self.prior

        # Initialize the current iteration number
        # Current iteration number
        self.iteration = int64(0)

        # Initialize the vectors to save results
        # StatArray of the data misfit

        self.data_misfit_v = StatArray.StatArray(2 * self.n_markov_chains, name='Data Misfit')
        self.data_misfit_v[0] = self.data_misfit

        target = sum(self.datapoint.active)
        self._n_target_hits = 0

        self.data_misfit_v.prior = Distribution('chi2', df=target)

        self.relative_chi_squared_fit = 100.0

        edges = StatArray.StatArray(linspace(1, 2*target))
        self.data_misfit_v.posterior = Histogram(mesh = RectilinearMesh1D(edges=edges))

        # Initialize a stopwatch to keep track of time
        self.clk = Stopwatch()
        self.invTime = float64(0.0)

        # Return none if important parameters are not used (used for hdf 5)
        if datapoint is None:
            return

        assert self.interactive_plot or self.save_hdf5, Exception(
            'You have chosen to neither view or save the inversion results!')

        # Set the ID for the data point the results pertain to

        # Set the increment at which to plot results
        # Increment at which to update the results

        # Set the display limits of the parameter in the HitMap
        # Display limits for parameters
        # Should we plot resistivity or Conductivity?
        # Logical whether to take the reciprocal of the parameters

        # Multiplier for discrepancy principle
        self.multiplier = float64(1.0)

        # Initialize the acceptance level
        # Model acceptance rate
        self.accepted = 0

        n = 2 * int32(self.n_markov_chains / self.update_plot_every)
        self.acceptance_x = StatArray.StatArray(arange(1, n + 1) * self.update_plot_every, name='Iteration #')
        self.acceptance_rate = StatArray.StatArray(full(n, fill_value=nan), name='% Acceptance')


        self.iRange = StatArray.StatArray(arange(2 * self.n_markov_chains), name="Iteration #", dtype=int64)

        # Initialize the index for the best model
        # self.iBestV = StatArray.StatArray(2*self.n_markov_chains, name='Iteration of best model')

        # Initialize the doi
        # self.doi = model.par.posterior.yBinCentres[0]

        # self.meanInterp = StatArray.StatArray(model.par.posterior.y.nCells.value)
        # self.bestInterp = StatArray.StatArray(model.par.posterior.y.nCells.value)
        # self.opacityInterp = StatArray.StatArray(model.par.posterior.y.nCells.value)

        # Initialize time in seconds
        self.inference_time = float64(0.0)

        # Initialize the best data, current data and best model
        self.best_model = deepcopy(self.model)
        self.best_datapoint = deepcopy(self.datapoint)
        self.best_posterior = self.posterior
        self.best_iteration = int64(0)

    def initialize_datapoint(self, datapoint, **kwargs):

        self.datapoint = datapoint

        # ---------------------------------------
        # Set the statistical properties of the datapoint
        # ---------------------------------------
        # Set the prior on the data
        self.datapoint.initialize(**kwargs)
        # Set the priors, proposals, and posteriors.
        self.datapoint.set_priors(**kwargs)
        self.datapoint.set_proposals(**kwargs)
        self.datapoint.set_posteriors()

    def initialize_model(self, **kwargs):
        # Find the conductivity of a half space model that best fits the data
        halfspace = self.datapoint.find_best_halfspace()
        self.halfspace = StatArray.StatArray(halfspace.values, 'halfspace')

        # Create an initial model for the first iteration
        # Initialize a 1D model with the half space conductivity
        # Assign the depth to the interface as half the bounds
        self.model = deepcopy(halfspace)

        # Setup the model for perturbation
        self.model.set_priors(
            value_mean=halfspace.values.item(),
            min_edge=kwargs['minimum_depth'],
            max_edge=kwargs['maximum_depth'],
            max_cells=kwargs['maximum_number_of_layers'],
            solve_value=True, #self.solve_parameter,
            solve_gradient=self.solve_gradient,
            parameter_limits=self.limits,
            min_width=kwargs.get('minimum_thickness', None),
            factor=kwargs.get('factor', 10.0), prng=self.prng
        )

        # Assign a Hitmap as a prior if one is given
        # if (not self.kwargs.referenceHitmap is None):
        #     Mod.setReferenceHitmap(self.kwargs.referenceHitmap)

        # Compute the predicted data
        self.datapoint.forward(self.model)

        observation = self.datapoint
        if self.ignore_likelihood:
            observation = None
        else:
            observation.sensitivity(self.model)

        local_variance = self.model.local_variance(observation)

        # Instantiate the proposal for the parameters.
        parameterProposal = Distribution('MvLogNormal', mean=self.model.values, variance=local_variance, linearSpace=True, prng=self.prng)

        probabilities = [kwargs['probability_of_birth'],
                         kwargs['probability_of_death'],
                         kwargs['probability_of_perturb'],
                         kwargs['probability_of_no_change']]
        self.model.set_proposals(probabilities=probabilities, proposal=parameterProposal, prng=self.prng)

        self.model.set_posteriors()

    def accept_reject(self):
        """ Propose a new random model and accept or reject it """
        perturbed_datapoint = deepcopy(self.datapoint)

        # Perturb the current model
        observation = perturbed_datapoint
        if self.ignore_likelihood:
            observation = None

        try:
            remapped_model, perturbed_model = self.model.perturb(observation)
        except:
            print('singularity line {} fid {}'.format(observation.line_number, observation.fiducial))
            return True

        # Propose a new data point, using assigned proposal distributions
        perturbed_datapoint.perturb()

        # Forward model the data from the candidate model
        perturbed_datapoint.forward(perturbed_model)

        # Compute the data misfit
        data_misfit1 = perturbed_datapoint.dataMisfit()

        # Evaluate the prior for the current data
        prior1 = perturbed_datapoint.probability
        # Test for early rejection
        if (prior1 == -inf):
            return

        # Evaluate the prior for the current model
        prior1 += perturbed_model.probability(self.solve_parameter, self.solve_gradient)

        # Test for early rejection
        if (prior1 == -inf):
            return

        # Compute the components of each acceptance ratio
        likelihood1 = 1.0
        observation = None
        if not self.ignore_likelihood:
            likelihood1 = perturbed_datapoint.likelihood(log=True)
            observation = deepcopy(perturbed_datapoint)

        proposal, proposal1 = perturbed_model.proposal_probabilities(remapped_model, observation)

        posterior1 = prior1 + likelihood1

        prior_ratio = prior1 - self.prior

        likelihood_ratio = likelihood1 - self.likelihood

        proposal_ratio = proposal - proposal1

        try:
            log_acceptance_ratio = longdouble(prior_ratio + likelihood_ratio + proposal_ratio)
            acceptance_probability = cF.expReal(log_acceptance_ratio)
        except:
            log_acceptance_ratio = -inf
            acceptance_probability = -1.0

        # If we accept the model
        accepted = acceptance_probability > self.prng.uniform()

        if (accepted):
            self.accepted += 1
            self.data_misfit = data_misfit1
            self.prior = prior1
            self.likelihood = likelihood1
            self.posterior = posterior1
            self.model = perturbed_model
            self.datapoint = perturbed_datapoint
            # Reset the sensitivity locally to the newly accepted model
            self.datapoint.sensitivity(self.model, modelChanged=False)

        return False

    def infer(self, hdf_file_handle):
        """ Markov Chain Monte Carlo approach for inversion of geophysical data
        userParameters: User input parameters object
        DataPoint: Datapoint to invert
        ID: Datapoint label for saving results
        pHDFfile: Optional HDF5 file opened using h5py.File('name.h5','w',driver='mpio', comm=world) before calling Inv_MCMC
        """

        if self.interactive_plot:
            self._init_posterior_plots()
            plt.show(block=False)

        self.clk.start()

        Go = True
        failed = False
        while (Go):
            # Accept or reject the new model
            failed = self.accept_reject()

            self.update()

            if self.interactive_plot:
                self.plot_posteriors(axes=self.ax,
                                     fig=self.fig,
                                     title="Fiducial {}".format(self.datapoint.fiducial),
                                     increment=self.update_plot_every)

            Go = not failed and (self.iteration <= self.n_markov_chains + self.burned_in_iteration)

            if (not failed) and (not self.burned_in):
                Go = self.iteration < self.n_markov_chains
                if not Go:
                    failed = True

        self.clk.stop()
        # self.invTime = float64(self.clk.timeinSeconds())
        # Does the user want to save the HDF5 results?
        if self.save_hdf5:
            # No parallel write is being used, so write a single file for the data point
            self.writeHdf(hdf_file_handle)

        # Does the user want to save the plot as a png?
        if self.save_png:# and not failed):
            # To save any thing the Results must be plot
            self.plot_posteriors(axes = self.ax, fig=self.fig)
            self.toPNG('.', self.datapoint.fiducial)

        return failed

    def __deepcopy__(self, memo={}):
        return None

    @property
    def hitmap(self):
        return self.model.values.posterior

    def update(self):
        """Update the posteriors of the McMC algorithm. """

        self.iteration += 1

        self.data_misfit_v[self.iteration - 1] = self.data_misfit

        # Determine if we are burning in
        if (not self.burned_in):
            target_misfit = sum(self.datapoint.active)

            # if self.data_misfit < target_misfit:
            if (self.iteration > 10000) and (isclose(self.data_misfit, self.multiplier*target_misfit, rtol=1e-1, atol=1e-2)):
                self._n_target_hits += 1

            if ((self.iteration > 10000) and (self.relative_chi_squared_fit < 1.0)) or ((self.iteration > 10000) and (self._n_target_hits > 1000)):
                self.burned_in = True  # Let the results know they are burned in
                self.burned_in_iteration = self.iteration       # Save the burn in iteration to the results
                self.best_iteration = self.iteration
                self.best_model = deepcopy(self.model)
                self.best_datapoint = deepcopy(self.datapoint)
                self.best_posterior = self.posterior

                self.data_misfit_v.reset_posteriors()
                self.model.reset_posteriors()
                self.datapoint.reset_posteriors()

        if (self.posterior > self.best_posterior):
            self.best_iteration = self.iteration
            self.best_model = deepcopy(self.model)
            self.best_datapoint = deepcopy(self.datapoint)
            self.best_posterior = self.posterior

        if ((self.iteration > 0) and (mod(self.iteration, self.update_plot_every) == 0)):
            acceptance_percent = 100.0 * float64(self.accepted) / float64(self.update_plot_every)
            self.acceptance_rate[int32(self.iteration / self.update_plot_every)-1] = acceptance_percent
            self.accepted = 0

        if (mod(self.iteration, self.update_plot_every) == 0):
            time_per_model = self.clk.lap() / self.update_plot_every
            bi = "" if self.burned_in else "*"
            tmp = "i=%i, k=%i, acc=%s%4.3f, %4.3f s/Model, %0.3f s Elapsed\n" % (self.iteration, float64(self.model.nCells[0]), bi, acceptance_percent, time_per_model, self.clk.timeinSeconds())
            if (self.rank == 1):
                print(tmp, flush=True)

            if (not self.burned_in and not self.datapoint.relative_error.hasPrior):
                self.multiplier *= self.kwargs['multiplier']

        # Added the layer depths to a list, we histogram this list every
        # iPlot iterations
        self.model.update_posteriors(0.5)#self.user_options.clip_ratio)

        # Update the height posterior
        self.datapoint.update_posteriors()

    def _init_posterior_plots(self, gs=None, **kwargs):
        """ Initialize the plotting region """
        # Setup the figure region. The figure window is split into a 4x3
        # region. Columns are able to span multiple rows
        fig  = kwargs.get('fig', plt.gcf())
        if gs is None:
            fig = kwargs.pop('fig', plt.figure(facecolor='white', figsize=(10, 7)))
            gs = fig

        if isinstance(gs, Figure):
            gs = gs.add_gridspec(nrows=1, ncols=1)[0, 0]

        gs = gs.subgridspec(2, 2, height_ratios=(1, 6))

        ax = [None] * 4

        ax[0] = cP.pretty(plt.subplot(gs[0, 0]))  # Acceptance Rate 0

        splt = gs[0, 1].subgridspec(1, 2, width_ratios=[4, 1])
        tmp = [plt.subplot(splt[0, 0])]
        tmp.append(plt.subplot(splt[0, 1]))#, sharey=ax[0]))
        ax[1] = tmp  # Data misfit vs iteration 1 and posterior

        ax[2] = self.model._init_posterior_plots(gs[1, 0])
        ax[3] = self.datapoint._init_posterior_plots(gs[1, 1])

        if self.interactive_plot:
            plt.show(block=False)
            plt.interactive(True)

        self.fig, self.ax = fig, ax

        return fig, ax

    def plot_posteriors(self, axes=None, title="", increment=None, **kwargs):
        """ Updates the figures for MCMC Inversion """
        # Plots that change with every iteration
        if self.iteration == 0:
            return

        if axes is None:
            fig = kwargs.pop('fig', None)
            axes = fig
            if fig is None:
                fig, axes = self._init_posterior_plots()

        if not isinstance(axes, list):
            axes = self._init_posterior_plots(axes)

        plot = True
        if increment is not None:
            if (mod(self.iteration, increment) != 0):
                plot = False

        if plot:
            self._plotAcceptanceVsIteration()

            # Update the data misfit vs iteration
            self._plotMisfitVsIteration()

            overlay = self.best_model if self.burned_in else self.model

            self.model.plot_posteriors(
                axes=self.ax[2],
                # ncells_kwargs={
                #     'normalize': True},
                edges_kwargs={
                    'transpose': True,
                    'trim': False},
                values_kwargs={
                    'colorbar': False,
                    'flipY': True,
                    'xscale': 'log',
                    'credible_interval_kwargs': {
                        # 'axis': 1
                    }
                },
                overlay=overlay)

            overlay = self.best_datapoint if self.burned_in else self.datapoint

            self.datapoint.plot_posteriors(
                axes=self.ax[3],
                # height_kwargs={
                #     'normalize': True},
                data_kwargs={},
                # rel_error_kwargs={
                #     'normalize': True},
                # add_error_kwargs={
                #     'normalize': True},
                overlay=overlay)

            cP.suptitle(title)

            # self.fig.tight_layout()
            if self.fig is not None:
                self.fig.canvas.draw()
                self.fig.canvas.flush_events()

            cP.pause(1e-9)

    def _plotAcceptanceVsIteration(self, **kwargs):
        """ Plots the acceptance percentage against iteration. """

        i = s_[:int64(self.iteration / self.update_plot_every)]

        acceptance_rate = self.acceptance_rate[i]
        i_positive = argwhere(acceptance_rate > 0.0)
        i_zero = argwhere(acceptance_rate == 0.0)

        kwargs['ax'] = kwargs.get('ax', self.ax[0])
        kwargs['marker'] = kwargs.get('marker', 'o')
        kwargs['alpha'] = kwargs.get('alpha', 0.7)
        kwargs['linestyle'] = kwargs.get('linestyle', 'none')
        kwargs['markeredgecolor'] = kwargs.get('markeredgecolor', 'k')

        self.acceptance_rate[i_positive].plot(x=self.acceptance_x[i_positive], color='k', **kwargs)
        self.acceptance_rate[i_zero].plot(x=self.acceptance_x[i_zero], color='r', **kwargs)

        self.ax[0].ticklabel_format(style='sci', axis='x', scilimits=(0, 0))

    def _plotMisfitVsIteration(self, **kwargs):
        """ Plot the data misfit against iteration. """

        ax = kwargs.get('ax', self.ax[1])
        m = kwargs.pop('marker', '.')
        # ms = kwargs.pop('markersize', 1)
        a = kwargs.pop('alpha', 0.7)
        ls = kwargs.pop('linestyle', 'none')
        c = kwargs.pop('color', 'k')
        # lw = kwargs.pop('linewidth', 1)

        kwargs['ax'] = ax[0]

        tmp_ax = self.data_misfit_v.plot(self.iRange, i=s_[:self.iteration], marker=m, alpha=a, linestyle=ls, color=c, **kwargs)
        plt.ylabel('Data Misfit')

        dum = self.multiplier * self.data_misfit_v.prior.df
        plt.axhline(dum, color='#C92641', linestyle='dashed')
        if (self.burned_in):
            plt.axvline(self.burned_in_iteration, color='#C92641',
                        linestyle='dashed')
            # plt.axvline(self.best_iteration, color=cP.wellSeparated[3])
        plt.yscale('log')
        tmp_ax.ticklabel_format(style='sci', axis='x', scilimits=(0, 0))

        plt.xlim([0, self.iRange[self.iteration]])

        if not self.burned_in:
            self.data_misfit_v.reset_posteriors()

        self.data_misfit_v.posterior.update(self.data_misfit_v[maximum(0, self.iteration-self.update_plot_every):self.iteration], trim=True)

        kwargs = {'ax' : ax[1],
                  'normalize' : True}
        kwargs['ax'].cla()
        tmp_ax = self.data_misfit_v.posterior.plot(transpose=True, **kwargs)
        ylim = tmp_ax.get_ylim()
        tmp_ax = self.data_misfit_v.prior.plot_pdf(ax=kwargs['ax'], transpose=True, c='#C92641', linestyle='dashed')

        centres = self.data_misfit_v.posterior.mesh.centres
        h_pdf = self.data_misfit_v.posterior.pdf.values
        pdf = self.data_misfit_v.prior.probability(self.data_misfit_v.posterior.mesh.centres, log=False)

        self.relative_chi_squared_fit = norm(h_pdf - pdf)/norm(pdf)

        plt.hlines(sum(self.datapoint.active), xmin=0.0, xmax=0.5*tmp_ax.get_xlim()[1], color='#C92641', linestyle='dashed')
        tmp_ax.set_ylim(ylim)


    # def _plotObservedPredictedData(self, **kwargs):
    #     """ Plot the observed and predicted data """
    #     if self.burnedIn:
    #         # self.datapoint.predictedData.plot_posteriors(colorbar=False)
    #         self.datapoint.plot(**kwargs)
    #         self.bestDataPoint.plot_predicted(color=cP.wellSeparated[3], **kwargs)
    #     else:

    #         self.datapoint.plot(**kwargs)
    #         self.datapoint.plot_predicted(color='g', **kwargs)

    def saveToLines(self, h5obj):
        """ Save the results to a HDF5 object for a line """
        self.clk.restart()
        self.toHdf(h5obj, str(self.datapoint.fiducial))

    def save(self, outdir, fiducial):
        """ Save the results to their own HDF5 file """
        with h5py.File(join(outdir, str(fiducial)+'.h5'), 'w') as f:
            self.toHdf(f, str(fiducial))

    def toPNG(self, directory, fiducial, dpi=300):
       """ save a png of the results """
       self.fig.set_size_inches(19, 11)
       figName = join(directory, '{}.png'.format(fiducial))
       self.fig.savefig(figName, dpi=dpi)

    def read(self, fileName, system_file_path, fiducial=None, index=None):
        """ Reads a data point's results from HDF5 file """

        with h5py.File(fileName, 'r')as f:
            R = self.fromHdf(f, system_file_path, index=index, fiducial=fiducial)

        self.plotMe = True
        return self


    def createHdf(self, parent, add_axis=None):
        """ Create the hdf group metadata in file
        parent: HDF object to create a group inside
        myName: Name of the group
        """

        assert self.datapoint is not None, ValueError("Inference needs a datapoint before creating HDF5 files.")

        if add_axis is not None:
            if not isinstance(add_axis, (int, int32, int64)):
                add_axis = size(add_axis)

        self.datapoint.createHdf(parent, 'data', add_axis=add_axis, fillvalue=nan)

        # Initialize and write the attributes that won't change
        parent.create_dataset('update_plot_every', data=self.update_plot_every)
        parent.create_dataset('interactive_plot', data=self.interactive_plot)
        parent.create_dataset('reciprocate_parameter', data=self.reciprocate_parameter)

        if not self.limits is None:
            parent.create_dataset('limits', data=self.limits)

        parent.create_dataset('n_markov_chains', data=self.n_markov_chains)
        parent.create_dataset('nsystems', data=self.datapoint.nSystems)
        self.acceptance_x.toHdf(parent,'ratex')

        # Initialize the attributes that will be written later
        s = add_axis
        if add_axis is None:
            s = 1

        parent.create_dataset('iteration', shape=(s), dtype=self.iteration.dtype, fillvalue=nan)
        parent.create_dataset('burned_in_iteration', shape=(s), dtype=self.burned_in_iteration.dtype, fillvalue=nan)
        parent.create_dataset('best_iteration', shape=(s), dtype=self.best_iteration.dtype, fillvalue=nan)
        parent.create_dataset('burned_in', shape=(s), dtype=type(self.burned_in), fillvalue=0)
        parent.create_dataset('multiplier',  shape=(s), dtype=self.multiplier.dtype, fillvalue=nan)
        parent.create_dataset('invtime',  shape=(s), dtype=float, fillvalue=nan)
        parent.create_dataset('savetime',  shape=(s), dtype=float, fillvalue=nan)

        self.acceptance_rate.createHdf(parent,'acceptance_rate', add_axis=add_axis, fillvalue=nan)
        self.data_misfit_v.createHdf(parent, 'phids', add_axis=add_axis, fillvalue=nan)
        self.halfspace.createHdf(parent, 'halfspace', add_axis=add_axis, fillvalue=nan)

        # Since the 1D models change size adaptively during the inversion, we need to pad the HDF creation to the maximum allowable number of layers.
        tmp = self.model.pad(self.model.mesh.max_cells)
        tmp.createHdf(parent, 'model', add_axis=add_axis, fillvalue=nan)

        return parent

    def writeHdf(self, parent, index=None):
        """ Given a HDF file initialized as line results, write the contents of results to the appropriate arrays """

        # Get the point index
        if index is None:
            fiducials = StatArray.StatArray.fromHdf(parent['data/fiducial'])
            index = fiducials.searchsorted(self.datapoint.fiducial)

        # Add the iteration number
        parent['iteration'][index] = self.iteration

        # Add the burn in iteration
        parent['burned_in_iteration'][index] = self.burned_in_iteration

        # Add the burn in iteration
        parent['best_iteration'][index] = self.best_iteration

        # Add the burned in logical
        parent['burned_in'][index] = self.burned_in

        # Add the depth of investigation
        # hdfFile['doi'][i] = self.doi()

        # Add the multiplier
        parent['multiplier'][index] = self.multiplier

        # Add the inversion time
        # hdfFile['invtime'][i] = self.invTime

        # Add the savetime
#        hdfFile['savetime'][i] = self.saveTime

        # Interpolate the mean and best model to the discretized hitmap
        # hm = self.model.par.posterior
        # self.meanInterp = StatArray.StatArray(hm.mean())
        # self.bestInterp = StatArray.StatArray(self.best_model.piecewise_constant_interpolate(self.best_model.par, hm, axis=0))
        # self.opacityInterp[:] = self.Hitmap.credibleRange(percent=95.0, log='e')

        # # Add the interpolated mean model
        # self.meanInterp.writeHdf(hdfFile, 'meaninterp',  index=i)
        # # Add the interpolated best
        # self.bestInterp.writeHdf(hdfFile, 'bestinterp',  index=i)
        # # Add the interpolated opacity

        # Add the acceptance rate
        self.acceptance_rate.writeHdf(hdfFile, 'acceptance_rate', index=i)

        # Add the data misfit
        self.data_misfit_v.writeHdf(hdfFile, 'phids', index=i)

        # Write the data posteriors
        self.datapoint.writeHdf(hdfFile,'data',  index=i)
        # Write the highest posterior data
        self.best_datapoint.writeHdf(hdfFile,'data', withPosterior=False, index=i)

        self.halfspace.writeHdf(hdfFile, 'halfspace', index=i)

        # Write the model posteriors
        self.model.writeHdf(hdfFile,'model', index=i)
        # Write the highest posterior data
        self.best_model.writeHdf(hdfFile,'model', withPosterior=False, index=i)


    def read_fromH5Obj(self, h5obj, fName, grpName, system_file_path = ''):
        """ Reads a data points results from HDF5 file """
        grp = h5obj.get(grpName)
        assert not grp is None, "ID "+str(grpName) + " does not exist in file " + fName
        self.fromHdf(grp, system_file_path)


    @classmethod
    def fromHdf(cls, hdfFile, index=None, fiducial=None):

        iNone = index is None
        fNone = fiducial is None

        assert not (iNone and fNone) ^ (not iNone and not fNone), Exception("Must specify either an index OR a fiducial.")

        if not fNone:
            fiducials = StatArray.StatArray.fromHdf(hdfFile['data/fiducial'])
            index = fiducials.searchsorted(fiducial)

        self = cls(
                datapoint = hdfRead.readKeyFromFile(hdfFile, '', '/', 'data', index=index),
                interactive_plot = True,
                multiplier = hdfRead.readKeyFromFile(hdfFile, '', '/', 'multiplier', index=index),
                n_markov_chains = array(hdfFile.get('n_markov_chains')),
                parameter_limits = None if not 'limits' in hdfFile else hdfFile.get('limits'),
                reciprocate_parameters = array(hdfFile.get('reciprocate_parameter')),
                save_hdf5 = False,
                save_png = False,
                update_plot_every = array(hdfFile.get('update_plot_every')),
                dont_initialize = True)

        s = s_[index, :]

        self.nSystems = array(hdfFile.get('nsystems'))
        self.acceptance_x = hdfRead.readKeyFromFile(hdfFile, '', '/', 'ratex')

        self.iteration = hdfRead.readKeyFromFile(hdfFile, '', '/', 'iteration', index=index)
        self.burned_in_iteration = hdfRead.readKeyFromFile(hdfFile, '', '/', 'burned_in_iteration', index=index)
        self.burned_in = hdfRead.readKeyFromFile(hdfFile, '', '/', 'burned_in', index=index)
        self.acceptance_rate = hdfRead.readKeyFromFile(hdfFile, '', '/', 'rate', index=s)

        self.best_datapoint = self.datapoint

        self.data_misfit_v = hdfRead.readKeyFromFile(hdfFile, '', '/', 'phids', index=s)
        self.data_misfit_v.prior = Distribution('chi2', df=sum(self.datapoint.active))

        self.model = hdfRead.readKeyFromFile(hdfFile, '', '/', 'model', index=index)
        self.best_model = self.model

        self.halfspace = hdfRead.readKeyFromFile(hdfFile, '', '/', 'halfspace', index=index)

        self.Hitmap = self.model.values.posterior

        self.invTime = array(hdfFile.get('invtime')[index])
        self.saveTime = array(hdfFile.get('savetime')[index])

        # Initialize a list of iteration number
        self.iRange = StatArray.StatArray(arange(2 * self.n_markov_chains), name="Iteration #", dtype=int64)

        self.verbose = False


        return self
