import pandas as pd
import numpy as np
import requests
import time
import os
import re
import warnings
import datetime 
import tempfile
import subprocess
import glob
import shutil
from itertools import product
import geopandas as gpd
from rasterstats import zonal_stats
import h5py
import rasterio
from rasterio.mask import mask
from rasterio.merge import merge
from rasterio.plot import show
from rasterio.merge import merge
from rasterio.transform import from_origin

def cross_df(data_dict):
    keys = data_dict.keys()
    values = data_dict.values()
    crossed_values = list(product(*values))
    df = pd.DataFrame(crossed_values, columns=keys)
    return df

def month_start_day_to_month(x):
    """
    Converts month start day to month.

    Args:
    x: Month start day.

    Returns:
    Month.
    """

    month = None

    month_dict = {
        "001": "01",
        "032": "02",
        "060": "03",
        "061": "03",
        "091": "04",
        "092": "04",
        "121": "05",
        "122": "05",
        "152": "06",
        "153": "06",
        "182": "07",
        "183": "07",
        "213": "08",
        "214": "08",
        "244": "09",
        "245": "09",
        "274": "10",
        "275": "10",
        "305": "11",
        "306": "11",
        "335": "12",
        "336": "12",
        }

    month = month_dict.get(x)

    return month

def pad2(x):
    """
    Pads a number with zeros to make it 2 digits long.

    Args:
    x: Number.

    Returns:
    Padded number.
    """

    out = None

    if len(str(x)) == 1:
        out = "0" + str(x)
    elif len(str(x)) == 2:
        out = str(x)

    return out

def pad3(x):
    """
    Pads a number with zeros to make it 3 digits long.

    Args:
    x: Number.

    Returns:
    Padded number.
    """

    out = None

    if len(str(x)) == 1:
        out = "00" + str(x)
    elif len(str(x)) == 2:
        out = "0" + str(x)
    elif len(str(x)) == 3:
        out = str(x)

    return out


def file_to_raster(f, variable, output_path, quality_flag_rm):
    
    h5_data = h5py.File(f, "r")
    
    # Daily --------------------------------------------------
    if ("VNP46A1" in f) or ("VNP46A2" in f):
        
        #### Check
        h5_names = list(h5_data["HDFEOS"]["GRIDS"]["VNP_Grid_DNB"]["Data Fields"].keys())
        
        if variable not in h5_names:
            warnings.warn("'" + variable + "'" + " not a valid variable option. Valid options include:\n" + ',\n '.join(h5_names), UserWarning)
        
        tile_i = re.findall(r'h\d{2}v\d{2}', f)[0]
        
        bm_tiles_sf = gpd.read_file("https://raw.githubusercontent.com/ramarty/blackmarbler/main/data/blackmarbletiles.geojson")
        grid_i_sf = bm_tiles_sf[bm_tiles_sf["TileID"] == tile_i]
                
        xMin = float(grid_i_sf.geometry.bounds.minx)
        yMin = float(grid_i_sf.geometry.bounds.miny)
        xMax = float(grid_i_sf.geometry.bounds.maxx)
        yMax = float(grid_i_sf.geometry.bounds.maxy)
        
        out = h5_data["HDFEOS"]["GRIDS"]["VNP_Grid_DNB"]["Data Fields"][variable]
        qf  = h5_data["HDFEOS"]["GRIDS"]["VNP_Grid_DNB"]["Data Fields"]["Mandatory_Quality_Flag"]

        out = out[:]
        qf  = qf[:]
        
        if len(quality_flag_rm) > 0:
            
            for val in quality_flag_rm:
                out = np.where(qf == val, np.nan, out)
      
    # Monthly / Annual --------------------------------------------------
    else:
        
        h5_names = list(h5_data["HDFEOS"]["GRIDS"]["VIIRS_Grid_DNB_2d"]["Data Fields"].keys())
        
        if variable not in h5_names:
            warnings.warn("'" + variable + "'" + " not a valid variable option. Valid options include:\n" + ',\n '.join(h5_names), UserWarning)
            
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

                qf = h5_data["HDFEOS"]["GRIDS"]["VIIRS_Grid_DNB_2d"]["Data Fields"][variable + "_Quality"]
                qf  = qf[:]
                
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
    #data = out[:]
    data = out
    #data = np.where(data == 65535, np.nan, data)

    # Define the pixel size and number of rows and columns
    pixel_size = 1  # Size of each pixel in the output raster
    rows, cols = data.shape

    # Define the spatial extent (bounding box) of the raster
    left, bottom, right, top = xMin, yMin, xMax, yMax

    psize_x = (xMax-xMin)/cols
    psize_y = (yMax-yMin)/rows

    # Create the raster file    
    with rasterio.open(output_path, 'w', driver='GTiff', height=rows, width=cols,
                       count=1, dtype=data.dtype, crs='EPSG:4326',
                       transform=from_origin(left, top, psize_x, psize_y)) as dst:
        dst.write(data, 1)
        
    return None 

