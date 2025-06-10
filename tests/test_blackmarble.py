from unittest.mock import patch

import numpy as np
import pytest

from blackmarble import BlackMarble


@pytest.fixture
def blackmarble_instance():
    return BlackMarble(bearer="mock-token")


def test_init_sets_token_from_argument():
    bm = BlackMarble(bearer="mock-token")
    assert bm._bearer == "mock-token"


@patch.dict("os.environ", {"BLACKMARBLE_TOKEN": "env-token"})
def test_init_sets_token_from_env():
    bm = BlackMarble()
    assert bm._bearer == "env-token"


def test_init_raises_when_no_token():
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError):
            BlackMarble()


def test_output_directory_returns_path(tmp_path):
    bm = BlackMarble(bearer="mock-token", output_directory=tmp_path)
    out_path = bm.output_directory
    assert out_path.exists()
    assert out_path == tmp_path


def test_remove_fill_value_replaces_fill():
    bm = BlackMarble(bearer="mock-token")
    array = np.array([[65535, 1], [2, 65535]])
    result = bm._remove_fill_value(array, "DNB_At_Sensor_Radiance_500m")
    assert np.isnan(result[0, 0])
    assert result[0, 1] == 1
    assert np.isnan(result[1, 1])


def test_remove_fill_value_ignores_unknown_variable():
    bm = BlackMarble(bearer="mock-token")
    arr = np.array([[1, 2], [3, 4]])
    out = bm._remove_fill_value(arr, "unknown_variable")
    assert np.array_equal(arr, out)
