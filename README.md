# BlackMarblePy

[![PyPI version](https://badge.fury.io/py/blackmarblepy.svg)](https://badge.fury.io/py/blackmarblepy)
[![docs](https://github.com/worldbank/blackmarblepy/actions/workflows/gh-pages.yml/badge.svg)](https://github.com/worldbank/blackmarblepy/actions/workflows/gh-pages.yml)
[![GitHub Repo stars](https://img.shields.io/github/stars/worldbank/blackmarblepy)](https://github.com/worldbank/blackmarblepy)
[![activity](https://img.shields.io/github/commit-activity/m/worldbank/blackmarblepy)](https://github.com/worldbank/blackmarblepy/graphs/commit-activity)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**BlackMarblePy** provides a simple and efficient way to retrieve and extract nighttime lights data from NASA's Black Marble project. [Black Marble](https://blackmarble.gsfc.nasa.gov) is a [NASA Earth Observatory](https://earthobservatory.nasa.gov) project that provides a product suite of daily, monthly and yearly global nighttime lights. This package automates the process of downloading all relevant tiles from the [NASA LAADS archive](https://ladsweb.modaps.eosdis.nasa.gov/archive/allData/5000/VNP46A3/) to cover a region of interest, converting the raw files (in HDF5 format), to georeferenced rasters, and mosaicing rasters together when needed.

## Features

- Download daily, monthly, and yearly nighttime lights data  for user-specified region of interest and time range.
- Parallel downloading for faster data retrieval and automatic retry mechanism for handling network errors.
- Access NASA Black Marble as a Xarray Dataset
  - Integrated data visualization with customization options
    - Choose between various plot types, including bar charts, line graphs, and heatmaps.
    - Customize plot appearance with color palettes, axes labels, titles, and legends.
    - Save visualizations as high-resolution images for presentations or reports.
  - Perform time series analysis on nighttime lights data.
    - Calculate zonal statistics like mean and sum.
    - Plot time series of nighttime lights data.

## Installation

**BlackMarblePy** is available on [PyPI](https://pypi.org) as [blackmarblepy](https://pypi.org/project/blackmarblepy) and can installed using `pip`:

```shell
pip install blackmarblepy
```

## Usage

Before downloading and extracting Black Marble data, define the [NASA LAADS archive](https://ladsweb.modaps.eosdis.nasa.gov/archive/allData/5000/VNP46A3/) `bearer` token, and define a region of interest (i.e., `gdf` as a [`geopandas.GeoDataFrame`](https://geopandas.org/en/stable/docs/reference/api/geopandas.GeoDataFrame.html)).

```python
from blackmarble.raster import bm_raster

# Raster stack of daily data
date_range = pd.date_range("2022-01-01", "2022-03-31", freq="D")

# Retrieve VNP46A2 for date range into a Xarray Dataset
daily = bm_raster(
    gdf,
    product_id="VNP46A2",
    date_range=date_range,
    bearer=bearer,
)
```

For more detailed information and examples, please refer to the [documentation](https://worldbank.github.io/blackmarblepy/examples/blackmarblepy.html).

## Contributing

Contributions are welcome! If you'd like to contribute, please follow our [contribution guidelines](CONTRIBUTING.md).

## License

This project is open-source - see the [LICENSE](LICENSE) file for details
