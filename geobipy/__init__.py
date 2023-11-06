#!/usr/bin/env python
# -- coding: utf-8 --
from os import getcwd
from os import makedirs
import pathlib
import argparse
import sys
import shutil
from datetime import timedelta
from numpy import int32
from numpy.random import Generator

# from .src.base import utilities
from .src.base import plotting
from .src.base.MPI import get_prng
# from .src.base import fileIO
# from .src.base import interpolation

# from .src.base.HDF import hdfRead
# from .src.base.HDF import hdfWrite
# Classes within geobipy
# Core
from .src.classes.core.StatArray import StatArray
# from .src.classes.core.Stopwatch import Stopwatch
# Data points
from .src.classes.data.datapoint.DataPoint import DataPoint
from .src.classes.data.datapoint.EmDataPoint import EmDataPoint
from .src.classes.data.datapoint.FdemDataPoint import FdemDataPoint
from .src.classes.data.datapoint.TdemDataPoint import TdemDataPoint
from .src.classes.data.datapoint.Tempest_datapoint import Tempest_datapoint
# Datasets
from .src.classes.data.dataset.Data import Data
from .src.classes.data.dataset.FdemData import FdemData
from .src.classes.data.dataset.TdemData import TdemData
from .src.classes.data.dataset.TempestData import TempestData
# Systems
from .src.classes.system.FdemSystem import FdemSystem
from .src.classes.system.TdemSystem import TdemSystem
from .src.classes.system.Waveform import Waveform
from .src.classes.system.CircularLoop import CircularLoop
from .src.classes.system.CircularLoops import CircularLoops
from .src.classes.system.SquareLoop import SquareLoop
from .src.classes.system.filters.butterworth import butterworth
# Meshes
from .src.classes.mesh.RectilinearMesh1D import RectilinearMesh1D
from .src.classes.mesh.RectilinearMesh2D import RectilinearMesh2D
from .src.classes.mesh.RectilinearMesh2D_stitched import RectilinearMesh2D_stitched
from .src.classes.mesh.RectilinearMesh3D import RectilinearMesh3D
# Models
from .src.classes.model.Model import Model
# Pointclouds
from .src.classes.pointcloud.PointCloud3D import PointCloud3D
from .src.classes.pointcloud.Point import Point
# Statistics
from .src.classes.statistics.Distribution import Distribution
from .src.classes.statistics.Histogram import Histogram
from .src.classes.statistics.Mixture import Mixture
from .src.classes.statistics.mixStudentT import mixStudentT
from .src.classes.statistics.mixNormal import mixNormal
from .src.classes.statistics.mixPearson import mixPearson
# McMC Inersion
from .src.inversion.Inference1D import Inference1D
from .src.inversion.Inference2D import Inference2D
from .src.inversion.Inference3D import Inference3D
from .src.inversion.user_parameters import user_parameters

# Set an MPI failed tag
dpFailed = 0
# Set an MPI success tag
dpWin = 1
# Set an MPI run tag
run = 2
# Set an MPI exit tag
killSwitch = 9

