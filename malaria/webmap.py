"""Interactive Leaflet map page for a region.

WhatsApp can't embed live JavaScript in a chat bubble, but it *can* send a
tappable link. This module builds a self-contained Leaflet HTML page (real
OpenStreetMap tiles, pan/zoom, layered risk markers + flood zones + rivers,
popups) that the worker opens in their phone browser. Served by the webhook at
/app/{region}; the WhatsApp reply includes the link.

No server-side rendering and no extra Python deps — Leaflet loads from a CDN in
the browser; we just inject the region's geo data as JSON.
"""

import json
from typing import Optional, Tuple

from . import choropleth, data

# risk -> (hex color, circle radius px) — matches the static map palette
_RISK = {
    "low": ("#2e7d32", 8),
    "moderate": ("#f9a825", 11),
    "high": ("#e53935", 14),
    "very high": ("#8e0000", 18),
}

_LINK_LABEL = {
    "Portuguese": "Mapa interativo",
    "English": "Interactive map",
    "Chichewa": "Mapu wokhoza kugwiritsa ntchito",
    "French": "Carte interactive",
}


def link_label(region_key: str, language: str = "") -> str:
    # Prefer the conversation's language so the map link doesn't mix languages
    # with the reply; fall back to the region's default language.
    if language and language in _LINK_LABEL:
        return _LINK_LABEL[language]
    rec = data.region_record(region_key) or {}
    return _LINK_LABEL.get(rec.get("language_default", "English"), "Interactive map")


