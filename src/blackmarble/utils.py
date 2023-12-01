import datetime
import glob
import os
import re
import shutil
import geopandas
import warnings
from importlib.resources import files

import backoff
import geopandas as gpd
import h5py
import httpx
import numpy as np
import pandas as pd
import rasterio
from httpx import HTTPError
from rasterio.mask import mask
from rasterio.merge import merge
from rasterio.transform import from_origin
from rasterstats import zonal_stats
from tqdm.auto import tqdm

from . import logger


def file_to_raster(f, variable, output_path, quality_flag_rm):
    h5_data = h5py.File(f, "r")

    # Daily --------------------------------------------------
    if ("VNP46A1" in f) or ("VNP46A2" in f):
        #### Check
        h5_names = list(
            h5_data["HDFEOS"]["GRIDS"]["VNP_Grid_DNB"]["Data Fields"].keys()
        )

        if variable not in h5_names:
            warnings.warn(
                "'"
                + variable
                + "'"
                + " not a valid variable option. Valid options include:\n"
                + ",\n ".join(h5_names),
                UserWarning,
            )

        tile_i = re.findall(r"h\d{2}v\d{2}", f)[0]

        bm_tiles_sf = gpd.read_file(
            files("blackmarble.data").joinpath("blackmarbletiles.geojson")
        )
        grid_i_sf = bm_tiles_sf[bm_tiles_sf["TileID"] == tile_i]

        xMin = float(grid_i_sf.geometry.bounds.minx.iloc[0])
        yMin = float(grid_i_sf.geometry.bounds.miny.iloc[0])
        xMax = float(grid_i_sf.geometry.bounds.maxx.iloc[0])
        yMax = float(grid_i_sf.geometry.bounds.maxy.iloc[0])

        out = h5_data["HDFEOS"]["GRIDS"]["VNP_Grid_DNB"]["Data Fields"][variable]
        qf = h5_data["HDFEOS"]["GRIDS"]["VNP_Grid_DNB"]["Data Fields"][
            "Mandatory_Quality_Flag"
        ]

        out = out[:]
        qf = qf[:]

        if len(quality_flag_rm) > 0:
            for val in quality_flag_rm:
                out = np.where(qf == val, np.nan, out)

    # Monthly / Annual --------------------------------------------------
    else:
        h5_names = list(
            h5_data["HDFEOS"]["GRIDS"]["VIIRS_Grid_DNB_2d"]["Data Fields"].keys()
        )

        if variable not in h5_names:
            warnings.warn(
                "'"
                + variable
                + "'"
                + " not a valid variable option. Valid options include:\n"
                + ",\n ".join(h5_names),
                UserWarning,
            )

        lat = h5_data["HDFEOS"]["GRIDS"]["VIIRS_Grid_DNB_2d"]["Data Fields"]["lat"]
        lon = h5_data["HDFEOS"]["GRIDS"]["VIIRS_Grid_DNB_2d"]["Data Fields"]["lon"]
        out = h5_data["HDFEOS"]["GRIDS"]["VIIRS_Grid_DNB_2d"]["Data Fields"][variable]

        out = out[:]

        #### Quality Flags
        if len(quality_flag_rm) > 0:
            variable_short = variable
            variable_short = re.sub("_Num", "", variable_short)
            variable_short = re.sub("_Std", "", variable_short)

            qf_name = variable_short + "_Quality"

            if qf_name in h5_names:
                qf = h5_data["HDFEOS"]["GRIDS"]["VIIRS_Grid_DNB_2d"]["Data Fields"][
                    variable + "_Quality"
                ]
                qf = qf[:]

                for val in quality_flag_rm:
                    out = np.where(qf == val, np.nan, out)

        xMin = min(lon)
        yMin = min(lat)
        xMax = max(lon)
        yMax = max(lat)

    # Cleanup --------------------------------------------------

    # Metadata
    nRows = out.shape[0]
    nCols = out.shape[1]
    res = nRows
    nodata_val = 65535
    myCrs = 4326

    # Makes raster
    # data = out[:]
    data = out
    # data = np.where(data == 65535, np.nan, data)

    # Define the pixel size and number of rows and columns
    pixel_size = 1  # Size of each pixel in the output raster
    rows, cols = data.shape

    # Define the spatial extent (bounding box) of the raster
    left, bottom, right, top = xMin, yMin, xMax, yMax

    psize_x = (xMax - xMin) / cols
    psize_y = (yMax - yMin) / rows

    # Create the raster file
    with rasterio.open(
        output_path,
        "w",
        driver="GTiff",
        height=rows,
        width=cols,
        count=1,
        dtype=data.dtype,
        crs="EPSG:4326",
        transform=from_origin(left, top, psize_x, psize_y),
    ) as dst:
        dst.write(data, 1)

    return None


