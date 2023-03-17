"""
1D Inference of Resolve Data
----------------------------

All plotting in GeoBIPy can be carried out using the 3D inference class

"""
from geobipy import StatArray
from create_synthetic_data import create_model, create_resolve, create_skytem, create_aerotem, create_tempest

def parallel_mpi(data_type, model_type, output_directory):

    import pathlib
    from mpi4py import MPI
    from geobipy.src.base import MPI as myMPI
    from datetime import timedelta

    data_filename = data_type + '_' + model_type

    # Make the data for the given test model
    if masterRank:
        wedge_model = create_model(model_type)

        if data_type == 'resolve':
            create_resolve(wedge_model, model_type)
        elif data_type == 'skytem_512':
            create_skytem(wedge_model, model_type, 512)
        elif data_type == 'skytem_304':
            create_skytem(wedge_model, model_type, 304)
        elif data_type == 'aerotem':
            create_aerotem(wedge_model, model_type)
        elif data_type == 'tempest':
            create_tempest(wedge_model, model_type)

    world = MPI.COMM_WORLD
    rank = world.rank
    nRanks = world.size
    masterRank = rank == 0

    myMPI.rankPrint(world,'Running GeoBIPy in parallel mode with {} cores'.format(nRanks))
    myMPI.rankPrint(world,'Using user input file {}'.format(parameter_file))
    myMPI.rankPrint(world,'Output files will be produced at {}'.format(output_directory))

    parameter_file = "{}_options".format(data_type)
    inputFile = pathlib.Path(parameter_file)
    assert inputFile.exists(), Exception("Cannot find input file {}".format(inputFile))

    output_directory = pathlib.Path(output_directory)
    assert output_directory.exists(), Exception("Make sure the output directory exists {}".format(output_directory))

    kwargs = user_parameters.read(inputFile)
    kwargs['data_filename'] = kwargs['data_filename'] + '//' + data_filename + '.csv'

    # Everyone needs the system classes read in early.
    dataset = kwargs['data_type'](system=kwargs['system_filename'])

    # Start keeping track of time.
    t0 = MPI.Wtime()

    inference3d = Inference3D(output_directory, kwargs['system_filename'], mpi_enabled=True)
    inference3d.create_hdf5(dataset, **kwargs)

    myMPI.rankPrint(world, "Created hdf5 files in {} h:m:s".format(str(timedelta(seconds=MPI.Wtime()-t0))))

    inference3d.infer(dataset, **kwargs)


def checkCommandArguments():
    """Check the users command line arguments. """
    import warnings
    import argparse
    # warnings.filterwarnings('error')

    Parser = argparse.ArgumentParser(description="GeoBIPy",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    Parser.add_argument('index', type=int, help='job array index 0-18')

    args = Parser.parse_args()

    return args.index

if __name__ == '__main__':
    import os
    import sys
    from pathlib import Path
    from geobipy import Inference3D
    from geobipy import user_parameters
    import numpy as np

    #%%
    # Running GeoBIPy to invert data
    # ++++++++++++++++++++++++++++++
    #
    # Define some directories and paths

    np.random.seed(0)

    index = checkCommandArguments()
    sys.path.append(os.getcwd())

    datas = ['tempest', 'skytem_512', 'skytem_304', 'resolve']
    keys = ['glacial', 'saline_clay', 'resistive_dolomites', 'resistive_basement', 'coastal_salt_water', 'ice_over_salt_water']

    tmp = np.unravel_index(index, (4, 6))

    data = datas[tmp[0]]
    key = keys[tmp[1]]

    ################################################################################
    # The directory where HDF files will be stored
    ################################################################################
    file_path = os.path.join(data, key)
    Path(file_path).mkdir(parents=True, exist_ok=True)

    for filename in os.listdir(file_path):
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
        except Exception as e:
            print('Failed to delete %s. Reason: %s' % (file_path, e))

    ################################################################################
    # The parameter file defines the set of user parameters needed to run geobipy.

    ################################################################################

    parallel_mpi(data, key, file_path)
