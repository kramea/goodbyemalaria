"""Alert-level choropleth maps (replaces the circle-marker maps).

Districts/provinces are shaded by their CURRENT alert level — outbreak (red),
elevated (orange), normal/dry (green), or no current data (grey) — so a field
worker sees at a glance where the emergencies are right now.

- Boundaries: geoBoundaries (cached GeoJSON in knowledge/boundaries/): Mozambique
  ADM1 provinces, Malawi ADM2 districts.
- Static PNG (for WhatsApp): matplotlib polygon fill (no geopandas/GDAL needed).
- Interactive: styled GeoJSON for a Leaflet layer (see webmap.py).
"""

import json
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

from . import data
from .config import MAPS_DIR, ROOT

_BOUNDARY_DIR = ROOT / "knowledge" / "boundaries"
_COUNTRY_FILE = {"Mozambique": "MOZ_ADM1", "Malawi": "MWI_ADM2"}

# Alert level -> fill colour + human label.
ALERT_COLORS = {
    "outbreak": ("#d73027", "Active outbreak"),
    "elevated": ("#fc8d59", "Elevated"),
    "normal":   ("#1a9850", "Normal / dry season"),
    "":         ("#d9d9d9", "No current data"),
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return s.lower().replace("_", " ").strip()


@lru_cache(maxsize=8)
def _region_key_by_name() -> tuple:
    """Map normalized region names -> region key, for matching admin shapeNames."""
    out = {}
    for key, r in data.regions().items():
        out[_norm(key)] = key
        for nm in r.get("names", []):
            out[_norm(nm)] = key
    return tuple(out.items())


def _match_key(shape_name: str) -> Optional[str]:
    lut = dict(_region_key_by_name())
    n = _norm(shape_name)
    if n in lut:
        return lut[n]
    # loose containment (e.g. "Zambezia" vs "Zambezia Province")
    for nm, key in lut.items():
        if nm and (nm in n or n in nm):
            return key
    return None


@lru_cache(maxsize=4)
def _load_country(country: str) -> Optional[dict]:
    stem = _COUNTRY_FILE.get(country)
    if not stem:
        return None
    path = _BOUNDARY_DIR / f"{stem}.geojson"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _polys(geom: dict):
    """Yield exterior rings as (xs, ys) for Polygon / MultiPolygon."""
    t, c = geom.get("type"), geom.get("coordinates")
    if t == "Polygon":
        rings = [c[0]] if c else []
    elif t == "MultiPolygon":
        rings = [poly[0] for poly in c if poly]
    else:
        rings = []
    for ring in rings:
        xs = [pt[0] for pt in ring]
        ys = [pt[1] for pt in ring]
        yield xs, ys


def _feature_alert(feature: dict) -> tuple:
    """Return (alert_level, region_key_or_None) for an admin feature."""
    name = feature.get("properties", {}).get("shapeName", "")
    key = _match_key(name)
    return (data.region_alert(key) if key else ""), key


def render_choropleth(country: str, focus_region_key: Optional[str] = None,
                      force: bool = False) -> Optional[Path]:
    """Render a country alert-level choropleth PNG; return its path (cached)."""
    gj = _load_country(country)
    if not gj:
        return None
    MAPS_DIR.mkdir(parents=True, exist_ok=True)
    suffix = f"_{focus_region_key}" if focus_region_key else ""
    out = MAPS_DIR / f"choropleth_{_COUNTRY_FILE[country]}{suffix}.png"
    if out.exists() and not force:
        return out

    fig, ax = plt.subplots(figsize=(7, 8))
    for feat in gj["features"]:
        alert, key = _feature_alert(feat)
        color = ALERT_COLORS.get(alert, ALERT_COLORS[""])[0]
        is_focus = key is not None and key == focus_region_key
        for xs, ys in _polys(feat["geometry"]):
            ax.fill(xs, ys, facecolor=color,
                    edgecolor=("#111111" if is_focus else "#ffffff"),
                    linewidth=(2.4 if is_focus else 0.6),
                    zorder=(3 if is_focus else 2))
        # Label covered regions at their centroid.
        if key:
            allx, ally = [], []
            for xs, ys in _polys(feat["geometry"]):
                allx += xs
                ally += ys
            if allx:
                ax.text(sum(allx) / len(allx), sum(ally) / len(ally),
                        feat["properties"]["shapeName"],
                        fontsize=(9 if is_focus else 7),
                        fontweight=("bold" if is_focus else "normal"),
                        ha="center", va="center", zorder=4,
                        color="#111111")

    ax.set_aspect("equal")
    ax.axis("off")
    title = f"Malaria alert level — {country}"
    if focus_region_key:
        title += f"  (focus: {focus_region_key.replace('_', ' ').title()})"
    ax.set_title(title, fontsize=13, fontweight="bold")

    # Legend (only the levels actually present + a focus marker).
    present = {a for f in gj["features"] for a in [_feature_alert(f)[0]]}
    handles = [Patch(facecolor=ALERT_COLORS[a][0], edgecolor="#777", label=ALERT_COLORS[a][1])
               for a in ["outbreak", "elevated", "normal", ""] if a in present]
    if focus_region_key:
        handles.append(Patch(facecolor="none", edgecolor="#111111", linewidth=2.4,
                             label="Your area"))
    ax.legend(handles=handles, loc="lower left", fontsize=8, frameon=True)

    fig.tight_layout()
    fig.savefig(out, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return out


def caption(country: str, focus_region_key: Optional[str]) -> str:
    alert = data.region_alert(focus_region_key) if focus_region_key else ""
    label = ALERT_COLORS.get(alert, ALERT_COLORS[""])[1]
    where = focus_region_key.replace("_", " ").title() if focus_region_key else country
    return f"🗺️ Malaria alert map — {where}: {label}. Red=outbreak, orange=elevated, green=normal."


def styled_geojson(country: str, focus_region_key: Optional[str] = None) -> Optional[dict]:
    """Return the country GeoJSON with alert/colour/focus injected per feature,
    for styling a Leaflet choropleth layer."""
    gj = _load_country(country)
    if not gj:
        return None
    for feat in gj["features"]:
        alert, key = _feature_alert(feat)
        color, label = ALERT_COLORS.get(alert, ALERT_COLORS[""])
        cs = (data.region_record(key) or {}).get("current_status", {}) if key else {}
        feat["properties"]["_alert"] = alert or "none"
        feat["properties"]["_alert_label"] = label
        feat["properties"]["_color"] = color
        feat["properties"]["_focus"] = bool(key and key == focus_region_key)
        feat["properties"]["_headline"] = cs.get("headline", "")
    return gj