@backoff.on_exception(
    backoff.expo,
    HTTPError,
)
def retrieve_manifest(product_id: str, date: datetime.date) -> pd.DataFrame:
    """NASA Black Marble

    Returns
    -------
    pandas.DataFrame
        NASA Black Marble data manifest (i.e., downloads links)
    """

    match product_id:
        case "VNP46A3":
            # if VNP46A3 then first day of the month
            tm_yday = date.replace(day=1).timetuple().tm_yday
        case "VNP46A4":
            # if VNP46A4 then first day of the year
            tm_yday = date.replace(month=1, day=1).timetuple().tm_yday
        case _:
            tm_yday = date.timetuple().tm_yday

    manifest = pd.read_csv(
        f"https://ladsweb.modaps.eosdis.nasa.gov/archive/allData/5000/{product_id}/{date.year}/{tm_yday}.csv"
    )
    manifest["year"] = date.year
    manifest["day"] = tm_yday

    return manifest


@backoff.on_exception(
    backoff.expo,
    HTTPError,
)
def download_raster(
    file_name,
    temp_dir,
    variable,
    bearer,
    quality_flag_rm,
    quiet,
    tile_i,
    n_tile,
    progress=None,
):
    """Download NASA BLA"""

    year = file_name[9:13]
    day = file_name[13:16]
    product_id = file_name[0:7]

    # f = os.path.join(temp_dir, product_id, year, day, file_name)
    f = os.path.join(temp_dir, file_name)

    url = f"https://ladsweb.modaps.eosdis.nasa.gov/archive/allData/5000/{product_id}/{year}/{day}/{file_name}"
    headers = {"Authorization": f"Bearer {bearer}"}
    download_path = os.path.join(temp_dir, file_name)

    with httpx.stream(
        "GET",
        url,
        headers=headers,
    ) as response:
        total = int(response.headers["Content-Length"])
        with open(download_path, "wb") as download_file, tqdm(
            total=total,
            unit="B",
            unit_scale=True,
            leave=None,
        ) as pbar:
            pbar.set_description(f"Processing {file_name}...")
            for chunk in response.iter_raw():
                download_file.write(chunk)
                pbar.update(len(chunk))

    # Convert to raster
    file_name_tif = re.sub(".h5", ".tif", file_name)

    file_to_raster(
        f,
        variable,
        os.path.join(temp_dir, "tif_files_tmp", file_name_tif),
        quality_flag_rm,
    )


def define_variable(variable, product_id):
    if variable is None:
        if product_id == "VNP46A1":
            variable = "DNB_At_Sensor_Radiance_500m"
        if product_id == "VNP46A2":
            variable = "Gap_Filled_DNB_BRDF-Corrected_NTL"
        if product_id in ["VNP46A3", "VNP46A4"]:
            variable = "NearNadir_Composite_Snow_Free"
    return variable


def define_date_name(date_i, product_id):
    if product_id in ["VNP46A1", "VNP46A2"]:
        date_name_i = "t" + re.sub("-", "_", date_i)

    if product_id == "VNP46A3":
        date_name_i = "t" + re.sub("-", "_", date_i)[:7]

    if product_id == "VNP46A4":
        date_name_i = "t" + re.sub("-", "_", date_i)[:4]

    return date_name_i


def bm_extract_i(
    roi_sf,
    product_id,
    date_i,
    bearer,
    variable,
    quality_flag_rm,
    aggregation_fun,
    check_all_tiles_exist,
    quiet,
    temp_dir,
):
    try:
        #### Extract data
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

        with rasterio.open(raster_path_i) as src:
            raster_data = src.read(1)

        # nodata=src.nodata
        ntl_data = zonal_stats(
            roi_sf,
            raster_data,
            affine=src.transform,
            nodata=np.nan,
            masked=False,
            stats=aggregation_fun,
        )

        ntl_data_df = pd.DataFrame(ntl_data)
        ntl_data_df = ntl_data_df.add_prefix("ntl_")

        roi_df = pd.DataFrame(roi_sf.drop("geometry", axis=1))
        poly_ntl_df = pd.concat([roi_df, ntl_data_df], axis=1)
        poly_ntl_df["date"] = date_i

    except:
        logger.info(
            "Skipping " + str(date_i) + " due to error. Data may not be available.\n"
        )
        poly_ntl_df = pd.DataFrame()

    return poly_ntl_df


