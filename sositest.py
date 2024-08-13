import sys
import matplotlib.pyplot as plt
import sosilogic
import numpy as np  
import pandas as pd 
import geopandas as gpd  # Make sure geopandas is imported

# In C:\Python\sosilogic\sosilogic\sosi_script.py
sys.path.append(r'C:\Python\sosilogic\sosilogic')

# Path to your .SOS file
filepath = r'C:\DATA\SOSI_testdata\Dreneringslinjer_3301_Drammen_åpne_stikkrenner.sos'

# Read the .SOS file directly, without manually opening it first
sosifile, all_attributes = sosilogic.read_sosi_file(filepath)

# Convert to GeoDataFrame
sosifile_dataframe = sosilogic.sosi_to_geodataframe(sosifile, all_attributes)

# Set pandas display options for better readability
pd.set_option('display.max_columns', None)  # Show all columns
pd.set_option('display.width', 1000)        # Set the width of the display
pd.set_option('display.colheader_justify', 'left')  # Left-align column headers
pd.set_option('display.max_colwidth', 50)   # Limit the width of columns

# Print the headers and the first row of the GeoDataFrame
print(sosifile_dataframe.head(1).to_string(index=False))

# Save the GeoDataFrame to a FlatGeobuf file
output_fgb_path = r"C:\DATA\SOSI_testdata\flatgeobuf_dreneringslinjer.fgb"
sosifile_dataframe.to_file(output_fgb_path, driver="FlatGeobuf")

print(f"GeoDataFrame saved to FlatGeobuf at {output_fgb_path}")

plt.show()
