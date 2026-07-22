"""NiceGUI dashboard page: request monitoring."""

import datetime
import logging
from typing import Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Request
from fastapi.responses import RedirectResponse
from nicegui import app as ng_app
from nicegui import ui

from app import metrics as mdb
from app.config import config
from app.ui.router import auth

logger = logging.getLogger(__name__)

_APP_NAME = "Candle Graph"

_NAV_ITEMS: list[tuple[str, str, str]] = [
    ("Dashboard", "dashboard", "/"),
    ("Configurazione", "settings", "/config"),
]

_REFRESH_OPTIONS: dict[int, str] = {15: "15s", 30: "30s", 60: "60s", 120: "120s"}
_DEFAULT_REFRESH: int = 30


def _refresh_enabled() -> bool:
    return config.get_bool("REFRESH_ENABLED")


def _refresh_interval() -> int:
    return config.get_int("REFRESH_INTERVAL", _DEFAULT_REFRESH)


def _get_tz() -> ZoneInfo:
    tz_name = config.get("TZ", "UTC")
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        logger.warning("Invalid TZ '%s' - falling back to UTC", tz_name)
        return ZoneInfo("UTC")


def _check_auth(request: Request) -> bool:
    return auth.verify_token(request.cookies.get(auth.cookie_name, ""))


def _fmt_ts(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts, tz=_get_tz()).strftime("%d/%m %H:%M:%S")


def _metric_card(label: str, value: str, color: str = "primary") -> None:
    with ui.card().classes("q-pa-md").style("min-width:130px; flex:1;"):
        ui.label(label).classes("text-caption text-grey-6 text-uppercase")
        ui.label(value).classes(f"text-h5 text-weight-bold text-{color}")


def _page_setup(section_title: str) -> Any:
    ui.page_title(f"{section_title} — {_APP_NAME}")
    return ui.dark_mode(value=ng_app.storage.user.get("dark_mode", True))


def _header(page_title: str, current: str = "", *, dark: Any) -> None:
    with ui.header().classes("bg-primary text-white items-center q-px-md q-gutter-sm"):
        ui.label(page_title).classes("text-h6 text-weight-bold col")

        for label, icon, path in _NAV_ITEMS:
            if label.lower() != current.lower():
                ui.button(icon=icon, on_click=lambda p=path: ui.navigate.to(p)).props("flat color=white round").tooltip(
                    label
                )

        ui.button(
            icon="logout",
            on_click=lambda: ui.run_javascript("window.location.href='/auth/logout'"),
        ).props("flat color=white round").tooltip("Logout")

        def _toggle_dark() -> None:
            dark.toggle()
            ng_app.storage.user["dark_mode"] = dark.value

        ui.button(icon="contrast", on_click=_toggle_dark).props("flat round dense color=white").tooltip("Dark / Light")
        ui.label(_APP_NAME).classes("text-body2").style("opacity:0.6")


def _footer() -> None:
    with ui.footer().classes("bg-primary text-white q-px-md q-py-xs row items-center"):
        ui.label(_APP_NAME).classes("col text-caption").style("opacity:0.6")


@ui.page("/")
async def dashboard_page(request: Request) -> Optional[RedirectResponse]:
    if not _check_auth(request):
        return RedirectResponse("/login")

    dark = _page_setup("Dashboard")
    _header("Dashboard", current="Dashboard", dark=dark)

    refresh_enabled: bool = _refresh_enabled()

    with ui.column().style("width:100%; padding:1.25rem; gap:1rem; overflow:auto;"):
        ui.label("Dashboard").classes("text-h6")

        stats_row = ui.row().classes("q-gutter-sm items-stretch full-width")
        ui.separator()
        history_label = ui.label("").classes("text-subtitle2 text-grey-6")
        history_wrap = ui.column().style("width:100%;")
        refresh_label = ui.label("").classes("text-caption text-grey-6").style("text-align:right; width:100%")

        async def refresh() -> None:
            stats = await mdb.get_stats(hours=24)
            history = await mdb.get_history(limit=50)

            stats_row.clear()
            with stats_row:
                _metric_card("Richieste 24h", str(stats["total"]))
                _metric_card("OK", str(stats["ok"]), "positive")
                _metric_card("Errori", str(stats["errors"]), "negative")
                _metric_card("Timeout", str(stats["timeouts"]), "warning")
                _metric_card("Durata media", f"{stats['avg_duration_s']}s")

            history_label.set_text(f"Storico richieste ({len(history)} record più recenti)")

            history_wrap.clear()
            with history_wrap:
                cols = [
                    {"name": "ts", "label": "Timestamp", "field": "ts", "align": "left"},
                    {"name": "symbol", "label": "Symbol", "field": "symbol", "align": "left"},
                    {"name": "status", "label": "Status", "field": "status", "align": "center"},
                    {"name": "duration", "label": "Durata (ms)", "field": "duration", "align": "right"},
                    {"name": "error", "label": "Errore", "field": "error", "align": "left"},
                ]
                rows = []
                for r in history:
                    dur = r["duration"]
                    rows.append(
                        {
                            "ts": _fmt_ts(r["ts"]),
                            "symbol": r["symbol"],
                            "status": r["status"],
                            "duration": f"{dur * 1000:.0f}" if dur is not None else "—",
                            "error": r["error_msg"] or "",
                        }
                    )
                tbl = ui.table(columns=cols, rows=rows).classes("full-width")
                tbl.add_slot(
                    "body-cell-status",
                    """
                    <q-td :props="props">
                      <q-badge
                        :color="props.value === 'ok' ? 'positive' : props.value === 'timeout' ? 'warning' : 'negative'"
                        :label="props.value"
                      />
                    </q-td>
                    """,
                )
                tbl.run_method("$forceUpdate")

            if refresh_enabled:
                now = datetime.datetime.now(_get_tz()).strftime("%H:%M:%S")
                refresh_label.set_text(f"Aggiornato: {now} · auto-refresh {_refresh_interval()}s")

        await refresh()
        if refresh_enabled:
            ui.timer(_refresh_interval(), refresh)
        else:
            refresh_label.set_text("auto-refresh disabilitato")

    _footer()
    return None


