# blackmarblepy 

[![codecov](https://codecov.io/gh/ramarty/blackmarblepy/branch/main/graph/badge.svg?token=blackmarblepy_token_here)](https://codecov.io/gh/ramarty/blackmarblepy)
[![CI](https://github.com/ramarty/blackmarblepy/actions/workflows/main.yml/badge.svg)](https://github.com/ramarty/blackmarblepy/actions/workflows/main.yml)

Create Georeferenced Rasters of Nighttime Lights from [NASA Black Marble data](https://blackmarble.gsfc.nasa.gov/). 

* [Overview](#overview)
* [Installation](#installation)
* [Bearer token](#token)
* [Functions](#function)
* [Quick start](#quickstart)

## Overview <a name="overview"></a>

This package facilitates downloading nighttime lights [Black Marble](https://blackmarble.gsfc.nasa.gov/) data. Black Marble data is downloaded from the [NASA LAADS Archive](https://ladsweb.modaps.eosdis.nasa.gov/archive/allData/5000/VNP46A3/).  The package automates the process of downloading all relevant tiles from the NASA LAADS archive to cover a region of interest, converting the raw files (in H5 format) to georeferenced rasters, and mosaicing rasters together when needed.

## Installation <a name="installation">

The package can be installed via pip.

```bash
$ pip install git+https://github.com/ramarty/blackmarblepy.git
```

```py
from blackmarblepy.bm_raster import bm_raster
from blackmarblepy.bm_extract import bm_extract
```

## Bearer Token <a name="token">

The function requires using a **Bearer Token**; to obtain a token, follow the below steps:

1. Go to the [NASA LAADS Archive](https://ladsweb.modaps.eosdis.nasa.gov/archive/allData/5000/VNP46A3/)
2. Click "Login" (bottom on top right); create an account if needed.
3. Click "See wget Download Command" (bottom near top, in the middle)
4. After clicking, you will see text that can be used to download data. The "Bearer" token will be a long string in red.

## Functions <a name="function">

The package provides two functions. `bm_raster` produces a raster of Black Marble nighttime lights. `bm_extract` produces a dataframe of aggregated nighttime lights to a region of interest (e.g., average nighttime lights within US States). Both functions take the following arguments:
 
* __roi_sf:__ Region of interest; sf polygon. Must be in the [WGS 84 (epsg:4326)](https://epsg.io/4326) coordinate reference system. For `bm_extract`, aggregates nighttime lights within each polygon of `roi_sf`.

* __product_id:__ One of the following: 

  - `"VNP46A1"`: Daily (raw)
  - `"VNP46A2"`: Daily (corrected)
  - `"VNP46A3"`: Monthly
  - `"VNP46A4"`: Annual
  
* __date:__  Date of raster data. Entering one date will produce a raster. Entering multiple dates will produce a raster stack. 

  - For `product_id`s `"VNP46A1"` and `"VNP46A2"`, a date (eg, `"2021-10-03"`). 
  - For `product_id` `"VNP46A3"`, a date or year-month (e.g., `"2021-10-01"`, where the day will be ignored, or `"2021-10"`).
  - For `product_id` `"VNP46A4"`, year or date  (e.g., `"2021-10-01"`, where the month and day will be ignored, or `2021`). 
  - bearer NASA bearer token. For instructions on how to create a token, see [here](https://github.com/ramarty/blackmarbler#bearer-token-).

* __variable:__ Variable to used to create raster (default: `NULL`). For information on all variable choices, see [here](https://ladsweb.modaps.eosdis.nasa.gov/api/v2/content/archives/Document%20Archive/Science%20Data%20Product%20Documentation/VIIRS_Black_Marble_UG_v1.2_April_2021.pdf); for `VNP46A1`, see Table 3; for `VNP46A2` see Table 6; for `VNP46A3` and `VNP46A4`, see Table 9. If `NULL`, uses the following default variables: 

  - For `product_id` `:VNP46A1"`, uses `DNB_At_Sensor_Radiance_500m`. 
  - For `product_id` `"VNP46A2"`, uses `Gap_Filled_DNB_BRDF-Corrected_NTL`. 
  - For `product_id`s `"VNP46A3"` and `"VNP46A4"`, uses `NearNadir_Composite_Snow_Free`. 

* __output_location_type:__ Where output should be stored (default: `r_memory`). Either:

  - `r_memory` where the function will return an output in R
  - `file` where the function will export the data as a file. For `bm_raster`, a `.tif` file will be saved; for `bm_extract`, a `.Rds` file will be saved. A file is saved for each date. Consequently, if `date = c(2018, 2019, 2020)`, three datasets will be saved: one for each year. Saving a dataset for each date can facilitate re-running the function later and only downloading data for dates where data have not been downloaded.

If `output_location_type = "file"`, the following arguments can be used:

* __file_dir:__ The directory where data should be exported (default: `NULL`, so the working directory will be used)
* __file_prefix:__ Prefix to add to the file to be saved. The file will be saved as the following: `[file_prefix][product_id]_t[date].[tif/Rds]`
* __file_skip_if_exists:__ Whether the function should first check wither the file already exists, and to skip downloading or extracting data if the data for that date if the file already exists (default: `TRUE`). If the function is first run with `date = c(2018, 2019, 2020)`, then is later run with `date = c(2018, 2019, 2020, 2021)`, the function will only download/extract data for 2021. Skipping existing files can facilitate re-running the function at a later date to download only more recent data. 

For `bm_extract` only:

* __aggregation_fun:__ A vector of functions to aggregate data (default: `"mean"`). The `zonal_stats` function from the `rasterstats` package is used for aggregations; this parameter is passed to `stats` argument in `zonal_stats`.

## Quickstart <a name="quickstart">

To see examples of using the package, see [here](https://github.com/ramarty/blackmarblepy/blob/main/examples/blackmarbley_example.ipynb).
