# https://github.com/jesperfjellin/sosilogikk

import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, LineString, Polygon
import shapely.affinity
import numpy as np
import logging

# Logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logging.getLogger('matplotlib.font_manager').disabled = True
logger = logging.getLogger()

def process_object(obj_dict, parsed_data, sosi_index, object_id):
    geom_type = obj_dict.get('OBJTYPE', None)
    coordinates = None
    attributes = {}

    # Extract coordinates
    if 'NØ' in obj_dict:
        # 2D coordinates
        coords = obj_dict['NØ']
        coordinates = [c['coord'] for c in coords]
    elif 'NØH' in obj_dict:
        # 3D coordinates
        coords = obj_dict['NØH']
        coordinates = [c['coord'] for c in coords]

    # Assign geometry based on object type
    if coordinates:
        if 'PUNKT' in obj_dict:
            geometry = Point(coordinates[0])
        elif 'KURVE' in obj_dict:
            geometry = LineString(coordinates)
        elif 'FLATE' in obj_dict:
            geometry = Polygon(coordinates)
        else:
            geometry = None
    else:
        geometry = None

    # Collect attributes (excluding coordinate data)
    for key, value in obj_dict.items():
        if key not in ['NØ', 'NØH']:
            attributes[key] = value

    # Update parsed_data
    if geometry:
        parsed_data['geometry'].append(geometry)
        parsed_data['attributes'].append(attributes)
        sosi_index[object_id] = obj_dict

def read_sosi_file(filepath):
    """
    Leser en SOSI-fil og returnerer geometri, attributter, ...ENHET-verdi, og en indeks for hvert objekt.
    
    Args:
        filepath (str): Sti til SOSI-fil.
    
    Returns:
        dict: Data med 'geometry' og 'attributes'.
        set: Alle attributter skriptet kommer over.
        float: Unit scale (fra ...ENHET).
        dict: SOSI index mapping av objekt ID til original_context (posisjon i innlest SOSI-fil.
        tuple: MIN-NØ og MAX-NØ verdier (min_n, min_e, max_n, max_e).
    """
  
    parsed_data = {
        'geometry': [],
        'attributes': []
    }
    enhet_scale = None
    sosi_index = {}
    all_attributes = set()
    object_id = 0

    # Variables for tracking
    stack = []  # Stack to keep track of nesting levels
    current_object = None
    min_n, min_e = float('inf'), float('inf')
    max_n, max_e = float('-inf'), float('-inf')

    try:
        with open(filepath, 'r', encoding='utf-8') as file:
            lines = file.readlines()

        line_number = 0
        while line_number < len(lines):
            line = lines[line_number]
            stripped_line = line.strip()
            if not stripped_line:
                line_number += 1
                continue  # Skip empty lines

            # Count the number of leading dots
            dot_count = len(line) - len(line.lstrip('.'))
            content = line.lstrip('.').strip()

            # Handle coordinate data under NØ or NØH
            if dot_count == 0:
                if stack and stack[-1]['key'] in ['NØ', 'NØH']:
                    coords = []
                    while line_number < len(lines) and not lines[line_number].strip().startswith('.'):
                        coord_line = lines[line_number].strip()
                        # Check for ...KP in the line
                        if '...KP' in coord_line:
                            coord_part, kp_part = coord_line.split('...KP')
                            kp_value = kp_part.strip()
                        else:
                            coord_part = coord_line
                            kp_value = None
                        parts = coord_part.strip().split()
                        if len(parts) >= 2:
                            x = float(parts[1])
                            y = float(parts[0])
                            if len(parts) == 3:
                                z = float(parts[2])
                                coord = (x, y, z)
                            else:
                                coord = (x, y)
                            coords.append({'coord': coord, 'KP': kp_value})
                            # Update min/max coordinates
                            min_n = min(min_n, y)
                            min_e = min(min_e, x)
                            max_n = max(max_n, y)
                            max_e = max(max_e, x)
                        line_number += 1
                    # Assign coordinates to the current attribute
                    current_attr = stack.pop()
                    current_dict = stack[-1]['dict']
                    current_dict[current_attr['key']] = coords
                    continue  # Skip the line_number increment at the end
                else:
                    line_number += 1
                    continue

            # Adjust the stack to match the current dot_count
            while len(stack) > dot_count:
                stack.pop()

            # Split the content into key and value
            if ' ' in content:
                key, value = content.split(' ', 1)
            else:
                key = content
                value = None

            # Handle special cases like ...ENHET, ...MIN-NØ, ...MAX-NØ
            if dot_count >= 3 and key in ['ENHET', 'MIN-NØ', 'MAX-NØ']:
                parts = content.split()
                if key == 'ENHET':
                    try:
                        enhet_scale = float(parts[1])
                    except (IndexError, ValueError):
                        raise ValueError(f"SOSILOGIKK: Invalid ...ENHET value at line {line_number}: {line.strip()}")
                elif key == 'MIN-NØ':
                    min_e = float(parts[1])
                    min_n = float(parts[2])
                elif key == 'MAX-NØ':
                    max_e = float(parts[1])
                    max_n = float(parts[2])
                line_number += 1
                continue

            # Build the current attribute dictionary
            current_dict_entry = {'dict': {}, 'key': key}
            if value is not None:
                current_dict_entry['dict'] = value
                all_attributes.add(key)
            else:
                current_dict_entry['dict'] = {}
            stack.append(current_dict_entry)

            # If this is a top-level object, store it
            if dot_count == 1:
                if current_object:
                    # Process the previous object
                    process_object(current_object['dict'], parsed_data, sosi_index, object_id)
                    object_id += 1
                current_object = current_dict_entry
            else:
                # Add to the parent dictionary
                parent_dict = stack[-2]['dict']
                if isinstance(parent_dict, dict):
                    parent_dict[key] = current_dict_entry['dict']
                else:
                    # Handle the case where the parent is a value, not a dict
                    pass

            line_number += 1

        # After the loop, store the last object
        if current_object:
            process_object(current_object['dict'], parsed_data, sosi_index, object_id)
            object_id += 1

        # Check for ...ENHET
        if enhet_scale is None:
            raise ValueError(f"SOSILOGIKK: Missing ...ENHET value in file {filepath}.")

        return parsed_data, all_attributes, enhet_scale, sosi_index, (min_n, min_e, max_n, max_e)

    except Exception as e:
        logger.error(f"SOSILOGIKK: An error occurred: {str(e)}")
        raise


