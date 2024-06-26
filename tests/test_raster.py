import pytest
from pydantic import ValidationError

from blackmarble.raster import bm_raster


def test_raster_validate_call():
    with pytest.raises(ValidationError):
        bm_raster()


def test_raster_validate_gdf():
    with pytest.raises(ValidationError):
        bm_raster(roi="geodataframe")  # wrong type
