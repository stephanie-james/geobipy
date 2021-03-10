""" @FdemSystem_Class
Module describing a frequency domain EM acquisition system
"""
from cached_property import cached_property
from copy import deepcopy
from ...classes.core.myObject import myObject
import numpy as np
from ...classes.core import StatArray
from .EmLoop import EmLoop
from .CircularLoop import CircularLoop
from ...base import fileIO as fIO
from ...base import MPI as myMPI
from ...base import customFunctions as cF


class FdemSystem(myObject):
    """ Defines a Frequency Domain ElectroMagnetic acquisition system """

    def __init__(self, frequencies=None, transmitterLoops = None, receiverLoops=None):
        """ Initialize an FdemSystem """

        # StatArray of frequencies
        if frequencies is None:
            return

        self.frequencies = frequencies
        self.transmitterLoops = transmitterLoops
        self.receiverLoops = receiverLoops

        # StatArray of Loop Separations
        self.loopOffsets = StatArray.StatArray((self.nFrequencies, 3), "loopOffsets", "m")
        for i, (t, r) in enumerate(zip(transmitterLoops, receiverLoops)):
            self.loopOffsets[i, :] = [r.x - t.x, r.y - t.y, r.z - t.z]

        self._w0 = None
        self._lamda0 = None
        self._lamda02 = None
        self._w1 = None
        self._lamda1 = None
        self._lamda12 = None


    @property
    def frequencies(self):
        return self._frequencies

    @frequencies.setter
    def frequencies(self, values):
        self._frequencies = StatArray.StatArray(values, "Frequencies", "Hz", dtype=np.float64)

    @property
    def loopOffsets(self):
        return self._loopOffsets

    @loopOffsets.setter
    def loopOffsets(self, values):
        assert np.ndim(values) == 2, ValueError("loopOffsets must be 2D with shape (nFrequencies, 3) for offsets in x, y, and z.")
        assert np.size(values, 0) == self.nFrequencies and np.size(values, 1) == 3 , ValueError("loopOffsets must be 2D with shape (nFrequencies, 3) for offsets in x, y, and z.")
        self._loopOffsets = StatArray.StatArray(values, "loopOffsets", "m")

    @property
    def loopSeparation(self):
        return np.linalg.norm(self.loopOffsets, axis=1)

    @property
    def nFrequencies(self):
        return self.frequencies.size


    @cached_property
    def lamda0(self):
        a0 = np.float64(-8.3885)
        s0 = np.float64(9.04226468670e-2)

        tmp = np.arange(120, dtype = np.float64)

        r = 1.0 / self.loopSeparation

        lamda0 = np.empty([self.nFrequencies, 120], dtype=np.float64)

        l0 = (10.0 ** ((tmp * s0) + a0))

        for i in range(self.nFrequencies):
            lamda0[i, :] = l0 * r[i]

        return lamda0


    @cached_property
    def lamda1(self):
        a1 = np.float64(-7.91001919)
        s1 = np.float64(8.7967143957e-2)

        tmp = np.arange(140, dtype = np.float64)

        r = 1.0 / self.loopSeparation

        lamda1 = np.empty([self.nFrequencies, 140], dtype=np.float64)

        l1 = (10.0 ** ((tmp * s1) + a1))

        for i in range(self.nFrequencies):
            lamda1[i, :] = l1 * r[i]

        return lamda1


    @cached_property
    def lamda02(self):
        return self.lamda0**2.0

    @cached_property
    def lamda12(self):
        return self.lamda1**2.0

    @property
    def receiverLoops(self):
        return self._receiverLoops

    @receiverLoops.setter
    def receiverLoops(self, values):
        assert np.size(values) == self.nFrequencies, ValueError("receiverLoops must have size {}".format(self.nFrequencies))
        assert all([isinstance(x, EmLoop) for x in values]), TypeError("receiverLoops must have type geobipy.EmLoop")
        self._receiverLoops = []
        for i in range(self.nFrequencies):
            self._receiverLoops.append(values[i].deepcopy())

    @property
    def transmitterLoops(self):
        return self._transmitterLoops

    @transmitterLoops.setter
    def transmitterLoops(self, values):
        assert np.size(values) == self.nFrequencies, ValueError("transmitterLoops must have size {}".format(self.nFrequencies))
        assert all([isinstance(x, EmLoop) for x in values]), TypeError("transmitterLoops must have type geobipy.EmLoop")
        self._transmitterLoops = []
        for i in range(self.nFrequencies):
            self._transmitterLoops.append(values[i].deepcopy())


    def deepcopy(self):
        return deepcopy(self)


    def __deepcopy__(self, memo):
        return FdemSystem(self.frequencies, self.transmitterLoops, self.receiverLoops, self.fileName)


    def read(self, fileName):
        """ Read in a file containing the system information

        The system file is structured using columns with the first line containing header information
        Each subsequent row contains the information for each measurement frequency
        freq  tor  tmom  tx ty tz ror rmom  rx   ry rz
        378   z    1     0  0  0  z   1     7.93 0  0
        1776  z    1     0  0  0  z   1     7.91 0  0
        ...

        where tor and ror are the orientations of the transmitter/reciever loops [x or z].
        tmom and rmom are the moments of the loops.
        t/rx,y,z are the loop offsets from the observation locations in the data file.

        """

        nFrequencies = fIO.getNlines(fileName, 1)
        frequencies = np.empty(nFrequencies)
        transmitters = []
        receivers = []
        with open(fileName) as f:
            tmp = f.readline().lower().split()

            assert 'freq' in tmp, ('Cannot read headers from FdemSystem File ' + fileName +
                                   '\nFirst line of system file should contain\nfreq tor tmom  tx ty tzoff ror rmom  rx   ry rzoff')
            for j, line in enumerate(f):  # For each line in the file
                line = fIO.parseString(line)
                frequencies[j] = np.float64(line[0])
                T = (CircularLoop(
                        line[1],
                        np.int(line[2]),
                        np.int(line[3]),
                        np.float64(line[4]),
                        np.float64(line[5])))
                R = (CircularLoop(
                        line[6],
                        np.int(line[7]),
                        np.float64(line[8]),
                        np.float64(line[9]),
                        np.float64(line[10])))
                transmitters.append(T)
                receivers.append(R)
        self.__init__(frequencies, transmitters, receivers)
        return self


    def fileInformation(self):
        """Description of the system file."""
        tmp = "The system file is structured using columns with the first line containing header information \n"
        "Each subsequent row contains the information for each measurement frequency \n"
        "freq  tor  tmom  tx ty tz ror rmom  rx   ry rz \n"
        "378   z    1     0  0  0  z   1     7.93 0  0 \n"
        "1776  z    1     0  0  0  z   1     7.91 0  0 \n"
        "... \n"
        "\n"
        "where tor and ror are the orientations of the transmitter/reciever loops [x or z]. \n"
        "tmom and rmom are the moments of the loops. \n"
        "t/rx,y,z are the loop offsets from the observation locations in the data file. \n"
        return tmp


    def getTensorID(self):
        """ For each coil orientation pair, adds the index of the frequency to the appropriate list
        e.g. two coils at the i$^{th}$ frequency with 'x' as their orientation cause i to be added to the 'xx' list."""
        tid = np.zeros(self.nFrequencies, dtype=np.int32)
        for i in range(self.nFrequencies):
            if ((self.transmitterLoops[i].orient == 'x') and self.receiverLoops[i].orient == 'x'):
                tid[i] = 1
            if ((self.transmitterLoops[i].orient == 'x') and self.receiverLoops[i].orient == 'y'):
                tid[i] = 2
            if ((self.transmitterLoops[i].orient == 'x') and self.receiverLoops[i].orient == 'z'):
                tid[i] = 3
            if ((self.transmitterLoops[i].orient == 'y') and self.receiverLoops[i].orient == 'x'):
                tid[i] = 4
            if ((self.transmitterLoops[i].orient == 'y') and self.receiverLoops[i].orient == 'y'):
                tid[i] = 5
            if ((self.transmitterLoops[i].orient == 'y') and self.receiverLoops[i].orient == 'z'):
                tid[i] = 6
            if ((self.transmitterLoops[i].orient == 'z') and self.receiverLoops[i].orient == 'x'):
                tid[i] = 7
            if ((self.transmitterLoops[i].orient == 'z') and self.receiverLoops[i].orient == 'y'):
                tid[i] = 8
            if ((self.transmitterLoops[i].orient == 'z') and self.receiverLoops[i].orient == 'z'):
                tid[i] = 9
        return tid


    def getComponentID(self):
        """ For each coil orientation pair, adds the index of the frequency to the appropriate list
        e.g. two coils at the i$^{th}$ frequency with 'x' as their orientation cause i to be added to the 'xx' list."""
        xx, xy, xz, yx, yy, yz, zx, zy, zz = ([] for i in range(9))
        for i in range(self.nFrequencies):
            if ((self.transmitterLoops[i].orient == 'x') and self.receiverLoops[i].orient == 'x'):
                xx.append(i)
            if ((self.transmitterLoops[i].orient == 'x') and self.receiverLoops[i].orient == 'y'):
                xy.append(i)
            if ((self.transmitterLoops[i].orient == 'x') and self.receiverLoops[i].orient == 'z'):
                xz.append(i)
            if ((self.transmitterLoops[i].orient == 'y') and self.receiverLoops[i].orient == 'x'):
                yx.append(i)
            if ((self.transmitterLoops[i].orient == 'y') and self.receiverLoops[i].orient == 'y'):
                yy.append(i)
            if ((self.transmitterLoops[i].orient == 'y') and self.receiverLoops[i].orient == 'z'):
                yz.append(i)
            if ((self.transmitterLoops[i].orient == 'z') and self.receiverLoops[i].orient == 'x'):
                zx.append(i)
            if ((self.transmitterLoops[i].orient == 'z') and self.receiverLoops[i].orient == 'y'):
                zy.append(i)
            if ((self.transmitterLoops[i].orient == 'z') and self.receiverLoops[i].orient == 'z'):
                zz.append(i)
        return np.asarray(xx), np.asarray(xy), np.asarray(xz), np.asarray(yx), np.asarray(yy), np.asarray(yz), np.asarray(zx), np.asarray(zy), np.asarray(zz)

    @property
    def summary(self):
        """ print a summary of the FdemSystem """
        msg = ("FdemSystem: \n"
               "{} \n"
               "{} \n"
               "{} \n").format(self._fileName, self.frequencies.summary, self.loopOffsets.summary)
        return msg


    def toHdf(self, h5obj, name):
        """ Write the object to a HDF file """
        # Create a new group inside h5obj
        grp = self.create_hdf_group(h5obj, name)
        grp.create_dataset('nFreq', data=self.nFrequencies)
        self._frequencies.toHdf(grp, 'freq')
        self.loopOffsets.toHdf(grp, 'loopoffsets')
        T = grp.create_group('T')
        R = grp.create_group('R')
        for i in range(self.nFrequencies):
            self.transmitterLoops[i].toHdf(T, 'T{}'.format(i))
            self.receiverLoops[i].toHdf(R, 'R{}'.format(i))


    def fromHdf(self, grp):
        """ Reads the object from a HDF file """
        nFreq = np.int(np.array(grp.get('nFreq')))
        frequencies = StatArray.StatArray().fromHdf(grp['freq'])

        if 'loopoffsets' in grp:
            loopOffsets = StatArray.StatArray().fromHdf(grp['loopoffsets'])
        else:
            loopOffsets = StatArray.StatArray().fromHdf(grp['dist'])

        transmitterLoops = []
        receiverLoops = []
        for i in range(nFreq):
            transmitterLoops.append(eval(cF.safeEval(grp['T/T{}'.format(i)].attrs.get('repr'))))
            receiverLoops.append(eval(cF.safeEval(grp['R/R{}'.format(i)].attrs.get('repr'))))

        self.__init__(frequencies, transmitterLoops, receiverLoops)

        self.loopOffsets = loopOffsets

        return self


    def Bcast(self, world, root=0):
        """ Broadcast the FdemSystem using MPI """
        nFreq = myMPI.Bcast(self.nFrequencies, world, root=root)
        if (world.rank > 0):
            self = FdemSystem(nFreq)
        this = FdemSystem(nFreq)
        this._frequencies = self._frequencies.Bcast(world, root=root)
        this.loopSeparation = self.loopSeparation.Bcast(world, root=root)
        for i in range(self.nFrequencies):
            this.transmitterLoops[i] = self.transmitterLoops[i].Bcast(world, root=root)
            this.receiverLoops[i] = self.receiverLoops[i].Bcast(world, root=root)
        return this


    def Isend(self, dest, world):
        myMPI.Isend(self.nFrequencies, dest=dest, world=world)
        self.frequencies.Isend(dest=dest, world=world)
        # self.loopOffsets.Isend(dest=dest, world=world)
        for i in range(self.nFrequencies):
            self.transmitterLoops[i].Isend(dest=dest, world=world)
            self.receiverLoops[i].Isend(dest=dest, world=world)


    def Irecv(self, source, world):
        nFreq = myMPI.Irecv(source=source, world=world)

        x = StatArray.StatArray()
        frequencies = x.Irecv(source=source, world=world)
        # out.loopOffsets = out.loopOffsets.Irecv(source=source, world=world)
        transmitterLoops = []
        receiverLoops = []
        x = CircularLoop()
        for i in range(nFreq):
            transmitterLoops.append(x.Irecv(source=source, world=world))
            receiverLoops.append(x.Irecv(source=source, world=world))

        return FdemSystem(frequencies, transmitterLoops, receiverLoops)


    @cached_property
    def w0(self):
        return np.asarray([
        9.62801364263e-07, -5.02069203805e-06, 1.25268783953e-05, -1.99324417376e-05, 2.29149033546e-05,
        -2.04737583809e-05, 1.49952002937e-05, -9.37502840980e-06, 5.20156955323e-06, -2.62939890538e-06,
        1.26550848081e-06, -5.73156151923e-07, 2.76281274155e-07, -1.09963734387e-07, 7.38038330280e-08,
        -9.31614600001e-09, 3.87247135578e-08, 2.10303178461e-08, 4.10556513877e-08, 4.13077946246e-08,
        5.68828741789e-08, 6.59543638130e-08, 8.40811858728e-08, 1.01532550003e-07, 1.26437360082e-07,
        1.54733678097e-07, 1.91218582499e-07, 2.35008851918e-07, 2.89750329490e-07, 3.56550504341e-07,
        4.39299297826e-07, 5.40794544880e-07, 6.66136379541e-07, 8.20175040653e-07, 1.01015545059e-06,
        1.24384500153e-06, 1.53187399787e-06, 1.88633707689e-06, 2.32307100992e-06, 2.86067883258e-06,
        3.52293208580e-06, 4.33827546442e-06, 5.34253613351e-06, 6.57906223200e-06, 8.10198829111e-06,
        9.97723263578e-06, 1.22867312381e-05, 1.51305855976e-05, 1.86329431672e-05, 2.29456891669e-05,
        2.82570465155e-05, 3.47973610445e-05, 4.28521099371e-05, 5.27705217882e-05, 6.49856943660e-05,
        8.00269662180e-05, 9.85515408752e-05, 1.21361571831e-04, 1.49454562334e-04, 1.84045784500e-04,
        2.26649641428e-04, 2.79106748890e-04, 3.43716968725e-04, 4.23267056591e-04, 5.21251001943e-04,
        6.41886194381e-04, 7.90483105615e-04, 9.73420647376e-04, 1.19877439042e-03, 1.47618560844e-03,
        1.81794224454e-03, 2.23860214971e-03, 2.75687537633e-03, 3.39471308297e-03, 4.18062141752e-03,
        5.14762977308e-03, 6.33918155348e-03, 7.80480111772e-03, 9.61064602702e-03, 1.18304971234e-02,
        1.45647517743e-02, 1.79219149417e-02, 2.20527911163e-02, 2.71124775541e-02, 3.33214363101e-02,
        4.08864842127e-02, 5.01074356716e-02, 6.12084049407e-02, 7.45146949048e-02, 9.00780900611e-02,
        1.07940155413e-01, 1.27267746478e-01, 1.46676027814e-01, 1.62254276550e-01, 1.68045766353e-01,
        1.52383204788e-01, 1.01214136498e-01, -2.44389126667e-03, -1.54078468398e-01, -3.03214415655e-01,
        -2.97674373379e-01, 7.93541259524e-03, 4.26273267393e-01, 1.00032384844e-01, -4.94117404043e-01,
        3.92604878741e-01, -1.90111691178e-01, 7.43654896362e-02, -2.78508428343e-02, 1.09992061155e-02,
        -4.69798719697e-03, 2.12587632706e-03, -9.81986734159e-04, 4.44992546836e-04, -1.89983519162e-04,
        7.31024164292e-05, -2.40057837293e-05, 6.23096824846e-06, -1.12363896552e-06, 1.04470606055e-07], dtype=np.float64)

    @cached_property
    def w1(self):
        return np.asarray([
        -6.76671159511e-14, 3.39808396836e-13, -7.43411889153e-13, 8.93613024469e-13, -5.47341591896e-13,
        -5.84920181906e-14, 5.20780672883e-13, -6.92656254606e-13, 6.88908045074e-13, -6.39910528298e-13,
        5.82098912530e-13, -4.84912700478e-13, 3.54684337858e-13, -2.10855291368e-13, 1.00452749275e-13,
        5.58449957721e-15, -5.67206735175e-14, 1.09107856853e-13, -6.04067500756e-14, 8.84512134731e-14,
        2.22321981827e-14, 8.38072239207e-14, 1.23647835900e-13, 1.44351787234e-13, 2.94276480713e-13,
        3.39965995918e-13, 6.17024672340e-13, 8.25310217692e-13, 1.32560792613e-12, 1.90949961267e-12,
        2.93458179767e-12, 4.33454210095e-12, 6.55863288798e-12, 9.78324910827e-12, 1.47126365223e-11,
        2.20240108708e-11, 3.30577485691e-11, 4.95377381480e-11, 7.43047574433e-11, 1.11400535181e-10,
        1.67052734516e-10, 2.50470107577e-10, 3.75597211630e-10, 5.63165204681e-10, 8.44458166896e-10,
        1.26621795331e-09, 1.89866561359e-09, 2.84693620927e-09, 4.26886170263e-09, 6.40104325574e-09,
        9.59798498616e-09, 1.43918931885e-08, 2.15798696769e-08, 3.23584600810e-08, 4.85195105813e-08,
        7.27538583183e-08, 1.09090191748e-07, 1.63577866557e-07, 2.45275193920e-07, 3.67784458730e-07,
        5.51470341585e-07, 8.26916206192e-07, 1.23991037294e-06, 1.85921554669e-06, 2.78777669034e-06,
        4.18019870272e-06, 6.26794044911e-06, 9.39858833064e-06, 1.40925408889e-05, 2.11312291505e-05,
        3.16846342900e-05, 4.75093313246e-05, 7.12354794719e-05, 1.06810848460e-04, 1.60146590551e-04,
        2.40110903628e-04, 3.59981158972e-04, 5.39658308918e-04, 8.08925141201e-04, 1.21234066243e-03,
        1.81650387595e-03, 2.72068483151e-03, 4.07274689463e-03, 6.09135552241e-03, 9.09940027636e-03,
        1.35660714813e-02, 2.01692550906e-02, 2.98534800308e-02, 4.39060697220e-02, 6.39211368217e-02,
        9.16763946228e-02, 1.28368795114e-01, 1.73241920046e-01, 2.19830379079e-01, 2.51193131178e-01,
        2.32380049895e-01, 1.17121080205e-01, -1.17252913088e-01, -3.52148528535e-01, -2.71162871370e-01,
        2.91134747110e-01, 3.17192840623e-01, -4.93075681595e-01, 3.11223091821e-01, -1.36044122543e-01,
        5.12141261934e-02, -1.90806300761e-02, 7.57044398633e-03, -3.25432753751e-03, 1.49774676371e-03,
        -7.24569558272e-04, 3.62792644965e-04, -1.85907973641e-04, 9.67201396593e-05, -5.07744171678e-05,
        2.67510121456e-05, -1.40667136728e-05, 7.33363699547e-06, -3.75638767050e-06, 1.86344211280e-06,
        -8.71623576811e-07, 3.61028200288e-07, -1.05847108097e-07, -1.51569361490e-08, 6.67633241420e-08,
        -8.33741579804e-08, 8.31065906136e-08, -7.53457009758e-08, 6.48057680299e-08, -5.37558016587e-08,
        4.32436265303e-08, -3.37262648712e-08, 2.53558687098e-08, -1.81287021528e-08, 1.20228328586e-08,
        -7.10898040664e-09, 3.53667004588e-09, -1.36030600198e-09, 3.52544249042e-10, -4.53719284366e-11], dtype=np.float64)