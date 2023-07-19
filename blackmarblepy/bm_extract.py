def bm_extract(roi_sf,
               product_id,
               date,
               bearer,
               variable = None,
               check_all_tiles_exist = True,
               output_location_type = "file",
               aggregation_fun = "mean",
               file_dir = None,
               file_prefix = "",
               file_skip_if_exists = True):

    variable = define_variable(variable, product_id)

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

                    poly_ntl_df = bm_extract_i(roi_sf, product_id, date_i, bearer, variable, aggregation_fun, check_all_tiles_exist)

                    #### Export data
                    poly_ntl_df.to_csv(out_path, index=False)      
                    print("File created: " + out_path)

                else:
                    print('"' + out_path + '" already exists; skipping.\n')
                    
            except:
                print("Skipping " + str(date_i) + " due to error. Likely data is not available.\n")

        r_out = None

    # File --------------------------------------------------------------------------
    if output_location_type == "memory":

        poly_ntl_df_list = [bm_extract_i(roi_sf, product_id, date_i, bearer, variable, aggregation_fun, check_all_tiles_exist) for date_i in date]
        poly_ntl_df = pd.concat(poly_ntl_df_list, ignore_index=True)

        r_out = poly_ntl_df

    return r_out