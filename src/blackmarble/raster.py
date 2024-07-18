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


def _remove_fill_value(x, variable):
    """
    Remove fill values from the given numpy array based on the specified Black Marble variable.
    Reference: https://viirsland.gsfc.nasa.gov/PDF/BlackMarbleUserGuide_v1.2_20220916.pdf
      * Table 3 (page 12)
      * Table 6 (page 16)
      * Table 9 (page 18)

    Parameters
    ----------
    x: np.array
        Numpy array of raster data.
    variable: str
        Black Marble Variable name.

    Returns
    -------
    np.array
        Numpy array with fill values replaced by np.nan.
    """

    # Dictionary mapping variables to their fill values
    fill_values = {
        "Granule": 255,
        "Mandatory_Quality_Flag": 255,
        "Latest_High_Quality_Retrieval": 255,
        "Snow_Flag": 255,
        "DNB_Platform": 255,
        "Land_Water_Mask": 255,
        "AllAngle_Composite_Snow_Covered_Quality": 255,
        "AllAngle_Composite_Snow_Free_Quality": 255,
        "NearNadir_Composite_Snow_Covered_Quality": 255,
        "NearNadir_Composite_Snow_Free_Quality": 255,
        "OffNadir_Composite_Snow_Covered_Quality": 255,
        "OffNadir_Composite_Snow_Free_Quality": 255,
        "UTC_Time": -999.9,
        "Sensor_Azimuth": -32768,
        "Sensor_Zenith": -32768,
        "Solar_Azimuth": -32768,
        "Solar_Zenith": -32768,
        "Lunar_Azimuth": -32768,
        "Lunar_Zenith": -32768,
        "Glint_Angle": -32768,
        "Moon_Illumination_Fraction": -32768,
        "Moon_Phase_Angle": -32768,
        "DNB_At_Sensor_Radiance_500m": 65535,
        "BrightnessTemperature_M12": 65535,
        "BrightnessTemperature_M13": 65535,
        "BrightnessTemperature_M15": 65535,
        "BrightnessTemperature_M16": 65535,
        "QF_Cloud_Mask": 65535,
        "QF_DNB": 65535,
        "QF_VIIRS_M10": 65535,
        "QF_VIIRS_M11": 65535,
        "QF_VIIRS_M12": 65535,
        "QF_VIIRS_M13": 65535,
        "QF_VIIRS_M15": 65535,
        "QF_VIIRS_M16": 65535,
        "Radiance_M10": 65535,
        "Radiance_M11": 65535,
        "DNB_BRDF-Corrected_NTL": 65535,
        "DNB_Lunar_Irradiance": 65535,
        "Gap_Filled_DNB_BRDF-Corrected_NTL": 65535,
        "AllAngle_Composite_Snow_Covered": 65535,
        "AllAngle_Composite_Snow_Covered_Num": 65535,
        "AllAngle_Composite_Snow_Free": 65535,
        "AllAngle_Composite_Snow_Free_Num": 65535,
        "NearNadir_Composite_Snow_Covered": 65535,
        "NearNadir_Composite_Snow_Covered_Num": 65535,
        "NearNadir_Composite_Snow_Free": 65535,
        "NearNadir_Composite_Snow_Free_Num": 65535,
        "OffNadir_Composite_Snow_Covered": 65535,
        "OffNadir_Composite_Snow_Covered_Num": 65535,
        "OffNadir_Composite_Snow_Free": 65535,
        "OffNadir_Composite_Snow_Free_Num": 65535,
        "AllAngle_Composite_Snow_Covered_Std": 65535,
        "AllAngle_Composite_Snow_Free_Std": 65535,
        "NearNadir_Composite_Snow_Covered_Std": 65535,
        "NearNadir_Composite_Snow_Free_Std": 65535,
        "OffNadir_Composite_Snow_Covered_Std": 65535,
        "OffNadir_Composite_Snow_Free_Std": 65535,
    }

    if fill_value := fill_values.get(variable):
        x = np.where(x == fill_value, np.nan, x)

    return x