def read_bm_csv(year, day, product_id):

    url = f"https://ladsweb.modaps.eosdis.nasa.gov/archive/allData/5000/{product_id}/{year}/{day}.csv"
    
    try:
        df = pd.read_csv(url)
        df['year'] = year
        df['day'] = day
        return df
    except Exception as e:
        #print(f"Error with year: {year}; day: {day}")
        return pd.DataFrame()
    
    time.sleep(0.1)

def create_dataset_name_df(product_id, all=True, years=None, months=None, days=None):

    #### Prep inputs
    if type(years) is not list:
        years = [years]
        
    if type(months) is not list:
        months = [months]
        
    if type(days) is not list:
        days = [days]

    #### Prep dates
    if product_id in ["VNP46A1", "VNP46A2"]:
        months = None
    if product_id in ["VNP46A3"]:
        days = None
    if product_id in ["VNP46A4"]:
        days = None
        months = None

    #### Determine end year
    year_end = int(datetime.date.today().strftime("%Y"))

    #### Make parameter dataframe
    if product_id in ["VNP46A1", "VNP46A2"]:
                
        param_df = cross_df({'year': range(2012, year_end + 1),
                             'day': [pad3(item) for item in range(1, 366)]})
        
        
        #param_df = cross_df(range(2012, year_end + 1),
        #           [pad3(item) for item in range(1, 366)])
            
        #param_df.rename(columns={0: 'year'}, inplace=True)
        #param_df.rename(columns={1: 'day'}, inplace=True)
        
    elif product_id == "VNP46A3":

        #param_df = cross_df(range(2012, year_end + 1), 
        #                    ["001", "032", "061", "092", "122", "153", "183", "214", "245", "275", "306", "336",
        #                     "060", "091", "121", "152", "182", "213", "244", "274", "305", "335"])
        
        #param_df.rename(columns={0: 'year'}, inplace=True)
        #param_df.rename(columns={1: 'day'}, inplace=True)
        
        param_df = cross_df({'year': range(2012, year_end + 1),
                            'day': ["001", "032", "061", "092", "122", "153", "183", "214", "245", "275", "306", "336",
                                    "060", "091", "121", "152", "182", "213", "244", "274", "305", "335"]})

    elif product_id == "VNP46A4":
        param_df = pd.DataFrame({
          "year": range(2012, year_end + 1),
          "day": "001"
        })

    #### Add month if daily or monthly data
    if product_id in ["VNP46A1", "VNP46A2", "VNP46A3"]:
        param_df["month"] = [month_start_day_to_month(item) for item in param_df["day"]]
        
    #### Subset time period
    ## Year
    if years is not None:
        years = [int(item) for item in years]
        param_df = param_df.loc[param_df["year"].isin(years)]

    ## Month
    if product_id in ["VNP46A3"]: # ["VNP46A1", "VNP46A2", "VNP46A3"]
        if months is not None:
            months = [pad2(str(item)) for item in months]
            param_df = param_df.loc[param_df["month"].isin(months)]

    if days is not None:
        days = [pad3(str(item)) for item in days]
        param_df = param_df.loc[param_df["day"].isin(days)]

    #### Create data
    files_df = pd.concat([read_bm_csv(row['year'], row['day'], product_id) for _, row in param_df.iterrows()], ignore_index=True)

    return files_df