def bm_raster_i(
    roi_sf: geopandas.GeoDataFrame,
    product_id: str,
    date: str,
    bearer,
    variable,
    quality_flag_rm,
    check_all_tiles_exist,
    quiet,
    temp_dir,
):
    #### Prep files to download
    if not isinstance(date, datetime.date):
        date = datetime.datetime.strptime(date, "%Y-%m-%d").date()

    bm_files_df = retrieve_manifest(product_id, date)
    bm_tiles_sf = gpd.read_file(
        files("blackmarble.data").joinpath("blackmarbletiles.geojson")
    )

    # Intersecting tiles
    bm_tiles_sf = bm_tiles_sf[~bm_tiles_sf["TileID"].str.contains("h00")]
    bm_tiles_sf = bm_tiles_sf[~bm_tiles_sf["TileID"].str.contains("v00")]

    grid_use_sf = gpd.overlay(bm_tiles_sf, roi_sf.dissolve(), how="intersection")

    # Make raster
    tile_ids_rx = "|".join(grid_use_sf["TileID"])
    bm_files_df = bm_files_df[bm_files_df["name"].str.contains(tile_ids_rx)]
    bm_files_df = bm_files_df.reset_index()

    #### Create directory for tif files
    shutil.rmtree(os.path.join(temp_dir, "tif_files_tmp"), ignore_errors=True)
    os.makedirs(os.path.join(temp_dir, "tif_files_tmp"))

    #### Download files and convert to rasters
    if (bm_files_df.shape[0] < grid_use_sf.shape[0]) and check_all_tiles_exist:
        logger.info(
            "Not all satellite imagery tiles for this location exist, so skipping. To ignore this error and process anyway, set check_all_tiles_exist = False"
        )
        raise ValueError(
            "Not all satellite imagery tiles for this location exist, so skipping. To ignore this error and process anyway, set check_all_tiles_exist = False"
        )

    else:
        tile_i = 1

        pbar = tqdm(bm_files_df["name"], leave=None)
        for file_name in pbar:
            n_tile = bm_files_df.shape[0]
            # Saves files in {temp_dir}/tif_files_tmp, which above is cleared and created
            download_raster(
                file_name,
                temp_dir,
                variable,
                bearer,
                quality_flag_rm,
                quiet,
                tile_i,
                n_tile,
            )
            tile_i = tile_i + 1

        #### Mosaic together
        # List of raster files to be mosaiced
        filepaths = glob.glob(os.path.join(temp_dir, "tif_files_tmp", "*.tif"))

        # Open the raster files
        src_files_to_mosaic = []
        for fp in filepaths:
            src = rasterio.open(fp)
            src_files_to_mosaic.append(src)

        # Merge the rasters
        mosaic, out_trans = merge(src_files_to_mosaic)

        # Delete folder of individual files
        # shutil.rmtree(os.path.join(temp_dir, 'tif_files_tmp'), ignore_errors=True)

        #### Create directory for mosaiced tif files
        # shutil.rmtree(os.path.join(temp_dir, 'tif_files_mosaic_tmp'), ignore_errors=True)
        os.makedirs(os.path.join(temp_dir, "tif_files_mosaic_tmp"), exist_ok=True)

        out_name = file_name[0:16] + ".tif"
        out_fp = os.path.join(temp_dir, "tif_files_mosaic_tmp", out_name)

        # Output as raster
        out_meta = src.meta.copy()

        out_meta.update(
            {
                "driver": "GTiff",
                "height": mosaic.shape[1],
                "width": mosaic.shape[2],
                "transform": out_trans,
                "crs": "+proj=longlat +datum=WGS84 +no_defs",
            }
        )

        with rasterio.open(out_fp, "w", **out_meta) as dest:
            dest.write(mosaic)

        #### Mask
        if True:
            dataset = rasterio.open(out_fp)
            mask_geometry = roi_sf.dissolve().geometry.values[
                0
            ]  # roi_sf.geometry.values[0]

            masked_image, mask_transform = mask(
                dataset,
                [mask_geometry],
                crop=True,
                nodata=np.nan,
                all_touched=True,
                pad=True,
            )

            # Copy the metadata from the original raster dataset
            masked_meta = dataset.meta.copy()
            masked_meta.update(
                {
                    "driver": "GTiff",
                    "height": masked_image.shape[1],
                    "width": masked_image.shape[2],
                    "transform": mask_transform,
                }
            )

            # Export the masked raster to a new file
            with rasterio.open(out_fp, "w", **masked_meta) as masked_dataset:
                masked_dataset.write(masked_image)

    return out_fp
