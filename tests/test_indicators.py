import pytest
import pandas as pd
import numpy as np
from libs.indicators import add_indicators


def test_add_indicators_success():
    # Create 50 rows of dummy data
    data = {"close": np.linspace(100, 150, 50)}
    df = pd.DataFrame(data)

    result = add_indicators(df, bb_k=2.0)

    # Check if columns exist
    expected_cols = [
        "bb_mid",
        "bb_up",
        "bb_low",
        "rsi",
        "macd",
        "macd_signal",
        "macd_hist",
    ]
    for col in expected_cols:
        assert col in result.columns

    # Check if result is not empty and has no NaNs
    assert not result.empty
    assert result[expected_cols].isna().sum().sum() == 0


def test_add_indicators_insufficient_data():
    data = {"close": [100.0] * 10}
    df = pd.DataFrame(data)
    result = add_indicators(df)
    assert result.empty


def test_add_indicators_missing_close():
    df = pd.DataFrame({"open": [100.0] * 50})
    with pytest.raises(
        ValueError, match="Il DataFrame di input deve contenere la colonna 'close'"
    ):
        add_indicators(df)


def test_add_indicators_with_nan():
    # Test filling of NaNs
    closes = [100.0] * 50
    closes[25] = np.nan
    df = pd.DataFrame({"close": closes})

    result = add_indicators(df)
    assert not result.empty
    assert result["close"].isna().sum() == 0
