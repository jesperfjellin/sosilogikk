import os
import logging
from pathlib import Path
from module.sosilogikk import read_sosi_file, sosi_to_geodataframe, write_geodataframe_to_sosi

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def read_sosi_to_gdf(sos_filepath):
    """
    Reads a .sos file and converts it to a GeoDataFrame.

    Args:
        sos_filepath (str | Path): Path to the .sos file.

    Returns:
        tuple: (GeoDataFrame, SOSI index, scale factor, extent, header metadata)
    """
    logger.info(f"Reading file: {sos_filepath}")
    
    # Read and convert the .sos file in one step
    parsed_data, all_attributes, enhet_scale, sosi_index, extent, header_metadata = read_sosi_file(sos_filepath)
    gdf, extent = sosi_to_geodataframe(parsed_data, all_attributes, enhet_scale)
    
    return gdf, sosi_index, enhet_scale, extent, header_metadata

def analyze_gdf(gdf):
    """
    Performs analysis on the GeoDataFrame.
    Override this function with your specific analysis.

    Args:
        gdf (gpd.GeoDataFrame): Input GeoDataFrame.

    Returns:
        gpd.GeoDataFrame: Processed GeoDataFrame.
    """
    logger.info(f"Number of features: {len(gdf)}")
    
    # Add your analysis code here
    
    return gdf

def process_sosi_file(input_path, output_path):
    """
    Process a single SOSI file.

    Args:
        input_path (Path): Path to input SOSI file
        output_path (Path): Path to output SOSI file
    """
    try:
        # Read and process
        gdf, sosi_index, enhet_scale, extent, header_metadata = read_sosi_to_gdf(input_path)
        processed_gdf = analyze_gdf(gdf)

        # Update metadata and write
        header_metadata['ENHET'] = enhet_scale
        success = write_geodataframe_to_sosi(
            gdf=processed_gdf,
            output_file=output_path,
            metadata=header_metadata,
            sosi_index=sosi_index,
            extent=extent,
            use_index=True
        )
        
        if success:
            logger.info(f"Successfully processed: {input_path.name}")
        else:
            logger.error(f"Failed to write: {output_path}")
            
    except Exception as e:
        logger.error(f"Error processing {input_path.name}: {str(e)}")
        raise

def main():
    # Define input/output directories
    input_dir = Path('C:\FKKOslo\Kartkontroll\2023\Viken_FKB-C_del_23\Elveg')
    output_dir = Path('/sti/til/output/mappe')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Process all .sos files
    for sosi_file in input_dir.glob('*.sos'):
        output_path = output_dir / f"processed_{sosi_file.name}"
        process_sosi_file(sosi_file, output_path)

if __name__ == "__main__":
    main()