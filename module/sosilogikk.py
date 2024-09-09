import pandas as pd
import geopandas as gpd
from shapely.geometry import LineString, Point, Polygon
import shapely.affinity
import numpy as np
import logging

# Logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logging.getLogger('matplotlib.font_manager').disabled = True
logger = logging.getLogger()

def read_sosi_file(filepath):
    """
    Reads a .SOS file and returns geometry, attributes, unit scale, and an index for each object.
    
    Args:
        filepath (str): Path to the .SOS file.
    
    Returns:
        dict: Data with 'geometry' and 'attributes'.
        set: All attributes encountered.
        float: Unit scale (from ...ENHET).
        dict: SOSI index mapping object ID to original content.
        tuple: MIN-NØ and MAX-NØ values (min_n, min_e, max_n, max_e).
    """
    logger.info("Entering read_sosi_file function")
    parsed_data = {
        'geometry': [],  # Geometries (LineString, Point, Polygon)
        'attributes': [] 
    }
    enhet_scale = None  # Set to None to explicitly check later
    sosi_index = {}  # Initialize the SOSI index
    all_attributes = set()  # Initialize the set of all attributes
    current_object = []  # Temporary list to hold the current object's lines
    object_id = 0  # Unique ID for each object

    # Other variables for handling geometries and attributes
    kurve_coordinates = {}  
    current_attributes = {}
    coordinates = []
    kp = None
    capturing = False
    geom_type = None
    flate_refs = []  
    expecting_coordinates = False  
    coordinate_dim = None  
    found_2d = False  
    min_n, min_e = float('inf'), float('inf')
    max_n, max_e = float('-inf'), float('-inf')

    try:
        with open(filepath, 'r', encoding='utf-8') as file:
            for line_number, line in enumerate(file, 1):
                stripped_line = line.strip()
                current_object.append(line)

                if stripped_line.startswith('...MIN-NØ'):
                    _, min_e, min_n = stripped_line.split()  # Swapped order
                    min_n, min_e = float(min_n), float(min_e)
                elif stripped_line.startswith('...MAX-NØ'):
                    _, max_e, max_n = stripped_line.split()  # Swapped order
                    max_n, max_e = float(max_n), float(max_e)
                
                # Extract the ...ENHET value
                if stripped_line.startswith('...ENHET'):
                    try:
                        enhet_scale = float(stripped_line.split()[1])
                        logger.info(f"Extracted scale factor ...ENHET: {enhet_scale}")
                    except (IndexError, ValueError) as e:
                        logger.error(f"Error parsing ...ENHET value at line {line_number}: {line.strip()} - {e}")
                        raise ValueError(f"Invalid or malformed ...ENHET value in {filepath}. Exiting.")

                # Capture geometry start (e.g., .KURVE, .PUNKT, .FLATE)
                if stripped_line.startswith(('.KURVE', '.PUNKT', '.FLATE')):
                    if capturing:  # End capturing for the current object before starting a new one
                        try:
                            if coordinates and current_attributes:  # Only add if we have both coordinates and attributes
                                uniform_coordinates = convert_to_2d_if_mixed(coordinates, coordinate_dim)
                                if geom_type == '.KURVE':
                                    kurve_id = current_attributes.get('OBJTYPE', '').split()[-1]
                                    if kurve_id:
                                        kurve_coordinates[kurve_id] = uniform_coordinates
                                    parsed_data['geometry'].append(LineString(uniform_coordinates))
                                    parsed_data['attributes'].append(current_attributes)
                                elif geom_type == '.PUNKT':
                                    if len(uniform_coordinates) == 1:
                                        parsed_data['geometry'].append(Point(uniform_coordinates[0]))
                                        parsed_data['attributes'].append(current_attributes)
                                elif geom_type == '.FLATE':
                                    if flate_refs:
                                        flate_coords = []
                                        for ref_id in flate_refs:
                                            ref_id = ref_id.strip()
                                            if ref_id in kurve_coordinates:
                                                flate_coords.extend(kurve_coordinates[ref_id])
                                        if flate_coords:
                                            parsed_data['geometry'].append(Polygon(flate_coords))
                                        else:
                                            parsed_data['geometry'].append(Point(uniform_coordinates[0]))
                                        parsed_data['attributes'].append(current_attributes)
                                    else:
                                        parsed_data['geometry'].append(Point(uniform_coordinates[0]))
                                        parsed_data['attributes'].append(current_attributes)

                            sosi_index[object_id] = current_object
                            object_id += 1  # Increment the object ID for the next object
                        except Exception as e:
                            logger.error(f"Error at line {line_number}: {line.strip()}")
                            logger.error(f"Error details: {e}")
                            raise

                    # Reset for the new geometry object
                    current_attributes = {}
                    coordinates = []
                    kp = None
                    capturing = True  # Now start capturing the new object
                    geom_type = stripped_line.split()[0]  # Set the geometry type (e.g., .KURVE, .PUNKT, .FLATE)
                    flate_refs = []
                    expecting_coordinates = False
                    coordinate_dim = None
                    found_2d = False
                    current_object = [line]  # Start capturing the new object
                    continue

                # Capture attributes
                if capturing:
                    if stripped_line.startswith('..'):
                        key_value = stripped_line[2:].split(maxsplit=1)
                        key = key_value[0].lstrip('.')  
                        if key in ['NØ', 'NØH']:
                            expecting_coordinates = True
                            coordinate_dim = 3 if key == 'NØH' else 2  
                            continue  
                        else:
                            expecting_coordinates = False
                            value = key_value[1] if len(key_value) == 2 else np.nan  
                            current_attributes[key] = value
                            all_attributes.add(key)  
                    elif expecting_coordinates and not stripped_line.startswith('.'):
                        try:
                            parts = stripped_line.split()
                            if coordinate_dim == 2:
                                coord = (float(parts[1]), float(parts[0]))  # Swapped order
                                found_2d = True
                            else:
                                coord = (float(parts[1]), float(parts[0]), float(parts[2]))  # Swapped x and y, keep z
                            coordinates.append(coord)
                        except ValueError:
                            pass
                    elif stripped_line.startswith('.') and not stripped_line.startswith('..'):
                        expecting_coordinates = False  

        # Check for missing ...ENHET value
        if enhet_scale is None:
            logger.error(f"Missing ...ENHET line in file {filepath}. This file is invalid. Exiting.")
            raise ValueError(f"...ENHET value not found in {filepath}. Exiting.")

        logger.info(f"Final enhet_scale: {enhet_scale}")
        logger.info(f"MIN-NØ: {min_n}, {min_e}, MAX-NØ: {max_n}, {max_e}")

    except Exception as e:
        logger.error(f"An error occurred in read_sosi_file: {str(e)}")
        raise

    logger.info("Exiting read_sosi_file function")
    return parsed_data, all_attributes, enhet_scale, sosi_index, (min_n, min_e, max_n, max_e)


