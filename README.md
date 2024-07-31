# BlackMarblePy

[![License: MPL 2.0](https://img.shields.io/badge/License-MPL_2.0-brightgreen.svg)](https://opensource.org/licenses/MPL-2.0)
[![PyPI version](https://badge.fury.io/py/blackmarblepy.svg)](https://badge.fury.io/py/blackmarblepy)
[![docs](https://github.com/worldbank/blackmarblepy/actions/workflows/gh-pages.yml/badge.svg)](https://github.com/worldbank/blackmarblepy/actions/workflows/gh-pages.yml)
[![tests](https://github.com/worldbank/blackmarblepy/actions/workflows/tests.yml/badge.svg)](https://github.com/worldbank/blackmarblepy/actions/workflows/tests.yml)
[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/worldbank/blackmarblepy/main.svg)](https://results.pre-commit.ci/latest/github/worldbank/blackmarblepy/main)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.10667907.svg)](https://zenodo.org/doi/10.5281/zenodo.10667907)
[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/worldbank/blackmarblepy/blob/main/notebooks/blackmarblepy.ipynb)
[![Downloads](https://static.pepy.tech/badge/blackmarblepy)](https://pepy.tech/project/blackmarblepy)
[![GitHub Repo stars](https://img.shields.io/github/stars/worldbank/blackmarblepy)](https://github.com/worldbank/blackmarblepy)

**BlackMarblePy** is a Python package that provides a simple way to use nighttime lights data from NASA's Black Marble project. [Black Marble](https://blackmarble.gsfc.nasa.gov) is a [NASA Earth Science Data Systems (ESDS)](https://www.earthdata.nasa.gov) project that provides a product suite of daily, monthly and yearly global [nighttime lights](https://www.earthdata.nasa.gov/learn/backgrounders/nighttime-lights). This package automates the process of downloading all relevant tiles from the [NASA LAADS DAAC](https://www.earthdata.nasa.gov/eosdis/daacs/laads) to cover a region of interest, converting the raw files (in HDF5 format), to georeferenced rasters, and mosaicking rasters together when needed.

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

The [**BlackMarblePy**](https://pypi.org/project/blackmarblepy) library allows you to interact with and manipulate data from NASA's Black Marble, which provides global nighttime lights data. Below is a guide on how to use the key functionalities of the library.

### Installation

**BlackMarblePy** is available on [PyPI](https://pypi.org) as [blackmarblepy](https://pypi.org/project/blackmarblepy) and can installed using `pip`:

#### From PyPI

```shell
pip install blackmarblepy
```

#### From Source

1. Clone or download this repository to your local machine. Then, navigate to the root directory of the repository:

    ```shell
    git clone https://github.com/worldbank/blackmarblepy.git
    cd blackmarblepy
    ```

2. Create a virtual environment (optional but recommended):

    ```shell
    python3 -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    ```

3. Install the package with dependencies:

    ```shell
    pip install .
    ```

    Install the package **in editable** mode with dependencies:

    ```shell
    pip install -e .
    ```

    The `-e` flag stands for "editable," meaning changes to the source code will immediately affect the installed package.

#### Building Documentation Locally

To build the documentation locally, after (1) and (2) above, please follow these steps:

- Install the package with documentation dependencies:

  ```shell
    pip install -e .[docs]
  ```

- Build the documentation:

  ```shell
    sphinx-build docs _build/html -b html
  ```

The generated documentation will be available in the `_build/html` directory. Open the `index.html` file in a web browser to view it.

### Usage

Before downloading and extracting Black Marble data, define the [NASA LAADS archive](https://ladsweb.modaps.eosdis.nasa.gov/archive/allData/5000/VNP46A3/) `bearer` token, and define a region of interest (i.e., `gdf` as a [`geopandas.GeoDataFrame`](https://geopandas.org/en/stable/docs/reference/api/geopandas.GeoDataFrame.html)).

```python
from blackmarble.raster import bm_raster

# Retrieve VNP46A2 for date range into a Xarray Dataset
daily = bm_raster(
    gdf,
    product_id="VNP46A2",
    date_range=pd.date_range("2022-01-01", "2022-03-31", freq="D"),
    bearer=bearer,
)
```

For more detailed information and examples, please refer to the [examples](https://worldbank.github.io/blackmarblepy/notebooks/blackmarblepy.html).

### Full API Reference

For a full reference of all available functions and their parameters, please refer to the [official documentation](api/blackmarble.rst).

## Contributing

We welcome contributions to improve this documentation. If you find errors, have suggestions, or want to add new content, please follow our [contribution guidelines](CONTRIBUTING.md).

### Feedback and Issues

If you have any feedback, encounter issues, or want to suggest improvements, please [open an issue](https://github.com/worldbank/blackmarblepy/issues).

### Versioning

[![CalVer](https://img.shields.io/badge/calver-YY.0M.MICRO-22bfda.svg)](https://calver.org)

This project follows the [CALVER](https://calver.org) (Calendar Versioning) scheme for versioning. If you have any questions or need more information about our versioning approach, feel free to ask.

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

## License

This projects is licensed under the [**Mozilla Public License**](https://opensource.org/license/mpl-2-0/) - see the **LICENSE** file for details.
