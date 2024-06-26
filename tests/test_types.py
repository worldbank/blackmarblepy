import pytest

from blackmarble.types import Product


def test_fails_product():
    with pytest.raises(ValueError):
        Product("blackmarblepy")
