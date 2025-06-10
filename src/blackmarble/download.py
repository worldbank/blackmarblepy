import asyncio
import datetime
import json
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, List

import humanize

import geopandas
import h5py
import httpx
import nest_asyncio
import pandas as pd
from httpx import HTTPError
from pqdm.threads import pqdm
from pydantic import BaseModel
from tenacity import retry, retry_if_exception_type, wait_exponential
from tqdm.auto import tqdm

from . import TILES, logger
from .types import Product


class InvalidHDF5File(Exception):
    """Raised when the downloaded HDF5 file is invalid or corrupted."""

    pass


def chunks(ls, n):
    """Yield successive n-sized chunks from list."""
    for i in range(0, len(ls), n):
        yield ls[i : i + n]


@retry(
    wait=wait_exponential(multiplier=1, min=1, max=60),
    retry=retry_if_exception_type(HTTPError),
    reraise=True,
)
async def get_url(client: httpx.AsyncClient, url: str, params: dict) -> httpx.Response:
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

                    from urllib.parse import urlencode

                    # Encode parameters and build full URL
                    query_string = urlencode(params)
                    full_url = f"{url}?{query_string}"

                    print(full_url)
                    tasks.append(asyncio.ensure_future(get_url(client, url, params)))

            responses = [
                await f
                for f in tqdm(
                    asyncio.as_completed(tasks),
                    total=len(tasks),
                    desc="OBTAINING MANIFEST...",
                )
            ]

            rs = []
            for r in responses:
                r.raise_for_status()
                try:
                    rs.append(pd.DataFrame(r.json()).T)
                except json.decoder.JSONDecodeError:
                    continue

            return pd.concat(rs)

    @retry(
        wait=wait_exponential(multiplier=1, min=1, max=60),
        retry=retry_if_exception_type((HTTPError, InvalidHDF5File)),
        reraise=True,
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
                    follow_redirects=True,
                    headers={"Authorization": f"Bearer {self.bearer}"},
                ) as response:
                    response.raise_for_status()
                    if "text/html" in response.headers.get("Content-Type"):
                        raise ValueError(
                            "Received an HTML response, which likely indicates an invalid or expired NASA Earthdata token.\n"
                            "Please visit https://urs.earthdata.nasa.gov/profile to verify that your token is valid and not expired."
                        )
                    else:
                        total = int(response.headers.get("Content-Length", 0))
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
        else:
            logger.info(f"File already exists, reusing: {filename}")

        # Validate the HDF5 file after writing
        try:
            with h5py.File(filename, "r"):
                pass
        except Exception as e:
            filename.unlink(missing_ok=True)
            raise InvalidHDF5File(f"HDF5 validation failed for {filename}: {e}")

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
        # Convert to EPSG:4326 and intersect with TILES
        gdf = geopandas.overlay(
            gdf.to_crs("EPSG:4326").dissolve(), TILES, how="intersection"
        )

        # Fetch manifest data asynchronously
        bm_files_df = asyncio.run(self.get_manifest(gdf, product_id, date_range))

        # Filter files to those intersecting with Black Marble tiles
        bm_files_df = bm_files_df[
            bm_files_df["name"].str.contains("|".join(gdf["TileID"]))
        ]

        # Calculate total size in a human-readable format
        total_size = humanize.naturalsize(bm_files_df["size"].astype(int).sum())

        # Prepare arguments for parallel download
        names = bm_files_df["fileURL"].tolist()
        download_args = [(name, skip_if_exists) for name in names]
        results = pqdm(
            download_args,
            self._download_file,
            n_jobs=4,
            argument_type="args",
            desc=f"Downloading ({total_size})...",
            unit="file",
        )

        for result in results:
            if isinstance(result, Exception):
                raise result

        return results