def convert_to_2d_if_mixed(coordinates, dimension):
    has_2d = any(len(coord) == 2 for coord in coordinates)
    if has_2d:
        return [(y, x) for x, y, *z in coordinates]  # Swapped x and y
    elif dimension == 3:
        return [(y, x, z) for x, y, z in coordinates]  # Swapped x and y, keep z
    else:
        return [(y, x) for x, y in coordinates]  # Swapped x and y
    
def force_2d(geom):
    if geom.has_z:
        if isinstance(geom, shapely.geometry.Point):
            return shapely.geometry.Point(geom.y, geom.x)  # Swapped x and y
        elif isinstance(geom, shapely.geometry.LineString):
            return shapely.geometry.LineString([(y, x) for x, y, z in geom.coords])  # Swapped x and y
        elif isinstance(geom, shapely.geometry.Polygon):
            exterior = [(y, x) for x, y, z in geom.exterior.coords]  # Swapped x and y
            interiors = [[(y, x) for x, y, z in interior.coords] for interior in geom.interiors]  # Swapped x and y
            return shapely.geometry.Polygon(exterior, interiors)
    return geom


def sosi_to_geodataframe(sosi_data_list, all_attributes_list, scale_factors):
    """
    Converts parsed SOSI data to a GeoDataFrame, handling multiple input files if provided.

    Args:
        sosi_data_list (list or dict): Parsed SOSI data with 'geometry' and 'attributes'.
        all_attributes_list (list or set): Set(s) of all registered attributes.
        scale_factors (list or float): Scaling factor(s) from ...ENHET.

    Returns:
        gpd.GeoDataFrame: GeoDataFrame containing the SOSI data.
        tuple: Overall extent (min_n, min_e, max_n, max_e).
    """
    # Ensure inputs are lists even if single file is provided
    if not isinstance(sosi_data_list, list):
        sosi_data_list = [sosi_data_list]
        all_attributes_list = [all_attributes_list]
        scale_factors = [scale_factors]
    
    gdfs = []
    overall_min_n, overall_min_e = float('inf'), float('inf')
    overall_max_n, overall_max_e = float('-inf'), float('-inf')
    
    for sosi_data, all_attributes, scale_factor in zip(sosi_data_list, all_attributes_list, scale_factors):
        geometries = sosi_data['geometry']
        attributes = sosi_data['attributes']

        # Check if there is a mismatch between geometries and attributes
        if len(geometries) != len(attributes):
            print(f"Warning: Mismatch found: {len(geometries)} geometries, {len(attributes)} attributes")
            min_length = min(len(geometries), len(attributes))
            geometries = geometries[:min_length]
            attributes = attributes[:min_length]

        # Apply the scale factor to the geometries
        scaled_geometries = scale_geometries(geometries, scale_factor)

        # Create a DataFrame from the attributes
        df = pd.DataFrame(attributes)

        # Ensure all attributes are present in the DataFrame
        for attribute in all_attributes:
            if attribute not in df:
                df[attribute] = np.nan

        # Create the GeoDataFrame
        gdf = gpd.GeoDataFrame(df, geometry=scaled_geometries)

        # Add an 'original_id' column to track the original position of each object in the SOSI file
        gdf['original_id'] = range(len(gdf))

        gdfs.append(gdf)
        
        # Update overall min and max coordinates
        min_n, min_e, max_n, max_e = gdf.total_bounds
        overall_min_n = min(overall_min_n, min_n)
        overall_min_e = min(overall_min_e, min_e)
        overall_max_n = max(overall_max_n, max_n)
        overall_max_e = max(overall_max_e, max_e)
    
    # Combine all GeoDataFrames
    combined_gdf = pd.concat(gdfs, ignore_index=True)
    combined_gdf['original_id'] = range(len(combined_gdf))
    
    return combined_gdf, (overall_min_n, overall_min_e, overall_max_n, overall_max_e)