@ui.page("/config")
async def config_page(request: Request) -> Optional[RedirectResponse]:
    if not _check_auth(request):
        return RedirectResponse("/login")

    dark = _page_setup("Configurazione")
    _header("Configurazione", current="Configurazione", dark=dark)

    with ui.column().style("width:100%; padding:1.25rem; gap:1.5rem;"):
        ui.label("Configurazione").classes("text-h6")

        with ui.card().classes("q-pa-md").style("max-width:480px;"):
            with ui.row().classes("items-center q-gutter-sm q-mb-sm"):
                ui.label("Interfaccia").classes("text-subtitle1 text-weight-bold")
                ui.badge("hot-reload").props("color=positive")
            ui.label(
                "Impostazioni di aggiornamento automatico della dashboard. "
                "Le modifiche si applicano alla prossima apertura della Dashboard."
            ).classes("text-caption text-grey-6 q-mb-md")

            cur_enabled: bool = _refresh_enabled()
            cur_interval: int = _refresh_interval()

            sw = ui.switch("Abilitato", value=cur_enabled).classes("q-mb-sm")

            sel = (
                ui.select(
                    options=_REFRESH_OPTIONS,
                    value=cur_interval,
                    label="Intervallo",
                )
                .props("outlined")
                .style("width:160px;")
                .bind_enabled_from(sw, "value")
            )

            tz_input = (
                ui.input("Fuso orario (IANA, es. Europe/Rome)", value=config.get("TZ", "UTC"))
                .props("outlined")
                .classes("q-mt-md")
                .style("width:280px;")
            )

            def _save() -> None:
                config.update_many(
                    {
                        "REFRESH_ENABLED": "true" if sw.value else "false",
                        "REFRESH_INTERVAL": str(int(sel.value)),
                        "TZ": tz_input.value.strip() or "UTC",
                    }
                )
                ui.notify(
                    "Auto-refresh disabilitato — attivo alla prossima apertura della Dashboard"
                    if not sw.value
                    else f"Auto-refresh {int(sel.value)}s — attivo alla prossima apertura della Dashboard",
                    color="positive",
                )

        with ui.card().classes("q-pa-md").style("max-width:480px;"):
            with ui.row().classes("items-center q-gutter-sm q-mb-sm"):
                ui.label("API").classes("text-subtitle1 text-weight-bold")
                ui.badge("hot-reload").props("color=positive")
            ui.label(
                "Limite di rate per /api/v1/chart (slowapi). I token validi restano "
                "in API_TOKENS nel .env — non modificabili da qui."
            ).classes("text-caption text-grey-6 q-mb-md")

            rate_limit_input = (
                ui.input("Rate limit (es. 20/minute)", value=config.get("RATE_LIMIT", "20/minute"))
                .props("outlined")
                .style("width:280px;")
            )

            def _save_api() -> None:
                config.update_many({"RATE_LIMIT": rate_limit_input.value.strip() or "20/minute"})
                ui.notify("Rate limit aggiornato — hot-reload senza restart", color="positive")

            ui.button("Salva", on_click=_save_api).props("color=primary").classes("q-mt-md")

    _footer()
    return None
