import pandas as pd
import geopandas as gpd
from shapely.geometry import LineString, Point, Polygon
import shapely.affinity
import numpy as np
import logging
import os

# Logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logging.getLogger('matplotlib.font_manager').disabled = True
logger = logging.getLogger()

__version__ = '2.0.0'
logger = logging.getLogger(__name__)
logger.info(f"sosilogikk version: {__version__}")


# ============================================================================
# PUBLIC API
# ============================================================================

def read_sosi(filepath, return_metadata=False):
    """
    Read one or more SOSI files and return a GeoDataFrame.

    This is the main entry point: it handles parsing, unit scaling, CRS mapping,
    and conversion to a GeoDataFrame.

    Args:
        filepath (str or list): Path to a SOSI file, or list of paths.
        return_metadata (bool): Whether to also return header/extent metadata.

    Returns:
        gpd.GeoDataFrame: GeoDataFrame with geometry and attributes from the SOSI file(s).
        dict (optional): Metadata if return_metadata=True, containing:
            - 'enhet_scale': float, unit scale from ...ENHET
            - 'extent': tuple (min_n, min_e, max_n, max_e)
            - 'header': dict with VERT-DATUM, KOORDSYS, etc.
            - 'sosi_index': dict, mapping of object ID to original content
            - 'all_attributes': set of all attributes

    Examples:
        >>> # Read a single file
        >>> gdf = read_sosi('data.sos')

        >>> # Read multiple files and combine them
        >>> gdf = read_sosi(['file1.sos', 'file2.sos'])

        >>> # Read with metadata
        >>> gdf, metadata = read_sosi('data.sos', return_metadata=True)
    """
    # Handle single file vs list of files
    if isinstance(filepath, (str, os.PathLike)):
        filepaths = [filepath]
    else:
        filepaths = filepath

    # Les alle filene
    sosi_data_list = []
    all_attributes_list = []
    scale_factors = []
    sosi_indexes = {}
    header_metadatas = []

    for idx, fp in enumerate(filepaths):
        result = _read_sosi_file(fp)
        sosi_data_list.append(result['data'])
        all_attributes_list.append(result['all_attributes'])
        scale_factors.append(result['enhet_scale'])
        sosi_indexes[idx] = result['sosi_index']
        header_metadatas.append(result['header_metadata'])

    # Konverter til GeoDataFrame
    gdf, extent = _sosi_to_geodataframe(
        sosi_data_list,
        all_attributes_list,
        scale_factors,
        header_metadatas=header_metadatas,
    )

    if return_metadata:
        # Combine metadata from all files
        # For simplicity, use header metadata from the first file
        metadata = {
            'enhet_scale': scale_factors[0] if len(scale_factors) == 1 else scale_factors,
            'extent': extent,
            'header': header_metadatas[0] if len(header_metadatas) == 1 else header_metadatas,
            'sosi_index': sosi_indexes[0] if len(sosi_indexes) == 1 else sosi_indexes,
            'all_attributes': set.union(*all_attributes_list)
        }
        return gdf, metadata
    else:
        return gdf


def write_sosi(gdf, output_filepath, metadata=None, use_index=True):
    """
    Write a GeoDataFrame back to a SOSI file.

    Args:
        gdf (gpd.GeoDataFrame): GeoDataFrame to serialize to SOSI.
        output_filepath (str): Path where the SOSI file will be written.
        metadata (dict, optional): Metadata from read_sosi() with header info.
                                   If None, defaults are used.
        use_index (bool): Whether to reuse the original SOSI index (default True).

    Returns:
        bool: True if writing succeeded, False otherwise.

    Examples:
        >>> # Read, modify, and write back
        >>> gdf, metadata = read_sosi('input.sos', return_metadata=True)
        >>> gdf['new_attribute'] = 'value'
        >>> write_sosi(gdf, 'output.sos', metadata=metadata)
    """
    # Unpack metadata if present
    if metadata is not None:
        header_metadata = metadata.get('header', {})
        extent = metadata.get('extent', None)
        sosi_index = metadata.get('sosi_index', None)
    else:
        # Use empty dict for header_metadata so default values are used
        header_metadata = {}
        extent = None
        sosi_index = None

    return _write_geodataframe_to_sosi(
        gdf,
        output_filepath,
        metadata=header_metadata,
        sosi_index=sosi_index,
        extent=extent,
        use_index=use_index
    )


# ============================================================================
# INTERNAL FUNCTIONS
# ============================================================================

