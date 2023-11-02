# BlackMarblePy

[![Python](https://img.shields.io/pypi/pyversions/blackmarblepy.svg)](https://badge.fury.io/py/blackmarblepy)
[![PyPI version](https://badge.fury.io/py/blackmarblepy.svg)](https://badge.fury.io/py/blackmarblepy)
[![docs](https://github.com/worldbank/blackmarblepy/actions/workflows/gh-pages.yml/badge.svg)](https://github.com/worldbank/blackmarblepy/actions/workflows/gh-pages.yml)

**BlackMarblePy** is a Python package for working with Black Marble data. [Black Marble](https://blackmarble.gsfc.nasa.gov) is a [NASA Earth Observatory](https://earthobservatory.nasa.gov) project that provides global nighttime lights data. The package automates the process of downloading all relevant tiles from the [NASA LAADS archive](https://ladsweb.modaps.eosdis.nasa.gov/archive/allData/5000/VNP46A3/) to cover a region of interest, converting the raw files (in H5 format) to georeferenced rasters, and mosaicing rasters together when needed.

## Features

- Download Black Marble data for specific time periods and regions.
- Visualize nighttime lights using customizable color palettes.
- Calculate basic statistics from Black Marble images.
- Perform time-series analysis on nighttime lights data.

## Installation

You can install BlackMarblePy using pip:

```shell
pip install blackmarblepy
```

## Usage

Before downloading and extracting Black Marble data, we first load libraries, define the NASA bearer token, and define a region of interest.

```python
## Libraries
from blackmarble.bm_raster import bm_raster
from blackmarble.bm_extract import bm_extract

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from gadm import GADMDownloader
import seaborn as sns

## Bear token
bearer == "BEARER TOKEN HERE"

## Get Region of Interest - Ghana
downloader = GADMDownloader(version="4.0")

country_name = "Ghana"
ghana_adm1 = downloader.get_shape_data_by_country_name(country_name=country_name,
                                                       ad_level=1)
```

### Raster of Nighttime Lights <a name="quickstart-raster"></a>

The below example shows making an annual raster of nighttime lights for Ghana.

```python
## Raster of nighttime lights
r = bm_raster(roi_sf = ghana_adm1,
              product_id = "VNP46A4",
              date = 2022,
              bearer = bearer)

## Map raster
r_np = r.read(1)
r_np = np.log(r_np+1)

plt.imshow(r_np, cmap='hot')
plt.tight_layout()
plt.axis("off")
```

For more detailed documentation and examples, please refer to the [documentation](https://worldbank.github.io/blackmarblepy/quickstart.html).

## Contributing

Contributions are welcome! If you'd like to contribute, please follow our [contribution guidelines](CONTRIBUTING.md).

## License

This project is open-source - see the [LICENSE](LICENSE) file for details
