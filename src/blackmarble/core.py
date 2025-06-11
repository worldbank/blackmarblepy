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
from rasterio.transform import from_bounds, from_origin
from rasterstats import zonal_stats
from rioxarray.merge import merge_arrays
from shapely.geometry import mapping
from tqdm.auto import tqdm

from . import TILES, logger
from .download import BlackMarbleDownloader
from .types import Product


class BlackMarble:
    """
    Interface for extracting and processing NASA Black Marble nighttime light products.

    The `BlackMarble` class provides tools for downloading, extracting, and processing
    NASA Black Marble nighttime light data. It supports zonal statistics extraction
    for selected products within a user-defined region of interest (ROI).

    Examples
    --------
    >>> # Option 1: Class-based interface
    >>> from blackmarble import BlackMarble, Product
    >>>
    >>> # Create a BlackMarble instance. If no bearer token is passed explicitly,
    >>> # it will attempt to read from the BLACKMARBLE_TOKEN environment variable.
    >>> bm = BlackMarble()  # or: BlackMarble(bearer="YOUR_BLACKMARBLE_TOKEN")
    >>>
    >>> # Define your region of interest as a GeoDataFrame (gdf)
    >>> # For example: gdf = gpd.read_file("path_to_shapefile.geojson")
    >>>
    >>> # Retrieve VNP46A2 for date range into a Xarray Dataset
    >>> daily = bm.raster(
    >>>     gdf,
    >>>     product_id=Product.VNP46A2,
    >>>     date_range="2022-01-01",
    >>> )

    References
    --------
    NASA Black Marble Products Overview:
      https://viirsland.gsfc.nasa.gov/Products/NASA/BlackMarble.html
    Black Marble User Guide:
        https://viirsland.gsfc.nasa.gov/PDF/BlackMarbleUserGuide_v1.2_20220916.pdf
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
        logger.debug(f"Active output directory: {self._output_directory}")
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
            Black Marble variable name.

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

    def _mask_by_quality_flag(
        self, data: np.ndarray, qf: np.ndarray, drop_values_by_quality_flag: List[int]
    ) -> np.ndarray:
        """
        Set elements in `data` to np.nan where the corresponding element in `qf` matches any value in `drop_values_by_quality_flag`.
        """
        if qf is None or len(drop_values_by_quality_flag) == 0:
            data

        qf = np.asarray(qf)
        drop_values_by_quality_flag = np.asarray(
            drop_values_by_quality_flag, dtype=qf.dtype
        )

        # Create a boolean mask where qf matches any of the drop values
        mask = np.isin(qf, drop_values_by_quality_flag)
        data = np.where(mask, np.nan, data)

        return data

    def _transform(self, tile_id: str, width, height):
        """
        Calculate the affine transform for a given tile ID and raster shape.

        Parameters
        ----------
        tile_id : str
            The NASA Black Marble tile identifier.
        width : int
            The number of columns (pixels) in the raster.
        height : int
            The number of rows (pixels) in the raster.
        """
        tile = TILES[TILES["TileID"] == tile_id]
        minx, miny, maxx, maxy = tile.total_bounds

        return from_bounds(minx, miny, maxx, maxy, width, height)

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

            # Obtain TileID
            h = attrs["HorizontalTileNumber"].decode("utf-8")
            v = attrs["VerticalTileNumber"].decode("utf-8")

            match product_id:
                case Product.VNP46A1:
                    data_key = "HDFEOS/GRIDS/VNP_Grid_DNB/Data Fields"
                    dataset = h5_data[data_key][variable]
                    qf = None  # No quality flag available
                case Product.VNP46A2:
                    data_key = "HDFEOS/GRIDS/VNP_Grid_DNB/Data Fields"
                    dataset = h5_data[data_key][variable]
                    qf = h5_data[data_key]["Mandatory_Quality_Flag"]
                case Product.VNP46A3 | Product.VNP46A4:
                    data_key = "HDFEOS/GRIDS/VIIRS_Grid_DNB_2d/Data Fields"
                    dataset = h5_data[data_key][variable]
                    variable_short = re.sub("_Num|_Std", "", variable)
                    qf_name = f"{variable_short}_Quality"
                    qf = h5_data[data_key].get(qf_name, dataset)

            # Post-processing
            data = dataset[:]
            data = self._remove_fill_value(data, variable)
            data = self._mask_by_quality_flag(data, qf, drop_values_by_quality_flag)

            scale = dataset.attrs.get("scale_factor", 1)
            offset = dataset.attrs.get("offset", 0)
            data = scale * data + offset

            # Prepare raster and transformation
            height, width = data.shape
            transform = self._transform(f"h{h}v{v}", width, height)

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

    def collate_tiles(self, gdf, date_range, pathnames, variable):
        """
        Convert HDF5 files to GeoTIFFs, load them as DataArrays, merge, clip, and combine along time.

        Parameters
        ----------
        gdf : geopandas.GeoDataFrame
            Region of interest.
        date_range : iterable
            Sequence of dates to process.
        pathnames : list
            List of HDF5 file paths.
        variable : str
            Name of the variable to extract from the HDF5 files.

        Returns
        -------
        combined : xarray.Dataset
            Dataset containing the processed variable, merged, clipped to the region of interest, and combined along the time dimension.
        """

        def pivot_paths_by_date(paths: List[Path]):
            results = {}
            for p in paths:
                key = datetime.datetime.strptime(p.stem.split(".")[1], "A%Y%j").date()
                results.setdefault(key, []).append(p)
            return results

        pivoted_paths = pivot_paths_by_date(pathnames)
        clipped_arrays = []

        for date in tqdm(
            date_range, desc="COLLATING TILES | Processing...", unit="date"
        ):
            h5_files = pivoted_paths.get(date)
            data_arrays = [
                rioxarray.open_rasterio(
                    self._h5_to_geotiff(
                        h5_file,
                        variable=variable,
                        drop_values_by_quality_flag=self.drop_values_by_quality_flag,
                        output_directory=self.output_directory,
                    )
                )
                for h5_file in h5_files
            ]
            if not data_arrays:
                logger.warning(f"No data available for date: {date}")
                continue  # Skip dates with no data

            # Merge tiles and clip to region of interest
            merged = merge_arrays(data_arrays, nodata=np.nan)
            clipped = merged.rio.clip(
                gdf.geometry.apply(mapping), gdf.crs, drop=True
            ).squeeze()
            clipped["time"] = pd.to_datetime(date)
            clipped_arrays.append(clipped)

        if not clipped_arrays:
            raise ValueError("No data arrays were processed. Check your inputs.")

        # Combine along time dimension
        combined = (
            xr.concat(clipped_arrays, dim="time", combine_attrs="drop_conflicts")
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
            Identifier for the NASA Black Marble VNP46 product. For detailed product descriptions, see also https://blackmarble.gsfc.nasa.gov/#product.

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
            gdf=gdf,
            product_id=product_id,
            date_range=date_range,
            skip_if_exists=self.output_skip_if_exists,
        )

        # Process and combine tiles into a single dataset
        combined = self.collate_tiles(
            gdf=gdf, date_range=date_range, pathnames=pathnames, variable=variable
        )

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
            Identifier for the NASA Black Marble VNP46 product. For detailed product descriptions, see also https://blackmarble.gsfc.nasa.gov/#product.

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

        def affine(da: xr.DataArray):
            left, bottom, right, top = (
                da["x"].min(),
                da["y"].min(),
                da["x"].max(),
                da["y"].max(),
            )
            height, width = da.shape
            return from_origin(
                left, top, (right - left) / width, (top - bottom) / height
            )

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
                affine=affine(da),
                stats=aggfunc,
            )

            stats_df = pd.DataFrame(stats).add_prefix("ntl_")
            merged = pd.concat([gdf, stats_df], axis=1)
            merged["date"] = time.values
            results.append(merged)

        return pd.concat(results, ignore_index=True)
