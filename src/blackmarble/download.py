import datetime
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import ClassVar, List

import backoff
import dask.dataframe as dd
import geopandas
import httpx
import pandas as pd
from httpx import HTTPError
from pqdm.threads import pqdm
from pydantic import BaseModel
from tqdm.auto import tqdm

from .types import Product


@dataclass
class BlackMarbleDownloader(BaseModel):
    """A downloader to retrieve `NASA Black Marble <https://blackmarble.gsfc.nasa.gov>`_ data.

    Attributes
    ----------
    bearer: str
        NASA EarthData bearer token

    directory: Path
        Local directory to which download
    """

    bearer: str
    directory: Path

    TILES: ClassVar[geopandas.GeoDataFrame] = geopandas.read_file(
        files("blackmarble.data").joinpath("blackmarbletiles.geojson")
    )
    URL: ClassVar[str] = "https://ladsweb.modaps.eosdis.nasa.gov/archive/allData/5000"

    def __init__(self, bearer: str, directory: Path):
        super().__init__(bearer=bearer, directory=directory)

    def _retrieve_manifest(
        self,
        product_id: Product,
        date_range: datetime.date | List[datetime.date],
    ) -> pd.DataFrame:
        """Retrieve NASA Black Marble data manifest. i.d., download links.

        Parameters
        ----------
        product_id: Product
            NASA Black Marble product suite (VNP46) identifier

        date_range: datetime.date | List[datetime.date]
            Date range for which to retrieve NASA Black Marble data manifest

        Returns
        -------
        pandas.DataFrame
            NASA Black Marble data manifest (i.e., downloads links)
        """
        if isinstance(date_range, datetime.date):
            date_range = [date_range]
        if isinstance(product_id, str):
            product_id = Product(product_id)

        urlpaths = set()
        for date in date_range:
            match product_id:
                case Product.VNP46A3:  # if VNP46A3 then first day of the month
                    tm_yday = date.replace(day=1).timetuple().tm_yday
                case Product.VNP46A4:  # if VNP46A4 then first day of the year
                    tm_yday = date.replace(month=1, day=1).timetuple().tm_yday
                case _:
                    tm_yday = date.timetuple().tm_yday

            urlpath = f"{self.URL}/{product_id.value}/{date.year}/{tm_yday}.csv"
            urlpaths.add(urlpath)

        return dd.read_csv(list(urlpaths)).compute()

    @backoff.on_exception(
        backoff.expo,
        HTTPError,
    )
    def _download_file(
        self,
        name: str,
    ):
        """Download NASA Black Marble file

        Parameters
        ----------
        names: str
             NASA Black Marble filename

        Returns
        -------
        filename: pathlib.Path
            Filename of downloaded data file
        """
        year = name[9:13]
        day = name[13:16]
        product_id = name[0:7]

        url = f"{self.URL}/{product_id}/{year}/{day}/{name}"
        headers = {"Authorization": f"Bearer {self.bearer}"}
        filename = Path(self.directory, name)

        with open(filename, "wb+") as f:
            with httpx.stream(
                "GET",
                url,
                headers=headers,
            ) as response:
                total = int(response.headers["Content-Length"])
                with tqdm(
                    total=total,
                    unit="B",
                    unit_scale=True,
                    leave=None,
                ) as pbar:
                    pbar.set_description(f"Retrieving {name}...")
                    for chunk in response.iter_raw():
                        f.write(chunk)
                        pbar.update(len(chunk))

                return filename

    def _download(self, names: List[str], n_jobs: int = 16):
        """Download (in parallel) from NASA Black Marble archive

        Parameters
        ----------
        names: List[str]
            List of names for which to download from the NASA Black Marble archive
        """
        args = [(name,) for name in names]

        return pqdm(
            args,
            self._download_file,
            n_jobs=n_jobs,
            argument_type="args",
            desc="Downloading...",
        )

    def download(
        self,
        gdf: geopandas.GeoDataFrame,
        product_id: Product,
        date_range: datetime.date | List[datetime.date],
        skip_if_exists: bool = True,
    ):
        """Download (in parallel) from NASA Black Marble archive

        Parameters
        ----------
        gdf: geopandas.GeoDataFrame
            Region of Interest

        product: Product
            Nasa Black Marble Product Id (e.g, VNP46A1)

        skip_if_exists: bool, default=True
            Whether to skip downloading or extracting data if the data file for that date already exists
        """
        gdf = geopandas.overlay(
            gdf.to_crs("EPSG:4326").dissolve(), self.TILES, how="intersection"
        )
        bm_files_df = self._retrieve_manifest(product_id, date_range)
        bm_files_df = bm_files_df[
            bm_files_df["name"].str.contains("|".join(gdf["TileID"]))
        ]
        names = bm_files_df["name"].tolist()

        return self._download(names)
