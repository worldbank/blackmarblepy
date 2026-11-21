import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from blackmarble import TILES, BlackMarble, Product
from blackmarble.download import BlackMarbleDownloader

DAY_1 = datetime.date(2024, 1, 1)
DAY_2 = datetime.date(2024, 1, 2)


@pytest.fixture
def roi():
    """A region inside a single Black Marble tile."""
    minx, miny, maxx, maxy = TILES.geometry.iloc[0].bounds
    x, y = (minx + maxx) / 2, (miny + maxy) / 2
    return gpd.GeoDataFrame(
        geometry=[box(x - 0.1, y - 0.1, x + 0.1, y + 0.1)], crs=TILES.crs
    )


def manifest_for(tile_id, dates):
    names = [f"VNP46A2.A{d:%Y%j}.{tile_id}.002.h5" for d in dates]
    return pd.DataFrame(
        {
            "name": names,
            "TileID": tile_id,
            "date": dates,
            "downloadsLink": names,
            "size": 1,
        }
    )


def download(roi, check_all_tiles_exist):
    """Downloads DAY_1 and DAY_2 when the manifest only lists DAY_1."""
    tile_id = TILES.iloc[0]["TileID"]
    downloader = BlackMarbleDownloader(
        "mock-token", Path("."), check_all_tiles_exist=check_all_tiles_exist
    )
    with (
        patch.object(
            BlackMarbleDownloader,
            "get_manifest",
            AsyncMock(return_value=manifest_for(tile_id, [DAY_1])),
        ),
        patch(
            "blackmarble.download.pqdm",
            side_effect=lambda args, *a, **kw: [name for name, _ in args],
        ),
    ):
        return downloader.download(roi, Product.VNP46A2, [DAY_1, DAY_2])


def test_missing_tile_raises_by_default(roi):
    with pytest.raises(ValueError, match="required files"):
        download(roi, check_all_tiles_exist=True)


def test_missing_tile_is_skipped_when_check_is_off(roi):
    files = download(roi, check_all_tiles_exist=False)

    assert len(files) == 1
    assert f"A{DAY_1:%Y%j}" in files[0]


def test_raster_passes_check_all_tiles_exist_to_the_downloader(roi):
    bm = BlackMarble(token="mock-token", check_all_tiles_exist=False)
    with (
        patch("blackmarble.core.BlackMarbleDownloader") as downloader,
        patch.object(BlackMarble, "collate_tiles", MagicMock()),
    ):
        bm.raster(roi, Product.VNP46A2, DAY_1)

    assert downloader.call_args.kwargs["check_all_tiles_exist"] is False


def test_date_without_files_does_not_crash_collate_tiles(roi):
    bm = BlackMarble(token="mock-token")

    with pytest.raises(ValueError, match="No data arrays"):
        bm.collate_tiles(roi, [DAY_1], pathnames=[], variable="DNB_BRDF-Corrected_NTL")