def render_choropleth_html(country: str, focus_region_key: Optional[str] = None,
                           pin: Optional[Tuple[float, float]] = None,
                           og_image: str = "") -> Optional[str]:
    """Interactive alert-level choropleth (filled admin polygons, no circles)."""
    gj = choropleth.styled_geojson(country, focus_region_key)
    if not gj:
        return None
    where = focus_region_key.replace("_", " ").title() if focus_region_key else country
    title = f"Malaria alert — {where}, {country}"
    desc = "District alert levels: red = active outbreak, orange = elevated, green = normal/dry."
    payload = json.dumps({"gj": gj, "pin": list(pin) if pin else None})

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>{title}</title>
<meta property="og:title" content="{title}"/>
<meta property="og:description" content="{desc}"/>
<meta property="og:image" content="{og_image}"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  html,body{{height:100%;margin:0;font-family:system-ui,Arial,sans-serif}}
  #map{{height:100%}}
  .title{{position:absolute;top:8px;left:50%;transform:translateX(-50%);z-index:1000;
    background:rgba(255,255,255,.92);padding:6px 12px;border-radius:8px;
    box-shadow:0 1px 6px rgba(0,0,0,.3);font-weight:700;font-size:14px;max-width:92%;text-align:center}}
  .legend{{background:rgba(255,255,255,.95);padding:8px 10px;border-radius:8px;font-size:12px;line-height:1.7;
    box-shadow:0 1px 6px rgba(0,0,0,.3)}}
  .legend i{{display:inline-block;width:14px;height:14px;margin-right:6px;vertical-align:middle;border:1px solid #777}}
</style>
</head>
<body>
<div class="title">🦟 {title}</div>
<div id="map"></div>
<script>
const D = {payload};
const map = L.map('map');
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',
  {{maxZoom:19, attribution:'&copy; OpenStreetMap contributors'}}).addTo(map);

const layer = L.geoJSON(D.gj, {{
  style: f => ({{
    fillColor: f.properties._color, fillOpacity: 0.65,
    color: f.properties._focus ? '#111' : '#fff',
    weight: f.properties._focus ? 3 : 1
  }}),
  onEachFeature: (f, lyr) => {{
    const p = f.properties;
    lyr.bindPopup('<b>'+p.shapeName+'</b><br>Status: '+p._alert_label+
      (p._headline?('<br><span style="font-size:12px">'+p._headline+'</span>'):''));
  }}
}}).addTo(map);
map.fitBounds(layer.getBounds(), {{padding:[20,20]}});

if (D.pin) {{
  L.marker([D.pin[0],D.pin[1]]).addTo(map).bindPopup('📍 Your location').openPopup();
}}

const legend = L.control({{position:'bottomleft'}});
legend.onAdd = function() {{
  const div = L.DomUtil.create('div','legend');
  div.innerHTML =
    '<i style="background:#d73027"></i>Active outbreak<br>'+
    '<i style="background:#fc8d59"></i>Elevated<br>'+
    '<i style="background:#1a9850"></i>Normal / dry season<br>'+
    '<i style="background:#d9d9d9"></i>No current data';
  return div;
}};
legend.addTo(map);
</script>
</body>
</html>"""


def render_leaflet_html(region_key: str, pin: Optional[Tuple[float, float]] = None,
                        og_image: str = "") -> Optional[str]:
    rec = data.region_record(region_key)
    if not rec or not rec.get("geo"):
        return None
    geo = rec["geo"]
    region_name = region_key.replace("_", " ").title()
    payload = {
        "region": region_name,
        "country": rec["country"],
        "center": geo.get("center", [0, 0]),
        "water_bodies": geo.get("water_bodies", []),
        "low_lying_zones": geo.get("low_lying_zones", []),
        "risk_hotspots": geo.get("risk_hotspots", []),
        "risk_style": _RISK,
        "pin": list(pin) if pin else None,
        "elevation_flood": rec.get("elevation_flood", ""),
    }
    geojson = json.dumps(payload)
    title = f"Malaria risk — {region_name}, {rec['country']}"
    desc = rec.get("elevation_flood", "Mosquito-risk hotspots and low-lying / flood-prone zones.")[:180]

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>{title}</title>
<meta property="og:title" content="{title}"/>
<meta property="og:description" content="{desc}"/>
<meta property="og:image" content="{og_image}"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  html,body{{height:100%;margin:0;font-family:system-ui,Arial,sans-serif}}
  #map{{height:100%}}
  .title{{position:absolute;top:8px;left:50%;transform:translateX(-50%);z-index:1000;
    background:rgba(255,255,255,.92);padding:6px 12px;border-radius:8px;
    box-shadow:0 1px 6px rgba(0,0,0,.3);font-weight:700;font-size:14px;max-width:92%;text-align:center}}
  .legend{{background:rgba(255,255,255,.92);padding:8px 10px;border-radius:8px;font-size:12px;line-height:1.6;
    box-shadow:0 1px 6px rgba(0,0,0,.3)}}
  .legend i{{display:inline-block;width:12px;height:12px;border-radius:50%;margin-right:6px;vertical-align:middle}}
  .legend .ll{{background:#7fc8f0;opacity:.6}} .legend .rv{{background:#2f6f99;border-radius:2px;height:4px;width:16px}}
  .note{{font-size:11px;color:#555;margin-top:6px;max-width:240px}}
</style>
</head>
<body>
<div class="title">🦟 {title}</div>
<div id="map"></div>
<script>
const D = {geojson};
const map = L.map('map');
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',
  {{maxZoom:19, attribution:'&copy; OpenStreetMap contributors'}}).addTo(map);

const bounds = [];
// rivers + lakes
(D.water_bodies||[]).forEach(w => {{
  if (w.path) {{
    const latlngs = w.path.map(p => [p[0],p[1]]);
    L.polyline(latlngs, {{color:'#2f6f99', weight:4, opacity:.8}}).addTo(map).bindPopup(w.name);
    latlngs.forEach(ll => bounds.push(ll));
  }}
  if (w.type==='lake' && w.center) {{
    L.circle([w.center[0],w.center[1]], {{radius:(w.radius_km||15)*1000, color:'#2f6f99',
      fillColor:'#4fa3d1', fillOpacity:.5}}).addTo(map).bindPopup(w.name);
    bounds.push([w.center[0],w.center[1]]);
  }}
}});
// low-lying / flood-prone zones
(D.low_lying_zones||[]).forEach(z => {{
  if (!z.center) return;
  L.circle([z.center[0],z.center[1]], {{radius:12000, color:'#2f6f99', weight:1, dashArray:'5,5',
    fillColor:'#7fc8f0', fillOpacity:.30}}).addTo(map)
   .bindPopup('<b>Low-lying / flood-prone</b><br>'+z.name+(z.note?('<br>'+z.note):''));
  bounds.push([z.center[0],z.center[1]]);
}});
// risk hotspots
(D.risk_hotspots||[]).forEach(h => {{
  if (!h.center) return;
  const st = D.risk_style[h.risk] || D.risk_style['moderate'];
  L.circleMarker([h.center[0],h.center[1]], {{radius:st[1], color:'#fff', weight:1.5,
    fillColor:st[0], fillOpacity:.95}}).addTo(map)
   .bindPopup('<b>'+h.name+'</b><br>Mosquito risk: '+h.risk);
  bounds.push([h.center[0],h.center[1]]);
}});
// shared location pin
if (D.pin) {{
  L.marker([D.pin[0],D.pin[1]]).addTo(map).bindPopup('📍 Your location').openPopup();
  bounds.push([D.pin[0],D.pin[1]]);
}}

if (bounds.length) map.fitBounds(bounds, {{padding:[40,40]}});
else map.setView(D.center, 9);

// legend
const legend = L.control({{position:'bottomleft'}});
legend.onAdd = function() {{
  const div = L.DomUtil.create('div','legend');
  div.innerHTML =
    '<i style="background:#8e0000"></i>Risk: very high<br>'+
    '<i style="background:#e53935"></i>Risk: high<br>'+
    '<i style="background:#f9a825"></i>Risk: moderate<br>'+
    '<i style="background:#2e7d32"></i>Risk: low<br>'+
    '<i class="ll"></i>Low-lying / flood-prone<br>'+
    '<i class="rv"></i>River / lake'+
    (D.elevation_flood?('<div class="note">'+D.elevation_flood+'</div>'):'');
  return div;
}};
legend.addTo(map);
</script>
</body>
</html>"""
