import logging
from pathlib import Path

__version__ = (Path(__file__).parent / "VERSION").read_text().strip()

logging.basicConfig(
    format="[%(asctime)s - %(name)s:%(lineno)d - %(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger: logging.Logger = logging.getLogger(__name__)

logger.setLevel(logging.WARN)