def checkCommandArguments():
    """Check the users command line arguments. """
    import warnings
    # warnings.filterwarnings('error')

    Parser = argparse.ArgumentParser(description="GeoBIPy",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    Parser.add_argument('options_file', help='User options file')
    Parser.add_argument('output_directory', help='Output directory for results')
    Parser.add_argument('--skip_hdf5', dest='skip_hdf5', default=False, help='Skip the creation of the HDF5 files.  Only do this if you know they have been created.')
    Parser.add_argument('--seed', dest='seed', default=None, help='Specify a seed file to fix the random number generator.')
    Parser.add_argument('--jump', dest='jump', default=None, type=int, help='Specify a number to jump the PRNG by. Only used in serial mode and for debugging purposes.')
    Parser.add_argument('--index', dest='index', type=int, default=None, help='Invert this data point only. Only used in serial mode.')
    Parser.add_argument('--fiducial', dest='fiducial', type=float, default=None, help='Invert this fiducial only. Only used in serial mode.')
    Parser.add_argument('--line', dest='line_number', type=float, default=None, help='Invert the fiducial on this line. Only used in serial mode.')
    Parser.add_argument('--verbose', dest='verbose', action='store_true', help='Throw warnings as errors.')
    Parser.add_argument('--mpi', dest='mpi', action='store_true', help='Run geobipy with MPI libraries.')
    Parser.add_argument('--debug', dest='debug', action='store_true', help='Run geobipy in debug mode.')

    args = Parser.parse_args()

    if args.seed is not None:
        if isinstance(args.seed, str):
            if not '.' in args.seed:
                args.seed = int(args.seed)

    if args.verbose:
        import warnings
        warnings.filterwarnings("error")

    return args

def serial_geobipy(inputFile, output_directory, seed=None, index=None, fiducial=None, line_number=None, debug=False, jump=None):

    from time import time

    print('Running GeoBIPy in serial mode')
    print('Using user input file {}'.format(inputFile))
    print('Output files will be produced at {}'.format(output_directory))

    inputFile = pathlib.Path(inputFile)
    assert inputFile.exists(), Exception("Cannot find input file {}".format(inputFile))

    output_directory = pathlib.Path(output_directory)
    assert output_directory.exists(), Exception("Make sure the output directory exists {}".format(output_directory))

    # Make sure the results folders exist
    makedirs(output_directory, exist_ok=True)

    # Copy the input file to the output directory for reference.
    shutil.copy(inputFile, output_directory)

    options = user_parameters.read(inputFile)

    data = options['data_type']._initialize_sequential_reading(options['data_filename'], options['system_filename'])

    prng = get_prng(seed=seed, jump=jump)

    inference3d = Inference3D(data=data, prng=prng, debug=debug)

    inference3d.create_hdf5(directory=output_directory, **options)

    inference3d.infer(index=index, fiducial=fiducial, line_number=line_number, **options)


def parallel_geobipy(inputFile, outputDir, skipHDF5, seed=None):
    parallel_mpi(inputFile, outputDir, skipHDF5, seed=seed)

def parallel_mpi(inputFile, output_directory, skipHDF5, seed=None):

    from mpi4py import MPI
    from .src.base import MPI as myMPI

    world = MPI.COMM_WORLD
    rank = world.rank
    nRanks = world.size
    masterRank = rank == 0

    myMPI.rankPrint(world,'Running GeoBIPy in parallel mode with {} cores'.format(nRanks))
    myMPI.rankPrint(world,'Using user input file {}'.format(inputFile))
    myMPI.rankPrint(world,'Output files will be produced at {}'.format(output_directory))

    inputFile = pathlib.Path(inputFile)
    assert inputFile.exists(), Exception("Cannot find input file {}".format(inputFile))

    output_directory = pathlib.Path(output_directory)
    assert output_directory.exists(), Exception("Make sure the output directory exists {}".format(output_directory))

    kwargs = user_parameters.read(inputFile)

    # Everyone needs the system classes read in early.
    data = kwargs['data_type']._initialize_sequential_reading(kwargs['data_filename'], kwargs['system_filename'])


    # Get the number of points in the file.
    if masterRank:
        # Copy the user_parameter file to the output directory
        shutil.copy(inputFile, output_directory)

    # Start keeping track of time.
    t0 = MPI.Wtime()

    prng = get_prng(seed=seed, world=world)

    inference3d = Inference3D(data, world=world, prng=prng)
    inference3d.create_hdf5(directory=output_directory, **kwargs)

    myMPI.rankPrint(world, "Created hdf5 files in {} h:m:s".format(str(timedelta(seconds=MPI.Wtime()-t0))))

    inference3d.infer(**kwargs)

def geobipy():
    """Run the serial implementation of GeoBIPy. """

    args = checkCommandArguments()
    sys.path.append(getcwd())

    if args.mpi:
        parallel_geobipy(args.options_file,
                         args.output_directory,
                         args.skip_hdf5,
                         seed = args.seed)
    else:
        serial_geobipy(args.options_file,
                       args.output_directory,
                       args.seed,
                       args.index,
                       args.fiducial,
                       args.line_number,
                       args.debug)
