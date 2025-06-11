# BlackMarblePy

[![Project Status: Active – The project has reached a stable, usable state and is being actively developed.](https://www.repostatus.org/badges/latest/active.svg)](https://www.repostatus.org/#active)
[![PyPI version](https://badge.fury.io/py/blackmarblepy.svg)](https://badge.fury.io/py/blackmarblepy)
[![License: MPL 2.0](https://img.shields.io/badge/License-MPL_2.0-brightgreen.svg)](https://opensource.org/licenses/MPL-2.0)
![Python Version](https://img.shields.io/pypi/pyversions/blackmarblepy)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.10667907.svg)](https://zenodo.org/doi/10.5281/zenodo.10667907)
[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/worldbank/blackmarblepy/blob/main/notebooks/blackmarblepy.ipynb)
[![Downloads](https://static.pepy.tech/badge/blackmarblepy)](https://pepy.tech/project/blackmarblepy)
[![GitHub Repo stars](https://img.shields.io/github/stars/worldbank/blackmarblepy)](https://github.com/worldbank/blackmarblepy)

**BlackMarblePy** is a Python package that provides a simple way to use nighttime lights data from NASA's Black Marble project. [Black Marble](https://blackmarble.gsfc.nasa.gov) is a [NASA Earth Science Data Systems (ESDS)](https://www.earthdata.nasa.gov) project that provides a product suite of daily, monthly and yearly global [nighttime lights](https://www.earthdata.nasa.gov/learn/backgrounders/nighttime-lights). This package automates the process of downloading all relevant tiles from the [NASA LAADS DAAC](https://www.earthdata.nasa.gov/eosdis/daacs/laads) to cover a region of interest, converting the raw files (in HDF5 format) to georeferenced rasters, and mosaicking rasters together when needed.

## Features

- Download *daily*, *monthly*, and *yearly* nighttime lights data for user-specified **region of interest** and **time**.
- Parallel downloading for faster data retrieval and automatic retry mechanism for handling network errors.
- Access [NASA Black Marble](https://blackmarble.gsfc.nasa.gov) as a [xarray.Dataset](https://docs.xarray.dev/en/stable/generated/xarray.Dataset.html)
  - Integrated data visualization with customization options
    - Choose between various plot types, including bar charts, line graphs, and heatmaps.
    - Customize plot appearance with color palettes, axes labels, titles, and legends.
    - Save visualizations as high-resolution images for presentations or reports.
  - Perform time series analysis on nighttime lights data.
    - Calculate zonal statistics like mean and sum.
    - Plot time series of nighttime lights data.

## Documentation

[![docs](https://github.com/worldbank/blackmarblepy/actions/workflows/gh-pages.yml/badge.svg)](https://github.com/worldbank/blackmarblepy/actions/workflows/gh-pages.yml)
[![tests](https://github.com/worldbank/blackmarblepy/actions/workflows/tests.yml/badge.svg)](https://github.com/worldbank/blackmarblepy/actions/workflows/tests.yml)
[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/worldbank/blackmarblepy/main.svg)](https://results.pre-commit.ci/latest/github/worldbank/blackmarblepy/main)

The [**BlackMarblePy**](https://pypi.org/project/blackmarblepy) library allows you to interact with and manipulate data from NASA's Black Marble, which provides global nighttime lights data. Below is a guide on how to use the key functionalities of the library.

### Installation

[![Project Status: Active – The project has reached a stable, usable state and is being actively developed.](https://www.repostatus.org/badges/latest/active.svg)](https://www.repostatus.org/#active)
[![PyPI version](https://badge.fury.io/py/blackmarblepy.svg)](https://badge.fury.io/py/blackmarblepy)
![Python Version](https://img.shields.io/pypi/pyversions/blackmarblepy)
[![License: MPL 2.0](https://img.shields.io/badge/License-MPL_2.0-brightgreen.svg)](https://opensource.org/licenses/MPL-2.0)

**BlackMarblePy** is available on [PyPI](https://pypi.org) as [blackmarblepy](https://pypi.org/project/blackmarblepy). To install, it is recommended to use a modern Python package manager. While [pip](https://packaging.python.org/en/latest/key_projects/#pip) is the traditional choice, you can also use [uv](https://docs.astral.sh/uv/), which is a fast drop-in replacement for [pip](https://packaging.python.org/en/latest/key_projects/#pip) that offers improved performance and compatibility with modern workflows.

#### Using pip

```shell
pip install blackmarblepy
```

#### Using uv (modern, faster alternative)

```shell
uv install blackmarblepy
```

### Usage

**BlackMarblePy** requires a NASA Earthdata bearer token for authenticated access to the NASA LAADS archive. To obtain a token, log in or register at Earthdata Login and generate a personal access token from your [Earthdata profile](https://urs.earthdata.nasa.gov/profile).

Before downloading or extracting [NASA Black Marble data](https://blackmarble.gsfc.nasa.gov), ensure the following:

- You have a valid and not expired `bearer` token set (retrieved from your [Earthdata profile](https://urs.earthdata.nasa.gov/profile)). For convenience and security, we [recommend setting your token as an `BLACKMARBLE_TOKEN` environment variable](https://duckduckgo.com/?q=how+to+set+environment+variable+linux+or+mac+or+windows).
- You have defined a region of interest `gdf` as a [`geopandas.GeoDataFrame`](https://geopandas.org/en/stable/docs/reference/api/geopandas.GeoDataFrame.html), which represents the area over which data will be queried and downloaded.

```python
# Option 1: Class-based interface
from blackmarble import BlackMarble, Product

# Create a BlackMarble instance. If no bearer token is passed explicitly,
# it will attempt to read from the BLACKMARBLE_TOKEN environment variable.
bm = BlackMarble()  # or: BlackMarble(bearer="YOUR_BLACKMARBLE_TOKEN")

# Define your region of interest as a GeoDataFrame (gdf)
# For example: gdf = gpd.read_file("path_to_shapefile.geojson")

# Retrieve VNP46A2 for date range into a Xarray Dataset
daily = bm.raster(
    gdf,
    product_id=Product.VNP46A2,
    date_range=pd.date_range("2022-01-01", "2022-03-31", freq="D"),
)
```

Alternatively, use the [bm_raster](https://worldbank.github.io/blackmarblepy/api/blackmarble.html#blackmarble.raster.bm_raster) procedural interface to retrieve daily NASA Black Marble data (*VNP46A2*) as an [`xarray.Dataset`](https://docs.xarray.dev/en/stable/generated/xarray.Dataset.html):

```python
# Option 2: Backward-compatible procedural interface
from blackmarble import bm_raster, Product

# Define your region of interest as a GeoDataFrame (gdf)
# For example: gdf = gpd.read_file("path_to_shapefile.geojson")

# Retrieve VNP46A2 for date range into a Xarray Dataset
daily = bm_raster(
    gdf,
    product_id=Product.VNP46A2,
    date_range=pd.date_range("2022-01-01", "2022-03-31", freq="D"),
    bearer=bearer, # optional: can be omitted if BLACKMARBLE_TOKEN is set in the environment
)
```

Data is sourced from the [NASA LAADS archive](https://ladsweb.modaps.eosdis.nasa.gov/archive/allData/5000/VNP46A3/), specifically from the [**VNP46**](https://blackmarble.gsfc.nasa.gov/#product) product suite (e.g., *VNP46A1*, *VNP46A4*). For more detailed information and examples, please refer to the [examples](https://worldbank.github.io/blackmarblepy/notebooks/blackmarblepy.html).

### Full API Reference

For a full reference of all available functions and their parameters, please refer to the [official documentation](api/blackmarble.rst).

## Contributing

We welcome contributions to improve this documentation. If you find errors, have suggestions, or want to add new content, please follow our [contribution guidelines](CONTRIBUTING.md).

### Feedback and Issues

If you have any feedback, encounter issues, or want to suggest improvements, please [open an issue](https://github.com/worldbank/blackmarblepy/issues).

### Versioning

This project follows the **YYYY.0M.MICRO** [CALVER](https://calver.org) scheme for versioning. If you have any questions or need more information about our versioning approach, feel free to ask.

### Contributors

This project follows the [all-contributors](https://allcontributors.org) specification.
Contributions of any kind are welcome!

<a href="https://orcid.org/0000-0001-6530-3780">
Gabriel Stefanini Vicente
<img alt="ORCID logo" src="https://info.orcid.org/wp-content/uploads/2019/11/orcid_16x16.png" width="16" height="16" />
</a>
<br>
<a href="https://orcid.org/0000-0002-3164-3813">
Robert Marty
<img alt="ORCID logo" src="https://info.orcid.org/wp-content/uploads/2019/11/orcid_16x16.png" width="16" height="16" />
</a>

<!-- ALL-CONTRIBUTORS-LIST:START - Do not remove or modify this section -->
<!-- prettier-ignore-start -->
<!-- markdownlint-disable -->

<!-- markdownlint-restore -->
<!-- prettier-ignore-end -->

<!-- ALL-CONTRIBUTORS-LIST:END -->

## Citation

When using **BlackMarblePy**, your support is much appreciated! Please consider using the following citation or download [bibliography.bib](https://raw.githubusercontent.com/worldbank/blackmarblepy/main/docs/bibliography.bib):

```bibtex
@misc{blackmarblepy,
  title = {{BlackMarblePy: Georeferenced Rasters and Statistics of Nighttime Lights from NASA Black Marble}},
  author = {Gabriel {Stefanini Vicente} and Robert Marty},
  year = {2023},
  howpublished = {\url{https://worldbank.github.io/blackmarblepy}},
  doi = {10.5281/zenodo.10667907},
  url = {https://worldbank.github.io/blackmarblepy},
}
```

{cite:empty}`blackmarblepy`

```{bibliography}
:filter: docname in docnames
:style: plain
```

## Related Projects

Looking for an R implementation? Check out the [blackmarbler](https://github.com/worldbank/blackmarbler) package, which provides similar functionality for working with NASA Black Marble data in R.

## License

This projects is licensed under the [**Mozilla Public License**](https://opensource.org/license/mpl-2-0/) - see the **LICENSE** file for details.
