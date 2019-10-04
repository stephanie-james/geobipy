""" @RectilinearMesh2D_Class
Module describing a 2D Rectilinear Mesh class with x and y axes specified
"""
#from ...base import Error as Err
from copy import deepcopy
import numpy as np
from ...base import customFunctions as cF
from ..core import StatArray
from ..mesh.RectilinearMesh1D import RectilinearMesh1D
from .Histogram2D import Histogram2D

class Hitmap2D(Histogram2D):
    """ Class defining a 2D hitmap whose cells are rectangular with linear sides """

    def deepcopy(self):
        return deepcopy(self)


    def __deepcopy__(self, memo):
        """ Define the deepcopy. """

        if self.xyz:
            out = Hitmap2D(xBins=self.xBins, yBins=self.yBins, zBins=self.zBins)
        else:
            out = Hitmap2D(xBins=self.xBins, yBins=self.yBins)
        out._counts = self._counts.deepcopy()

        return out


    def marginalProbability(self, fractions, distributions, axis, reciprocateParameter=False, log=None):
        """Compute the marginal probability between the hitmap and a set of distributions.

        .. math::
            :label: marginal
            
            p(distribution_{i} | \\boldsymbol{d}) = 


        """
        assert axis < 2, ValueError("Must have 0 <= axis < 2")

        if axis == 0:
            ax = self.x.cellCentres
        else:
            ax = self.y.cellCentres

        if reciprocateParameter:
            ax = 1.0 / ax

        ax, dum = cF._log(ax, log)

        if not isinstance(distributions, list):
            distributions = [distributions]

        # Sort by mean
        # means = [x.mean for x in distributions]
        # i = np.argsort(means)
        # sortedDistributions = []
        # for j in i:
        #     sortedDistributions.append(distributions[j])
        sortedDistributions = distributions

        # Compute the probabilities along the hitmap axis, using each distribution
        nDistributions = np.size(sortedDistributions)
        pdfs = np.zeros([nDistributions, ax.size])
        for i in range(nDistributions):
            pdfs[i, :] = fractions[i] * sortedDistributions[i].probability(ax)

        if nDistributions > 1:
            x = np.searchsorted(ax, sortedDistributions[1].mean)
            pdfs[0, x:] = 0.0

            for i in range(1, nDistributions-1):
                x = ax.searchsorted(sortedDistributions[i-1].mean)
                pdfs[i, :x] = 0.0
                x = ax.searchsorted(sortedDistributions[i+1].mean)
                pdfs[i, x:] = 0.0

            x = ax.searchsorted(sortedDistributions[nDistributions-2].mean)
            pdfs[-1, :x] = 0.0

        # Normalize by the sum of the pdfs
        normalizedPdfs = pdfs / np.sum(pdfs, axis=0)

        # Initialize the facies Model
        axisPdf = self.axisPdf(axis)
        marginalProbability = np.empty([nDistributions, self.shape[axis]])
        for j in range(nDistributions):
            marginalProbability[j, :] = np.sum(axisPdf * normalizedPdfs[j, :], axis=1-axis)

        return np.squeeze(marginalProbability)

        

    def varianceCutoff(self, percent=67.0):
        """ Get the cutoff value along y axis from the bottom up where the variance is percent*max(variance) """
        p = 0.01*percent
        s = (np.repeat(self.x[np.newaxis,:],np.size(self.arr,0),0) * self.arr).std(axis = 1)
        mS = s.max()
        iC = s.searchsorted(p*mS,side='right')-1

        return self.y[iC]


    def getOpacityLevel(self, percent):
        """ Get the index along axis 1 from the bottom up that corresponds to the percent opacity """
        p = 0.01*percent
        op = self.axisOpacity()[::-1]
        nz = op.size - 1
        iC = 0
        while op[iC] < p and iC < nz:
            iC +=1
        return self.y.cellCentres[op.size - iC -1]


    def hdfName(self):
        """ Reprodicibility procedure """
        return('Hitmap2D()')
        

    def fromHdf(self, grp, index=None):
        """ Reads in the object froma HDF file """

        ai=None
        bi=None
        if (not index is None):
            assert cF.isInt(index), TypeError('index must be an integer {}'.format(index))
            ai = np.s_[index, :, :]
            bi = np.s_[index, :]

        item = grp.get('arr')
        obj = eval(cF.safeEval(item.attrs.get('repr')))
        arr = obj.fromHdf(item, index=ai)

        item = grp.get('x')
        this = eval(cF.safeEval(item.attrs.get('repr')))
        x = this.fromHdf(item, index=bi)
        item = grp.get('y')
        this = eval(cF.safeEval(item.attrs.get('repr')))
        y = this.fromHdf(item, index=bi)

        tmp = Hitmap2D(xBins=x.cellEdges, yBins=y.cellEdges)
        tmp._counts[:, :] = arr

        return tmp
