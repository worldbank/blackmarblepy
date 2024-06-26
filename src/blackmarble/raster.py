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
from .types import Product

VARIABLE_DEFAULT = {
    Product.VNP46A1: "DNB_At_Sensor_Radiance_500m",
    Product.VNP46A2: "Gap_Filled_DNB_BRDF-Corrected_NTL",
    Product.VNP46A3: "NearNadir_Composite_Snow_Free",
    Product.VNP46A4: "NearNadir_Composite_Snow_Free",
}


def remove_fill_value(x, variable):
    """
    # Remove fill values

    # https://viirsland.gsfc.nasa.gov/PDF/BlackMarbleUserGuide_v1.2_20220916.pdf
    # * Table 3 (page 12)
    # * Table 6 (page 16)
    # * Table 9 (page 18)

    Parameters
    ----------
    x: np array of raster
    variable: Black Marble Variable

    Returns
    ------
    np array
    """

    #### 255
    if variable in [
        "Granule",
        "Mandatory_Quality_Flag",
        "Latest_High_Quality_Retrieval",
        "Snow_Flag",
        "DNB_Platform",
        "Land_Water_Mask",
        "AllAngle_Composite_Snow_Covered_Quality",
        "AllAngle_Composite_Snow_Free_Quality",
        "NearNadir_Composite_Snow_Covered_Quality",
        "NearNadir_Composite_Snow_Free_Quality",
        "OffNadir_Composite_Snow_Covered_Quality",
        "OffNadir_Composite_Snow_Free_Quality",
    ]:
        x = np.where(x == 255, np.nan, x)

    #### -999.9
    if variable == "UTC_Time":
        x = np.where(x == -999.9, np.nan, x)

    #### -32768
    if variable in [
        "Sensor_Azimuth",
        "Sensor_Zenith",
        "Solar_Azimuth",
        "Solar_Zenith",
        "Lunar_Azimuth",
        "Lunar_Zenith",
        "Glint_Angle",
        "Moon_Illumination_Fraction",
        "Moon_Phase_Angle",
    ]:
        x = np.where(x == -32768, np.nan, x)

    #### 65535
    if variable in [
        "DNB_At_Sensor_Radiance_500m",
        "BrightnessTemperature_M12",
        "BrightnessTemperature_M13",
        "BrightnessTemperature_M15",
        "BrightnessTemperature_M16",
        "QF_Cloud_Mask",
        "QF_DNB",
        "QF_VIIRS_M10",
        "QF_VIIRS_M11",
        "QF_VIIRS_M12",
        "QF_VIIRS_M13",
        "QF_VIIRS_M15",
        "QF_VIIRS_M16",
        "Radiance_M10",
        "Radiance_M11",
        "QF_Cloud_Mask",
        "DNB_BRDF-Corrected_NTL",
        "DNB_Lunar_Irradiance",
        "Gap_Filled_DNB_BRDF-Corrected_NTL",
        "AllAngle_Composite_Snow_Covered",
        "AllAngle_Composite_Snow_Covered_Num",
        "AllAngle_Composite_Snow_Free",
        "AllAngle_Composite_Snow_Free_Num",
        "NearNadir_Composite_Snow_Covered",
        "NearNadir_Composite_Snow_Covered_Num",
        "NearNadir_Composite_Snow_Free",
        "NearNadir_Composite_Snow_Free_Num",
        "OffNadir_Composite_Snow_Covered",
        "OffNadir_Composite_Snow_Covered_Num",
        "OffNadir_Composite_Snow_Free",
        "OffNadir_Composite_Snow_Free_Num",
        "AllAngle_Composite_Snow_Covered_Std",
        "AllAngle_Composite_Snow_Free_Std",
        "NearNadir_Composite_Snow_Covered_Std",
        "NearNadir_Composite_Snow_Free_Std",
        "OffNadir_Composite_Snow_Covered_Std",
        "OffNadir_Composite_Snow_Free_Std",
    ]:
        x = np.where(x == 65535, np.nan, x)

    return x


