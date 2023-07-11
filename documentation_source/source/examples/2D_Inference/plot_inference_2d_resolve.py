"""
2D Posterior analysis of Resolve inference
------------------------------------------

All plotting in GeoBIPy can be carried out using the 3D inference class

"""
from inference_2d_plotting import create_plots

if __name__ == '__main__':
   types = ['glacial', 'saline_clay', 'resistive_dolomites', 'resistive_basement', 'coastal_salt_water', 'ice_over_salt_water']

   for model in types:
      print(model)
      create_plots("resolve", model)
