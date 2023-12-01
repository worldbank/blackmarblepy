import os
import shutil
import tempfile
import time

import numpy as np
import rasterio
from rasterio.merge import merge

from tqdm.auto import tqdm

from . import logger
from .utils import bm_raster_i, define_date_name, define_variable


def bm_raster(
    roi_sf,
    product_id,
    date,
    bearer,
    variable=None,
    quality_flag_rm=[255],
    check_all_tiles_exist=True,
    output_location_type="tempfile",
    file_dir=None,
    file_prefix="",
    file_skip_if_exists=True,
    quiet=False,
):
    """Make a raster of nighttime lights from [NASA Black Marble data](https://blackmarble.gsfc.nasa.gov/).

    Parameters
    ----------

    roi_st : geopandas.DataFrame
        Region of interest; geopandas dataframe (polygon). Must be in the [WGS 84 (epsg:4326)](https://epsg.io/4326) coordinate reference system.

    product_id: string. One of the following:
        * `"VNP46A1"`: Daily (raw)
        * `"VNP46A2"`: Daily (corrected)
        * `"VNP46A3"`: Monthly
        * `"VNP46A4"`: Annual

    date: Date of raster data. Entering one date will produce a raster. Entering multiple dates will produce a raster stack.
        * For `product_id`s `"VNP46A1"` and `"VNP46A2"`, a date (eg, `"2021-10-03"`).
        * For `product_id` `"VNP46A3"`, a date or year-month (e.g., `"2021-10-01"`, where the day will be ignored, or `"2021-10"`).
        * For `product_id` `"VNP46A4"`, year or date  (e.g., `"2021-10-01"`, where the month and day will be ignored, or `2021`).

    bearer: NASA bearer token. For instructions on how to create a token, see [here](https://github.com/ramarty/blackmarbler#bearer-token-).

    variable: Variable to used to create raster (default: `NULL`). If `NULL`, uses the following default variables:
        * For `product_id` `:VNP46A1"`, uses `DNB_At_Sensor_Radiance_500m`.
        * For `product_id` `"VNP46A2"`, uses `Gap_Filled_DNB_BRDF-Corrected_NTL`.
        * For `product_id`s `"VNP46A3"` and `"VNP46A4"`, uses `NearNadir_Composite_Snow_Free`.
    For information on other variable choices, see [here](https://ladsweb.modaps.eosdis.nasa.gov/api/v2/content/archives/Document%20Archive/Science%20Data%20Product%20Documentation/VIIRS_Black_Marble_UG_v1.2_April_2021.pdf); for `VNP46A1`, see Table 3; for `VNP46A2` see Table 6; for `VNP46A3` and `VNP46A4`, see Table 9.

    quality_flag_rm: long
        Quality flag values to use to set values to `NA`. Each pixel has a quality flag value, where low quality values can be removed. Values are set to `NA` for each value in ther `quality_flag_rm` vector. (Default: `c(255)`).

        For `VNP46A1` and `VNP46A2` (daily data):
        - `0`: High-quality, Persistent nighttime lights
        - `1`: High-quality, Ephemeral nighttime Lights
        - `2`: Poor-quality, Outlier, potential cloud contamination, or other issues
        - `255`: No retrieval, Fill value (masked out on ingestion)

    For `VNP46A3` and `VNP46A4` (monthly and annual data):
    - `0`: Good-quality, The number of observations used for the composite is larger than 3
    - `1`: Poor-quality, The number of observations used for the composite is less than or equal to 3
    - `2`: Gap filled NTL based on historical data
    - `255`: Fill value

    check_all_tiles_exist: Check whether all Black Marble nighttime light tiles exist for the region of interest. Sometimes not all tiles are available, so the full region of interest may not be covered. If `TRUE`, skips cases where not all tiles are available. (Default: `TRUE`).

    output_location_type: Where to produce output; either `r_memory` or `file`. If `r_memory`, functions returns a raster in R. If `file`, function exports a `.tif` file and returns `NULL`.

    For `output_location_type = file`:

        file_dir: The directory where data should be exported (default: `NULL`, so the working directory will be used)

        file_prefix: Prefix to add to the file to be saved. The file will be saved as the following: `[file_prefix][product_id]_t[date].tif`

        file_skip_if_exists: Whether the function should first check wither the file already exists, and to skip downloading or extracting data if the data for that date if the file already exists (default: `TRUE`).

    quiet: Suppress output that show downloading progress and other messages. (Default: `FALSE`).

    Returns
    -------
    None (if output_location_type = "file")
        A geotif file is saved to the "file_dir" directory. Nothing is returned from the function.

    Raster (if output_location_type = "tempfile")

    """

    #### Make directory to put temporary files into
    temp_main_dir = tempfile.gettempdir()

    current_time_millis = int(round(time.time() * 1000))
    temp_dir = os.path.join(temp_main_dir, "bm_raster_temp_" + str(current_time_millis))

    os.makedirs(temp_dir)

    #### Define NTL Variable
    variable = define_variable(variable, product_id)

    #### Ensure quality_flag_rm is a list
    if type(quality_flag_rm) is not list:
        quality_flag_rm = [quality_flag_rm]

    #### Ensure date is a list of strings
    if type(date) is not list:
        date = [date]

    date = [str(item) for item in date]

    if file_dir is None:
        file_dir = os.getcwd()

    # File --------------------------------------------------------------------------
    if output_location_type == "file":
        # crate progress bar
        pbar = tqdm(date, leave=None)

        for date_i in pbar:
            pbar.set_description("Downloading raster(s)...")
            date_name_i = define_date_name(date_i, product_id)

            try:
                out_name = file_prefix + product_id + "_" + date_name_i + ".tif"
                out_path = os.path.join(file_dir, out_name)

                # Only make .tif if raster doesn't already exist
                if (not file_skip_if_exists) | (not os.path.exists(out_path)):
                    raster_path_i = bm_raster_i(
                        roi_sf,
                        product_id,
                        date_i,
                        bearer,
                        variable,
                        quality_flag_rm,
                        check_all_tiles_exist,
                        quiet,
                        temp_dir,
                    )
                    shutil.move(raster_path_i, out_path)  # Move from tmp to main folder

                    if quiet == False:
                        logger.info("File created: " + out_path)

                else:
                    if quiet == False:
                        logger.info('"' + out_path + '" already exists; skipping.\n')

                r_out = None
            except:
                r_out = None

    # Tempfile --------------------------------------------------------------------------
    if output_location_type == "tempfile":
        try:
            #### Create raster for each date
            raster_path_list = []
            for date_i in date:
                date_name_i = define_date_name(date_i, product_id)

                raster_path_i = bm_raster_i(
                    roi_sf,
                    product_id,
                    date_i,
                    bearer,
                    variable,
                    quality_flag_rm,
                    check_all_tiles_exist,
                    quiet,
                    temp_dir,
                )
                raster_path_list.append(raster_path_i)

            #### Stack Rasters
            # Read the first file to get the dimensions and metadata
            with rasterio.open(raster_path_list[0]) as src:
                width = src.width
                height = src.height
                count = len(raster_path_list)
                crs = src.crs
                transform = src.transform
                dtype = src.dtypes[0]

                # Create an empty numpy array to store the raster data
                data = np.zeros((count, height, width), dtype=dtype)

                # Read data from each file and store it in the numpy array
                for i, file_path in enumerate(raster_path_list):
                    with rasterio.open(file_path) as src:
                        data[i] = src.read(1)

            # Create a new raster file and write the data
            timestamp = str(int(time.time()))
            tmp_raster_file_name = (
                product_id + "_" + date[0].replace("-", "_") + "_" + timestamp + ".tif"
            )

            with rasterio.open(
                os.path.join(temp_dir, tmp_raster_file_name),
                "w",
                driver="GTiff",
                width=width,
                height=height,
                count=count,
                dtype=dtype,
                crs=crs,
                transform=transform,
            ) as dst:
                for i in range(count):
                    dst.write(data[i], i + 1)

            # Move from black marble temp folder to main temp folder
            shutil.move(os.path.join(temp_dir, tmp_raster_file_name), temp_main_dir)

            r_out = rasterio.open(os.path.join(temp_main_dir, tmp_raster_file_name))

        except Exception as e:
            # Delete temp files used to make raster
            shutil.rmtree(temp_dir, ignore_errors=True)

            if quiet == False:
                logger.info(
                    "Skipping "
                    + str(date_i)
                    + " due to error. Data may not be available.\n"
                )
            r_out = None

    # Delete temp files used to make raster
    shutil.rmtree(temp_dir, ignore_errors=True)

    return r_out