def h5_to_geotiff(
    f: Path,
    /,
    variable: str = None,
    quality_flag_rm=[],
    output_directory: Path = None,
    output_prefix: str = None,
):
    """
    Convert HDF5 file to GeoTIFF for a selected (or default) variable from NASA Black Marble data

    Parameters
    ----------
    f: Path
        H5DF filename

    variable: str, default = None
        Variable for which to create a GeoTIFF raster. Further information, please see the `NASA Black Marble User Guide <https://ladsweb.modaps.eosdis.nasa.gov/api/v2/content/archives/Document%20Archive/Science%20Data%20Product%20Documentation/VIIRS_Black_Marble_UG_v1.2_April_2021.pdf>`_ for `VNP46A1`, see Table 3; for `VNP46A2` see Table 6; for `VNP46A3` and `VNP46A4`, see Table 9. By default, it uses the following default variables:

        - For ``VNP46A1``, uses ``DNB_At_Sensor_Radiance_500m``
        - For ``VNP46A2``, uses ``Gap_Filled_DNB_BRDF-Corrected_NTL``
        - For ``VNP46A3``, uses ``NearNadir_Composite_Snow_Free``.
        - For ``VNP46A4``, uses ``NearNadir_Composite_Snow_Free``.

    Returns
    ------
    output_path: Path
        Path to which export a GeoTIFF raster
    """
    output_path = Path(output_directory, f.name).with_suffix(".tif")
    product_id = Product(f.stem.split(".")[0])

    if variable is None:
        variable = VARIABLE_DEFAULT.get(product_id)

    with h5py.File(f, "r") as h5_data:
        attrs = h5_data.attrs

        if product_id in [Product.VNP46A1, Product.VNP46A2]:
            dataset = h5_data["HDFEOS"]["GRIDS"]["VNP_Grid_DNB"]["Data Fields"][
                variable
            ]

            left, bottom, right, top = (
                attrs.get("WestBoundingCoord"),
                attrs.get("SouthBoundingCoord"),
                attrs.get("EastBoundingCoord"),
                attrs.get("NorthBoundingCoord"),
            )

            qf = h5_data["HDFEOS"]["GRIDS"]["VNP_Grid_DNB"]["Data Fields"][
                "Mandatory_Quality_Flag"
            ]
        else:
            dataset = h5_data["HDFEOS"]["GRIDS"]["VIIRS_Grid_DNB_2d"]["Data Fields"][
                variable
            ]

            lat = h5_data["HDFEOS"]["GRIDS"]["VIIRS_Grid_DNB_2d"]["Data Fields"]["lat"]
            lon = h5_data["HDFEOS"]["GRIDS"]["VIIRS_Grid_DNB_2d"]["Data Fields"]["lon"]
            left, bottom, right, top = min(lon), min(lat), max(lon), max(lat)

            if len(quality_flag_rm) > 0:
                variable_short = variable
                variable_short = re.sub("_Num", "", variable_short)
                variable_short = re.sub("_Std", "", variable_short)

                h5_names = list(
                    h5_data["HDFEOS"]["GRIDS"]["VIIRS_Grid_DNB_2d"][
                        "Data Fields"
                    ].keys()
                )
                if (qf_name := f"{variable_short}_Quality") in h5_names:
                    qf = h5_data["HDFEOS"]["GRIDS"]["VIIRS_Grid_DNB_2d"]["Data Fields"][
                        qf_name
                    ]
                # if variable in h5_names:
                #    qf = h5_data["HDFEOS"]["GRIDS"]["VIIRS_Grid_DNB_2d"]["Data Fields"][
                #        variable
                #    ]

        # Extract data and attributes
        scale_factor = dataset.attrs.get("scale_factor", 1)
        offset = dataset.attrs.get("offset", 0)

        data = dataset[:]

        data = remove_fill_value(data, variable)
        data = scale_factor * data + offset

        if len(quality_flag_rm) > 0:
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


