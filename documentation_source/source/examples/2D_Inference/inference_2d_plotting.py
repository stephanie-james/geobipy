"""
2D Posterior analysis of the Bayesian inference
-----------------------------------------------

All plotting in GeoBIPy can be carried out using the 3D inference class

"""
import argparse
import matplotlib.pyplot as plt
import numpy as np
from geobipy import Inference2D
from create_model import create_model

#%%
def create_plots(data_type, model_type):
    #%%
    # Inference for a line of inferences
    # ++++++++++++++++++++++++++++++++++
    #
    # We can instantiate the inference handler by providing a path to the directory containing
    # HDF5 files generated by GeoBIPy.
    #
    # The InfereceXD classes are low memory.  They only read information from the HDF5 files
    # as and when it is needed.
    #
    # The first time you use these classes to create plots, expect longer initial processing times.
    # I precompute expensive properties and store them in the HDF5 files for later use.

    ################################################################################
    results_2d = Inference2D.fromHdf('../Parallel_Inference/{}/{}/0.0.h5'.format(data_type, model_type))

    kwargs = {
            "log" : 10,
            "cmap" : 'jet'
            }

    fig = plt.figure(figsize=(16, 4))
    plt.suptitle("{} {}".format(data_type, model_type))
    gs0 = fig.add_gridspec(3, 4)
    ax1 = fig.add_subplot(gs0[0, 0])
    true_model = create_model(model_type)

    if data_type == 'resolve':
        true_model.mesh.y_edges = true_model.mesh.y_edges / 4.1

    kwargs['vmin'] = np.log10(np.min(true_model.values))
    kwargs['vmax'] = np.log10(np.max(true_model.values))

    true_model.pcolor(**kwargs)
    results_2d.plot_data_elevation(linewidth=0.3);
    results_2d.plot_elevation(linewidth=0.3);

    if data_type == 'resolve':
        plt.ylim([-240, 60])
    else:
        plt.ylim([-550, 60])

    ax1 = fig.add_subplot(gs0[1, 0])
    results_2d.plot_mean_model(**kwargs);
    results_2d.plot_data_elevation(linewidth=0.3);
    results_2d.plot_elevation(linewidth=0.3);

    # By adding the useVariance keyword, we can make regions of lower confidence more transparent
    ax1 = fig.add_subplot(gs0[2, 0])
    results_2d.plot_mode_model(use_variance=False, **kwargs);
    results_2d.plot_data_elevation(linewidth=0.3);
    results_2d.plot_elevation(linewidth=0.3);

    # # We can also choose to keep parameters above the DOI opaque.
    # results_2d.compute_doi()
    # plt.subplot(313)
    # results_2d.plot_mean_model(use_variance=True, mask_below_doi=True, **kwargs);
    # results_2d.plot_data_elevation(linewidth=0.3);
    # results_2d.plot_elevation(linewidth=0.3);

    ################################################################################
    # We can plot the parameter values that produced the highest posterior
    ax = fig.add_subplot(gs0[0, 1])
    results_2d.plot_k_layers()

    ax1 = fig.add_subplot(gs0[1, 1], sharex=ax)
    results_2d.plot_best_model(**kwargs);
    results_2d.plot_data_elevation(linewidth=0.3);
    results_2d.plot_elevation(linewidth=0.3);


    del kwargs['vmin']
    del kwargs['vmax']

    ax1 = fig.add_subplot(gs0[0, 2])
    plt.title('5%')
    results_2d.plot_percentile(percent=0.05, **kwargs)
    ax1 = fig.add_subplot(gs0[1, 2])
    plt.title('50%')
    results_2d.plot_percentile(percent=0.5, **kwargs)
    ax1 = fig.add_subplot(gs0[2, 2])
    plt.title('95%')
    results_2d.plot_percentile(percent=0.95, **kwargs)



    ################################################################################
    # Now we can start plotting some more interesting posterior properties.
    # How about the confidence?
    ax1 = fig.add_subplot(gs0[0, 3])
    results_2d.plot_confidence();
    results_2d.plot_data_elevation(linewidth=0.3);
    results_2d.plot_elevation(linewidth=0.3);

    ################################################################################
    # We can take the interface depth posterior for each data point,
    # and display an interface probability cross section
    # This posterior can be washed out, so the clim_scaling keyword lets me saturate
    # the top and bottom 0.5% of the colour range
    ax1 = fig.add_subplot(gs0[1, 3])
    plt.title('P(Interface)')
    results_2d.plot_interfaces(cmap='Greys', clim_scaling=0.5);
    results_2d.plot_data_elevation(linewidth=0.3);
    results_2d.plot_elevation(linewidth=0.3);

    ax1 = fig.add_subplot(gs0[2, 3])
    results_2d.plot_entropy(cmap='Greys', clim_scaling=0.5);
    results_2d.plot_data_elevation(linewidth=0.3);
    results_2d.plot_elevation(linewidth=0.3);

    # plt.show(block=True)
    plt.savefig('{}_{}.png'.format(data_type, model_type), dpi=300)


if __name__ == '__main__':

    Parser = argparse.ArgumentParser(description="Plotting 2D inferences",
                                        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    Parser.add_argument('--data_type', dest='data_type', default=None, help='Skip the creation of the HDF5 files.  Only do this if you know they have been created.')
    Parser.add_argument('--model_type', dest='model_type', default=None, help='Specify a numpy seed file to fix the random number generator. Only used in serial mode.')

    args = Parser.parse_args()

    data_types = ['resolve', 'skytem_304', 'skytem_512', ' tempest'] if args.data_type is None else args.data_type
    model_types = ['glacial', 'saline_clay', 'resistive_dolomites', 'resistive_basement', 'coastal_salt_water', 'ice_over_salt_water'] if args.model_type is None else args.model_type

    if not isinstance(data_types, list): data_types = [data_types]
    if not isinstance(model_types, list): model_types = [model_types]

    for data in data_types:
        print(data)
        for model in model_types:
            print('   ',model)
            create_plots(data, model)
