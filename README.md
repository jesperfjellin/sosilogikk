

<div align="center">
  <img src="./images/sosilogikk.jpg" alt="Project Logo" width="400"/>
</div>

<div align="center">


  
</div>

---

Logikk for å bruke Python biblioteker som Geopandas, Shapely, Fiona etc på .SOS-filer. sosilogikk.py i mappen module definerer en logikk for å bryte opp en .SOS-fil i objektsegmenter som kan lastes inn i en Geopandas dataframe. 

28/05/2025: sosilogikk er ikke under aktiv utvikling, men hvis det er nødvendige bugfixes/manglende funksjonalitet, lag gjerne en pull request/fork repoet. 

# Installering
Pakken installeres gjennom programvarelageret PyPi:

```bash
pip install sosilogikk
```

Alt som trengs for å laste SOSI-data inn i en GeoDataFrame er fire linjer med kode:
<div align="center">
  <img src="./images/Eksempel.png" alt="Example"/>
</div>
Resultatet er en GeoDataFrame som er kompatibel med det meste av Python GIS-pakker (GDAL, Shapely, Fiona, osv):<br><br>

<div align="center">
  <img src="./images/gdf.png" alt="GDF"/>
</div>
