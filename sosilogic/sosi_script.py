import pandas as pd
import geopandas as gpd
from shapely.geometry import LineString, Point, Polygon
import numpy as np
import logging

# Setup logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

def read_sosi_file(filepath):
    """
    Reads a .SOS file and returns the geometry and attributes in a structured format.
    
    Args:
        filepath (str): Path to the .SOS file.
    
    Returns:
        dict: Parsed data with 'geometry' and 'attributes'.
    """
    parsed_data = {
        'geometry': [],  # List of geometries (LineString, Point, Polygon)
        'attributes': [] # List of dictionaries containing attributes
    }

    kurve_coordinates = {}  # Store coordinates of each .KURVE by ID
    current_attributes = {}
    all_attributes = set()  # Collect all possible attributes
    coordinates = []
    kp = None
    capturing = False
    geom_type = None
    flate_refs = []  # List to hold .REF ids for .FLATE
    expecting_coordinates = False  # Flag to expect coordinates after ..NØ or ..NØH
    coordinate_dim = None  # Reset on each new geometry
    found_2d = False  # Track if any 2D coordinates are found

    logger.info(f"Opening file: {filepath}")
    with open(filepath, 'r', encoding='UTF-8') as file:
        for line_number, line in enumerate(file, 1):
            stripped_line = line.strip()

            if stripped_line.startswith('.HODE'):
                continue

            if stripped_line == '.SLUTT':
                break

            if stripped_line.startswith(('.KURVE', '.PUNKT', '.FLATE')):
                if capturing:
                    try:
                        if coordinates:
                            #logger.debug(f"Coordinates collected for {geom_type}: {coordinates}")
                            uniform_coordinates = convert_to_2d_if_mixed(coordinates, coordinate_dim)
                            #logger.debug(f"Uniform coordinates: {uniform_coordinates}")
                            if geom_type == '.KURVE':
                                kurve_id = current_attributes.get('OBJTYPE', '').split()[-1]
                                if kurve_id:
                                    kurve_coordinates[kurve_id] = uniform_coordinates
                                parsed_data['geometry'].append(LineString(uniform_coordinates))
                            elif geom_type == '.PUNKT':
                                if len(uniform_coordinates) == 1:
                                    parsed_data['geometry'].append(Point(uniform_coordinates[0]))
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
                                        parsed_data['geometry'].append(Point(uniform_coordinates[0]))  # Fallback
                                else:
                                    parsed_data['geometry'].append(Point(uniform_coordinates[0]))  # Fallback
                            #logger.debug(f"Added geometry: {parsed_data['geometry'][-1]}")

                        if kp:
                            current_attributes['KP'] = kp
                            #logger.debug(f"Added KP: {kp}")

                        parsed_data['attributes'].append(current_attributes)
                        #logger.debug(f"Added attributes: {current_attributes}")
                    except Exception as e:
                        logger.error(f"Error at line {line_number}: {line.strip()}")
                        logger.error(f"Error details: {e}")
                        raise

                current_attributes = {}
                coordinates = []
                kp = None
                capturing = True
                geom_type = stripped_line.split()[0]
                flate_refs = []  # Reset flate references
                expecting_coordinates = False
                coordinate_dim = None  # Reset dimension
                found_2d = False  # Reset 2D flag
                #logger.info(f"Started capturing {geom_type} at line {line_number}")
                continue

            if capturing:
                if stripped_line.startswith('..'):
                    key_value = stripped_line[2:].split(maxsplit=1)
                    key = key_value[0].lstrip('.')  # Remove leading dots
                    if key in ['NØ', 'NØH']:
                        expecting_coordinates = True
                        coordinate_dim = 3 if key == 'NØH' else 2  # Set dimension based on key
                        #logger.debug(f"Expecting coordinates of dimension {coordinate_dim} after key {key}")
                        continue  # Skip this line and expect coordinates in the next lines
                    else:
                        expecting_coordinates = False
                        if len(key_value) == 2:
                            value = key_value[1]
                        else:
                            value = np.nan  # Assign NaN if no value
                        current_attributes[key] = value
                        all_attributes.add(key)  # Track all attributes
                        #logger.debug(f"Captured attribute {key}: {value} at line {line_number}")
                elif expecting_coordinates and not stripped_line.startswith('.'):
                    try:
                        parts = stripped_line.split()
                        if coordinate_dim == 2:
                            coord = tuple(map(float, parts[:2]))
                            found_2d = True  # Mark as found 2D coordinate
                        else:
                            coord = tuple(map(float, parts[:3]))  # Expect 3 coordinates for ..NØH
                        coordinates.append(coord)
                        #logger.debug(f"Captured coordinate {coord} at line {line_number}")
                        # Optionally, capture KP if present
                        if '...KP' in stripped_line:
                            kp_index = stripped_line.index('...KP')
                            kp_value = stripped_line[kp_index + 5:]  # Get everything after ...KP
                            kp = kp_value.strip()
                            #logger.debug(f"Captured KP value: {kp} at line {line_number}")
                    except ValueError:
                        pass
                        #logger.error(f"Invalid coordinate at line {line_number}: {line.strip()}")
                elif stripped_line.startswith('.') and not stripped_line.startswith('..'):
                    expecting_coordinates = False  # Coordinates are interrupted by another geometric block

    if capturing:
        try:
            if coordinates:
                #logger.debug(f"Final coordinates collected for {geom_type}: {coordinates}")
                uniform_coordinates = convert_to_2d_if_mixed(coordinates, coordinate_dim)
                #logger.debug(f"Uniform coordinates: {uniform_coordinates}")
                if geom_type == '.KURVE':
                    kurve_id = current_attributes.get('OBJTYPE', '').split()[-1]
                    if kurve_id:
                        kurve_coordinates[kurve_id] = uniform_coordinates
                    parsed_data['geometry'].append(LineString(uniform_coordinates))
                elif geom_type == '.PUNKT':
                    if len(uniform_coordinates) == 1:
                        parsed_data['geometry'].append(Point(uniform_coordinates[0]))
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
                            parsed_data['geometry'].append(Point(uniform_coordinates[0]))  # Fallback
                    else:
                        parsed_data['geometry'].append(Point(uniform_coordinates[0]))  # Fallback
                #logger.debug(f"Added final geometry: {parsed_data['geometry'][-1]}")

            if kp:
                current_attributes['KP'] = kp
                #logger.debug(f"Added final KP: {kp}")

            parsed_data['attributes'].append(current_attributes)
            #logger.debug(f"Added final attributes: {current_attributes}")
        except Exception as e:
            logger.error(f"Error at end of file with last object")
            logger.error(f"Error details: {e}")
            raise

    # Ensure lengths match
    if len(parsed_data['geometry']) != len(parsed_data['attributes']):
        logger.warning(f"Mismatch between geometries and attributes: {len(parsed_data['geometry'])} vs {len(parsed_data['attributes'])}")
        # Handle the mismatch here, e.g., by skipping or padding.

    logger.info(f"Total parsed geometries: {len(parsed_data['geometry'])}")
    logger.info(f"Total parsed attributes: {len(parsed_data['attributes'])}")

    return parsed_data, all_attributes

