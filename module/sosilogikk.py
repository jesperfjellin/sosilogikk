import pandas as pd
import geopandas as gpd
from shapely.geometry import LineString, Point, Polygon
import numpy as np
import logging

# Logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logging.getLogger('matplotlib.font_manager').disabled = True
logger = logging.getLogger()

def read_sosi_file(filepath):
    """
    Leser en .SOS fil og returnerer geometrien og attributtene i et strukturert format.
    
    Args:
        filepath (str): Stien til SOS-fila.
    
    Returns:
        dict: Data med 'geometry' og 'attributes'.
    """
    parsed_data = {
        'geometry': [],  # Geometrier (LineString, Point, Polygon)
        'attributes': [] 
    }

    kurve_coordinates = {}  # .KURVE geometrier blir behandlet i en egen dictionary pga relasjonen til .FLATE geometrier for å definere gyldige flater
    current_attributes = {}
    all_attributes = set()  # Samler alle mulige attributter
    coordinates = []
    kp = None
    capturing = False
    geom_type = None
    flate_refs = []  # Liste for å holde .REF ID'er for .FLATE
    expecting_coordinates = False  
    coordinate_dim = None  # Resetter for hver ny geometri
    found_2d = False  # Sjekker hvis noen 2D geometrier har blitt funnet

    logger.info(f"Opening file: {filepath}")
    with open(filepath, 'r', encoding='windows-1252') as file:
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
                            uniform_coordinates = convert_to_2d_if_mixed(coordinates, coordinate_dim)
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

                        if kp:
                            current_attributes['KP'] = kp

                        parsed_data['attributes'].append(current_attributes)
                    except Exception as e:
                        logger.error(f"Error at line {line_number}: {line.strip()}")
                        logger.error(f"Error details: {e}")
                        raise

                current_attributes = {}
                coordinates = []
                kp = None
                capturing = True
                geom_type = stripped_line.split()[0]
                flate_refs = []  # Resetter flate.REF
                expecting_coordinates = False
                coordinate_dim = None  # Resetter dimensjon
                found_2d = False  # Resetter 2D flagg
                continue

            if capturing:
                if stripped_line.startswith('..'):
                    key_value = stripped_line[2:].split(maxsplit=1)
                    key = key_value[0].lstrip('.')  
                    if key in ['NØ', 'NØH']:
                        expecting_coordinates = True
                        coordinate_dim = 3 if key == 'NØH' else 2  # Setter dimensjon til 3 hvis geometri har NØH 
                        continue  
                    else:
                        expecting_coordinates = False
                        if len(key_value) == 2:
                            value = key_value[1]
                        else:
                            value = np.nan  # NaN hvis ingen verdi
                        current_attributes[key] = value
                        all_attributes.add(key)  
                elif expecting_coordinates and not stripped_line.startswith('.'):
                    try:
                        parts = stripped_line.split()
                        if coordinate_dim == 2:
                            coord = tuple(map(float, parts[:2]))
                            found_2d = True  
                        else:
                            coord = tuple(map(float, parts[:3]))  # Forventer 3 koordinater for ..NØH
                        coordinates.append(coord)
                        if '...KP' in stripped_line:
                            kp_index = stripped_line.index('...KP')
                            kp_value = stripped_line[kp_index + 5:]  # Fanger alt etter ...KP
                            kp = kp_value.strip()
                    except ValueError:
                        pass
                elif stripped_line.startswith('.') and not stripped_line.startswith('..'):
                    expecting_coordinates = False  # Koordinater avsluttes hvis ny geometriblokk fanges

    if capturing:
        try:
            if coordinates:
                uniform_coordinates = convert_to_2d_if_mixed(coordinates, coordinate_dim)
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

            if kp:
                current_attributes['KP'] = kp

            parsed_data['attributes'].append(current_attributes)
        except Exception as e:
            logger.error(f"Error at end of file with last object")
            logger.error(f"Error details: {e}")
            raise

    # Sjekker at vi ha fanget like mange set med geometrier som attributter
    if len(parsed_data['geometry']) != len(parsed_data['attributes']):
        logger.warning(f"Mismatch between geometries and attributes: {len(parsed_data['geometry'])} vs {len(parsed_data['attributes'])}")
        

    logger.info(f"Total parsed geometries: {len(parsed_data['geometry'])}")
    logger.info(f"Total parsed attributes: {len(parsed_data['attributes'])}")

    return parsed_data, all_attributes

def convert_to_2d_if_mixed(coordinates, dimension):
    """
    Konverterer alle koordinater til 2D hvis noen 2D-koordinater er funnet, ellers beholder de som 3D.

    Args:
        coordinates (list): Liste over tupler som representerer koordinater.
        dimension (int): Den forventede dimensjonen (2 eller 3).

    Returns:
        list: Liste over tupler med ensartede dimensjoner.
    """
    has_2d = any(len(coord) == 2 for coord in coordinates)
    if has_2d:
        return [(x, y) for x, y, *z in coordinates]  # Konverterer blandete geometrier (har både NØ og NØH til 2D)
    elif dimension == 3:
        # Beholder geometrier som kun har NØH som 3D 
        return coordinates
    else:
        return [(x, y) for x, y in coordinates]  

def sosi_to_geodataframe(parsed_data, all_attributes):
    """
    Konverterer tolkede SOSI-data til en GeoDataFrame.

    Args:
        parsed_data (dict): Tolkede SOSI-data med 'geometry' og 'attributes'.
        all_attributes (set): Sett med alle registrerte attributter.

    Returns:
        gpd.GeoDataFrame: GeoDataFrame som inneholder SOSI-dataene.
    """
    geometries = parsed_data['geometry']
    attributes = parsed_data['attributes']

    if len(geometries) != len(attributes):
        logger.warning(f"Mismatch found: {len(geometries)} geometries, {len(attributes)} attributes")
        min_length = min(len(geometries), len(attributes))
        geometries = geometries[:min_length]
        attributes = attributes[:min_length]

    df = pd.DataFrame(attributes)
    
    # Sjekker at alle attributter er til stede
    for attribute in all_attributes:
        if attribute not in df:
            df[attribute] = np.nan

    gdf = gpd.GeoDataFrame(df, geometry=geometries)

    return gdf
