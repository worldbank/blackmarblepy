import pandas as pd
import numpy as np
import requests
import time
import os
import re
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

from blackmarblepy.utils import (cross_df,
                                month_start_day_to_month,
                                pad2,
                                pad3,
                                file_to_raster,
                                read_bm_csv,
                                create_dataset_name_df,
                                download_raster,
                                define_variable,
                                define_date_name,
                                bm_extract_i,
                                bm_raster_i)

def bm_raster(roi_sf, 
              product_id, 
              date, 
              bearer, 
              variable=None, 
              check_all_tiles_exist = True,
              output_location_type="memory",
              file_dir=None, 
              file_prefix="", 
              file_skip_if_exists=True,
              quiet = False):
    
    variable = define_variable(variable, product_id)
    
    if type(date) is not list:
        date = [date]
        
    date = [str(item) for item in date]
    
    if file_dir is None:
        file_dir = os.getcwd()

    raster_path_list = []    
    for date_i in date:
        
        date_name_i = define_date_name(date_i, product_id)

        try: 
            
            # File --------------------------------------------------------------------------
            if output_location_type == "file":
                out_name = file_prefix + product_id + "_" + date_name_i + ".tif"
                out_path = os.path.join(file_dir, out_name)

                # Only make .tif if raster doesn't already exist
                if (not file_skip_if_exists) | (not os.path.exists(out_path)):

                    raster_path_i = bm_raster_i(roi_sf, product_id, date_i, bearer, variable, check_all_tiles_exist, quiet)
                    shutil.move(raster_path_i, out_path) # Move from tmp to main folder
                    
                    if quiet == False:
                        print("File created: " + out_path)

                else:
                    if quiet == False:
                        print('"' + out_path + '" already exists; skipping.\n')

                r_out = None

            # Memory --------------------------------------------------------------------------
            if output_location_type == "memory":

                raster_path_i = bm_raster_i(roi_sf, product_id, date_i, bearer, variable, check_all_tiles_exist, quiet)
                raster_path_list.append(raster_path_i) 

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
                temp_dir = tempfile.gettempdir()

                timestamp = str(int(time.time()))
                tmp_raster_file_name = product_id + "_" + date[0].replace("-", "_") + "_" + timestamp + ".tif"

                with rasterio.open(os.path.join(temp_dir, tmp_raster_file_name), 'w', driver='GTiff', width=width, height=height,
                                   count=count, dtype=dtype, crs=crs, transform=transform) as dst:
                    for i in range(count):
                        dst.write(data[i], i+1) 


                r_out = rasterio.open(os.path.join(temp_dir, tmp_raster_file_name))
                
        except:
            if quiet == False:
                print("Skipping " + str(date_i) + " due to error. Data may not be available.\n")
            r_out = None

    return r_out





