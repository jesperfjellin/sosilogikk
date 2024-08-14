import sys
import matplotlib.pyplot as plt
from module.sosilogikk import read_sosi_file, sosi_to_geodataframe  # Import functions directly
import numpy as np  
import pandas as pd 
import geopandas as gpd

filepath = r'C:\DATA\SOSI_testdata\Dreneringslinjer_3301_Drammen_åpne_stikkrenner.sos'

sosifile, all_attributes = read_sosi_file(filepath) 

# Konverterer til GeoDataFrame
sosifile_dataframe = sosi_to_geodataframe(sosifile, all_attributes)  

# Pandas display options
pd.set_option('display.max_columns', None)  
pd.set_option('display.width', 1000)        
pd.set_option('display.colheader_justify', 'left')  
pd.set_option('display.max_colwidth', 50)  

# Printer headers og første rad i GDF
print(sosifile_dataframe.head(1).to_string(index=False))

# Lagrer til Flatgeobuf
output_fgb_path = r"C:\DATA\SOSI_testdata\flatgeobuf_dreneringslinjer.fgb"
sosifile_dataframe.to_file(output_fgb_path, driver="FlatGeobuf")

print(f"GeoDataFrame saved to FlatGeobuf at {output_fgb_path}")

plt.show()
