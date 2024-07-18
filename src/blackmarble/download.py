import asyncio
import datetime
import json
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import ClassVar, List

import backoff
import geopandas
import httpx
import nest_asyncio
import pandas as pd
from httpx import HTTPError
from pqdm.threads import pqdm
from pydantic import BaseModel
from tqdm.auto import tqdm
from .types import Product


def chunks(ls, n):
    """Yield successive n-sized chunks from list."""
    for i in range(0, len(ls), n):
        yield ls[i : i + n]


@backoff.on_exception(
    backoff.expo,
    HTTPError,
)
async def get_url(client, url, params):
    """

    Returns
    -------
    httpx.Response
        HTTP response
    """
    return await client.get(url, params=params)


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
    URL: ClassVar[str] = "https://ladsweb.modaps.eosdis.nasa.gov"

    def __init__(self, bearer: str, directory: Path):
        nest_asyncio.apply()
        super().__init__(bearer=bearer, directory=directory)

    async def get_manifest(
        self,
        gdf: geopandas.GeoDataFrame,
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

        # Create bounding box
        gdf = pd.concat([gdf, gdf.bounds], axis="columns").round(2)
        gdf["bbox"] = gdf.round(2).apply(
            lambda row: f"x{row.minx}y{row.miny},x{row.maxx}y{row.maxy}", axis=1
        )

        async with httpx.AsyncClient(verify=False) as client:
            tasks = []
            for chunk in chunks(date_range, 250):
                for _, row in gdf.iterrows():
                    url = f"{self.URL}/api/v1/files"
                    params = {
                        "product": product_id.value,
                        "collection": "5000",
                        "dateRanges": f"{min(chunk)}..{max(chunk)}",
                        "areaOfInterest": row["bbox"],
                    }
                    tasks.append(asyncio.ensure_future(get_url(client, url, params)))

            responses = [
                await f
                for f in tqdm(
                    asyncio.as_completed(tasks),
                    total=len(tasks),
                    desc="GETTING MANIFEST...",
                )
            ]

            rs = []
            for r in responses:
                try:
                    rs.append(pd.DataFrame(r.json()).T)
                except json.decoder.JSONDecodeError:
                    continue

            return pd.concat(rs)

    @backoff.on_exception(
        backoff.expo,
        HTTPError,
    )
    def _download_file(
        self,
        name: str,
        skip_if_exists: bool = True,
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
        url = f"{self.URL}{name}"
        name = name.split("/")[-1]

        if not (filename := Path(self.directory, name)).exists() or not skip_if_exists:
            with open(filename, "wb+") as f:
                with httpx.stream(
                    "GET",
                    url,
                    headers={"Authorization": f"Bearer {self.bearer}"},
                ) as response:
                    total = int(response.headers["Content-Length"])
                    with tqdm(
                        total=total,
                        unit="B",
                        unit_scale=True,
                        leave=None,
                    ) as pbar:
                        pbar.set_description(f"Downloading {name}...")
                        for chunk in response.iter_raw():
                            f.write(chunk)
                            pbar.update(len(chunk))
        return filename

    def download(
        self,
        gdf: geopandas.GeoDataFrame,
        product_id: Product,
        date_range: List[datetime.date],
        skip_if_exists: bool = True,
    ):
        """
        Downloads files asynchronously from NASA Black Marble archive.

        Parameters
        ----------
        gdf: geopandas.GeoDataFrame
             Region of Interest. Converted to EPSG:4326 and intersected with Black Mable tiles

        product: Product
            Nasa Black Marble Product Id (e.g, VNP46A1)

        date_range: List[datetime.date]
            Date range for which to download NASA Black Marble data.

        skip_if_exists: bool, default=True
            Whether to skip downloading data if file already exists

        Returns
        -------
        list: List[pathlib.Path]
            List of downloaded H5 filenames.
        """
        # Convert to EPSG:4326 and intersect with self.TILES
        gdf = geopandas.overlay(
            gdf.to_crs("EPSG:4326").dissolve(), self.TILES, how="intersection"
        )

        # Fetch manifest data asynchronously
        bm_files_df = asyncio.run(self.get_manifest(gdf, product_id, date_range))

        # Filter files to those intersecting with Black Marble tiles
        bm_files_df = bm_files_df[
            bm_files_df["name"].str.contains("|".join(gdf["TileID"]))
        ]

        # Prepare arguments for parallel download
        names = bm_files_df["fileURL"].tolist()
        args = [(name, skip_if_exists) for name in names]
        return pqdm(
            args,
            self._download_file,
            n_jobs=4,  # os.cpu_count(),
            argument_type="args",
            desc="Downloading...",
        )
