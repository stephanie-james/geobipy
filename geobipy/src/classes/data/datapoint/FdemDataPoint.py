""" @FdemDataPoint_Class
Module describing a frequency domain EMData Point that contains a single measurement.
"""
from copy import copy, deepcopy
from ....classes.core import StatArray
from ...forwardmodelling.Electromagnetic.FD.fdem1d import fdem1dfwd, fdem1dsen
from .EmDataPoint import EmDataPoint
from ...model.Model import Model
from ...model.Model1D import Model1D
from ...statistics.Histogram2D import Histogram2D
from ....base.logging import myLogger
from ...system.FdemSystem import FdemSystem
import matplotlib.pyplot as plt
import numpy as np
#from ....base import Error as Err
from ....base import utilities as cf
from ....base import MPI as myMPI
from ....base import plotting as cp


class FdemDataPoint(EmDataPoint):
    """Class defines a Frequency domain electromagnetic data point.

    Contains an easting, northing, height, elevation, observed and predicted data, and uncertainty estimates for the data.

    FdemDataPoint(x, y, z, elevation, data, std, system, lineNumber, fiducial)

    Parameters
    ----------
    x : float
        Easting co-ordinate of the data point
    y : float
        Northing co-ordinate of the data point
    z : float
        Height above ground of the data point
    elevation : float, optional
        Elevation from sea level of the data point
    data : geobipy.StatArray or array_like, optional
        Data values to assign the data of length 2*number of frequencies.
        * If None, initialized with zeros.
    std : geobipy.StatArray or array_like, optional
        Estimated uncertainty standard deviation of the data of length 2*number of frequencies.
        * If None, initialized with ones if data is None, else 0.1*data values.
    system : str or geobipy.FdemSystem, optional
        Describes the acquisition system with loop orientation and frequencies.
        * If str should be the path to a system file to read in.
        * If geobipy.FdemSystem, will be deepcopied.
    lineNumber : float, optional
        The line number associated with the datapoint
    fiducial : float, optional
        The fiducial associated with the datapoint

    """

    def __init__(self, x=0.0, y=0.0, z=0.0, elevation=0.0, data=None, std=None, predictedData=None, system=None, lineNumber=0.0, fiducial=0.0):
        """Define initializer. """

        self.units = None

        self._system = None
        if (system is None):
            return super().__init__(x=x, y=y, z=z, elevation=elevation)

        self.system = system

        super().__init__(x=x, y=y, z=z, elevation=elevation, channels_per_system=2*self.nFrequencies, components_per_channel=None, data=data, std=std, predictedData=predictedData, lineNumber=lineNumber, fiducial=fiducial)

        self._data.name = 'Frequency domain data'

        # StatArray of calibration parameters
        # The four columns are Bias,Variance,InphaseBias,QuadratureBias.
        self.calibration = StatArray.StatArray([self.nChannels * 2], 'Calibration Parameters')

        self.channelNames = None


    def __deepcopy__(self, memo={}):
        out = super().__deepcopy__(memo)
        out._system = self._system
        # out.calibration = deepcopy(self.calibration)
        return out

    @property
    def units(self):
        return self._units

    @units.setter
    def units(self, value):
        if value is None:
            value = "ppm"
        else:
            assert isinstance(value, str), TypeError("units must have type str")
        self._units = value

    @property
    def system(self):
        return self._system

    @system.setter
    def system(self, value):

        if isinstance(value, (str, FdemSystem)):
            value = [value]

        assert all((isinstance(sys, (str, FdemSystem)) for sys in value)), TypeError("System must have items of type str or geobipy.FdemSystem")

        systems = []
        for j, sys in enumerate(value):
            if (isinstance(sys, str)):
                systems.append(FdemSystem().read(sys))
            elif (isinstance(sys, FdemSystem)):
                systems.append(sys)

        self._system = systems


    @property
    def channelNames(self):
        return self._channelNames


    @channelNames.setter
    def channelNames(self, values):
        if values is None:
            if self.system is None:
                self._channelNames = ['None']
                return
            self._channelNames = []
            for i in range(self.nSystems):
                # Set the channel names
                if not self.system[i] is None:
                    for iFrequency in range(2*self.nFrequencies[i]):
                        self._channelNames.append('{} {} (Hz)'.format(self.getMeasurementType(iFrequency, i), self.getFrequency(iFrequency, i)))
        else:
            assert all((isinstance(x, str) for x in values))
            assert len(values) == self.nChannels, Exception("Length of channelNames must equal total number of channels {}".format(self.nChannels))
            self._channelNames = values

    @property
    def nFrequencies(self):
        return np.asarray([x.nFrequencies for x in self.system])

    @property
    def channels(self):
        return np.squeeze(np.asarray([np.tile(self.frequencies(i), 2) for i in range(self.nSystems)]))


    def _inphaseIndices(self, system=0):
        """The slice indices for the requested in-phase data.

        Parameters
        ----------
        system : int
            Requested system index.

        Returns
        -------
        out : numpy.slice
            The slice pertaining to the requested system.

        """

        assert system < self.nSystems, ValueError("system must be < nSystems {}".format(self.nSystems))

        return np.s_[self.systemOffset[system]:self.systemOffset[system] + self.nFrequencies[system]]


    def _quadratureIndices(self, system=0):
        """The slice indices for the requested in-phase data.

        Parameters
        ----------
        system : int
            Requested system index.

        Returns
        -------
        out : numpy.slice
            The slice pertaining to the requested system.

        """

        assert system < self.nSystems, ValueError("system must be < nSystems {}".format(self.nSystems))

        return np.s_[self.systemOffset[system] + self.nFrequencies[system]: 2*self.nFrequencies[system]]


    def frequencies(self, system=0):
        """ Return the frequencies in an StatArray """
        return StatArray.StatArray(self.system[system].frequencies, name='Frequency', units='Hz')


    def inphase(self, system=0):
        return self.data[self._inphaseIndices(system)]


    def inphaseStd(self, system=0):
        return self.std[self._inphaseIndices(system)]

    # @property
    # def nFrequencies(self):
    #     return np.int32(0.5*self.nChannelsPerSystem)

    def predictedInphase(self, system=0):
        return self.predictedData[self._inphaseIndices(system)]

    def predictedQuadrature(self, system=0):
        return self.predictedData[self._quadratureIndices(system)]

    def quadrature(self, system=0):
        return self.data[self._quadratureIndices(system)]

    def quadratureStd(self, system=0):
        return self.std[self._quadratureIndices(system)]

    def getMeasurementType(self, channel, system=0):
        """Returns the measurement type of the channel

        Parameters
        ----------
        channel : int
            Channel number
        system : int, optional
            System number

        Returns
        -------
        out : str
            Either "In-Phase " or "Quadrature "

        """
        return 'In-Phase' if channel < self.nFrequencies[system] else 'Quadrature'

    def getFrequency(self, channel, system=0):
        """Return the measurement frequency of the channel

        Parameters
        ----------
        channel : int
            Channel number
        system : int, optional
            System number

        Returns
        -------
        out : float
            The measurement frequency of the channel

        """
        return self.system[system].frequencies[channel%self.nFrequencies[system]]

    def set_priors(self, height_prior=None, data_prior=None, relative_error_prior=None, additive_error_prior=None):

        super().set_priors(height_prior, relative_error_prior, additive_error_prior)

        if not data_prior is None:
            self.predictedData.set_prior(data_prior)

    def set_predicted_data_posterior(self):
        if self.predictedData.hasPrior:
            freqs = np.log10(self.frequencies())
            data = np.log10(self.data[self.active])
            a = data.min()
            b = data.max()

            xbuf = 0.05*(freqs[-1] - freqs[0])
            xbins = StatArray.StatArray(np.logspace(freqs[0]-xbuf, freqs[-1]+xbuf, 200), freqs.name, freqs.units)
            buf = 0.5*(b - a)
            ybins = StatArray.StatArray(np.logspace(a-buf, b+buf, 200), data.name, data.units)
            # rto = 0.5 * (ybins[0] + ybins[-1])
            # ybins -= rto

            H = Histogram2D(xEdges=xbins, xlog=10, yEdges=ybins, ylog=10)

            self.predictedData.setPosterior(H)


    def createHdf(self, parent, name, withPosterior=True, nRepeats=None, fillvalue=None):
        """ Create the hdf group metadata in file
        parent: HDF object to create a group inside
        myName: Name of the group
        """
        grp = super().createHdf(parent, name, withPosterior, nRepeats, fillvalue)
        # self.calibration.createHdf(grp, 'calibration', withPosterior=withPosterior, nRepeats=nRepeats, fillvalue=fillvalue)

        self.system[0].toHdf(grp, 'sys')

        return grp

    # def writeHdf(self, parent, name, withPosterior=True, index=None):
    #     """ Write the StatArray to an HDF object
    #     parent: Upper hdf file or group
    #     myName: object hdf name. Assumes createHdf has already been called
    #     create: optionally create the data set as well before writing
    #     """
    #     super().writeHdf(parent, name, withPosterior, index)

    #     grp = parent[name]

        # self.calibration.writeHdf(grp, 'calibration',  withPosterior=withPosterior, index=index)

    @classmethod
    def fromHdf(cls, grp, index=None, **kwargs):
        """ Reads the object from a HDF group """

        system = FdemSystem.fromHdf(grp['sys'])

        out = super(FdemDataPoint, cls).fromHdf(grp, index)

        out.system = system
        out._channels_per_system = out.nFrequencies

        return out


    def calibrate(self, Predicted=True):
        """ Apply calibration factors to the data point """
        # Make complex numbers from the data
        if (Predicted):
            tmp = cf.mergeComplex(self._predictedData)
        else:
            tmp = cf.mergeComplex(self._data)

        # Get the calibration factors for each frequency
        i1 = 0
        i2 = self.nFrequencies
        G = self.calibration[i1:i2]
        i1 += self.nFrequencies
        i2 += self.nFrequencies
        Phi = self.calibration[i1:i2]
        i1 += self.nFrequencies
        i2 += self.nFrequencies
        Bi = self.calibration[i1:i2]
        i1 += self.nFrequencies
        i2 += self.nFrequencies
        Bq = self.calibration[i1:i2]

        # Calibrate the data
        tmp[:] = G * np.exp(1j * Phi) * tmp + Bi + (1j * Bq)

        # Split the complex numbers back out
        if (Predicted):
            self._predictedData[:] = cf.splitComplex(tmp)
        else:
            self._data[:] = cf.splitComplex(tmp)


    def plot(self, title='Frequency Domain EM Data', system=0,  with_error_bars=True, **kwargs):
        """ Plot the Inphase and Quadrature Data

        Parameters
        ----------
        title : str
            Title of the plot
        system : int
            If multiple system are present, select which one
        with_error_bars : bool
            Plot vertical lines representing 1 standard deviation

        See Also
        --------
        matplotlib.pyplot.errorbar : For more keyword arguements

        Returns
        -------
        out : matplotlib.pyplot.ax
            Figure axis

        """
        ax = kwargs.pop('ax', None)
        if not ax is None:
            plt.sca(ax)
        else:
            ax = plt.gca()
        plt.cla()
        cp.pretty(ax)

        cp.xlabel('Frequency (Hz)')
        cp.ylabel('Frequency domain data (ppm)')
        cp.title(title)

        inColor = kwargs.pop('incolor', cp.wellSeparated[0])
        quadColor = kwargs.pop('quadcolor', cp.wellSeparated[1])
        im = kwargs.pop('inmarker', 'v')
        qm = kwargs.pop('quadmarker', 'o')
        kwargs['markersize'] = kwargs.pop('markersize', 7)
        kwargs['markeredgecolor'] = kwargs.pop('markeredgecolor', 'k')
        kwargs['markeredgewidth'] = kwargs.pop('markeredgewidth', 1.0)
        kwargs['alpha'] = kwargs.pop('alpha', 0.8)
        kwargs['linestyle'] = kwargs.pop('linestyle', 'none')
        kwargs['linewidth'] = kwargs.pop('linewidth', 2)

        xscale = kwargs.pop('xscale','log')
        yscale = kwargs.pop('yscale','log')

        f = self.frequencies(system)

        if with_error_bars:
            plt.errorbar(f, self.inphase(system), yerr=self.inphaseStd(system),
                marker=im, color=inColor, markerfacecolor=inColor, label='In-Phase', **kwargs)

            plt.errorbar(f, self.quadrature(system), yerr=self.quadratureStd(system),
                marker=qm, color=quadColor, markerfacecolor=quadColor, label='Quadrature', **kwargs)
        else:
            plt.plot(f, np.log10(self.inphase(system)),
                marker=im, color=inColor, markerfacecolor=inColor, label='In-Phase', **kwargs)

            plt.plot(f, np.log10(self.quadrature(system)),
                marker=qm, color=quadColor, markerfacecolor=quadColor, label='Quadrature', **kwargs)

        plt.xscale(xscale)
        plt.yscale(yscale)
        plt.legend(fontsize=8)

        return ax


    def plotPredicted(self, title='Frequency Domain EM Data', system=0, **kwargs):
        """ Plot the predicted Inphase and Quadrature Data

        Parameters
        ----------
        title : str
            Title of the plot
        system : int
            If multiple system are present, select which one

        See Also
        --------
        matplotlib.pyplot.semilogx : For more keyword arguements

        Returns
        -------
        out : matplotlib.pyplot.ax
            Figure axis

        """
        ax = kwargs.pop('ax', None)
        if not ax is None:
            plt.sca(ax)
        else:
            ax = plt.gca()
        cp.pretty(ax)

        noLabels = kwargs.pop('nolabels', False)

        if (not noLabels):
            cp.xlabel('Frequency (Hz)')
            cp.ylabel('Data (ppm)')
            cp.title(title)

        c = kwargs.pop('color', cp.wellSeparated[3])
        lw = kwargs.pop('linewidth', 2)
        a = kwargs.pop('alpha', 0.7)

        xscale = kwargs.pop('xscale','log')
        yscale = kwargs.pop('yscale','log')

        plt.semilogx(self.frequencies(system), self.predictedInphase(system), color=c, linewidth=lw, alpha=a, **kwargs)
        plt.semilogx(self.frequencies(system), self.predictedQuadrature(system), color=c, linewidth=lw, alpha=a, **kwargs)

        plt.xscale(xscale)
        plt.yscale(yscale)

        return ax

    def updatePosteriors(self):
        super().updatePosteriors()


    def updateSensitivity(self, model):
        """ Compute an updated sensitivity matrix based on the one already containined in the FdemDataPoint object  """
        self.J = self.sensitivity(model)


    def FindBestHalfSpace(self, minConductivity=1e-6, maxConductivity=1e2, percentThreshold=1.0, maxIterations=100):
        """Uses the bisection approach to find a half space conductivity that best matches the EM data by minimizing the data misfit

        Parameters
        ----------
        minConductivity : float
            Minimum conductivity to start the search
        maxConductivity : float
            Maximum conductivity to start the search
        percentThreshold : float, optional
            Stopping criteria for the relative change in data fit
        maxIterations : int, optional
            Stop after this number of iterations

        Returns
        -------
        out : geobipy.Model1D
            Best fitting halfspace model

        """
        percentThreshold = 0.01 * percentThreshold
        c0 = np.log10(minConductivity)
        c1 = np.log10(maxConductivity)
        cnew = 0.5 * (c0 + c1)
        # Initialize a single layer model
        p = StatArray.StatArray(1, 'Conductivity', r'$\frac{S}{m}$')
        model = Model1D(nCells=1, edges=np.asarray([0.0, np.inf]), parameters=p)
        # Initialize the first conductivity
        model._par[0] = 10.0**c0
        self.forward(model)  # Forward model the EM data
        PhiD1 = self.dataMisfit(squared=True)  # Compute the measure between observed and predicted data
        # Initialize the second conductivity
        model._par[0] = 10.0**c1
        self.forward(model)  # Forward model the EM data
        PhiD2 = self.dataMisfit(squared=True)  # Compute the measure between observed and predicted data
        # Compute a relative change in the data misfit
        dPhiD = abs(PhiD2 - PhiD1) / PhiD2
        i = 1
        # Continue until there is less than 1% change
        while (dPhiD > percentThreshold and i < maxIterations):
            cnew = 0.5 * (c0 + c1)  # Bisect the conductivities
            model._par[0] = 10.0**cnew
            self.forward(model)  # Forward model the EM data
            PhiDnew = self.dataMisfit(squared=True)
            if (PhiD2 > PhiDnew):
                c1 = cnew
                PhiD2 = PhiDnew
            elif (PhiD1 > PhiDnew):
                c0 = cnew
                PhiD1 = PhiDnew
            dPhiD = abs(PhiD2 - PhiD1) / PhiD2
            i += 1

        return model


    def forward(self, mod):
        """ Forward model the data from the given model """

        assert isinstance(mod, Model1D), TypeError("Invalid model class for forward modeling [1D]")

        self._forward1D(mod)


    def sensitivity(self, mod):
        """ Compute the sensitivty matrix for the given model """

        assert isinstance(mod, Model1D), TypeError("Invalid model class for sensitivity matrix [1D]")

        return StatArray.StatArray(self._sensitivity1D(mod), 'Sensitivity', '$\\frac{ppm.m}{S}$')


    def _forward1D(self, mod):
        """ Forward model the data from a 1D layered earth model """
        assert np.isinf(mod.edges[-1]), ValueError('mod.edges must have last entry be infinity for forward modelling.')
        for i, s in enumerate(self.system):
            tmp = fdem1dfwd(s, mod, self.z[0])
            self._predictedData[:self.nFrequencies[i]] = tmp.real
            self._predictedData[self.nFrequencies[i]:] = tmp.imag


    def _sensitivity1D(self, mod):
        """ Compute the sensitivty matrix for a 1D layered earth model """
        # Re-arrange the sensitivity matrix to Real:Imaginary vertical
        # concatenation
        J = StatArray.StatArray((self.nChannels, np.int(mod.nCells.value)), 'Sensitivity', '$\\frac{ppm.m}{S}$')

        for j, s in enumerate(self.system):
            Jtmp = fdem1dsen(s, mod, self.z[0])
            J[:self.nFrequencies[j], :] = Jtmp.real
            J[self.nFrequencies[j]:, :] = Jtmp.imag

        self.J = J
        return self.J


    def Isend(self, dest, world, systems=None):
        tmp = np.asarray([self.x, self.y, self.z, self.elevation, self.nSystems, self.lineNumber, self.fiducial], dtype=np.float64)
        myMPI.Isend(tmp, dest=dest, ndim=1, shape=(7, ), dtype=np.float64, world=world)

        if systems is None:
            for i in range(self.nSystems):
                self.system[i].Isend(dest=dest, world=world)
        self._data.Isend(dest, world)
        self._std.Isend(dest, world)
        self._predictedData.Isend(dest, world)

    @classmethod
    def Irecv(cls, source, world, systems=None):

        tmp = myMPI.Irecv(source=source, ndim=1, shape=(7, ), dtype=np.float64, world=world)

        if systems is None:
            systems = [FdemSystem.Irecv(source=source, world=world) for i in range(np.int32(tmp[4]))]

        d = StatArray.StatArray.Irecv(source, world)
        s = StatArray.StatArray.Irecv(source, world)
        p = StatArray.StatArray.Irecv(source, world)

        return cls(tmp[0], tmp[1], tmp[2], tmp[3], data=d, std=s, predictedData=p, system=systems, lineNumber=tmp[5], fiducial=tmp[6])


