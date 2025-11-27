

<div align="center">
  <img src="./images/sosilogikk.jpg" alt="Project Logo" width="400"/>
</div>

---

sosilogikk is a small utility to read Norwegian SOSI vector files (FKB 5.x) into GeoPandas, and write them back out. It handles the SOSI header, encoding, ENHET scaling, KOORDSYS→EPSG mapping, and assembles geometries (points, curves, polygons).

## Install

```bash
pip install sosilogikk
```

## Minimal example: SOSI → GeoJSON

```python
from sosilogikk import read_sosi

# Path to a single .sos file
sosi_path = "sample/roads.sos"

# Parse to GeoDataFrame (includes CRS when KOORDSYS is present)
gdf, metadata = read_sosi(sosi_path, return_metadata=True)

# Write to GeoJSON
gdf.to_file("sample/roads.geojson", driver="GeoJSON")
```

You’ll get a CRS-aware GeoDataFrame: KOORDSYS 22/23/25 map to EPSG 25832/25833/25835, ENHET scales coordinates, and mixed 2D/3D geometries are flattened to 2D.
