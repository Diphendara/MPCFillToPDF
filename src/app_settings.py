import json
import logging
from dataclasses import dataclass
from pathlib import Path

_log = logging.getLogger(__name__)

DEFAULT_CUT_LINE_COLOR = "#000000"
DEFAULT_CUT_LINE_STYLE = "ticks"
DEFAULT_CUT_LINE_WIDTH = 1.0
DEFAULT_CUT_LINE_OVER_CARDS = False
DEFAULT_CUT_LINE_OVER_FRONTS = True
DEFAULT_CUT_LINE_OVER_BACKS = True


@dataclass
class AppSettings:
    output_dir: Path | None = None
    cut_line_color: str = DEFAULT_CUT_LINE_COLOR
    cut_line_style: str = DEFAULT_CUT_LINE_STYLE
    cut_line_width: float = DEFAULT_CUT_LINE_WIDTH
    cut_line_over_cards: bool = DEFAULT_CUT_LINE_OVER_CARDS
    cut_line_over_fronts: bool = DEFAULT_CUT_LINE_OVER_FRONTS
    cut_line_over_backs: bool = DEFAULT_CUT_LINE_OVER_BACKS


def _settings_path(base_dir: Path) -> Path:
    return base_dir / "MPCFillToPDF" / "settings.json"


def load_settings(base_dir: Path) -> AppSettings:
    """Load settings from disk, returning defaults on any error."""
    path = _settings_path(base_dir)
    if not path.exists():
        return AppSettings()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        raw_dir = data.get("output_dir")
        output_dir: Path | None = None
        if raw_dir:
            p = Path(raw_dir)
            if p.exists():
                output_dir = p
        color = str(data.get("cut_line_color", DEFAULT_CUT_LINE_COLOR)).strip()
        if not color.startswith("#") or len(color) not in (4, 7):
            color = DEFAULT_CUT_LINE_COLOR
        style = str(data.get("cut_line_style", DEFAULT_CUT_LINE_STYLE)).strip()
        if style not in ("ticks", "full"):
            style = DEFAULT_CUT_LINE_STYLE
        try:
            width = float(data.get("cut_line_width", DEFAULT_CUT_LINE_WIDTH))
            width = max(0.1, min(10.0, width))
        except (TypeError, ValueError):
            width = DEFAULT_CUT_LINE_WIDTH
        over_cards = bool(data.get("cut_line_over_cards", DEFAULT_CUT_LINE_OVER_CARDS))
        over_fronts = bool(data.get("cut_line_over_fronts", DEFAULT_CUT_LINE_OVER_FRONTS))
        over_backs = bool(data.get("cut_line_over_backs", DEFAULT_CUT_LINE_OVER_BACKS))
        return AppSettings(
            output_dir=output_dir,
            cut_line_color=color,
            cut_line_style=style,
            cut_line_width=width,
            cut_line_over_cards=over_cards,
            cut_line_over_fronts=over_fronts,
            cut_line_over_backs=over_backs,
        )
    except Exception as exc:
        _log.warning("Could not load settings.json: %s", exc)
        return AppSettings()


def save_settings(settings: AppSettings, base_dir: Path) -> None:
    """Persist settings to disk. Silently ignores write errors."""
    path = _settings_path(base_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "output_dir": str(settings.output_dir) if settings.output_dir else None,
            "cut_line_color": settings.cut_line_color,
            "cut_line_style": settings.cut_line_style,
            "cut_line_width": settings.cut_line_width,
            "cut_line_over_cards": settings.cut_line_over_cards,
            "cut_line_over_fronts": settings.cut_line_over_fronts,
            "cut_line_over_backs": settings.cut_line_over_backs,
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except Exception as exc:
        _log.warning("Could not save settings.json: %s", exc)
