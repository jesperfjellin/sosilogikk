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

__version__ = '1.0.17'
logger = logging.getLogger(__name__)
logger.info(f"sosilogikk version: {__version__}")

def read_sosi_file(filepath):
    """
    Leser en SOSI-fil og returnerer geometri, attributter, ...ENHET-verdi, og en indeks for hvert objekt.
    
    Args:
        filepath (str): Sti til SOSI-fil.
    
    Returns:
        dict: Data med 'geometry' og 'attributes'.
        set: Alle attributter skriptet kommer over.
        float: Unit scale (fra ...ENHET).
        dict: SOSI index mapping av objekt ID til original_context.
        tuple: MIN-NØ og MAX-NØ verdier (min_n, min_e, max_n, max_e).
        dict: Header metadata including VERT-DATUM, KOORDSYS, etc.
    """
    
    parsed_data = {
        'geometry': [],  # Geometrier (punkt, kurve, flate)
        'attributes': [] 
    }
    enhet_scale = None  # ...ENHET verdi for innlest fil
    sosi_index = {}  # Initialiserer SOSI index
    all_attributes = set()  # Initialiserer set for alle attributter
    current_object = []  # Midlertidig liste for å holde nåværende objekts egenskaper
    object_id = 0  # Unik ID for hvert objekt

    # Andre variabler for å håndtere geometrier og attributter
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

    # Header metadata dictionary
    header_metadata = {
        'ENHET': None,
        'VERT-DATUM': None,
        'KOORDSYS': None,
        'ORIGO-NØ': None,
        'SOSI-VERSJON': None,
        'SOSI-NIVÅ': None,
        'OBJEKTKATALOG': None
    }
    
    encoding_map = {
        'ISO8859-10': 'iso-8859-10',
        'ISO8859-1': 'iso-8859-1',
        'UTF-8': 'utf-8-sig',
        'ANSI': 'cp1252'
        # Add more mappings as needed
    }

    # Default to UTF-8 for initial read to get TEGNSETT
    file_encoding = 'utf-8-sig'
    
    try:
        # First try to read the header with UTF-8 to find TEGNSETT
        with open(filepath, 'r', encoding='utf-8-sig') as file:
            for line in file:
                if line.strip().startswith('..TEGNSETT'):
                    specified_encoding = line.strip().split()[-1]
                    file_encoding = encoding_map.get(specified_encoding, 'utf-8-sig')
                    logger.info(f"SOSILOGIKK: Found character encoding: {specified_encoding}, using: {file_encoding}")
                    break
                if line.strip().startswith('.KURVE') or line.strip().startswith('.PUNKT'):
                    # If we hit geometry without finding TEGNSETT, stop looking
                    break
    except UnicodeDecodeError:
        # If UTF-8 fails, try ISO-8859-1 to read TEGNSETT
        try:
            with open(filepath, 'r', encoding='iso-8859-1') as file:
                for line in file:
                    if line.strip().startswith('..TEGNSETT'):
                        specified_encoding = line.strip().split()[-1]
                        file_encoding = encoding_map.get(specified_encoding, 'iso-8859-1')
                        logger.info(f"SOSILOGIKK: Found character encoding: {specified_encoding}, using: {file_encoding}")
                        break
                    if line.strip().startswith('.KURVE') or line.strip().startswith('.PUNKT'):
                        break
        except UnicodeDecodeError:
            logger.warning("SOSILOGIKK: Could not read TEGNSETT, defaulting to ISO-8859-1")
            file_encoding = 'iso-8859-1'

    try:
        with open(filepath, 'r', encoding=file_encoding) as file:
            in_header = False
            current_section = None
            #logger.debug("Starting to read file...")
            
            for line_number, line in enumerate(file, 1):
                stripped_line = line.strip()

                # Skip comment lines
                if stripped_line.startswith('!'):
                    continue

                # Start header section
                if stripped_line == '.HODE':
                    in_header = True
                    #logger.debug("Found .HODE section")
                    continue

                # End header section if we hit a geometric object or end of file
                if stripped_line.startswith(('.KURVE', '.PUNKT', '.FLATE', '.SLUTT')):
                    #logger.debug("Exiting header section")
                    in_header = False
                    # Continue with geometric object processing
                    if capturing:
                        try:
                            if coordinates and current_attributes:
                                uniform_coordinates = convert_to_2d_if_mixed(coordinates, coordinate_dim)
                                if geom_type == '.KURVE':
                                    objtype_value = current_attributes.get('OBJTYPE', '')
                                    if objtype_value:
                                        kurve_id = objtype_value.split()[-1]
                                    else:
                                        if current_attributes.get('ENDRET', '') == 'H':
                                            kurve_id = f"kurve_{object_id}"
                                        else:
                                            logger.error(f"SOSILOGIKK: Missing OBJTYPE for KURVE at line {line_number} without ..ENDRET H.")
                                            raise ValueError(f"SOSILOGIKK: OBJTYPE missing in KURVE at line {line_number} and not marked as deleted with ..ENDRET H.")

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
                            object_id += 1
                        except Exception as e:
                            logger.error(f"SOSILOGIKK: Error processing object ending at line {line_number}: {line.strip()}")
                            logger.error(f"SOSILOGIKK: Error detaljer: {e}")
                            raise

                    current_attributes = {}
                    coordinates = []
                    kp = None
                    capturing = True
                    geom_type = stripped_line.split()[0]
                    flate_refs = []
                    expecting_coordinates = False
                    coordinate_dim = None
                    found_2d = False
                    current_object = [line]
                    continue

                # Process header content
                if in_header:
                    if stripped_line.startswith('..') and not stripped_line.startswith('...'):
                        # Two-dot line indicates a new section
                        current_section = stripped_line.split()[0]
                        #logger.debug(f"Found header section: {current_section}")
                    elif stripped_line.startswith('...'):
                        # Three-dot line is an attribute of current section
                        attr_name, attr_value = stripped_line[3:].split(maxsplit=1)
                        #logger.debug(f"Processing header attribute: {attr_name} = {attr_value} in section {current_section}")
                        
                        if current_section == '..TRANSPAR':
                            if attr_name == 'ENHET':
                                enhet_scale = float(attr_value)
                                header_metadata['ENHET'] = enhet_scale
                                logger.info(f"Found ENHET value: {enhet_scale}")
                            elif attr_name == 'VERT-DATUM':
                                header_metadata['VERT-DATUM'] = attr_value
                            elif attr_name == 'KOORDSYS':
                                header_metadata['KOORDSYS'] = attr_value
                            elif attr_name == 'ORIGO-NØ':
                                header_metadata['ORIGO-NØ'] = attr_value
                        elif current_section == '..OMRÅDE':
                            if attr_name == 'MIN-NØ':
                                min_n, min_e = map(float, attr_value.split())
                            elif attr_name == 'MAX-NØ':
                                max_n, max_e = map(float, attr_value.split())
                    continue

                # Rest of the existing code for capturing attributes and coordinates
                if capturing:
                    current_object.append(line)
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
                                if len(parts) < 2:
                                    raise IndexError("Not enough coordinate components for 2D point.")
                                x_str, y_str = parts[0], parts[1]
                                coord = (float(y_str), float(x_str))
                                found_2d = True
                            else:
                                if len(parts) < 3:
                                    raise IndexError("Not enough coordinate components for 3D point.")
                                x_str, y_str, z_str = parts[0], parts[1], parts[2]
                                coord = (float(y_str), float(x_str), float(z_str))
                            coordinates.append(coord)
                        except (ValueError, IndexError) as e:
                            logger.error(f"SOSILOGIKK: Error parsing coordinates at line {line_number} in object {geom_type}: {line.strip()} - {e}")
                            raise
                    elif stripped_line.startswith('.') and not stripped_line.startswith('..'):
                        expecting_coordinates = False
                    else:
                        if geom_type == '.FLATE' and stripped_line.startswith('KP'):
                            flate_refs.append(stripped_line)

        # Save the last object if there is one
        if capturing and coordinates and current_attributes:
            try:
                uniform_coordinates = convert_to_2d_if_mixed(coordinates, coordinate_dim)
                if geom_type == '.KURVE':
                    parsed_data['geometry'].append(LineString(uniform_coordinates))
                elif geom_type == '.PUNKT' and len(uniform_coordinates) == 1:
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
                            parsed_data['geometry'].append(Point(uniform_coordinates[0]))
                    else:
                        parsed_data['geometry'].append(Point(uniform_coordinates[0]))
                parsed_data['attributes'].append(current_attributes)
                sosi_index[object_id] = current_object
            except Exception as e:
                logger.error(f"SOSILOGIKK: Error processing final object: {e}")
                raise

        # Check if we found ENHET value
        if enhet_scale is None:
            logger.error(f"SOSILOGIKK: Mangler ...ENHET linje i SOSI-fil {filepath}. Denne filen er ugyldig. Avslutter.")
            raise ValueError(f"SOSILOGIKK: ...ENHET verdi ikke funnet i fil {filepath}. Avslutter.")

        logger.info(f"SOSILOGIKK: ...ENHET-verdi for innlest fil: {enhet_scale}")
        logger.info(f"SOSILOGIKK: MIN-NØ: {min_n}, {min_e}, MAX-NØ: {max_n}, {max_e}")

    except Exception as e:
        logger.error(f"SOSILOGIKK: En error oppstod i read_sosi_file funksjon: {str(e)}")
        raise

    return parsed_data, all_attributes, enhet_scale, sosi_index, (min_n, min_e, max_n, max_e), header_metadata