def convert_to_2d_if_mixed(coordinates, dimension):
    """
    Konverterer blandete geometrier (geometri med både 2D- og 3D-koordinater) til ren 2D-geometri.
    Dette er nødvendig for å laste geometrien inn i en GeoPandas GeoDataFrame, som krever 2D-geometri for å fungere korrekt.

    Args:
        coordinates (list): Liste over koordinater (som kan være 2D eller 3D).
        dimension (int): Antall dimensjoner i geometrien (2 eller 3).

    Returns:
        list: En liste med 2D-koordinater (y, x) hvis det finnes blanding av 2D og 3D koordinater.
              Returnerer 3D-koordinater (y, x, z) hvis geometrien har 3 dimensjoner.
    """
    has_2d = any(len(coord) == 2 for coord in coordinates)
    if has_2d:
        return [(y, x) for x, y, *z in coordinates]  # Swapped x and y
    elif dimension == 3:
        return [(y, x, z) for x, y, z in coordinates]  # Swapped x and y, keep z
    else:
        return [(y, x) for x, y in coordinates]  # Swapped x and y
    
def force_2d(geom):
    """
    Fjerner Z-dimensjonen fra en geometritype som har 3D-koordinater, og konverterer geometrien til 2D.
    Funksjonen støtter punkt, linje, og polygon-geometrier. Koordinatene blir også ombyttet slik at de returneres som (y, x).

    Args:
        geom (shapely.geometry): Shapely-geometriobjekt som kan være et punkt, linje, eller polygon.

    Returns:
        shapely.geometry: Geometriobjekt konvertert til 2D med (y, x) koordinater.
                         Returnerer originalgeometrien hvis den allerede er 2D.
    """
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
    Konverterer parsede SOSI-data til en GeoDataFrame, og håndterer flere input-filer hvis gitt.

    Args:
        sosi_data_list (liste eller dict): Parsede SOSI-data med 'geometry' og 'attributes'.
        all_attributes_list (liste eller sett): Sett med alle registrerte attributter.
        scale_factors (liste eller float): Skaleringsfaktor(er) fra ...ENHET.

    Returns:
        gpd.GeoDataFrame: GeoDataFrame som inneholder SOSI-dataene.
        tuple: Totalt utstrekning (min_n, min_e, max_n, max_e).
    """
    # Sørger for at input SOSI-filer utgjør en liste, selv om det kun er en SOSI-fil som blir brukt
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

        # Sjekker om det er en mismatch mellom antall attributter og geometrier (det skal være et 1:1 forhold, ellers er det geometrier som ikke har noen attributter
        if len(geometries) != len(attributes):
            print(f"SOSILOGIKK: Advarsel: mismatch funnet: {len(geometries)} geometrier, {len(attributes)} attributter")
            min_length = min(len(geometries), len(attributes))
            geometries = geometries[:min_length]
            attributes = attributes[:min_length]

        # Anvender ...ENHET verdi (scale_factor) på geometri
        scaled_geometries = scale_geometries(geometries, scale_factor)

        # Lager DataFrame fra attributter
        df = pd.DataFrame(attributes)

        # Sjekker at alle attributter er til stede i DataFrame
        for attribute in all_attributes:
            if attribute not in df:
                df[attribute] = np.nan

        # Lager GeoDataFrame
        gdf = gpd.GeoDataFrame(df, geometry=scaled_geometries)

        # Legger til 'original_id' kolonne i GeoDataFramen for å holde styr på den originale posisjonen til hvert geometriske objekt i de originale SOSI-filene
        gdf['original_id'] = range(len(gdf))

        gdfs.append(gdf)
        
        # Oppdaterer total min max koordinater
        min_n, min_e, max_n, max_e = gdf.total_bounds
        overall_min_n = min(overall_min_n, min_n)
        overall_min_e = min(overall_min_e, min_e)
        overall_max_n = max(overall_max_n, max_n)
        overall_max_e = max(overall_max_e, max_e)
    
    # Slår sammen alle GeoDataFrames
    combined_gdf = pd.concat(gdfs, ignore_index=True)
    combined_gdf['original_id'] = range(len(combined_gdf))
    
    return combined_gdf, (overall_min_n, overall_min_e, overall_max_n, overall_max_e)


def scale_geometries(geometries, scale_factor=1.0):
    """
    Skalerer geometrier i henhold til den oppgitte skaleringsfaktoren.

    Args:
        geometries (liste over shapely.geometry): Liste over geometrier som skal skaleres.
        scale_factor (float): Skaleringsfaktoren som skal brukes på geometrier.

    Returns:
        liste over shapely.geometry: De skalerte geometrier.
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
    Skriver en GeoDataFrame tilbake til en SOSI-fil, og bruker valgfritt den originale SOSI-indeksen for å bevare formateringen.

    Args:
        gdf (gpd.GeoDataFrame): GeoDataFrame som inneholder SOSI-data.
        sosi_index (dict): Indeks som mapper objekt-IDer til original SOSI-innhold.
        output_filepath (str eller Path): Sti der den nye SOSI-filen vil bli skrevet.
        extent (tuple): Utstrekningen av dataene (min_n, min_e, max_n, max_e).
        enhet_scale (float): Skaleringsfaktoren for koordinatene.
        use_index (bool): Om SOSI-indeksen skal brukes for skriving (standard er True).

    Returns:
        bool: True hvis filen ble skrevet vellykket, False ellers.
    """
    logger = logging.getLogger(__name__)
    logger.info(f"SOSILOGIKK: Skriver GeoDataFrame til SOSI-fil: {output_filepath}")
    min_n, min_e, max_n, max_e = extent
    
    try:
        with open(output_filepath, 'w', encoding='utf-8') as outfile:
            # Write the SOSI file header
            logger.info("SOSILOGIKK: Skriver .HODE seksjon...")
            outfile.write(".HODE\n..TEGNSETT UTF-8\n..OMRÅDE\n")
            outfile.write(f"...MIN-NØ {min_e:.2f} {min_n:.2f}\n")  # Reversert rekkefølge for FYSAK
            outfile.write(f"...MAX-NØ {max_e:.2f} {max_n:.2f}\n")  # Reversert rekkefølge for FYSAK
            
            if enhet_scale is not None:
                enhet_str = f"{enhet_scale:.6f}".rstrip('0').rstrip('.')
                outfile.write(f"...ENHET {enhet_str}\n")
            else:
                logger.warning("SOSILOGIKK: enhet_scale er None, ignorerer ...ENHET linje")
            
            logger.info(f"SOSILOGIKK: GeoDataFrame lengde: {len(gdf)}")
            if use_index:
                logger.info(f"SOSILOGIKK: SOSI index størrelse: {len(sosi_index)}")
                written_ids = set()

                for index, row in gdf.iterrows():
                    original_id = row.get('original_id')
                    
                    if original_id is None:
                        logger.warning(f"SOSILOGIKK: Rad {index} har ingen original_id. Hopper over.")
                        continue

                    if original_id in written_ids:
                        logger.info(f"SOSILOGIKK: Hopper over duplisert innhold for original_id: {original_id}")
                        continue

                    if original_id not in sosi_index:
                        logger.warning(f"SOSILOGIKK: Ingen SOSI index verdi for original_id: {original_id}. Hopper over.")
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

            outfile.write(".SLUTT\n")

        #logger.info(f"Successfully wrote SOSI file to {output_filepath}")
        return True

    except IOError as e:
        logger.error(f"SOSILOGIKK: IO error oppstod mens SOSI-fil ble skrevet: {str(e)}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"SOSILOGIKK: Uforventet error oppstod mens SOSI-fil ble skrevet: {str(e)}", exc_info=True)
        return False