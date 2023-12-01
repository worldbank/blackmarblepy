import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

import httpx
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from .utils import file_to_raster

# example constant variable
NAME = "blackmarble"


class DownloadProgress(Progress):
    def get_renderables(self):
        for task in self.tasks:
            if task.fields.get("progress_type") == "summary":
                self.columns = (
                    TextColumn(
                        "[blue]{task.description}[/blue][magenta]{task.completed} of {task.total}...",
                        justify="right",
                    ),
                    BarColumn(bar_width=None),
                    TimeRemainingColumn(),
                    TimeElapsedColumn(),
                )
            if task.fields.get("progress_type") == "download":
                self.columns = (
                    TextColumn("[blue]{task.description}", justify="left"),
                    DownloadColumn(),
                    BarColumn(bar_width=None),
                    "[progress.percentage]{task.percentage:>3.0f}%",
                )
            yield self.make_tasks_table([task])


@dataclass
class BlackMarbleDownloader:
    """NASA Black Marble Downloader

    Attributes
    ----------
    bearer: str
        NASA bearer
    """

    bearer: Optional[str]
    cache_dir: Optional[Union[str, Path]] = None

    def download_raster(
        self,
        file_name,
        temp_dir,
        variable,
        quality_flag_rm,
        progress=DownloadProgress(),
    ):
        # Path
        year = file_name[9:13]
        day = file_name[13:16]
        product_id = file_name[0:7]

        f = os.path.join(temp_dir, file_name)

        url = f"https://ladsweb.modaps.eosdis.nasa.gov/archive/allData/5000/{product_id}/{year}/{day}/{file_name}"
        headers = {"Authorization": f"Bearer {self.bearer}"}
        download_path = os.path.join(temp_dir, file_name)

        with httpx.stream("GET", url, headers=headers) as response:
            total = int(response.headers["Content-Length"])
            with progress:
                with open(download_path, "wb") as download_file:
                    task = progress.add_task(
                        "[red]Downloading...[/red]",
                        total=total,
                        progress_type="download",
                    )
                    for chunk in response.iter_raw():
                        download_file.write(chunk)
                        progress.update(
                            task,
                            advance=len(chunk),
                            description=f"[yellow]Downloading {file_name}...[/yellow]",
                        )

        file_name_tif = re.sub(".h5", ".tif", file_name)

        file_to_raster(
            f,
            variable,
            os.path.join(temp_dir, "tif_files_tmp", file_name_tif),
            quality_flag_rm,
        )

        progress.update(
            task,
            description=f"[green]Downloaded {file_name}[/green]",
        )
        return None