def convert_to_2d_if_mixed(coordinates, dimension):
    """
    Konverterer blandete geometrier (geometri med både 2D- og 3D-koordinater) til ren 2D-geometri.
    Dette er nødvendig for å laste geometrien inn i en GeoPandas GeoDataFrame, som krever 2D-geometri for �� fungere korrekt.

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

        # Sjekker om det er en mismatch mellom antall attributter og geometrier
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


def write_geodataframe_to_sosi(gdf, output_file, metadata=None, sosi_index=None, extent=None, use_index=True):
    """
    Skriver en GeoDataFrame tilbake til en SOSI-fil.

    Args:
        gdf (gpd.GeoDataFrame): GeoDataFrame som inneholder SOSI-data.
        output_file (str): Sti der den nye SOSI-filen vil bli skrevet.
        metadata (dict): Header metadata (VERT-DATUM, KOORDSYS, etc.).
        sosi_index (dict, optional): Indeks som mapper objekt-IDer til original SOSI-innhold.
        extent (tuple, optional): Utstrekningen av dataene (min_n, min_e, max_n, max_e).
        use_index (bool, optional): Om SOSI-indeksen skal brukes for skriving (standard er True).

    Returns:
        bool: True hvis filen ble skrevet vellykket, False ellers.
    """
    logger = logging.getLogger(__name__)
    logger.info(f"SOSILOGIKK: Skriver GeoDataFrame til SOSI-fil: {output_file}")
    
    if extent is None:
        # Calculate extent from GeoDataFrame if not provided
        bounds = gdf.total_bounds
        min_n, min_e, max_n, max_e = bounds
    else:
        min_n, min_e, max_n, max_e = extent

    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            # Write the SOSI file header
            logger.info("SOSILOGIKK: Skriver .HODE seksjon...")
            f.write('.HODE\n')
            f.write('..TEGNSETT UTF-8\n')
            
            # Write TRANSPAR section
            f.write('..TRANSPAR\n')
            f.write(f'...ENHET {metadata.get("ENHET", "0.01")}\n')
            if metadata and 'VERT-DATUM' in metadata:
                f.write(f'...VERT-DATUM {metadata["VERT-DATUM"]}\n')
            if metadata and 'KOORDSYS' in metadata:
                f.write(f'...KOORDSYS {metadata["KOORDSYS"]}\n')
            f.write('...ORIGO-NØ 0 0\n')
            
            # Write OMRÅDE section
            f.write('..OMRÅDE\n')
            f.write(f'...MIN-NØ {min_n:.2f} {min_e:.2f}\n')
            f.write(f'...MAX-NØ {max_n:.2f} {max_e:.2f}\n')
            
            # Write version info
            if metadata and 'SOSI-VERSJON' in metadata:
                f.write(f'..SOSI-VERSJON {metadata["SOSI-VERSJON"]}\n')
            if metadata and 'SOSI-NIVÅ' in metadata:
                f.write(f'..SOSI-NIVÅ {metadata["SOSI-NIVÅ"]}\n')
            if metadata and 'OBJEKTKATALOG' in metadata:
                f.write(f'..OBJEKTKATALOG {metadata["OBJEKTKATALOG"]}\n')

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

                    f.writelines(sosi_index[original_id])
                    written_ids.add(original_id)
            else:
                # Write each row without using the index
                for index, row in gdf.iterrows():
                    f.write(f".OBJTYPE {row['OBJTYPE']}\n")
                    for key, value in row.items():
                        if key not in ['geometry', 'OBJTYPE']:
                            f.write(f"..{key} {value}\n")
                    
                    # Write geometry
                    geom = row['geometry']
                    if geom.geom_type == 'Polygon':
                        f.write("..FLATE\n")
                        for x, y in geom.exterior.coords:
                            f.write(f"...KURVE {x:.2f} {y:.2f}\n")  # Coordinates as is
                    elif geom.geom_type == 'LineString':
                        f.write("..KURVE\n")
                        for x, y in geom.coords:
                            f.write(f"...KURVE {x:.2f} {y:.2f}\n")  # Coordinates as is
                    elif geom.geom_type == 'Point':
                        f.write(f"..PUNKT {geom.x:.2f} {geom.y:.2f}\n")  # Coordinates as is
                    
                    f.write("..NØ\n")

            f.write(".SLUTT\n")

        #logger.info(f"Successfully wrote SOSI file to {output_filepath}")
        return True

    except IOError as e:
        logger.error(f"SOSILOGIKK: IO error oppstod mens SOSI-fil ble skrevet: {str(e)}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"SOSILOGIKK: Uforventet error oppstod mens SOSI-fil ble skrevet: {str(e)}", exc_info=True)
        return False