def _read_sosi_file(filepath):
    """
    Read a single SOSI file and return geometry, attributes, ...ENHET value, and an index per object.

    Args:
        filepath (str): Path to SOSI file.

    Returns:
        dict: With keys:
            - 'data': dict with 'geometry' and 'attributes'
            - 'all_attributes': set of all attributes
            - 'enhet_scale': float, unit scale from ...ENHET
            - 'sosi_index': dict, mapping of object ID to original context
            - 'extent': tuple (min_n, min_e, max_n, max_e)
            - 'header_metadata': dict with VERT-DATUM, KOORDSYS, etc.
    """
    
    parsed_data = {
        'geometry': [],  # Geometries (point, curve, polygon)
        'attributes': [] 
    }
    enhet_scale = None  # ...ENHET value for the file
    sosi_index = {}  # SOSI index initialization
    all_attributes = set()  # Collect all attribute names
    current_object = []  # Temporary storage for current object's raw lines
    object_id = 0  # Unique ID per object

    # Working variables for geometry/attribute handling
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

    # Default to UTF-8 for initial read to find TEGNSETT
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
                                uniform_coordinates = _convert_to_2d_if_mixed(coordinates, coordinate_dim)
                                if stripped_line.startswith(('.KURVE', '.PUNKT', '.FLATE')):
                                    current_attributes['SOSI_REF'] = stripped_line.split(' ')[1][:-1]
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

                # Capture attributes and coordinates
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
                                # SOSI format: parts[0] is North, parts[1] is East
                                n_str, e_str = parts[0], parts[1]
                                # Store as (East, North) = (x, y) for shapely
                                coord = (float(e_str), float(n_str))
                                found_2d = True
                            else:
                                if len(parts) < 3:
                                    raise IndexError("Not enough coordinate components for 3D point.")
                                # SOSI format: parts[0] is North, parts[1] is East, parts[2] is Height
                                n_str, e_str, h_str = parts[0], parts[1], parts[2]
                                # Store as (East, North, Height) = (x, y, z) for shapely
                                coord = (float(e_str), float(n_str), float(h_str))
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
                uniform_coordinates = _convert_to_2d_if_mixed(coordinates, coordinate_dim)
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

    return {
        'data': parsed_data,
        'all_attributes': all_attributes,
        'enhet_scale': enhet_scale,
        'sosi_index': sosi_index,
        'extent': (min_n, min_e, max_n, max_e),
        'header_metadata': header_metadata
    }


def _convert_to_2d_if_mixed(coordinates, dimension):
    """
    Convert mixed geometries (2D and 3D) to 2D coordinates so GeoPandas can ingest them.

    Args:
        coordinates (list): Coordinates (2D or 3D).
        dimension (int): Declared dimension (2 or 3).

    Returns:
        list: 2D coordinates (x, y) when mixing occurs; otherwise 3D (x, y, z) if present.
    """
    has_2d = any(len(coord) == 2 for coord in coordinates)
    if has_2d:
        # Keep as (East, North)
        return [(x, y) for x, y, *z in coordinates]
    elif dimension == 3:
        # Keep as (East, North, Height)
        return [(x, y, z) for x, y, z in coordinates]
    else:
        # Keep as (East, North)
        return [(x, y) for x, y in coordinates]
    
def _force_2d(geom):
    """
    Drop the Z dimension from a geometry and return a 2D version.
    Supports Point, LineString, and Polygon; keeps x/y ordering.

    Args:
        geom (shapely.geometry): Point, LineString, or Polygon.

    Returns:
        shapely.geometry: 2D geometry (x, y); returns the input if already 2D.
    """
    if geom.has_z:
        if isinstance(geom, shapely.geometry.Point):
            return shapely.geometry.Point(geom.x, geom.y)
        elif isinstance(geom, shapely.geometry.LineString):
            return shapely.geometry.LineString([(x, y) for x, y, z in geom.coords])
        elif isinstance(geom, shapely.geometry.Polygon):
            exterior = [(x, y) for x, y, z in geom.exterior.coords]
            interiors = [[(x, y) for x, y, z in interior.coords] for interior in geom.interiors]
            return shapely.geometry.Polygon(exterior, interiors)
    return geom


def _koordsys_to_epsg(koordsys):
    """
    Maps SOSI KOORDSYS codes to EPSG codes.

    Common Kartverket mappings:
    - 22 -> EPSG:25832 (ETRS89 / UTM 32N)
    - 23 -> EPSG:25833 (ETRS89 / UTM 33N)
    - 25 -> EPSG:25835 (ETRS89 / UTM 35N)
    """
    mapping = {
        "22": 25832,
        "23": 25833,
        "25": 25835,
        22: 25832,
        23: 25833,
        25: 25835,
    }
    return mapping.get(koordsys)