def scale_geometries(geometries, scale_factor=1.0):
    """
    Scales geometries according to the provided scale factor.

    Args:
        geometries (list of shapely.geometry): List of geometries to be scaled.
        scale_factor (float): The scale factor to apply to the geometries.

    Returns:
        list of shapely.geometry: The scaled geometries.
    """
    scaled_geometries = []
    
    for geom in geometries:
        # Scale the geometry
        if scale_factor != 1.0:
            geom = shapely.affinity.scale(geom, xfact=scale_factor, yfact=scale_factor, origin=(0, 0))
        scaled_geometries.append(geom)
    
    return scaled_geometries


def write_geodataframe_to_sosi(gdf, sosi_index, output_filepath, extent, enhet_scale, use_index=True):
    """
    Writes a GeoDataFrame back to a SOSI file, optionally using the original SOSI index to preserve formatting.

    Args:
        gdf (gpd.GeoDataFrame): The GeoDataFrame containing the SOSI data.
        sosi_index (dict): The index mapping object IDs to original SOSI content.
        output_filepath (str or Path): The path where the new SOSI file will be written.
        extent (tuple): The extent of the data (min_n, min_e, max_n, max_e).
        enhet_scale (float): The scale factor for the coordinates.
        use_index (bool): Whether to use the SOSI index for writing (default True).

    Returns:
        bool: True if the file was successfully written, False otherwise.
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Writing GeoDataFrame to SOSI file: {output_filepath}")
    min_n, min_e, max_n, max_e = extent
    
    try:
        with open(output_filepath, 'w', encoding='utf-8') as outfile:
            # Write the SOSI file header
            logger.info("Writing header section...")
            outfile.write(".HODE\n..TEGNSETT UTF-8\n..OMRÅDE\n")
            outfile.write(f"...MIN-NØ {min_e:.2f} {min_n:.2f}\n")  # Swapped order
            outfile.write(f"...MAX-NØ {max_e:.2f} {max_n:.2f}\n")  # Swapped order
            
            if enhet_scale is not None:
                enhet_str = f"{enhet_scale:.6f}".rstrip('0').rstrip('.')
                outfile.write(f"...ENHET {enhet_str}\n")
            else:
                logger.warning("enhet_scale is None, skipping ...ENHET line")
            
            logger.info(f"GeoDataFrame length: {len(gdf)}")
            if use_index:
                logger.info(f"SOSI index size: {len(sosi_index)}")
                written_ids = set()

                for index, row in gdf.iterrows():
                    original_id = row.get('original_id')
                    
                    if original_id is None:
                        logger.warning(f"Row {index} has no original_id. Skipping.")
                        continue

                    if original_id in written_ids:
                        logger.info(f"Skipping duplicate content for original_id: {original_id}")
                        continue

                    if original_id not in sosi_index:
                        logger.warning(f"No SOSI index entry for original_id: {original_id}. Skipping.")
                        continue

                    outfile.writelines(sosi_index[original_id])
                    written_ids.add(original_id)
            else:
                # Write each row without using the index
                for index, row in gdf.iterrows():
                    outfile.write(f".OBJTYPE {row['OBJTYPE']}\n")
                    for key, value in row.items():
                        if key not in ['geometry', 'OBJTYPE']:
                            outfile.write(f"..{key} {value}\n")
                    
                    # Write geometry
                    geom = row['geometry']
                    if geom.geom_type == 'Polygon':
                        outfile.write("..FLATE\n")
                        for x, y in geom.exterior.coords:
                            outfile.write(f"...KURVE {x:.2f} {y:.2f}\n")  # Swapped order
                    elif geom.geom_type == 'LineString':
                        outfile.write("..KURVE\n")
                        for x, y in geom.coords:
                            outfile.write(f"...KURVE {x:.2f} {y:.2f}\n")  # Swapped order
                    elif geom.geom_type == 'Point':
                        outfile.write(f"..PUNKT {geom.x:.2f} {geom.y:.2f}\n")  # Swapped order
                    
                    outfile.write("..NØ\n")

            # Write the SOSI file footer
            logger.info("Writing footer .SLUTT")
            outfile.write(".SLUTT\n")

        logger.info(f"Successfully wrote SOSI file to {output_filepath}")
        return True

    except IOError as e:
        logger.error(f"IO error occurred while writing SOSI file: {str(e)}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Unexpected error occurred while writing SOSI file: {str(e)}", exc_info=True)
        return False