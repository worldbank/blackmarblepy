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

**BlackMarblePy** is available on [PyPI](https://pypi.org); you can install it using `pip`:

```shell
pip install blackmarblepy
```

## Usage

Before downloading and extracting Black Marble data, define the NASA bearer token, and define a region of interest. For more detailed documentation and examples, please refer to the [documentation](https://worldbank.github.io/blackmarblepy).

## Contributing

Contributions are welcome! If you'd like to contribute, please follow our [contribution guidelines](CONTRIBUTING.md).

## License

This project is open-source - see the [LICENSE](LICENSE) file for details
