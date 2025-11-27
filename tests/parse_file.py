"""Parse the sample SOSI file and emit a GeoJSON for quick inspection."""

from pathlib import Path
import logging
import sys

# Ensure the project src/ is on the path so we can import the local package when not installed
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
for p in (SRC_ROOT, PROJECT_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from sosilogikk import read_sosi


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    base = Path(__file__).resolve().parent
    sosi_path = base / "data" / "kulturminner.sos"
    output_dir = base / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    geojson_path = output_dir / "kulturminner.geojson"

    logging.info("Reading SOSI from %s", sosi_path)
    gdf, metadata = read_sosi(sosi_path, return_metadata=True)
    logging.info(
        "Parsed %d features; KOORDSYS=%s, ENHET=%s",
        len(gdf),
        metadata["header"].get("KOORDSYS"),
        metadata["enhet_scale"],
    )

    logging.info("Writing GeoJSON to %s", geojson_path)
    gdf.to_file(geojson_path, driver="GeoJSON")
    logging.info("Done.")


if __name__ == "__main__":
    main()
