"""Grafica TA (Prezzo+BB, RSI, MACD) thread-safe e senza stato globale."""

from __future__ import annotations
import io
import logging
import pandas as pd
import matplotlib as _mpl
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

# Forza backend non interattivo
_mpl.use("Agg")

logger = logging.getLogger(__name__)


def _draw_core_chart(fig: Figure, df: pd.DataFrame, symbol: str) -> None:
    """
    Logica di disegno condivisa.
    Usa l'oggetto Figure passato per evitare stato globale.
    """
    ax_price, ax_rsi, ax_macd = fig.subplots(
        3, 1, sharex=True, gridspec_kw={"height_ratios": [2, 1, 1]}
    )

    fig.suptitle(
        f"{symbol} — Technical Analysis",
        fontsize=16,
        fontweight="bold",
        y=0.98,
        color="#00ffcc",
    )
    fig.set_facecolor("#0d1117")

    # Estrazione dati
    last_row = df.iloc[-1]
    last_price = float(last_row["close"])
    last_date = last_row["date"]

    # 1. Price + Bollinger
    ax_price.set_facecolor("#0d1117")
    ax_price.plot(df["date"], df["close"], label="Close", color="#00ffff", linewidth=2)
    ax_price.plot(
        df["date"],
        df["bb_mid"],
        label="BB Mid",
        color="#ffffff",
        alpha=0.4,
        linestyle="--",
    )
    ax_price.plot(df["date"], df["bb_low"], color="#444444", alpha=0.5)
    ax_price.plot(df["date"], df["bb_up"], color="#444444", alpha=0.5)
    ax_price.fill_between(
        df["date"], df["bb_low"], df["bb_up"], color="#ffffff", alpha=0.05
    )
    ax_price.scatter(
        last_date, last_price, color="#00ffff", s=80, edgecolors="white", zorder=5
    )

    ax_price.set_ylabel("Price", color="#cccccc")
    ax_price.grid(True, alpha=0.1, linestyle=":")
    ax_price.legend(loc="upper left", fontsize="small", framealpha=0.3)
    ax_price.tick_params(colors="#cccccc")

    # 2. RSI
    ax_rsi.set_facecolor("#0d1117")
    ax_rsi.plot(df["date"], df["rsi"], label="RSI(14)", color="#ff00ff", linewidth=2)
    ax_rsi.axhline(30, color="#00ff00", linestyle="--", alpha=0.3)
    ax_rsi.axhline(70, color="#ff0000", linestyle="--", alpha=0.3)
    ax_rsi.set_ylim(0, 100)
    ax_rsi.set_ylabel("RSI", color="#cccccc")
    ax_rsi.grid(True, alpha=0.1, linestyle=":")
    ax_rsi.tick_params(colors="#cccccc")

    # 3. MACD
    ax_macd.set_facecolor("#0d1117")
    ax_macd.plot(df["date"], df["macd"], label="MACD", color="#0099ff")
    ax_macd.plot(df["date"], df["macd_signal"], label="Signal", color="#ff9900")
    colors = ["#00ff00" if x >= 0 else "#ff0000" for x in df["macd_hist"]]
    ax_macd.bar(df["date"], df["macd_hist"], color=colors, alpha=0.6)
    ax_macd.axhline(0, color="#ffffff", linewidth=0.5, alpha=0.5)
    ax_macd.set_ylabel("MACD", color="#cccccc")
    ax_macd.grid(True, alpha=0.1, linestyle=":")
    ax_macd.tick_params(colors="#cccccc")

    fig.autofmt_xdate()
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))


def get_plot_bytes(df: pd.DataFrame, symbol: str) -> bytes:
    """
    Genera il grafico in memoria e restituisce i byte del PNG.
    Thread-safe.
    """
    if df is None or df.empty or len(df) < 2:
        return b""

    # Assicuro datetime
    plot_df = df.copy()
    if not pd.api.types.is_datetime64_any_dtype(plot_df["date"]):
        plot_df["date"] = pd.to_datetime(plot_df["date"])

    fig = Figure(figsize=(13, 11), dpi=140)
    canvas = FigureCanvasAgg(fig)

    try:
        _draw_core_chart(fig, plot_df, symbol)
        buf = io.BytesIO()
        canvas.print_png(buf)
        return buf.getvalue()
    except Exception as e:
        logger.error("Error in get_plot_bytes: %s", e)
        return b""
