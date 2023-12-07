from datetime import date
from enum import Enum

from pydantic import BaseModel, validator


class Product(Enum):
    """NASA Black Marble product suite (VNP46)"""

    VNP46A1 = "VNP46A1"
    VNP46A2 = "VNP46A2"
    VNP46A3 = "VNP46A3"
    VNP46A4 = "VNP46A4"


class DateRange(BaseModel):
    start_date: date
    end_date: date

    @validator("start_date", "end_date", pre=True)
    def parse_dates(cls, v):
        if isinstance(v, str):
            return date.fromisoformat(v)
        return v

    @validator("end_date")
    def check_date_range(cls, v, values, **kwargs):
        if "start_date" in values and v < values["start_date"]:
            raise ValueError("End date cannot be before start date")
        return v
