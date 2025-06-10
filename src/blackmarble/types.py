from enum import Enum


class Product(Enum):
    """
    Representing of NASA's Black Marble VNP46 product suite.

    Products:
        - VNP46A1: Daily at-sensor top-of-atmosphere (TOA) nighttime radiance.
        - VNP46A2: Daily moonlight-adjusted nighttime lights (NTL).
        - VNP46A3: Monthly-aggregated, gap-filled nighttime light composites
        - VNP46A4: Yearly-aggregated, gap-filled nighttime light composites.

    For more details, see: https://blackmarble.gsfc.nasa.gov/#product
    """

    VNP46A1 = "VNP46A1"
    VNP46A2 = "VNP46A2"
    VNP46A3 = "VNP46A3"
    VNP46A4 = "VNP46A4"
