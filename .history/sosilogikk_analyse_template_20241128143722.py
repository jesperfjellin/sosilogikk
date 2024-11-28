#
#
#
#
# Dette er en template for å lage en analyse av SOSI-filer ved bruk av 'sosilogikk', en Python-pakke skrevet av Jesper Fjellin. Alt som trengs er å erstatte funksjoner i 'analyze_gdf' med den egne analysene.
#
#
#
#
#






import os
import logging
from pathlib import Path
from module.sosilogikk import read_sosi_file, sosi_to_geodataframe, write_geodataframe_to_sosi

# Konfigurer logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def read_sosi_to_gdf(sos_filepath):
    """
    Leser en SOSI-fil og konverterer den til en GeoDataFrame.

    Args:
        sos_filepath (str | Path): Sti til SOSI-filen.

    Returns:
        tuple: (GeoDataFrame, SOSI-indeks, målestokk-faktor, utstrekning, header-metadata)
    """
    logger.info(f"Leser fil: {sos_filepath}")
    
    # Les og konverter SOSI-filen i ett trinn
    parsed_data, all_attributes, enhet_scale, sosi_index, extent, header_metadata = read_sosi_file(sos_filepath)
    gdf, extent = sosi_to_geodataframe(parsed_data, all_attributes, enhet_scale)
    
    return gdf, sosi_index, enhet_scale, extent, header_metadata

def analyze_gdf(gdf):
    """
    Utfører analyse på GeoDataFrame.
    Erstatt denne funksjonen med din spesifikke analyse.

    Args:
        gdf (gpd.GeoDataFrame): Input GeoDataFrame.

    Returns:
        gpd.GeoDataFrame: Behandlet GeoDataFrame.
    """
    
    
    # Resultatet av analysen skal være en modifisert GeoDataFrame
    return gdf

def process_sosi_file(input_path, output_path):
    """
    Behandler en enkelt SOSI-fil.

    Args:
        input_path (Path): Sti til input SOSI-fil
        output_path (Path): Sti til output SOSI-fil
    """
    try:
        # Les og prosesser
        gdf, sosi_index, enhet_scale, extent, header_metadata = read_sosi_to_gdf(input_path)
        processed_gdf = analyze_gdf(gdf)

        # Oppdater metadata og skriv
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
            logger.info(f"Vellykket prosessering av: {input_path.name}")
        else:
            logger.error(f"Kunne ikke skrive fil: {output_path}")
            
    except Exception as e:
        logger.error(f"Feil under prosessering av {input_path.name}: {str(e)}")
        raise

def main():
    # Definer input/output-mapper
    input_dir = Path(r'sti/til/mappe/med/.sos/filer')
    output_dir = Path(r'sti/til/output/mappe')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Prosesser alle SOSI-filer
    for sosi_file in input_dir.glob('*.sos'):
        output_path = output_dir / f"processed_{sosi_file.name}"
        process_sosi_file(sosi_file, output_path)

if __name__ == "__main__":
    main()