def _sosi_to_geodataframe(sosi_data_list, all_attributes_list, scale_factors, header_metadatas=None):
    """
    Convert parsed SOSI data to a GeoDataFrame, handling multiple input files.

    Args:
        sosi_data_list (list or dict): Parsed SOSI data with 'geometry' and 'attributes'.
        all_attributes_list (list or set): Set of all seen attributes.
        scale_factors (list or float): Scale factors from ...ENHET.
        header_metadatas (list or dict, optional): Header metadata per file.

    Returns:
        gpd.GeoDataFrame: Combined GeoDataFrame.
        tuple: Overall extent (min_n, min_e, max_n, max_e).
    """
    # Normalize inputs to lists even for a single file
    if not isinstance(sosi_data_list, list):
        sosi_data_list = [sosi_data_list]
        all_attributes_list = [all_attributes_list]
        scale_factors = [scale_factors]
        header_metadatas = [header_metadatas] if header_metadatas is not None else [None]
    elif header_metadatas is None:
        header_metadatas = [None] * len(sosi_data_list)
    
    gdfs = []
    epsg_list = []
    overall_min_n, overall_min_e = float('inf'), float('inf')
    overall_max_n, overall_max_e = float('-inf'), float('-inf')
    
    for sosi_data, all_attributes, scale_factor, header_metadata in zip(
        sosi_data_list, all_attributes_list, scale_factors, header_metadatas
    ):
        geometries = sosi_data['geometry']
        attributes = sosi_data['attributes']

        # Guard against mismatched geometry/attribute counts
        if len(geometries) != len(attributes):
            print(f"SOSILOGIKK: Advarsel: mismatch funnet: {len(geometries)} geometrier, {len(attributes)} attributter")
            min_length = min(len(geometries), len(attributes))
            geometries = geometries[:min_length]
            attributes = attributes[:min_length]

        # Apply ...ENHET scale factor
        scaled_geometries = _scale_geometries(geometries, scale_factor)

        # Build DataFrame from attributes
        df = pd.DataFrame(attributes)

        # Ensure all attributes exist as columns
        for attribute in all_attributes:
            if attribute not in df:
                df[attribute] = np.nan

        # Build GeoDataFrame
        gdf = gpd.GeoDataFrame(df, geometry=scaled_geometries)

        epsg = None
        if header_metadata and header_metadata.get("KOORDSYS") is not None:
            epsg = _koordsys_to_epsg(header_metadata.get("KOORDSYS"))
        epsg_list.append(epsg)
        if epsg:
            gdf.set_crs(epsg, inplace=True)

        # Track original position for round-tripping
        gdf['original_id'] = range(len(gdf))

        gdfs.append(gdf)
        
        # Oppdaterer total min max koordinater
        min_n, min_e, max_n, max_e = gdf.total_bounds
        overall_min_n = min(overall_min_n, min_n)
        overall_min_e = min(overall_min_e, min_e)
        overall_max_n = max(overall_max_n, max_n)
        overall_max_e = max(overall_max_e, max_e)
    
    # Merge all GeoDataFrames
    combined_gdf = pd.concat(gdfs, ignore_index=True)
    unique_epsg = {epsg for epsg in epsg_list if epsg is not None}
    if len(unique_epsg) == 1:
        combined_gdf.set_crs(unique_epsg.pop(), inplace=True)
    combined_gdf['original_id'] = range(len(combined_gdf))
    
    return combined_gdf, (overall_min_n, overall_min_e, overall_max_n, overall_max_e)


def _scale_geometries(geometries, scale_factor=1.0):
    """
    Scale geometries by the provided factor.

    Args:
        geometries (list of shapely.geometry): Geometries to scale.
        scale_factor (float): Factor to apply.

    Returns:
        list of shapely.geometry: Scaled geometries.
    """
    scaled_geometries = []
    
    for geom in geometries:
        # Scale the geometry
        if scale_factor != 1.0:
            geom = shapely.affinity.scale(geom, xfact=scale_factor, yfact=scale_factor, origin=(0, 0))
        scaled_geometries.append(geom)
    
    return scaled_geometries


def _write_geodataframe_to_sosi(gdf, output_file, metadata=None, sosi_index=None, extent=None, use_index=True):
    """
    Write a GeoDataFrame back to a SOSI file.

    Args:
        gdf (gpd.GeoDataFrame): GeoDataFrame containing SOSI data.
        output_file (str): Destination path.
        metadata (dict): Header metadata (VERT-DATUM, KOORDSYS, etc.).
        sosi_index (dict, optional): Mapping of object IDs to original SOSI content.
        extent (tuple, optional): Data extent (min_n, min_e, max_n, max_e).
        use_index (bool, optional): Whether to use the SOSI index for writing (default True).

    Returns:
        bool: True if written successfully, False otherwise.
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
