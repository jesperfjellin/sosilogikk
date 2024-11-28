import os
import logging
import geopandas as gpd
from module.sosilogikk import read_sosi_file, sosi_to_geodataframe, write_geodataframe_to_sosi

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def extract_koordsys(filepath):
    """
    Extracts the coordinate system from a .sos file.

    Args:
        filepath (str): Path to the .sos file.

    Returns:
        str: EPSG code corresponding to the coordinate system.
    """
    koordsys_map = {
        "22": "EPSG:25832",
        "23": "EPSG:25833",
        "25": "EPSG:25835"
    }
    
    with open(filepath, 'r', encoding='UTF-8') as file:
        for line in file:
            if line.startswith('...KOORDSYS'):
                koordsys_code = line.split()[1]
                return koordsys_map.get(koordsys_code)
    raise ValueError("...KOORDSYS not found in the SOSI file!")

def read_sosi_to_gdf(sos_filepath):
    """
    Reads a .sos file and converts it to a GeoDataFrame.

    Args:
        sos_filepath (str): Path to the .sos file.

    Returns:
        gpd.GeoDataFrame: GeoDataFrame containing the data.
        dict: SOSI index mapping object IDs to original context.
        float: Scale factor from the .sos file.
        tuple: Extent of the data (min_n, min_e, max_n, max_e).
        dict: Header metadata including VERT-DATUM, KOORDSYS, etc.
    """
    logger.info(f"Reading file: {sos_filepath}")
    
    # Read the .sos file using sosilogikk
    parsed_data, all_attributes, enhet_scale, sosi_index, extent, header_metadata = read_sosi_file(sos_filepath)
    
    # Convert parsed data to a GeoDataFrame
    gdf, extent = sosi_to_geodataframe(parsed_data, all_attributes, enhet_scale)
    
    return gdf, sosi_index, enhet_scale, extent, header_metadata

def analyze_gdf(gdf):
    """
    Performs analysis on the GeoDataFrame.

    Args:
        gdf (gpd.GeoDataFrame): GeoDataFrame to analyze.

    Returns:
        gpd.GeoDataFrame: Processed GeoDataFrame.
    """
    # Perform your analysis here

    # Placeholder analysis: Count the number of features
    feature_count = len(gdf)
    logger.info(f"Number of features: {feature_count}")

    return gdf

def write_sosi_file(gdf, sosi_index, output_filepath, extent, metadata):
    """
    Writes a GeoDataFrame to a .sos file.

    Args:
        gdf (gpd.GeoDataFrame): GeoDataFrame to write.
        sosi_index (dict): SOSI index mapping object IDs to original context.
        output_filepath (str): Path to the output .sos file.
        extent (tuple): Extent of the data (min_n, min_e, max_n, max_e).
        metadata (dict): Header metadata including ENHET, VERT-DATUM, KOORDSYS, etc.
    """
    success = write_geodataframe_to_sosi(
        gdf=gdf,
        output_file=output_filepath,
        metadata=metadata,
        sosi_index=sosi_index,
        extent=extent,
        use_index=True
    )
    if success:
        logger.info(f"SOSI file successfully written to {output_filepath}")
    else:
        logger.error("Failed to write SOSI file.")

def main():
    # Path to your .sos file(s)
    sos_directory = '/sti/til/mappe/med/.sos/filer'
    output_directory = '/sti/til/output/mappe'
    os.makedirs(output_directory, exist_ok=True)
    
    # Loop through all .sos files in the directory
    for filename in os.listdir(sos_directory):
        if filename.lower().endswith(".sos"):
            sos_filepath = os.path.join(sos_directory, filename)
            
            # Read the .sos file into a GeoDataFrame
            gdf, sosi_index, enhet_scale, extent, header_metadata = read_sosi_to_gdf(sos_filepath)
            
            # Perform analysis on the GeoDataFrame
            processed_gdf = analyze_gdf(gdf)
            
            # Write the processed GeoDataFrame back to a .sos file
            output_filepath = os.path.join(output_directory, f"processed_{filename}")
            # Update header_metadata with enhet_scale
            header_metadata['ENHET'] = enhet_scale
            write_sosi_file(processed_gdf, sosi_index, output_filepath, extent, header_metadata)

if __name__ == "__main__":
    main()
