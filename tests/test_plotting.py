import pandas as pd
import numpy as np
from libs.plotting import get_plot_bytes


def test_get_plot_bytes_success():
    # Create data with indicators (required for plotting)
    dates = pd.date_range(start="2024-01-01", periods=50)
    data = {
        "date": dates,
        "close": np.random.uniform(100, 200, 50),
        "bb_mid": np.random.uniform(100, 200, 50),
        "bb_up": np.random.uniform(150, 250, 50),
        "bb_low": np.random.uniform(50, 150, 50),
        "rsi": np.random.uniform(0, 100, 50),
        "macd": np.random.uniform(-1, 1, 50),
        "macd_signal": np.random.uniform(-1, 1, 50),
        "macd_hist": np.random.uniform(-1, 1, 50),
    }
    df = pd.DataFrame(data)

    img_bytes = get_plot_bytes(df, "BTC/USDT")

    assert isinstance(img_bytes, bytes)
    assert len(img_bytes) > 0
    # Check for PNG magic number
    assert img_bytes.startswith(b"\x89PNG\r\n\x1a\n")


def test_get_plot_bytes_empty():
    df = pd.DataFrame()
    assert get_plot_bytes(df, "TEST") == b""
