from module.sosilogikk import read_sosi_file, sosi_to_geodataframe  # Import functions directly
import pandas as pd 


filepath = r'C:\DATA\SOSI_testdata\Dreneringslinjer_3301_Drammen_åpne_stikkrenner.sos' # Disse 3 linjene er alt som skal til for å laste SOSI-filen din inn i en GeoDataFrame
sosifile, all_attributes = read_sosi_file(filepath)                                    #
sosifile_dataframe = sosi_to_geodataframe(sosifile, all_attributes)                    # Konverterer til GeoDataFrame


# Pandas display options
pd.set_option('display.max_columns', None)  
pd.set_option('display.width', 1000)        
pd.set_option('display.colheader_justify', 'left')  
pd.set_option('display.max_colwidth', 50)  


print(sosifile_dataframe.head(1).to_string(index=False))                               # Printer headers og første rad i GDF
output_fgb_path = r"C:\DATA\SOSI_testdata\flatgeobuf_dreneringslinjer.fgb"             # Lagrer til Flatgeobuf
sosifile_dataframe.to_file(output_fgb_path, driver="FlatGeobuf")                       # Lagrer til Flatgeobuf

print(f"GeoDataFrame saved to FlatGeobuf at {output_fgb_path}")

