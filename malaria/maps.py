"""Offline thematic risk-map renderer for a region.

Curated-data approach: draws a clean, legible thematic map from the `geo` block
in knowledge/regions.json — water bodies, low-lying / flood-prone zones, and
graduated mosquito-risk hotspots — using matplotlib (Agg, no display, no network
tiles). Output PNGs are written to MAPS_DIR and served by the webhook so Twilio
can attach them to WhatsApp messages.

This is intentionally a thematic (schematic) map, not a street map: it makes the
malaria-relevant layers (elevation/flood + risk) the focus. The upgrade path is
to overlay real MAP prevalence + DEM/HAND rasters here later.
"""

import math
from pathlib import Path
from typing import List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Circle

from . import config, data

# risk level -> (color, marker size, z-order weight)
_RISK_STYLE = {
    "low": ("#2e7d32", 90),
    "moderate": ("#f9a825", 150),
    "high": ("#e53935", 230),
    "very high": ("#8e0000", 330),
}


def _km_to_deg(lat: float, km: float) -> Tuple[float, float]:
    dlat = km / 111.0
    dlon = km / (111.0 * max(0.2, math.cos(math.radians(lat))))
    return dlat, dlon


def _collect_points(geo: dict) -> List[Tuple[float, float]]:
    pts: List[Tuple[float, float]] = []
    if geo.get("center"):
        pts.append(tuple(geo["center"]))
    for wb in geo.get("water_bodies", []):
        if wb.get("path"):
            pts.extend(tuple(p) for p in wb["path"])
        if wb.get("center"):
            pts.append(tuple(wb["center"]))
    for z in geo.get("low_lying_zones", []):
        if z.get("center"):
            pts.append(tuple(z["center"]))
    for h in geo.get("risk_hotspots", []):
        if h.get("center"):
            pts.append(tuple(h["center"]))
    return pts


def map_path(region_key: str) -> Path:
    return config.MAPS_DIR / f"{region_key}.png"


