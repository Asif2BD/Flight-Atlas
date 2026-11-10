# World land map

`world-land.geojson` contains Natural Earth 1:110 million land polygons, in longitude/latitude (WGS84). Natural Earth data is in the public domain. The renderer uses real geographic geometry, not a decorative world silhouette.

Source: https://www.naturalearthdata.com/downloads/110m-physical-vectors/110m-land/
License: https://www.naturalearthdata.com/about/terms-of-use/

Map boundaries and coastline simplification are for visualization, not navigation. Routes are approximate shortest great-circle arcs, not recorded flight tracks. Projection: equirectangular. Routes are split at the antimeridian.

# Country borders and names

`world-countries.geojson` holds Natural Earth 1:110 million admin-0 country polygons (v5.1.2), reduced to an ISO 3166 alpha-2 code, an English name and coordinates rounded to 0.01°. `countries.csv` maps ISO alpha-2 codes to English names, taken from Natural Earth 1:50 million admin-0 countries (v5.1.2) with a few territories added by hand. Natural Earth data is in the public domain.

Source: https://www.naturalearthdata.com/downloads/110m-cultural-vectors/110m-admin-0-countries/ and https://www.naturalearthdata.com/downloads/50m-cultural-vectors/50m-admin-0-countries/

Borders are Natural Earth's de facto boundaries and carry no political position. Countries too small for the 1:110m layer (for example Monaco, Andorra, Liechtenstein) are shown by their pins.
