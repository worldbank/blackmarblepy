import pytest

from blackmarble.types import Product


def test_product_enum_values():
    assert Product.VNP46A1.value == "VNP46A1"
    assert Product.VNP46A2.value == "VNP46A2"
    assert Product.VNP46A3.value == "VNP46A3"
    assert Product.VNP46A4.value == "VNP46A4"


def test_product_enum_membership():
    assert Product("VNP46A1") == Product.VNP46A1
    assert Product("VNP46A4").name == "VNP46A4"


def test_product_enum_str_behavior():
    product = Product.VNP46A2
    assert str(product) == "Product.VNP46A2"
    assert product.name == "VNP46A2"
    assert product.value == "VNP46A2"


def test_product_enum_invalid():
    with pytest.raises(ValueError):
        Product("INVALID_CODE")
