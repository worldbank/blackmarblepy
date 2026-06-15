import asyncio
import datetime
import json
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, List
from urllib.parse import urlencode

import geopandas
import h5py
import httpx
import humanize
import nest_asyncio
import pandas as pd
from httpx import HTTPError
from pqdm.threads import pqdm
from pydantic import BaseModel
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
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
    token: str
        NASA EarthData bearer token

    directory: Path
        Local directory to which download

    collection: str
        NASA Black Marble collection version ('5000' for collection-1, '5200' for collection-2)
    """

    token: str
    directory: Path
    collection: str = "5200"  # Default to collection-2
    URL: ClassVar[str] = "https://ladsweb.modaps.eosdis.nasa.gov"

    def __init__(self, token: str, directory: Path, collection: str = "5200"):
        nest_asyncio.apply()
        super().__init__(token=token, directory=directory, collection=collection)

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
        lambda row: f"[BBOX]W{row.minx} N{row.maxy} E{row.maxx} S{row.miny}",
        axis=1,
    )
        async with httpx.AsyncClient(verify=False) as client:
            manifests = []

            for chunk in chunks(date_range, 250):
                for _, row in gdf.iterrows():
                    url = f"{self.URL}/api/v2/content/details"

                    start_date = min(chunk).isoformat()
                    end_date = max(chunk).isoformat()

                    base_params = {
                        "products": product_id.value,
                        "archiveSet": self.collection,
                        "temporalRanges": f"{start_date}..{end_date}",
                        "regions": row["bbox"],
                        "page": 1,
                    }

                    full_url = f"{url}?{urlencode(base_params)}"
                    logger.debug(full_url)

                    first_response = await get_url(client, url, base_params)
                    first_response.raise_for_status()
                    first_data = first_response.json()

                    manifests.append(pd.DataFrame(first_data.get("content", [])))

                    total_pages = first_data.get("n_pages", 1)
                    for page in range(2, total_pages + 1):
                        page_params = {**base_params, "page": page}
                        response = await get_url(client, url, page_params)
                        response.raise_for_status()
                        page_data = response.json()
                        manifests.append(pd.DataFrame(page_data.get("content", [])))

            manifest = pd.concat(manifests, ignore_index=True)
            #print(manifest.columns)
            manifest["TileID"] = (
                manifest["name"].apply(lambda x: x.split(".")[2]).astype(str)
            )
            manifest["date"] = pd.to_datetime(manifest["start"]).dt.date

            return manifest.drop_duplicates(subset="name")

    @retry(
        wait=wait_exponential(multiplier=1, min=1, max=60),
        stop = stop_after_attempt(5),
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
        # url = f"{self.URL}{name}"
        # print(url)
        # name = name.split("/")[-1]
        url = str(name).strip()
        if not url.startswith("http"):
            url = f"{self.URL}{url}"

        name = Path(url).name

        filename = Path(self.directory, name)
        tmpfile = filename.with_suffix(filename.suffix + ".part")

        if filename.exists() and skip_if_exists:
            logger.info(f"File already exists, reusing: {filename}")
            return filename

        timeout = httpx.Timeout(connect=30.0, read=120.0, write=120.0, pool=30.0)
        tmpfile.unlink(missing_ok=True)

        try:
            with httpx.stream(
                "GET",
                url,
                follow_redirects=True,
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=timeout,
            ) as response:
                response.raise_for_status()

                if "text/html" in response.headers.get("Content-Type", ""):
                    raise ValueError(
                        "Received an HTML response, which likely indicates an invalid or expired NASA Earthdata token.\n"
                        "Please visit https://urs.earthdata.nasa.gov/profile to verify that your token is valid and not expired."
                    )

                total = int(response.headers.get("Content-Length", 0))
                written = 0

                with open(tmpfile, "wb") as f:
                    with tqdm(
                        total=total,
                        unit="B",
                        unit_scale=True,
                        leave=None,
                    ) as pbar:
                        pbar.set_description(f"Downloading {name}...")
                        for chunk in response.iter_bytes():
                            if not chunk:
                                continue
                            f.write(chunk)
                            written += len(chunk)
                            pbar.update(len(chunk))

            if total and written != total:
                tmpfile.unlink(missing_ok=True)
                raise InvalidHDF5File(
                    f"Incomplete download for {filename.name}: expected {total} bytes, got {written}"
                )

            try:
                with h5py.File(tmpfile, "r"):
                    pass
            except Exception as e:
                tmpfile.unlink(missing_ok=True)
                raise InvalidHDF5File(f"HDF5 validation failed for {tmpfile}: {e}")

            tmpfile.replace(filename)
            return filename

        except Exception:
            tmpfile.unlink(missing_ok=True)
            raise
       

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
        manifest = asyncio.run(self.get_manifest(gdf, product_id, date_range))

        # Create a full cross-join of tiles and dates
        all_combinations = gdf.merge(
            pd.DataFrame(date_range, columns=["date"]), how="cross"
        )

        #print(sorted(manifest["TileID"].unique()))
        #print(sorted(all_combinations["TileID"].unique()))

        # print(all_combinations.head())
        # print(manifest.head())
        # Merge with manifest to identify missing files
        merged = all_combinations.merge(
            manifest, on=["TileID", "date"], how="left", indicator=True
        )

        # Find missing tiles (those present in all_combinations but not in manifest)
        missing_tiles = merged[merged["_merge"] == "left_only"]
        if not missing_tiles.empty:
            for idx, row in missing_tiles.iterrows():
                logger.warning(
                    f"Tile '{row['TileID']}' for date '{row['date']}' could not be found in the manifest."
                )
            msg = (
                f"The manifest retrieved from NASA DAAC ({self.URL}) indicates that {len(missing_tiles)} required files could not found.\n"
                "Some files may be missing due to recent data removals, maintenance periods or changes in data availability.\n"
                "Please try adjusting the requested date range, check data availability again or report this issue if the problem persists."
            )
            
            raise ValueError(msg)

        # Filter files to those intersecting with Black Marble tiles
        matched = manifest[manifest["name"].str.contains("|".join(gdf["TileID"]))]

        # Prepare arguments for parallel download
        names = matched["downloadsLink"].tolist()
        #print(names)
        download_args = [(name, skip_if_exists) for name in names]
        total_size = humanize.naturalsize(matched["size"].astype(int).sum())

        results = pqdm(
            download_args,
            self._download_file,
            n_jobs=1,
            argument_type="args",
            desc=f"Downloading ({total_size})...",
            unit="file",
        )

        for result in results:
            if isinstance(result, Exception):
                raise result

        return results
