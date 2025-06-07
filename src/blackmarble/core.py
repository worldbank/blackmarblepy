import datetime
import os
import re
import tempfile
from pathlib import Path
from typing import List, Optional, Union

import geopandas as gpd
import h5py
import numpy as np
import pandas as pd
import rasterio
import rioxarray
import xarray as xr
from pydantic import ConfigDict, validate_call
from rasterio.transform import from_origin
from rasterstats import zonal_stats
from rioxarray.merge import merge_arrays
from shapely.geometry import mapping
from tqdm.auto import tqdm

from . import logger
from .download import BlackMarbleDownloader
from .types import Product


class BlackMarble:
    """
    Interface for extracting and processing NASA Black Marble nighttime light products.

    This class handles downloading and extracting zonal statistics for
    selected NASA Black Marble products using a specified region of interest.

    Attributes
    ----------
    VARIABLE_DEFAULT : dict
        Default variables for each Black Marble product, used if no variable is explicitly provided.
    """

    VARIABLE_DEFAULT = {
        Product.VNP46A1: "DNB_At_Sensor_Radiance_500m",
        Product.VNP46A2: "Gap_Filled_DNB_BRDF-Corrected_NTL",
        Product.VNP46A3: "NearNadir_Composite_Snow_Free",
        Product.VNP46A4: "NearNadir_Composite_Snow_Free",
    }

    def __init__(
        self,
        bearer: Optional[str] = None,
        check_all_tiles_exist: bool = True,
        drop_values_by_quality_flag: List[int] = [255],
        output_directory: Optional[Path] = None,
        output_skip_if_exists: bool = True,
    ):
        """
        Initialize a BlackMarble instance.

        Parameters
        ----------
        bearer : str, optional
            NASA Earthdata Bearer token. If not provided, the environment variable
            `BLACKMARBLE_TOKEN` is used.
        check_all_tiles_exist: bool, default=True
            Check whether all Black Marble nighttime light tiles exist for the region of interest. Sometimes not all tiles are available, so the full region of interest may not be covered. By default (True), it skips cases where not all tiles are available.
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
        output_directory : pathlib.Path, optional
            Directory where output GeoTIFF or extracted data will be saved. If None, a temporary directory
            is created and reused internally for all output operations.
        output_skip_if_exists: bool, default=True
            Whether to skip downloading or extracting data if the data file for that date already exists.
        """
        self._bearer = bearer or os.getenv("BLACKMARBLE_TOKEN")
        if not self._bearer:
            raise ValueError(
                "A NASA Earthdata bearer token must be provided, either via the 'bearer' argument "
                "or the 'BLACKMARBLE_TOKEN' environment variable."
            )

        self.check_all_tiles_exist = check_all_tiles_exist
        self.drop_values_by_quality_flag = drop_values_by_quality_flag
        self.output_skip_if_exists = output_skip_if_exists

        if output_directory is not None:
            self._output_directory = Path(output_directory).resolve()
        else:
            self._tmpdir = tempfile.TemporaryDirectory()
            self._output_directory = Path(self._tmpdir.name).resolve()

    def close(self):
        """Clean up temporary resources, if used."""
        if self._tmpdir:
            self._tmpdir.cleanup()
            self._tmpdir = None

    @property
    def output_directory(self) -> Path:
        """Return the active output directory path."""
        self._output_directory.mkdir(parents=True, exist_ok=True)
        logger.info(self._output_directory)
        return self._output_directory

    def _remove_fill_value(self, x: np.ndarray, variable: str) -> np.array:
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
        fill_value = fill_values.get(variable)
        return np.where(x == fill_value, np.nan, x) if fill_value is not None else x

    def _transform(self, da: xr.DataArray):
        left, bottom, right, top = (
            da["x"].min(),
            da["y"].min(),
            da["x"].max(),
            da["y"].max(),
        )
        height, width = da.shape
        return from_origin(left, top, (right - left) / width, (top - bottom) / height)

    def _h5_to_geotiff(
        self,
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
            H5DF filename.

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
        -------
        output_path: Path
            Path to the exported GeoTIFF raster.
        """
        output_path = Path(output_directory or f.parent, f.name).with_suffix(".tif")
        product_id = Product(f.stem.split(".")[0])

        with h5py.File(f, "r") as h5_data:
            attrs = h5_data.attrs
            if product_id in [Product.VNP46A1, Product.VNP46A2]:
                data_key = "HDFEOS/GRIDS/VNP_Grid_DNB/Data Fields"
                qf = h5_data[data_key]["Mandatory_Quality_Flag"]
                dataset = h5_data[data_key][variable]
                left, bottom, right, top = (
                    attrs["WestBoundingCoord"],
                    attrs["SouthBoundingCoord"],
                    attrs["EastBoundingCoord"],
                    attrs["NorthBoundingCoord"],
                )
            else:
                data_key = "HDFEOS/GRIDS/VIIRS_Grid_DNB_2d/Data Fields"
                lat = h5_data[data_key]["lat"]
                lon = h5_data[data_key]["lon"]
                left, bottom, right, top = (
                    min(lon[:]),
                    min(lat[:]),
                    max(lon[:]),
                    max(lat[:]),
                )
                dataset = h5_data[data_key][variable]
                variable_short = re.sub("_Num|_Std", "", variable)
                qf_name = f"{variable_short}_Quality"
                qf = h5_data[data_key].get(qf_name, dataset)

            data = dataset[:]
            data = self._remove_fill_value(data, variable)
            scale = dataset.attrs.get("scale_factor", 1)
            offset = dataset.attrs.get("offset", 0)
            data = scale * data + offset
            qf = qf[:]

            for val in drop_values_by_quality_flag:
                data = np.where(qf == val, np.nan, data)

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

    def _pivot_paths_by_date(self, paths: List[Path]):
        results = {}
        for p in paths:
            key = datetime.datetime.strptime(p.stem.split(".")[1], "A%Y%j").date()
            results.setdefault(key, []).append(p)
        return results

    @validate_call(config=ConfigDict(arbitrary_types_allowed=True))
    def raster(
        self,
        gdf: gpd.GeoDataFrame,
        product_id: Product,
        date_range: datetime.date | List[datetime.date],
        variable: Optional[str] = None,
    ) -> xr.Dataset:
        """Create a stack of nighttime lights rasters by retrieiving from `NASA Black Marble <https://blackmarble.gsfc.nasa.gov>`_ data.

        Parameters
        ----------
        gdf: geopandas.GeoDataFrame
            Region of interest

        product_id: Product
            Identifier for the NASA Black Marble VNP46 product.

            Available options include:

            - ``VNP46A1``: Daily top-of-atmosphere (TOA) radiance (raw)
            - ``VNP46A2``: Daily moonlight-corrected nighttime lights
            - ``VNP46A3``: Monthly gap-filled nighttime light composites
            - ``VNP46A4``: Annual gap-filled nighttime light composites

            For detailed product descriptions, see: https://blackmarble.gsfc.nasa.gov/#product

        date_range: datetime.date | List[datetime.date]
            Date range (single date or list of dates) for which to retrieve NASA Black Marble data.

        variable: str, default = None
            Variable for which to a GeoTIFF raster. Further information, please see the `NASA Black Marble User Guide <https://ladsweb.modaps.eosdis.nasa.gov/api/v2/content/archives/Document%20Archive/Science%20Data%20Product%20Documentation/VIIRS_Black_Marble_UG_v1.2_April_2021.pdf>`_ for `VNP46A1`, see Table 3; for `VNP46A2` see Table 6; for `VNP46A3` and `VNP46A4`, see Table 9. By default, it uses the following default variables:

            - For ``VNP46A1``, uses ``DNB_At_Sensor_Radiance_500m``
            - For ``VNP46A2``, uses ``Gap_Filled_DNB_BRDF-Corrected_NTL``
            - For ``VNP46A3``, uses ``NearNadir_Composite_Snow_Free``.
            - For ``VNP46A4``, uses ``NearNadir_Composite_Snow_Free``.

        Returns
        -------
        xarray.Dataset
            `xarray.Dataset` containing a stack of nighttime lights rasters
        """
        # Ensure `date_range` is always a list, even if a single date is provided
        if not isinstance(date_range, list):
            date_range = [date_range]
        if variable is None:
            variable = self.VARIABLE_DEFAULT[product_id]

        # Normalize the date range depending on the product's temporal resolution
        match product_id:
            case Product.VNP46A3:
                # VNP46A3 is a monthly product.
                # Normalize all dates to the first day of their respective months
                date_range = sorted(set([d.replace(day=1) for d in date_range]))
            case Product.VNP46A4:
                # VNP46A4 is an annual product.
                # Normalize all dates to the first day of the year
                date_range = sorted(
                    set([d.replace(day=1, month=1) for d in date_range])
                )

        # Download NASA Black Marble tiles for the specified region and dates and
        # returns a mapping of file paths grouped by date for further processing.
        downloader = BlackMarbleDownloader(self._bearer, self.output_directory)
        pathnames = downloader.download(
            gdf, product_id, date_range, self.output_skip_if_exists
        )

        datasets = []

        # Process tiles for each date in the range
        for date in tqdm(date_range, desc="COLLATING TILES | Processing..."):
            pathnames_by_date = self._pivot_paths_by_date(pathnames).get(date)

            try:
                # Convert HDF5 files to GeoTIFFs and open them as DataArrays
                da = [
                    rioxarray.open_rasterio(
                        self._h5_to_geotiff(
                            f,
                            variable=variable,
                            drop_values_by_quality_flag=self.drop_values_by_quality_flag,
                            output_directory=self.output_directory,
                        ),
                    )
                    for f in pathnames_by_date
                ]
                # Merge tiles and clip to region of interest
                merged = merge_arrays(da)
                clipped = merged.rio.clip(
                    gdf.geometry.apply(mapping), gdf.crs, drop=True
                )
                clipped["time"] = pd.to_datetime(date)
                datasets.append(clipped.squeeze())

            except TypeError:
                continue

        # Materialize list from filter object
        datasets = filter(lambda item: item is not None, datasets)

        # Combine along time dimension
        combined = (
            xr.concat(datasets, dim="time", combine_attrs="drop_conflicts")
            .to_dataset(name=variable, promote_attrs=True)
            .sortby("time")
            .drop_vars(["band", "spatial_ref"], errors="ignore")
        )

        # Add metadata if standard variable
        if variable in self.VARIABLE_DEFAULT.values():
            combined[variable].attrs = {
                "units": "nW/cm²sr",
                "long_name": variable,
            }

        return combined

    def extract(
        self,
        gdf: gpd.GeoDataFrame,
        product_id: Product,
        date_range: Union[datetime.date, List[datetime.date]],
        variable: Optional[str] = None,
        aggfunc: Union[str, List[str]] = ["mean"],
    ) -> pd.DataFrame:
        """Extract and aggregate nighttime lights zonal statistics from `NASA Black Marble <https://blackmarble.gsfc.nasa.gov>`_.

        Parameters
        ----------
        gdf: geopandas.GeoDataFrame
            Region of interest

        product_id: Product
            Identifier for the NASA Black Marble VNP46 product.

            Available options include:

            - ``VNP46A1``: Daily top-of-atmosphere (TOA) radiance (raw)
            - ``VNP46A2``: Daily moonlight-corrected nighttime lights
            - ``VNP46A3``: Monthly gap-filled nighttime light composites
            - ``VNP46A4``: Annual gap-filled nighttime light composites

            For detailed product descriptions, see: https://blackmarble.gsfc.nasa.gov/#product

        date_range: datetime.date | List[datetime.date]
            Date range (single date or list of dates) for which to retrieve NASA Black Marble data.

        variable: str, default = None
            Variable to create GeoTIFF raster. Further information, please see the `NASA Black Marble User Guide <https://ladsweb.modaps.eosdis.nasa.gov/api/v2/content/archives/Document%20Archive/Science%20Data%20Product%20Documentation/VIIRS_Black_Marble_UG_v1.2_April_2021.pdf>`_ for `VNP46A1`, see Table 3; for `VNP46A2` see Table 6; for `VNP46A3` and `VNP46A4`, see Table 9. By default, it uses the following default variables:

            - For ``VNP46A1``, uses ``DNB_At_Sensor_Radiance_500m``
            - For ``VNP46A2``, uses ``Gap_Filled_DNB_BRDF-Corrected_NTL``
            - For ``VNP46A3``, uses ``NearNadir_Composite_Snow_Free``.
            - For ``VNP46A4``, uses ``NearNadir_Composite_Snow_Free``.

        aggfunc: str | List[str], default=["mean"]
            Which statistics to calculate for each zone. All possible choices are listed in `rasterstats.utils.VALID_STATS <https://pythonhosted.org/rasterstats/rasterstats.html?highlight=zonal_stats#rasterstats.gen>`_.

        Returns
        -------
        pandas.DataFrame
            Zonal statistics dataframe
        """
        # If no variable is explicitly specified, use the default variable associated
        if variable is None:
            variable = self.VARIABLE_DEFAULT.get(Product(product_id))

        dataset = self.raster(
            gdf=gdf,
            product_id=product_id,
            date_range=date_range,
            variable=variable,
        )

        results = []
        for time in dataset["time"]:
            da = dataset[variable].sel(time=time)

            stats = zonal_stats(
                gdf,
                da.values,
                nodata=np.nan,
                affine=self._transform(da),
                stats=aggfunc,
            )

            stats_df = pd.DataFrame(stats).add_prefix("ntl_")
            merged = pd.concat([gdf, stats_df], axis=1)
            merged["date"] = time.values
            results.append(merged)

        return pd.concat(results, ignore_index=True)
