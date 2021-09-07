""" @Inference1D
Class to store inversion results. Contains plotting and writing to file procedures
"""
from os.path import join
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.pyplot import pause
from matplotlib.ticker import MaxNLocator
from ..base import plotting as cP
from ..base import utilities as cF
import numpy as np
from ..base import fileIO as fIO
import h5py
from ..base.HDF.hdfWrite import write_nd
from ..classes.core import StatArray
from ..classes.statistics.Hitmap2D import Hitmap2D
from ..classes.statistics.Histogram1D import Histogram1D
from ..classes.statistics.Distribution import Distribution
from ..classes.core.myObject import myObject
from ..classes.data.datapoint.FdemDataPoint import FdemDataPoint
from ..classes.data.datapoint.TdemDataPoint import TdemDataPoint
from ..classes.model.Model1D import Model1D
from ..classes.core.Stopwatch import Stopwatch
from ..base.HDF import hdfRead

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
        The relative error prior must have been set with dataPoint.relErr.set_prior()
        The additive error prior must have been set with dataPoint.addErr.set_prior()
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

    def __init__(self, dataPoint=None, model=None, fiducial=0.0, **kwargs):
        """ Initialize the results of the inversion """

        # Initialize a stopwatch to keep track of time
        self.clk = Stopwatch()
        self.invTime = np.float64(0.0)
        self.saveTime = np.float64(0.0)

        # Logicals of whether to plot or save
        self.saveMe = kwargs.pop('save', True)
        self.plotMe = kwargs.pop('plot', False)
        self.savePNG = kwargs.pop('savePNG', False)

        self.fig = None
        # Return none if important parameters are not used (used for hdf 5)
        if all(x1 is None for x1 in [dataPoint, model]):
            return

        assert self.plotMe or self.saveMe, Exception('You have chosen to neither view or save the inversion results!')

        nMarkovChains = kwargs.pop('nMarkovChains', 100000)
        plotEvery = kwargs.pop('plotEvery', nMarkovChains / 20)
        parameterDisplayLimits = kwargs.pop('parameterDisplayLimits', [0.0, 1.0])
        reciprocateParameter = kwargs.pop('reciprocateParameters', False)

        verbose = kwargs.pop('verbose', False)

        # Set the ID for the data point the results pertain to
        # Data Point identifier
        self.fiducial = np.float(fiducial)
        # Set the increment at which to plot results
        # Increment at which to update the results
        self.iPlot = np.int64(plotEvery)
        # Set the display limits of the parameter in the HitMap
        # Display limits for parameters
        self.limits = np.asarray(parameterDisplayLimits) if not parameterDisplayLimits is None else None
        # Should we plot resistivity or Conductivity?
        # Logical whether to take the reciprocal of the parameters
        self.reciprocateParameter = reciprocateParameter
        # Set the screen resolution
        # Screen Size
        self.sx = np.int32(1920)
        self.sy = np.int32(1080)
        # Copy the number of systems
        # Number of systems in the DataPoint
        self.nSystems = np.int32(dataPoint.nSystems)
        # Copy the number of Markov Chains
        # Number of Markov Chains to use
        self.nMC = np.int64(nMarkovChains)
        # Initialize a list of iteration number (This might seem like a waste of memory, but is faster than calling np.arange(nMC) every time)
        # StatArray of precomputed integers
        self.iRange = StatArray.StatArray(np.arange(2 * self.nMC), name="Iteration #", dtype=np.int64)
        # Initialize the current iteration number
        # Current iteration number
        self.i = np.int64(0)
        self.iBest = np.int64(0)
        # Initialize the vectors to save results
        # StatArray of the data misfit
        self.PhiDs = StatArray.StatArray(2 * self.nMC, name = 'Data Misfit')
        # Multiplier for discrepancy principle
        self.multiplier = np.float64(0.0)
        # Initialize the acceptance level
        # Model acceptance rate
        self.acceptance = 0.0