def render_region_map(
    region_key: str,
    highlight_point: Optional[Tuple[float, float]] = None,
    force: bool = False,
) -> Optional[Path]:
    """Render (and cache) the thematic map for a region. Returns the PNG path.

    highlight_point=(lat, lon) adds a 'location' star (used for shared GPS pins);
    when a highlight is given we always re-render to a point-specific file.
    """
    rec = data.region_record(region_key)
    if not rec:
        return None
    geo = rec.get("geo")
    if not geo:
        return None

    config.MAPS_DIR.mkdir(parents=True, exist_ok=True)
    if highlight_point:
        out = config.MAPS_DIR / f"{region_key}_pin.png"
    else:
        out = map_path(region_key)
    if out.exists() and not force and not highlight_point:
        return out

    pts = _collect_points(geo)
    if highlight_point:
        pts.append(tuple(highlight_point))
    if not pts:
        return None

    lats = [p[0] for p in pts]
    lons = [p[1] for p in pts]
    pad_lat = max(0.15, (max(lats) - min(lats)) * 0.25)
    pad_lon = max(0.15, (max(lons) - min(lons)) * 0.25)
    lat_min, lat_max = min(lats) - pad_lat, max(lats) + pad_lat
    lon_min, lon_max = min(lons) - pad_lon, max(lons) + pad_lon

    fig, ax = plt.subplots(figsize=(7.2, 7.6), dpi=130)
    ax.set_facecolor("#eef3ec")  # land
    ax.set_xlim(lon_min, lon_max)
    ax.set_ylim(lat_min, lat_max)
    ax.set_aspect(1.0 / max(0.2, math.cos(math.radians((lat_min + lat_max) / 2))))

    # Water bodies
    for wb in geo.get("water_bodies", []):
        if wb.get("type") == "lake" and wb.get("center"):
            dlat, dlon = _km_to_deg(wb["center"][0], wb.get("radius_km", 15))
            ax.add_patch(
                Circle((wb["center"][1], wb["center"][0]), radius=(dlat + dlon) / 2,
                       facecolor="#4fa3d1", edgecolor="#2f6f99", alpha=0.55, zorder=1)
            )
            ax.annotate(wb["name"], (wb["center"][1], wb["center"][0]),
                        color="#1b4f72", fontsize=8, ha="center", va="center", zorder=6)
        if wb.get("path"):
            xs = [p[1] for p in wb["path"]]
            ys = [p[0] for p in wb["path"]]
            ax.plot(xs, ys, color="#2f6f99", linewidth=3, alpha=0.8, zorder=2,
                    solid_capstyle="round")
            ax.annotate(wb["name"], (xs[len(xs) // 2], ys[len(ys) // 2]),
                        color="#1b4f72", fontsize=8, zorder=6)

    # Low-lying / flood-prone zones (translucent blue blobs)
    for z in geo.get("low_lying_zones", []):
        c = z.get("center")
        if not c:
            continue
        dlat, dlon = _km_to_deg(c[0], 12)
        ax.add_patch(
            Circle((c[1], c[0]), radius=(dlat + dlon) / 2, facecolor="#7fc8f0",
                   edgecolor="#2f6f99", alpha=0.30, linestyle="--", zorder=3)
        )

    # Risk hotspots (graduated)
    for h in geo.get("risk_hotspots", []):
        c = h.get("center")
        if not c:
            continue
        color, size = _RISK_STYLE.get(h.get("risk", "moderate"), _RISK_STYLE["moderate"])
        ax.scatter([c[1]], [c[0]], s=size, c=color, edgecolors="white",
                   linewidths=1.2, zorder=5)
        ax.annotate(f"  {h['name']}", (c[1], c[0]), color="#222", fontsize=8,
                    va="center", zorder=7)

    # Shared-location pin
    if highlight_point:
        ax.scatter([highlight_point[1]], [highlight_point[0]], s=420, marker="*",
                   c="#1565c0", edgecolors="white", linewidths=1.4, zorder=8)
        ax.annotate("  your location", (highlight_point[1], highlight_point[0]),
                    color="#0d3b66", fontsize=9, fontweight="bold", va="center", zorder=8)

    # Cosmetics
    title = f"Malaria risk — {region_key.replace('_', ' ').title()}, {rec['country']}"
    ax.set_title(title, fontsize=13, fontweight="bold", pad=10)
    ax.set_xlabel("Longitude", fontsize=8)
    ax.set_ylabel("Latitude", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.grid(True, color="white", linewidth=0.6, alpha=0.7)

    legend_items = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=_RISK_STYLE["very high"][0],
               markersize=11, label="Risk: very high"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=_RISK_STYLE["high"][0],
               markersize=10, label="Risk: high"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=_RISK_STYLE["moderate"][0],
               markersize=8, label="Risk: moderate"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=_RISK_STYLE["low"][0],
               markersize=7, label="Risk: low"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#7fc8f0",
               markersize=11, alpha=0.6, label="Low-lying / flood-prone"),
        Line2D([0], [0], color="#2f6f99", linewidth=3, label="River / lake"),
    ]
    ax.legend(handles=legend_items, loc="lower left", fontsize=7, framealpha=0.9)

    fig.text(0.5, 0.012,
             "Approximate, curated (WHO WMR 2025 · MAP · CHIRPS · SRTM DEM). "
             "Thematic risk map — not for navigation.",
             ha="center", fontsize=6.5, color="#666")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out


def map_caption(region_key: str) -> str:
    rec = data.region_record(region_key)
    if not rec:
        return ""
    name = region_key.replace("_", " ").title()
    return (f"🗺️ {name} risk map: red = mosquito-risk hotspots (darker = higher), "
            f"blue dashed = low-lying / flood-prone zones, blue lines/circles = "
            f"rivers & lakes.")