def convert_to_2d_if_mixed(coordinates, dimension):
    """
    Converts all coordinates to 2D if any 2D coordinates are found, otherwise keeps them as 3D.
    
    Args:
        coordinates (list): List of tuples representing coordinates.
        dimension (int): The expected dimension (2 or 3).
    
    Returns:
        list: List of tuples with uniform dimensions.
    """
    has_2d = any(len(coord) == 2 for coord in coordinates)
    if has_2d:
        # Convert all coordinates to 2D
        #logger.debug("Converting mixed 2D and 3D coordinates to 2D.")
        return [(x, y) for x, y, *z in coordinates]  # Strip Z if present
    elif dimension == 3:
        # Keep as 3D
        return coordinates
    else:
        return [(x, y) for x, y in coordinates]  # Ensure 2D coordinates

def sosi_to_geodataframe(parsed_data, all_attributes):
    """
    Converts parsed SOSI data to a GeoDataFrame.
    
    Args:
        parsed_data (dict): Parsed SOSI data with 'geometry' and 'attributes'.
        all_attributes (set): Set of all attributes encountered.
    
    Returns:
        gpd.GeoDataFrame: GeoDataFrame containing the SOSI data.
    """
    geometries = parsed_data['geometry']
    attributes = parsed_data['attributes']

    # Ensure geometries and attributes are the same length
    if len(geometries) != len(attributes):
        logger.warning(f"Mismatch found: {len(geometries)} geometries, {len(attributes)} attributes")
        # Handle mismatches, e.g., truncate to the shorter list
        min_length = min(len(geometries), len(attributes))
        geometries = geometries[:min_length]
        attributes = attributes[:min_length]

    df = pd.DataFrame(attributes)
    
    # Ensure all attributes are present
    for attribute in all_attributes:
        if attribute not in df:
            df[attribute] = np.nan

    gdf = gpd.GeoDataFrame(df, geometry=geometries)

    return gdf