#    self.rate=np.zeros(np.int(self.nMC/1000)+1)
        n = 2 * np.int(self.nMC / 1000)
        self.rate = StatArray.StatArray(n, name='% Acceptance')
        self.ratex = StatArray.StatArray(np.arange(1, n + 1) * 1000, name='Iteration #')
        # Initialize the burned in state
        self.iBurn = self.nMC
        self.burnedIn = False
        # Initialize the index for the best model
        self.iBest = np.int32(0)
        self.iBestV = StatArray.StatArray(2*self.nMC, name='Iteration of best model')

        self.iz = np.arange(model.par.posterior.y.nCells.value)

        # Initialize the doi
        # self.doi = model.par.posterior.yBinCentres[0]

        self.meanInterp = StatArray.StatArray(model.par.posterior.y.nCells.value)
        self.bestInterp = StatArray.StatArray(model.par.posterior.y.nCells.value)
        self.opacityInterp = StatArray.StatArray(model.par.posterior.y.nCells.value)

        # Set a tag to catch data points that are not minimizing
        self.zeroCount = 0

        self.verbose = verbose

        # Initialize times in seconds
        self.invTime = np.float64(0.0)
        self.saveTime = np.float64(0.0)

        # Initialize the best data, current data and best model
        self.currentDataPoint = dataPoint
        self.bestDataPoint = dataPoint

        self.currentModel = model
        self.bestModel = model

    def __deepcopy__(self, memo={}):
        return None

    @property
    def hitmap(self):
        return self.currentModel.par.posterior

    def update(self, i, model, dataPoint, iBest, bestDataPoint, bestModel, multiplier, PhiD, posterior, posteriorComponents, ratioComponents, accepted, dimensionChange, clipRatio):
        """Update the posteriors of the McMC algorithm. """
        self.i = np.int32(i)
        self.iBest = np.int32(iBest)
        self.PhiDs[self.i - 1] = PhiD.copy()  # Store the data misfit
        self.multiplier = np.float64(multiplier)

        if (self.burnedIn):  # We need to update some plotting options
            # Added the layer depths to a list, we histogram this list every
            # iPlot iterations
            model.updatePosteriors(clipRatio)

            # Update the height posterior
            dataPoint.updatePosteriors()

        if (np.mod(i, 1000) == 0):
            ratePercent = 100.0 * (np.float64(self.acceptance) / np.float64(1000))
            self.rate[np.int(self.i / 1000) - 1] = ratePercent
            self.acceptance = 0
            if (ratePercent < 2.0):
                self.zeroCount += 1
            else:
                self.zeroCount = 0

        self.currentDataPoint = dataPoint  # Reference
        self.bestDataPoint = bestDataPoint # Reference

        self.currentModel = model
        self.bestModel = bestModel # Reference


    def initFigure(self, fig = None):
        """ Initialize the plotting region """
        # Setup the figure region. The figure window is split into a 4x3
        # region. Columns are able to span multiple rows

        # plt.ion()

        if fig is None:
            self.fig = plt.figure(facecolor='white', figsize=(10, 7))
        else:
            self.fig = plt.figure(fig.number)

        mngr = plt.get_current_fig_manager()
        try:
            mng.frame.Maximize(True)
        except:
            try:
                mngr.window.showMaximized()
            except:
                try:
                    mngr.window.state('zoomed')
                except:
                    pass

        gs = self.fig.add_gridspec(2, 2, height_ratios=(1, 6))
        self.ax = []

        self.ax.append(plt.subplot(gs[0, 0])) # Acceptance Rate 0
        self.ax.append(plt.subplot(gs[0, 1])) # Data misfit vs iteration 1
        for ax in self.ax:
            cP.pretty(ax)

        self.ax.append(self.currentModel.init_posterior_plots(gs[1, 0]))
        self.ax.append(self.currentDataPoint.init_posterior_plots(gs[1, 1]))

        if self.plotMe:
            plt.show(block=False)
        # plt.draw()


    def plot(self, title="", increment=None):
        """ Updates the figures for MCMC Inversion """
        # Plots that change with every iteration
        if self.i == 0:
            return

        if (self.fig is None):
            self.initFigure()

        plt.figure(self.fig.number)

        plot = True
        if not increment is None:
            if (np.mod(self.i, increment) != 0):
                plot = False

        if plot:

            self._plotAcceptanceVsIteration()

            # Update the data misfit vs iteration
            self._plotMisfitVsIteration()

            self.currentModel.plot_posteriors(
                axes = self.ax[2],
                ncells_kwargs = {
                    'normalize':True},
                edges_kwargs = {
                    'normalize':True,
                    'rotate':True,
                    'flipY':True,
                    'trim':False},
                parameter_kwargs = {
                    # 'reciprocateX':self.reciprocateParameter,
                    'noColorbar':True,
                    'flipY':True,
                    'xscale':'log',
                    'credible_interval_kwargs':{
                        # 'log':10,
                        # 'reciprocate':True
                        }
                    },
                best = self.bestModel)

            self.currentDataPoint.plot_posteriors(
                axes=self.ax[3],
                height_kwargs = {
                    'normalize':True},
                data_kwargs = {},
                rel_error_kwargs = {
                    'normalize':True},
                add_error_kwargs = {
                    'normalize':True},
                best = self.bestDataPoint)

            cP.suptitle(title)

            # self.fig.tight_layout()
            self.fig.canvas.draw()
            self.fig.canvas.flush_events()

            cP.pause(1e-9)


    def _plotAcceptanceVsIteration(self, **kwargs):
        """ Plots the acceptance percentage against iteration. """

        i = np.s_[:np.int64(self.i / 1000)]
        self.rate.plot(self.ratex, i=i,
                        ax = self.ax[0],
                        marker = 'o',
                        alpha = 0.7,
                        linestyle = 'none',
                        markeredgecolor = 'k'
                        )
        # cP.xlabel('Iteration #')
        # cP.ylabel('% Acceptance')
        self.ax[0].ticklabel_format(style='sci', axis='x', scilimits=(0,0))


    def _plotMisfitVsIteration(self, **kwargs):
        """ Plot the data misfit against iteration. """

        kwargs['ax'] = self.ax[1]
        m = kwargs.pop('marker', '.')
        ms = kwargs.pop('markersize', 2)
        a = kwargs.pop('alpha', 0.7)
        ls = kwargs.pop('linestyle', 'none')
        c = kwargs.pop('color', 'k')
        lw = kwargs.pop('linewidth', 3)

        ax = self.PhiDs.plot(self.iRange, i=np.s_[:self.i], marker=m, alpha=a, markersize=ms, linestyle=ls, color=c, **kwargs)
        plt.ylabel('Data Misfit')
        dum = self.multiplier * self.currentDataPoint.active.size
        plt.axhline(dum, color='#C92641', linestyle='dashed', linewidth=lw)
        if (self.burnedIn):
            plt.axvline(self.iBurn, color='#C92641', linestyle='dashed', linewidth=lw)
            # plt.axvline(self.iBest, color=cP.wellSeparated[3])
        # plt.yscale('log')
        ax.ticklabel_format(style='sci', axis='x', scilimits=(0,0))

        plt.xlim([0, self.iRange[self.i]])


    # def _plotObservedPredictedData(self, **kwargs):
    #     """ Plot the observed and predicted data """
    #     if self.burnedIn:
    #         # self.currentDataPoint.predictedData.plotPosteriors(noColorbar=True)
    #         self.currentDataPoint.plot(**kwargs)
    #         self.bestDataPoint.plotPredicted(color=cP.wellSeparated[3], **kwargs)
    #     else:
    #         self.currentDataPoint.plot(**kwargs)
    #         self.currentDataPoint.plotPredicted(color='g', **kwargs)

    def saveToLines(self, h5obj, fiducial):
        """ Save the results to a HDF5 object for a line """
        self.clk.restart()
        self.toHdf(h5obj, str(fiducial))

    def save(self, outdir, fiducial):
        """ Save the results to their own HDF5 file """
        with h5py.File(join(outdir,str(fiducial)+'.h5'),'w') as f:
            self.toHdf(f, str(fiducial))

    def toPNG(self, directory, fiducial, dpi=300):
       """ save a png of the results """
       self.fig.set_size_inches(19, 11)
       figName = join(directory, '{}.png'.format(fiducial))
       self.fig.savefig(figName, dpi=dpi)

       if (self.verbose):
           fig = plt.figure(1)
           fig.set_size_inches(19, 11)
           figName = join(directory,str(fiducial) + '_rap.png')
           plt.savefig(figName, dpi=dpi)

           fig = plt.figure(2)
           fig.set_size_inches(19, 11)
           figName = join(directory,str(fiducial) + '_posterior_components.png')
           plt.savefig(figName, dpi=dpi)

           fig = plt.figure(3)
           fig.set_size_inches(19, 11)
           figName = join(directory,str(fiducial) + '_ratio_crossplot.png')
           plt.savefig(figName, dpi=dpi)

           fig = plt.figure(4)
           fig.set_size_inches(19, 11)
           figName = join(directory,str(fiducial) + '_ratios_vs_iteration.png')
           plt.savefig(figName, dpi=dpi)


    def read(self, fileName, system_file_path, fiducial=None, index=None):
        """ Reads a data point's results from HDF5 file """

        with h5py.File(fileName, 'r')as f:
            R = self.fromHdf(f, system_file_path, index=index, fiducial=fiducial)

        self.plotMe = True
        return self


    def read_fromH5Obj(self, h5obj, fName, grpName, system_file_path = ''):
        """ Reads a data points results from HDF5 file """
        grp = h5obj.get(grpName)
        assert not grp is None, "ID "+str(grpName) + " does not exist in file " + fName
        self.fromHdf(grp, system_file_path)


    def fromHdf(self, hdfFile, system_file_path, index=None, fiducial=None):

        iNone = index is None
        fNone = fiducial is None

        assert not (iNone and fNone) ^ (not iNone and not fNone), Exception("Must specify either an index OR a fiducial.")

        fiducials = StatArray.StatArray.fromHdf(hdfFile['fiducials'])

        if not fNone:
            index = fiducials.searchsorted(fiducial)

        s = np.s_[index, :]

        self.fiducial = np.float64(fiducials[index])

        self.iPlot = np.array(hdfFile.get('iplot'))
        self.plotMe = np.array(hdfFile.get('plotme'))

        tmp = hdfFile.get('limits')
        self.limits = None if tmp is None else np.array(tmp)
        self.reciprocateParameter = np.array(hdfFile.get('reciprocateParameter'))
        self.nMC = np.array(hdfFile.get('nmc'))
        self.nSystems = np.array(hdfFile.get('nsystems'))
        self.ratex = hdfRead.readKeyFromFile(hdfFile,'','/','ratex')

        self.i = hdfRead.readKeyFromFile(hdfFile,'','/','i', index=index)
        self.iBurn = hdfRead.readKeyFromFile(hdfFile,'','/','iburn', index=index)
        self.burnedIn = hdfRead.readKeyFromFile(hdfFile,'','/','burnedin', index=index)
        # self.doi = hdfRead.readKeyFromFile(hdfFile,'','/','doi', index=index)
        self.multiplier = hdfRead.readKeyFromFile(hdfFile,'','/','multiplier', index=index)
        self.rate = hdfRead.readKeyFromFile(hdfFile,'','/','rate', index=s)
        self.PhiDs = hdfRead.readKeyFromFile(hdfFile,'','/','phids', index=s)

        self.bestDataPoint = hdfRead.readKeyFromFile(hdfFile,'','/','bestd', index=index, system_file_path=system_file_path)
        self.currentDataPoint = hdfRead.readKeyFromFile(hdfFile,'','/','currentdatapoint', index=index, system_file_path=system_file_path)

        self.currentModel = hdfRead.readKeyFromFile(hdfFile,'','/','currentmodel', index=index)
        self.Hitmap = self.currentModel.par.posterior
        # self.currentModel._max_edge = np.log(self.Hitmap.y.centres[-1])
        # except:
        #     self.Hitmap = hdfRead.readKeyFromFile(hdfFile,'','/','hitmap', index=index)


        self.bestModel = hdfRead.readKeyFromFile(hdfFile,'','/','bestmodel', index=index)
        # self.bestModel._max_edge = np.log(self.Hitmap.y.centres[-1])

        self.invTime = np.array(hdfFile.get('invtime')[index])
        self.saveTime = np.array(hdfFile.get('savetime')[index])

        # Initialize a list of iteration number
        self.iRange = StatArray.StatArray(np.arange(2 * self.nMC), name="Iteration #", dtype=np.int64)

        self.verbose = False

        self.plotMe = True

        return self

    def verbose(self):
        # if self.verbose & self.burnedIn:

        if self.verbose:
            self.verboseFigs = []
            self.verboseAxs = []

            # Posterior components
            fig = plt.figure(facecolor='white', figsize=(10,7))
            self.verboseFigs.append(fig)
            self.verboseAxs.append(fig.add_subplot(511))
            self.verboseAxs.append(fig.add_subplot(512))
            self.verboseAxs.append(fig.add_subplot(513))

            fig = plt.figure(facecolor='white', figsize=(10,7))
            self.verboseFigs.append(fig)
            for i in range(8):
                self.verboseAxs.append(fig.add_subplot(8, 1, i+1))

            # Cross Plots
            fig = plt.figure(facecolor='white', figsize=(10,7))
            self.verboseFigs.append(fig)
            for i in range(4):
                self.verboseAxs.append(fig.add_subplot(1, 4, i+1))

            # ratios vs iteration number
            fig = plt.figure(facecolor='white', figsize=(10,7))
            self.verboseFigs.append(fig)
            for i in range(5):
                self.verboseAxs.append(fig.add_subplot(5, 1, i+1))

            for ax in self.verboseAxs:
                cP.pretty(ax)

        plt.figure(self.verboseFigs[0].number)
        plt.sca(self.verboseAxs[0])
        plt.cla()
        self.allRelErr[0, :].plot(self.iRange, i=np.s_[:self.i], c='k')
        plt.sca(self.verboseAxs[1])
        plt.cla()
        self.allAddErr[0, :].plot(self.iRange, i=np.s_[:self.i], axis=1, c='k')
        plt.sca(self.verboseAxs[2])
        plt.cla()
        self.allZ.plot(x=self.iRange, i=np.s_[:self.i], marker='o', linestyle='none', markersize=2, alpha=0.3, markeredgewidth=1)


        # Posterior components plot Figure 1
        labels=['nCells','depth','parameter','gradient','relative','additive','height','calibration']
        plt.figure(self.verboseFigs[1].number)
        for i in range(8):
            plt.sca(self.verboseAxs[3 + i])
            plt.cla()
            self.posteriorComponents[i, :].plot(linewidth=0.5)
            plt.ylabel('')
            plt.title(labels[i])
            if labels[i] == 'gradient':
                plt.ylim([-30.0, 1.0])


        ira = self.iRange[:np.int(1.2*self.nMC)][self.accepted]
        irna = self.iRange[:np.int(1.2*self.nMC)][~self.accepted]

        plt.figure(self.verboseFigs[3].number)
        # Number of layers vs iteration
        plt.sca(self.verboseAxs[15])
        plt.cla()
        self.allK[~self.accepted].plot(x = irna, marker='o', markersize=1,  linestyle='None', alpha=0.3, color='k')
        self.allK[self.accepted].plot(x = ira, marker='o', markersize=1, linestyle='None', alpha=0.3)
        plt.title('black = rejected')


        plt.figure(self.verboseFigs[2].number)
        # Cross plot of current vs candidate prior
        plt.sca(self.verboseAxs[11])
        plt.cla()
        x = StatArray.StatArray(self.ratioComponents[0, :], 'Candidate Prior')
        y = StatArray.StatArray(self.ratioComponents[1, :], 'Current Prior')

        x[x == -np.inf] = np.nan
        y[y == -np.inf] = np.nan
        x[~self.accepted].plot(x = y[~self.accepted], linestyle='', marker='.', color='k', alpha=0.3)
        x[self.accepted].plot(x = y[self.accepted], linestyle='', marker='.', alpha=0.3)
        # v1 = np.maximum(np.minimum(np.nanmin(x), np.nanmin(y)), -20.0)
        v2 = np.maximum(np.nanmax(x), np.nanmax(y))
        v1 = v2 - 25.0
        plt.xlim([v1, v2])
        plt.ylim([v1, v2])
        plt.plot([v1,v2], [v1,v2])

        # Prior ratio vs iteration
        plt.figure(self.verboseFigs[3].number)
        plt.sca(self.verboseAxs[16])
        plt.cla()
        r = x - y
        r[~self.accepted].plot(x = irna, marker='o', markersize=1, linestyle='None', alpha=0.3, color='k')
        r[self.accepted].plot(x = ira, marker='o', markersize=1, linestyle='None', alpha=0.3)
        plt.ylim([v1, 5.0])
        cP.ylabel('Prior Ratio')



        plt.figure(self.verboseFigs[2].number)
        # Cross plot of the likelihood ratios
        plt.sca(self.verboseAxs[12])
        plt.cla()
        x = StatArray.StatArray(self.ratioComponents[2, :], 'Candidate Likelihood')
        y = StatArray.StatArray(self.ratioComponents[3, :], 'Current Likelihood')
        x[~self.accepted].plot(x = y[~self.accepted], linestyle='', marker='.', color='k', alpha=0.3)
        x[self.accepted].plot(x = y[self.accepted], linestyle='', marker='.', alpha=0.3)

        v2 = np.maximum(np.nanmax(x), np.nanmax(y)) + 5.0
        v1 = v2 - 200.0
        # v1 = -100.0
        # v2 = -55.0
        plt.xlim([v1, v2])
        plt.ylim([v1, v2])
        plt.plot([v1, v2], [v1, v2])
        plt.title('black = rejected')

        plt.figure(self.verboseFigs[3].number)
        # Likelihood ratio vs iteration
        plt.sca(self.verboseAxs[17])
        plt.cla()
        r = x - y
        r[~self.accepted].plot(x = irna, marker='o', markersize=1, linestyle='None', alpha=0.3, color='k')
        r[self.accepted].plot(x = ira, marker='o', markersize=1, linestyle='None', alpha=0.3)
        cP.ylabel('Likelihood Ratio')
        plt.ylim([-20.0, 20.0])

        plt.figure(self.verboseFigs[2].number)
        # Cross plot of the proposal ratios
        plt.sca(self.verboseAxs[13])
        plt.cla()
        y = StatArray.StatArray(self.ratioComponents[4, :], 'Current Proposal')
        x = StatArray.StatArray(self.ratioComponents[5, :], 'Candidate Proposal')
        x[~self.accepted].plot(x = y[~self.accepted], linestyle='', marker='.', color='k', alpha=0.3)
        x[self.accepted].plot(x = y[self.accepted], linestyle='', marker='.', alpha=0.3)
        # v1 = np.maximum(np.minimum(np.nanmin(x), np.nanmin(y)), -200.0)
        v2 = np.maximum(np.nanmax(x), np.nanmax(y)) + 10.0
        v1 = v2 - 60.0
        v1 = -20.0
        v2 = 20.0
        # plt.plot([v1,v2], [v1,v2])
        plt.xlim([v1, v2])
        plt.ylim([v1, v2])


        plt.figure(self.verboseFigs[2].number)
        # Cross plot of the proposal ratios coloured by a change in dimension
        plt.sca(self.verboseAxs[14])
        plt.cla()
        y = StatArray.StatArray(self.ratioComponents[4, :], 'Current Proposal')
        x = StatArray.StatArray(self.ratioComponents[5, :], 'Candidate Proposal')
        x[~self.dimensionChange].plot(x = y[~self.dimensionChange], linestyle='', marker='.', color='k', alpha=0.3)
        x[self.dimensionChange].plot(x = y[self.dimensionChange], linestyle='', marker='.', alpha=0.3)
        # v1 = np.maximum(np.minimum(np.nanmin(x), np.nanmin(y)), -200.0)
        # v2 = np.maximum(np.nanmax(x), np.nanmax(y)) + 10.0
        # v1 = v2 - 60.0

        # plt.plot([v1,v2], [v1,v2])
        plt.xlim([v1, v2])
        plt.ylim([v1, v2])
        plt.title('black = no dimension change')

        plt.figure(self.verboseFigs[3].number)
        # Proposal ratio vs iteration
        plt.sca(self.verboseAxs[18])
        plt.cla()
        r = x - y
        r[~self.accepted].plot(x = irna, marker='o', markersize=1, linestyle='None', alpha=0.3, color='k')
        r[self.accepted].plot(x = ira, marker='o', markersize=1, linestyle='None', alpha=0.3)
        cP.ylabel('Proposal Ratio')
        plt.ylim([v1, v2])

        # Acceptance ratio vs iteration
        plt.sca(self.verboseAxs[19])
        plt.cla()
        x = StatArray.StatArray(self.ratioComponents[6, :], 'Acceptance Ratio')
        x[~self.accepted].plot(x = irna, marker='o', markersize=1, linestyle='None', alpha=0.3, color='k')
        x[self.accepted].plot(x = ira, marker='o', markersize=1, linestyle='None', alpha=0.3)
        plt.ylim([-20.0, 20.0])


        for fig in self.verboseFigs:
            fig.canvas.draw()
            fig.canvas.flush_events()

