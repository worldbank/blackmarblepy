import datetime
import re
import tempfile
from pathlib import Path
from typing import List, Optional

import geopandas
import h5py
import numpy as np
import pandas as pd
import rasterio
import rioxarray
import xarray as xr
from pydantic import ConfigDict, validate_call
from rasterio.transform import from_origin
from rioxarray.merge import merge_arrays
from shapely.geometry import mapping
from tqdm.auto import tqdm

from .download import BlackMarbleDownloader
from .types import ProductId


def h5_to_geotiff(
    f: Path,
    /,
    output_directory: Path = None,
    output_prefix: str = None,
    variable: str = None,
    quality_flag_rm=[255],
):
    """
    Convert HDF5 file to GeoTIFF for a selected (or default) variable from NASA Black Marble data

    Parameters
    ----------


    Returns
    ------
    output_path: Path
        Path to which GeoTIFF
    """
    variable_default = {
        ProductId.VNP46A1: "DNB_At_Sensor_Radiance_500m",
        ProductId.VNP46A2: "Gap_Filled_DNB_BRDF-Corrected_NTL",
        ProductId.VNP46A3: "NearNadir_Composite_Snow_Free",
        ProductId.VNP46A4: "NearNadir_Composite_Snow_Free",
    }
    output_path = Path(output_directory, f.stem).with_suffix(".tif")
    product_id = ProductId(f.stem.split(".")[0])
    variable = variable_default.get(product_id)

    with h5py.File(f, "r") as h5_data:
        attrs = h5_data.attrs

        if product_id in [ProductId.VNP46A1, ProductId.VNP46A2]:
            dataset = h5_data["HDFEOS"]["GRIDS"]["VNP_Grid_DNB"]["Data Fields"][
                variable
            ]
            qf = h5_data["HDFEOS"]["GRIDS"]["VNP_Grid_DNB"]["Data Fields"][
                "Mandatory_Quality_Flag"
            ]
            left, bottom, right, top = (
                attrs.get("WestBoundingCoord"),
                attrs.get("SouthBoundingCoord"),
                attrs.get("EastBoundingCoord"),
                attrs.get("NorthBoundingCoord"),
            )
        else:
            dataset = h5_data["HDFEOS"]["GRIDS"]["VIIRS_Grid_DNB_2d"]["Data Fields"][
                variable
            ]
            h5_names = list(
                h5_data["HDFEOS"]["GRIDS"]["VIIRS_Grid_DNB_2d"]["Data Fields"].keys()
            )
            lat = h5_data["HDFEOS"]["GRIDS"]["VIIRS_Grid_DNB_2d"]["Data Fields"]["lat"]
            lon = h5_data["HDFEOS"]["GRIDS"]["VIIRS_Grid_DNB_2d"]["Data Fields"]["lon"]
            left, bottom, right, top = min(lon), min(lat), max(lon), max(lat)

            if len(quality_flag_rm) > 0:
                variable_short = variable
                variable_short = re.sub("_Num", "", variable_short)
                variable_short = re.sub("_Std", "", variable_short)

                qf_name = variable_short + "_Quality"

                if qf_name in h5_names:
                    qf = h5_data["HDFEOS"]["GRIDS"]["VIIRS_Grid_DNB_2d"]["Data Fields"][
                        variable + "_Quality"
                    ]

        # Extract data and attributes
        data = dataset[:]
        qf = qf[:]

        for val in quality_flag_rm:
            data = np.where(qf == val, np.nan, data)

        # Get geospatial metadata (coordinates and attributes)
        height, width = data.shape
        transform = from_origin(
            left,
            top,
            (right - left) / width,
            (top - bottom) / height,
        )

        with rasterio.open(
            output_path,
            "w",
            driver="GTiff",
            height=height,
            width=width,
            count=1,
            dtype=data.dtype,
            crs="EPSG:4326",
            transform=transform,
        ) as dst:
            dst.write(data, 1)
            dst.update_tags(**attrs)

        return output_path


def _pivot_paths_by_date(paths: List[Path]):
    """Return dictionary of paths by date

    Returns
    -------
    dict
    """
    results = {}
    for p in paths:
        key = datetime.datetime.strptime(p.stem.split(".")[1], "A%Y%j").date()
        if key not in results:
            results[key] = []
        results[key].append(p)

    return results


