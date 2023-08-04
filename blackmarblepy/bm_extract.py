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

def bm_extract(roi_sf,
               product_id,
               date,
               bearer,
               variable = None,
               check_all_tiles_exist = True,
               output_location_type = "memory",
               aggregation_fun = "mean",
               file_dir = None,
               file_prefix = "",
               file_skip_if_exists = True,
               quiet = False):

    #### Make directory to put temporary files into
    temp_main_dir = tempfile.gettempdir()
    
    current_time_millis = int(round(time.time() * 1000))
    temp_dir = os.path.join(temp_main_dir, "bm_raster_temp_" + str(current_time_millis))
    
    os.makedirs(temp_dir)
    
    #### Define NTL Variable
    variable = define_variable(variable, product_id)

    #### Ensure date is a list of strings
    if type(date) is not list:
        date = [date]
                
    date = [str(item) for item in date]

    if file_dir is None:
        file_dir = os.getcwd()

    raster_path_list = []

    # File --------------------------------------------------------------------------
    if output_location_type == "file":
    
        for date_i in date:
            
            try:
                date_name_i = define_date_name(date_i, product_id)

                out_name = file_prefix + product_id + "_" + date_name_i + ".csv"
                out_path = os.path.join(file_dir, out_name)

                # Only make .tif if raster doesn't already exist
                if (not file_skip_if_exists) | (not os.path.exists(out_path)):

                    poly_ntl_df = bm_extract_i(roi_sf, product_id, 
                                               date_i, bearer, variable, 
                                               aggregation_fun, check_all_tiles_exist, quiet, temp_dir)

                    #### Export data
                    poly_ntl_df.to_csv(out_path, index=False)

                    if quiet == False:      
                        print("File created: " + out_path)

                else:
                    if quiet == False:
                        print('"' + out_path + '" already exists; skipping.\n')
                    
            except:
                # Delete temp files used to make raster
                shutil.rmtree(temp_dir, ignore_errors=True)
            
                if quiet == False:
                    print("Skipping " + str(date_i) + " due to error. Likely data is not available.\n")

        r_out = None

    # File --------------------------------------------------------------------------
    if output_location_type == "memory":

        poly_ntl_df_list = [bm_extract_i(roi_sf, product_id, 
                                         date_i, bearer, variable, aggregation_fun, 
                                         check_all_tiles_exist, quiet, temp_dir) for date_i in date]
        poly_ntl_df = pd.concat(poly_ntl_df_list, ignore_index=True)

        r_out = poly_ntl_df

    # Delete temp files used to make raster
    shutil.rmtree(temp_dir, ignore_errors=True)

    return r_out