def transform(da: xr.DataArray):
    """Return Affice transformation"""
    left, bottom, right, top = (
        da["x"].min(),
        da["y"].min(),
        da["x"].max(),
        da["y"].max(),
    )
    height, width = da.shape

    return from_origin(
        left,
        top,
        (right - left) / width,
        (top - bottom) / height,
    )


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
    product_id: Product,
    date_range: datetime.date | List[datetime.date],
    bearer: str,
    variable: Optional[str] = None,
    quality_flag_rm: List[int] = [],
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
        Variable for which to a GeoTIFF raster. Further information, please see the `NASA Black Marble User Guide <https://ladsweb.modaps.eosdis.nasa.gov/api/v2/content/archives/Document%20Archive/Science%20Data%20Product%20Documentation/VIIRS_Black_Marble_UG_v1.2_April_2021.pdf>`_ for `VNP46A1`, see Table 3; for `VNP46A2` see Table 6; for `VNP46A3` and `VNP46A4`, see Table 9. By default, it uses the following default variables:

        - For ``VNP46A1``, uses ``DNB_At_Sensor_Radiance_500m``
        - For ``VNP46A2``, uses ``Gap_Filled_DNB_BRDF-Corrected_NTL``
        - For ``VNP46A3``, uses ``NearNadir_Composite_Snow_Free``.
        - For ``VNP46A4``, uses ``NearNadir_Composite_Snow_Free``.

    quality_flag: List[int], default = []
        Quality flag values to use to set values to ``NA``. Each pixel has a quality flag value, where low quality values can be removed. Values are set to ``NA`` for each value in ther ``quality_flag_rm`` vector.

        For ``VNP46A1`` and ``VNP46A2`` (daily data):

        - ``0``: High-quality, Persistent nighttime lights
        - ``1``: High-quality, Ephemeral nighttime Lights
        - ``2``: Poor-quality, Outlier, potential cloud contamination, or other issues

        For ``VNP46A3`` and ``VNP46A4`` (monthly and annual data):

        - ``0``: Good-quality, The number of observations used for the composite is larger than 3
        - ``1``: Poor-quality, The number of observations used for the composite is less than or equal to 3
        - ``2``: Gap filled NTL based on historical data

    check_all_tiles_exist: bool, default=True
        Check whether all Black Marble nighttime light tiles exist for the region of interest. Sometimes not all tiles are available, so the full region of interest may not be covered. By default (True), it skips cases where not all tiles are available.

    file_directory: pathlib.Path, optional
        Where to produce output. By default, the output will be produced onto a temporary directory.

    file_prefix: str, optional
        Prefix

    file_skip_if_exists: bool, default=True
        Whether to skip downloading or extracting data if the data file for that date already exists.

    Returns
    -------
    xarray.Dataset
        `xarray.Dataset` containing a stack of nighttime lights rasters
    """
    # Validate and fix args
    if not isinstance(quality_flag_rm, list):
        quality_flag_rm = [quality_flag_rm]
    if not isinstance(date_range, list):
        date_range = [date_range]

    if variable is None:
        variable = VARIABLE_DEFAULT.get(product_id)

    match product_id:
        case Product.VNP46A3:
            date_range = sorted(set([d.replace(day=1) for d in date_range]))
        case Product.VNP46A4:
            date_range = sorted(set([d.replace(day=1, month=1) for d in date_range]))

    # Download and construct Dataset
    with file_directory if file_directory else tempfile.TemporaryDirectory() as d:
        downloader = BlackMarbleDownloader(bearer, d)
        pathnames = downloader.download(gdf, product_id, date_range)

        dx = []
        for date in tqdm(date_range, desc="COLLATING RESULTS | Processing..."):
            filenames = _pivot_paths_by_date(pathnames).get(date)

            try:
                # Open each GeoTIFF file as a DataArray and store in a list
                da = [
                    rioxarray.open_rasterio(
                        h5_to_geotiff(
                            f,
                            variable=variable,
                            quality_flag_rm=quality_flag_rm,
                            output_prefix=file_prefix,
                            output_directory=d,
                        ),
                    )
                    for f in filenames
                ]
                ds = merge_arrays(da)
                ds = ds.rio.clip(gdf.geometry.apply(mapping), gdf.crs, drop=True)
                ds["time"] = pd.to_datetime(date)

                dx.append(ds.squeeze())
            except TypeError:
                continue

        dx = filter(lambda item: item is not None, dx)

        # Stack the individual dates along "time" dimension
        ds = (
            xr.concat(dx, dim="time", combine_attrs="drop_conflicts")
            .to_dataset(name=variable, promote_attrs=True)
            .sortby("time")
            .drop(["band", "spatial_ref"])
        )
        if variable in VARIABLE_DEFAULT.values():
            ds.assign_attrs(
                long_name=variable,
                units="nW/cm²sr",
            )
            ds[variable].attrs = {"units": "nW/cm²sr"}

        return ds
