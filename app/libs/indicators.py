"""Calcolo degli indicatori tecnici: Bande di Bollinger, RSI e MACD."""

from __future__ import annotations
import logging
from typing import Any, cast
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD

logger = logging.getLogger(__name__)


def add_indicators(df_input: pd.DataFrame, bb_k: float = 2.0) -> pd.DataFrame:
    """
    Aggiunge indicatori tecnici al DataFrame fornito in input.
    I calcoli includono:
    - Bande di Bollinger (window=20, k=bb_k).
    - RSI(14): Indice di Forza Relativa.
    - MACD(12, 26, 9).

    :param df_input: DataFrame con almeno la colonna 'close'.
    :param bb_k: Moltiplicatore deviazione standard per Bollinger.
    :return: Un nuovo DataFrame con gli indicatori calcolati.
    """
    if df_input.empty:
        return pd.DataFrame()

    if "close" not in df_input.columns:
        raise ValueError("Il DataFrame di input deve contenere la colonna 'close'.")

    if len(df_input) < 26:
        logger.warning(
            "Dati insufficienti per calcolare gli indicatori (richieste almeno 26 barre, ricevute %d)",
            len(df_input),
        )
        return pd.DataFrame()

    df = df_input.copy(deep=True)

    if df["close"].isna().any():
        df["close"] = df["close"].ffill().bfill()

    close_series = cast(Any, df["close"])

    # --- 1. Bande di Bollinger ---
    bb_window = 20
    roll = close_series.rolling(window=bb_window, min_periods=bb_window)
    mid = roll.mean()
    std = roll.std(ddof=1)

    df["bb_mid"] = mid
    df["bb_up"] = mid + bb_k * std
    df["bb_low"] = mid - bb_k * std

    # --- 2. RSI(14) ---
    rsi_window = 14
    if len(df) < rsi_window:
        rsi_window = len(df)
    df["rsi"] = RSIIndicator(close=close_series, window=max(1, rsi_window)).rsi()

    # --- 3. MACD(12, 26, 9) ---
    macd_tool = MACD(close=close_series, window_slow=26, window_fast=12, window_sign=9)
    df["macd"] = macd_tool.macd()
    df["macd_signal"] = macd_tool.macd_signal()
    df["macd_hist"] = macd_tool.macd_diff()

    cols_to_check = [
        "bb_mid",
        "bb_low",
        "bb_up",
        "rsi",
        "macd",
        "macd_signal",
        "macd_hist",
    ]

    df_clean = df.dropna(subset=cols_to_check, how="any")

    if df_clean.empty:
        return pd.DataFrame(columns=df.columns)

    return cast(pd.DataFrame, df_clean.reset_index(drop=True))
