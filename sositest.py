# C:\Python\temp\sositest.py
import sys
import matplotlib.pyplot as plt
import sosilogic
import numpy as np  # Import NumPy for handling NaN
import pandas as pd  # Import pandas for setting display options

sys.path.append(r'C:\Python\temp')

# Path to your .SOS file
filepath = r'C:\DATA\SOSI_testdata\Dreneringslinjer_3301_Drammen_hjelpefiler.sos'

# Read the .SOS file
sosifile, all_attributes = sosilogic.read_sosi_file(filepath)

# Convert to GeoDataFrame
sosifile_dataframe = sosilogic.sosi_to_geodataframe(sosifile, all_attributes)

# Set pandas display options to show full content
pd.set_option('display.max_colwidth', None)

# Print the first 5 rows of the GeoDataFrame with full geometry
print(sosifile_dataframe.head().to_string())

# Plot the GeoDataFrame
sosifile_dataframe.plot()
plt.show()
