# C:\Python\temp\sosilogic\sosi_script.py

import pandas as pd
import geopandas as gpd
from shapely.geometry import LineString, Point, Polygon
import numpy as np  # Import NumPy for handling NaN

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
    flate_ref_ids = []  # Store .REF IDs for .FLATE objects
    current_attributes = {}
    all_attributes = set()  # Collect all possible attributes
    coordinates = []
    kp = None
    capturing = False
    geom_type = None
    flate_refs = []  # List to hold .REF ids for .FLATE

    with open(filepath, 'r', encoding='ISO-8859-1') as file:
        for line_number, line in enumerate(file, 1):
            stripped_line = line.strip()

            if stripped_line.startswith('.HODE'):
                continue

            if stripped_line == '.SLUTT':
                break

            if stripped_line.startswith(('.KURVE', '.PUNKT', '.FLATE')):
                if capturing:
                    try:
                        if geom_type == '.KURVE':
                            kurve_id = current_attributes.get('OBJTYPE', '').split()[-1]
                            if kurve_id:
                                kurve_coordinates[kurve_id] = coordinates
                            parsed_data['geometry'].append(LineString(coordinates))
                        elif geom_type == '.PUNKT':
                            if len(coordinates) == 1:
                                parsed_data['geometry'].append(Point(coordinates[0]))
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
                                    parsed_data['geometry'].append(Point(coordinates[0]))  # Fallback
                            else:
                                parsed_data['geometry'].append(Point(coordinates[0]))  # Fallback

                        if kp:
                            current_attributes['KP'] = kp

                        parsed_data['attributes'].append(current_attributes)
                    except Exception as e:
                        print(f"Error at line {line_number}: {line.strip()}")
                        print(f"Error details: {e}")
                        raise

                current_attributes = {}
                coordinates = []
                kp = None
                capturing = True
                geom_type = stripped_line.split()[0]
                flate_refs = []  # Reset flate references
                continue

            if capturing:
                if stripped_line.startswith('..'):
                    key_value = stripped_line[2:].split(maxsplit=1)
                    key = key_value[0].lstrip('.')  # Remove leading dots
                    if len(key_value) == 2:
                        value = key_value[1]
                    else:
                        value = np.nan  # Assign NaN if no value
                    current_attributes[key] = value
                    all_attributes.add(key)  # Track all attributes
                elif not stripped_line.startswith('.'):
                    parts = stripped_line.split()
                    try:
                        coord = tuple(map(float, parts[:2]))
                        coordinates.append(coord)
                    except ValueError:
                        pass

                    if '...KP' in stripped_line:
                        kp_index = stripped_line.index('...KP')
                        kp_value = stripped_line[kp_index+5:]  # Get everything after ...KP
                        kp = kp_value.strip()

    if capturing and coordinates:
        try:
            if geom_type == '.KURVE':
                kurve_id = current_attributes.get('OBJTYPE', '').split()[-1]
                if kurve_id:
                    kurve_coordinates[kurve_id] = coordinates
                parsed_data['geometry'].append(LineString(coordinates))
            elif geom_type == '.PUNKT':
                if len(coordinates) == 1:
                    parsed_data['geometry'].append(Point(coordinates[0]))
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
                        parsed_data['geometry'].append(Point(coordinates[0]))  # Fallback
                else:
                    parsed_data['geometry'].append(Point(coordinates[0]))  # Fallback

            if kp:
                current_attributes['KP'] = kp

            parsed_data['attributes'].append(current_attributes)
        except Exception as e:
            print(f"Error at end of file with last object")
            print(f"Error details: {e}")
            raise

    return parsed_data, all_attributes

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

    df = pd.DataFrame(attributes)
    
    # Ensure all attributes are present
    for attribute in all_attributes:
        if attribute not in df:
            df[attribute] = np.nan

    gdf = gpd.GeoDataFrame(df, geometry=geometries)

    return gdf