def download_raster(file_name, temp_dir, variable, bearer, quality_flag_rm, quiet, tile_i, n_tile):
    
    # Path
    year = file_name[9:13]
    day = file_name[13:16]
    product_id = file_name[0:7]

    f = os.path.join(temp_dir, product_id, year, day, file_name)

    # Download
    if quiet == False:
        print("Downloading " + str(tile_i) + "/" + str(n_tile) + ": " + file_name)
        
    wget_command = f"/usr/local/bin/wget -e robots=off -m -np .html,.tmp -nH --cut-dirs=3 'https://ladsweb.modaps.eosdis.nasa.gov/archive/allData/5000/{product_id}/{year}/{day}/{file_name}' --header 'Authorization: Bearer {bearer}' -P {temp_dir}/" 
    #print(wget_command)
    #subprocess.run(wget_command, shell=True)
    subprocess.run(wget_command, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Convert to raster
    file_name_tif = re.sub(".h5", ".tif", file_name)

    file_to_raster(f, variable, os.path.join(temp_dir, 'tif_files_tmp', file_name_tif), quality_flag_rm)
    
    #shutil.rmtree(os.path.join(temp_dir, product_id), ignore_errors=True)

    #os.remove(os.path.join(temp_dir, file_name)) # Delete .h5 file
    
    return None

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

def bm_extract_i(roi_sf, 
                 product_id, 
                 date_i, 
                 bearer, 
                 variable,
                 quality_flag_rm,
                 aggregation_fun,
                 check_all_tiles_exist,
                 quiet,
                 temp_dir):
    
    try:
        #### Extract data
        raster_path_i = bm_raster_i(roi_sf, product_id, date_i, 
                                    bearer, variable, quality_flag_rm, check_all_tiles_exist, quiet, temp_dir)

        with rasterio.open(raster_path_i) as src:
            raster_data = src.read(1)

        # nodata=src.nodata
        ntl_data = zonal_stats(roi_sf, raster_data, 
                               affine=src.transform, nodata=np.nan, masked=False, stats = aggregation_fun)

        ntl_data_df = pd.DataFrame(ntl_data)
        ntl_data_df = ntl_data_df.add_prefix('ntl_')

        roi_df = pd.DataFrame(roi_sf.drop('geometry', axis=1))
        poly_ntl_df = pd.concat([roi_df, ntl_data_df], axis=1)
        poly_ntl_df['date'] = date_i 
        
    except:
        print("Skipping " + str(date_i) + " due to error. Data may not be available.\n")
        poly_ntl_df = pd.DataFrame()
    
    return poly_ntl_df

def bm_raster_i(roi_sf, 
                product_id, 
                date, 
                bearer, 
                variable, 
                quality_flag_rm,
                check_all_tiles_exist,
                quiet,
                temp_dir):
    
    #### Prep files to download
    
    # Black marble grid: TODO: Add to python repo
    bm_tiles_sf = gpd.read_file("https://raw.githubusercontent.com/ramarty/blackmarbler/main/data/blackmarbletiles.geojson")

    # Prep dates            
    if product_id == "VNP46A3":
        if len(date) <= 7:
            date = date + "-01"

    if product_id == "VNP46A4":
        if len(date) in [4, 10]:
            date = date + "-01-01"

    date = datetime.datetime.strptime(date, "%Y-%m-%d").date()

    # Grab tile dataframe
    year = date.year
    month = date.month
    day = date.timetuple().tm_yday
    
    bm_files_df = create_dataset_name_df(product_id=product_id, all=True, years=year, months=month, days=day)
    
    # Intersecting tiles
    bm_tiles_sf = bm_tiles_sf[~bm_tiles_sf["TileID"].str.contains("h00")]
    bm_tiles_sf = bm_tiles_sf[~bm_tiles_sf["TileID"].str.contains("v00")]

    grid_use_sf = gpd.overlay(bm_tiles_sf, roi_sf.dissolve(), how='intersection')

    # Make raster
    tile_ids_rx = "|".join(grid_use_sf["TileID"])
    bm_files_df = bm_files_df[bm_files_df["name"].str.contains(tile_ids_rx)]
    bm_files_df = bm_files_df.reset_index()
    
    #temp_dir = tempfile.gettempdir()

    #shutil.rmtree(os.path.join(temp_dir, product_id), ignore_errors=True)

    #### Create directory for tif files
    shutil.rmtree(os.path.join(temp_dir, 'tif_files_tmp'), ignore_errors=True)
    os.makedirs(os.path.join(temp_dir, 'tif_files_tmp'))
    
    #### Download files and convert to rasters    
    if (bm_files_df.shape[0] < grid_use_sf.shape[0]) and check_all_tiles_exist:
        print("Not all satellite imagery tiles for this location exist, so skipping. To ignore this error and process anyway, set check_all_tiles_exist = False")
        raise ValueError("Not all satellite imagery tiles for this location exist, so skipping. To ignore this error and process anyway, set check_all_tiles_exist = False")
                
    else:
    
        tile_i = 1
        for file_name in bm_files_df['name']:
            
            n_tile = bm_files_df.shape[0] 

            # Saves files in {temp_dir}/tif_files_tmp, which above is cleared and created
            download_raster(file_name, temp_dir, variable, bearer, quality_flag_rm, quiet, tile_i, n_tile)

            tile_i = tile_i + 1
            
        #### Mosaic together
        # List of raster files to be mosaiced
        filepaths = glob.glob(os.path.join(temp_dir, 'tif_files_tmp', "*.tif"))

        # Open the raster files
        src_files_to_mosaic = []
        for fp in filepaths:
            src = rasterio.open(fp)
            src_files_to_mosaic.append(src)

        # Merge the rasters
        mosaic, out_trans = merge(src_files_to_mosaic)

        # Delete folder of individual files
        #shutil.rmtree(os.path.join(temp_dir, 'tif_files_tmp'), ignore_errors=True)

        #### Create directory for mosaiced tif files
        #shutil.rmtree(os.path.join(temp_dir, 'tif_files_mosaic_tmp'), ignore_errors=True)
        os.makedirs(os.path.join(temp_dir, 'tif_files_mosaic_tmp'), exist_ok = True)

        out_name = file_name[0:16] + '.tif'
        out_fp = os.path.join(temp_dir, 'tif_files_mosaic_tmp', out_name)

        # Output as raster
        out_meta = src.meta.copy()

        out_meta.update({"driver": "GTiff",
                         "height": mosaic.shape[1],
                         "width": mosaic.shape[2],
                         "transform": out_trans,
                         "crs": "+proj=longlat +datum=WGS84 +no_defs"
                        }
                       )

        with rasterio.open(out_fp, "w", **out_meta) as dest:
            dest.write(mosaic)

        #### Mask
        if True:
            dataset = rasterio.open(out_fp)
            mask_geometry = roi_sf.dissolve().geometry.values[0] # roi_sf.geometry.values[0]

            masked_image, mask_transform = mask(dataset, [mask_geometry], crop=True, nodata = np.nan, all_touched = True, pad = True)

            # Copy the metadata from the original raster dataset
            masked_meta = dataset.meta.copy()
            masked_meta.update({
                "driver": "GTiff",
                "height": masked_image.shape[1],
                "width": masked_image.shape[2],
                "transform": mask_transform
            })

            # Export the masked raster to a new file
            with rasterio.open(out_fp, "w", **masked_meta) as masked_dataset:
                masked_dataset.write(masked_image)
                
    return out_fp