def h5_to_geotiff(
    f: Path,
    /,
    variable: str = None,
    drop_values_by_quality_flag: List[int] = [255],
    output_directory: Path = None,
):
    """
    Convert HDF5 file to GeoTIFF for a selected (or default) variable from NASA Black Marble data

    Parameters
    ----------
    f: Path
        H5DF filename

    variable: str, optional
        Variable for which to create a GeoTIFF raster. If None, defaults will be used based on the product.
            - VNP46A1: 'DNB_At_Sensor_Radiance_500m'
            - VNP46A2: 'Gap_Filled_DNB_BRDF-Corrected_NTL'
            - VNP46A3: 'NearNadir_Composite_Snow_Free'
            - VNP46A4: 'NearNadir_Composite_Snow_Free'
        Further information, please see the `NASA Black Marble User Guide <https://ladsweb.modaps.eosdis.nasa.gov/api/v2/content/archives/Document%20Archive/Science%20Data%20Product%20Documentation/VIIRS_Black_Marble_UG_v1.2_April_2021.pdf>`_ for `VNP46A1`, see Table 3; for `VNP46A2` see Table 6; for `VNP46A3` and `VNP46A4`, see Table 9.

    drop_values_by_quality_flag: List[int], optional
        List of the quality flag values for which to drop data values. Each pixel has a quality flag value, where low quality values can be removed. Values are set to ``NA`` for each value in the list.

    output_directory : Path, optional
        Directory to save the output GeoTIFF file. If None, uses the same directory as input file.

    Returns
    ------
    output_path: Path
        Path to the exported GeoTIFF raster.
    """
    output_path = Path(output_directory, f.name).with_suffix(".tif")
    product_id = Product(f.stem.split(".")[0])

    if variable is None:
        variable = VARIABLE_DEFAULT.get(product_id)

    with h5py.File(f, "r") as h5_data:
        attrs = h5_data.attrs
        data_field_key = "HDFEOS/GRIDS/VNP_Grid_DNB/Data Fields"

        if product_id in [Product.VNP46A1, Product.VNP46A2]:
            dataset = h5_data[data_field_key][variable]
            left, bottom, right, top = (
                attrs.get("WestBoundingCoord"),
                attrs.get("SouthBoundingCoord"),
                attrs.get("EastBoundingCoord"),
                attrs.get("NorthBoundingCoord"),
            )
            qf = h5_data[data_field_key]["Mandatory_Quality_Flag"]
        else:
            data_field_key = "HDFEOS/GRIDS/VIIRS_Grid_DNB_2d/Data Fields"
            dataset = h5_data[data_field_key][variable]
            lat = h5_data[data_field_key]["lat"]
            lon = h5_data[data_field_key]["lon"]
            left, bottom, right, top = min(lon), min(lat), max(lon), max(lat)

            variable_short = re.sub("_Num|_Std", "", variable)
            qf_name = f"{variable_short}_Quality"
            qf = h5_data[data_field_key].get(
                qf_name, h5_data[data_field_key].get(variable)
            )

        # Extract data and attributes
        scale_factor = dataset.attrs.get("scale_factor", 1)
        offset = dataset.attrs.get("offset", 0)
        data = scale_factor * _remove_fill_value(dataset[:], variable) + offset

        # Quality flag
        qf = qf[:]

        for val in drop_values_by_quality_flag:
            data = np.where(qf == val, np.nan, data)

        # Get geospatial metadata (coordinates and attributes)
        height, width = data.shape
        transform = from_origin(
            left, top, (right - left) / width, (top - bottom) / height
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


@validate_call(config=ConfigDict(arbitrary_types_allowed=True))
def bm_raster(
    gdf: geopandas.GeoDataFrame,
    product_id: Product,
    date_range: datetime.date | List[datetime.date],
    bearer: str,
    variable: Optional[str] = None,
    drop_values_by_quality_flag: List[int] = [],
    check_all_tiles_exist: bool = True,
    output_directory: Optional[Path] = None,
    output_skip_if_exists: bool = True,
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

    drop_values_by_quality_flag: List[int], optional
        List of the quality flag values for which to drop data values. Each pixel has a quality flag value, where low quality values can be removed. Values are set to ``NA`` for each value in the list.

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

    output_directory: pathlib.Path, optional
        Directory to produce output. By default, the output will be produced onto a temporary directory.

    output_skip_if_exists: bool, default=True
        Whether to skip downloading or extracting data if the data file for that date already exists.

    Returns
    -------
    xarray.Dataset
        `xarray.Dataset` containing a stack of nighttime lights rasters
    """
    # Validate and fix arguments
    if not isinstance(drop_values_by_quality_flag, list):
        drop_values_by_quality_flag = [drop_values_by_quality_flag]
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
    with output_directory if output_directory else tempfile.TemporaryDirectory() as d:
        downloader = BlackMarbleDownloader(bearer, d)
        pathnames = downloader.download(
            gdf, product_id, date_range, output_skip_if_exists
        )

        datasets = []
        for date in tqdm(date_range, desc="COLLATING RESULTS | Processing..."):
            filenames = _pivot_paths_by_date(pathnames).get(date)

            try:
                # Open each GeoTIFF file as a DataArray and store in a list
                da = [
                    rioxarray.open_rasterio(
                        h5_to_geotiff(
                            f,
                            variable=variable,
                            drop_values_by_quality_flag=drop_values_by_quality_flag,
                            output_directory=d,
                        ),
                    )
                    for f in filenames
                ]
                ds = merge_arrays(da)
                clipped_dataset = ds.rio.clip(
                    gdf.geometry.apply(mapping), gdf.crs, drop=True
                )
                clipped_dataset["time"] = pd.to_datetime(date)

                datasets.append(clipped_dataset.squeeze())
            except TypeError:
                continue

        # Filter out None values
        datasets = filter(lambda item: item is not None, datasets)

        # Stack the individual dates along "time" dimension
        combined_dataset = (
            xr.concat(datasets, dim="time", combine_attrs="drop_conflicts")
            .to_dataset(name=variable, promote_attrs=True)
            .sortby("time")
            .drop(["band", "spatial_ref"])
        )
        if variable in VARIABLE_DEFAULT.values():
            ds.assign_attrs(
                long_name=variable,
                units="nW/cm²sr",
            )
            combined_dataset[variable].attrs = {"units": "nW/cm²sr"}

        return combined_dataset
