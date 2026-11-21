import datetime
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from blackmarble import TILES, BlackMarble, Product

DAY = datetime.date(2024, 1, 1)


@pytest.fixture
def roi():
    return TILES.iloc[[0]][["geometry"]]


def raster_of(variable):
    """A one-date raster that holds only `variable`, as BlackMarble.raster returns it."""
    values = np.ones((1, 2, 2))
    coords = {"time": [pd.Timestamp(DAY)], "y": [0, 1], "x": [0, 1]}
    return xr.Dataset({variable: (("time", "y", "x"), values)}, coords=coords)


@pytest.mark.parametrize(
    "product_id, variable",
    [
        (Product.VNP46A2, "DNB_BRDF-Corrected_NTL"),
        (Product.VNP46A4, "NearNadir_Composite_Snow_Free"),
        (Product.VNP46A4, "AllAngle_Composite_Snow_Free"),
    ],
)
def test_extract_reads_the_requested_variable(roi, product_id, variable):
    bm = BlackMarble(token="mock-token")
    with (
        patch.object(BlackMarble, "raster", return_value=raster_of(variable)),
        patch(
            "blackmarble.core.exact_extract", return_value=pd.DataFrame({"sum": [4.0]})
        ) as stats,
    ):
        result = bm.extract(roi, product_id, DAY, variable=variable)

    assert stats.call_args.kwargs["rast"].name == variable
    assert result["ntl_sum"].tolist() == [4.0]
