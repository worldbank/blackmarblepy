import importlib.metadata
import logging
import sys
from importlib.resources import files

import geopandas as gpd

__all__ = ["BlackMarble", "bm_extract", "bm_raster", "Product"]

try:
    __version__ = importlib.metadata.version("blackmarblepy")
except importlib.metadata.PackageNotFoundError:
    __version__ = "dev"

LOG_FORMAT = "[%(asctime)s] [%(levelname)s] [%(module)s]: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

logger = logging.getLogger("blackmarblepy")
logger.setLevel(logging.WARN)

if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    logger.addHandler(handler)

TILES: gpd.GeoDataFrame = gpd.read_file(
    files("blackmarble.data").joinpath("blackmarbletiles.geojson")
)

from .core import BlackMarble  # noqa: E402
from .extract import bm_extract  # noqa: E402
from .raster import bm_raster  # noqa: E402
from .types import Product  # noqa: E402