@validate_call(config=ConfigDict(arbitrary_types_allowed=True))
def bm_raster(
    gdf: geopandas.GeoDataFrame,
    /,
    product_id: ProductId,
    date_range: datetime.date | List[datetime.date],
    bearer: str,
    variable: Optional[str] = None,
    quality_flag_rm: List[int] = [255],
    check_all_tiles_exist: bool = True,
    file_directory: Optional[Path] = None,
    file_prefix: Optional[str] = None,
    file_skip_if_exists: bool = True,
):
    """Create a stack of nighttime lights rasters by retrieiving from `NASA Black Marble <https://blackmarble.gsfc.nasa.gov>`_ data.

    Parameters
    ----------
    roi: geopandas.GeoDataFrame
        Region of interest

    product_id: Product
        NASA Black Marble product suite (VNP46) identifier. The available products are shown in following list:

        - ``VNP46A1``: Daily (raw)
        - ``VNP46A2``: Daily (corrected)
        - ``VNP46A3``: Monthly
        - ``VNP46A4``: Annual

    date_range: datetime.date | List[datetime.date]
        Date range (single date or list of dates) for which to retrieve NASA Black Marble data.

    bearer: str
        NASA Earthdata Bearer token. Please refer to the `documentation <https://worldbank.github.io/blackmarblepy/examples/blackmarblepy.html#nasa-earthdata-bearer-token>`_.

    variable: str, default = None
        Variable to create GeoTIFF raster. Further information, pleae see the `NASA Black Marble User Guide <https://ladsweb.modaps.eosdis.nasa.gov/api/v2/content/archives/Document%20Archive/Science%20Data%20Product%20Documentation/VIIRS_Black_Marble_UG_v1.2_April_2021.pdf>`_ for `VNP46A1`, see Table 3; for `VNP46A2` see Table 6; for `VNP46A3` and `VNP46A4`, see Table 9. By default, it uses the following default variables:

        - For ``VNP46A1``, uses ``DNB_At_Sensor_Radiance_500m``
        - For ``VNP46A2``, uses ``Gap_Filled_DNB_BRDF-Corrected_NTL``
        - For ``VNP46A3``, uses ``NearNadir_Composite_Snow_Free``.
        - For ``VNP46A4``, uses ``NearNadir_Composite_Snow_Free``.

    quality_flag: List[int], default = [255]
        Quality flag values to use to set values to ``NA``. Each pixel has a quality flag value, where low quality values can be removed. Values are set to ``NA`` for each value in ther ``quality_flag_rm`` vector.

        For ``VNP46A1`` and ``VNP46A2`` (daily data):

        - ``0``: High-quality, Persistent nighttime lights
        - ``1``: High-quality, Ephemeral nighttime Lights
        - ``2``: Poor-quality, Outlier, potential cloud contamination, or other issues
        - ``255``: No retrieval, Fill value (masked out on ingestion)

        For ``VNP46A3`` and ``VNP46A4`` (monthly and annual data):

        - ``0``: Good-quality, The number of observations used for the composite is larger than 3
        - ``1``: Poor-quality, The number of observations used for the composite is less than or equal to 3
        - ``2``: Gap filled NTL based on historical data
        - ``255``: Fill value

    check_all_tiles_exist: bool, default=True
        Check whether all Black Marble nighttime light tiles exist for the region of interest. Sometimes not all tiles are available, so the full region of interest may not be covered. By default (True), it skips cases where not all tiles are available.

    file_directory: pathlib.Path, optional
        Where to produce output. By default, the output will be procuded onto a temporary directory.

    file_directory_prefix: str, optional
        Prefix

    file_skip_if_exists: bool, default=True
        Whether to skip downloading or extracting data if the data file for that date already exists.

    Returns
    -------
    xarray.Dataset
        A Xarray dataset contaning a stack of nighttime lights rasters
    """
    # Validate and fix args
    if not isinstance(quality_flag_rm, list):
        quality_flag_rm = [quality_flag_rm]
    if not isinstance(date_range, list):
        date_range = [date_range]

    match product_id:
        case ProductId.VNP46A3:
            date_range = sorted(set([d.replace(day=1) for d in date_range]))
        case ProductId.VNP46A4:
            date_range = sorted(set([d.replace(day=1, month=1) for d in date_range]))

    # Download and construct Dataset
    with file_directory if file_directory else tempfile.TemporaryDirectory() as d:
        downloader = BlackMarbleDownloader(bearer, d)
        pathnames = downloader.download(gdf, product_id, date_range)

        dx = []
        for date in tqdm(date_range, desc="COLLATING RESULTS | Processing..."):
            # _pivot_paths_by_date(pathnames), desc="COLLATING RESULTS | Processing..."
            filenames = _pivot_paths_by_date(pathnames).get(date)

            # Open each GeoTIFF file as a DataArray and store in a list
            da = [rioxarray.open_rasterio(h5_to_geotiff(f, d)) for f in filenames]
            ds = merge_arrays(da)
            ds = ds.rio.clip(gdf.geometry.apply(mapping), gdf.crs, drop=True)
            ds["time"] = pd.to_datetime(date)

            dx.append(ds.squeeze())

        # Stack the individual dates along "time" dimension
        ds = (
            xr.concat(dx, dim="time", combine_attrs="drop_conflicts")
            .to_dataset(name="radiance", promote_attrs=True)
            .sortby("time")
            .drop(["band", "spatial_ref"])
            .assign_attrs(
                units="Watts per square meter per steradian (W/m²/sr)",
                description="Radiance",
            )
        )
        ds.radiance.attrs["units"] = "W/m²/sr"

        return ds
