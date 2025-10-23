
import streamlit as st
from streamlit_folium import st_folium
import folium
import requests
import pandas as pd
from typing import Tuple, Dict, Any, List

st.set_page_config(page_title="Simple OSM Navigator (OSRM) — single map + reliable click", layout="wide")

st.title("🚗 Simple OSM Navigator (OSRM only)")
st.caption("Pick start/end (search or map click) → OSRM driving route. Alternatives, steps, GPX export.")

# ------------------------
# Helpers
# ------------------------
@st.cache_data(show_spinner=False)
def geocode_place(q: str) -> Tuple[float, float]:
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": q, "format": "json", "limit": 1}
    r = requests.get(url, params=params, headers={"User-Agent": "streamlit-osm-simple-nav"}, timeout=20)
    r.raise_for_status()
    data = r.json()
    if not data:
        raise ValueError("No geocoding results.")
    return float(data[0]["lat"]), float(data[0]["lon"])

def osrm_route(start: Tuple[float,float], end: Tuple[float,float], alternatives: bool, steps: bool=True) -> Dict[str, Any]:
    url = f"https://router.project-osrm.org/route/v1/driving/{start[1]},{start[0]};{end[1]},{end[0]}"
    params = {
        "overview": "full",
        "geometries": "geojson",
        "steps": "true" if steps else "false",
        "alternatives": "true" if alternatives else "false",
        "annotations": "false",
    }
    r = requests.get(url, params=params, headers={"User-Agent": "streamlit-osm-simple-nav"}, timeout=30)
    r.raise_for_status()
    return r.json()

def gpx_from_geojson_line(coords: List[List[float]], name: str = "route") -> str:
    header = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<gpx version="1.1" creator="simple-osm-nav" xmlns="http://www.topografix.com/GPX/1/1">\n'
        f'  <trk><name>{name}</name><trkseg>\n'
    )
    body = ""
    for lon, lat in coords:
        body += f'    <trkpt lat="{lat}" lon="{lon}"></trkpt>\n'
    footer = '  </trkseg></trk>\n</gpx>\n'
    return header + body + footer

def preset_geo(name: str) -> Tuple[float,float]:
    mapping = {
        "Tokyo Station": (35.681236, 139.767125),
        "Shinjuku Station": (35.690921, 139.700258),
        "Shibuya Crossing": (35.659494, 139.700553),
        "Osaka Station": (34.702485, 135.495951),
        "Nagoya Station": (35.170915, 136.881537),
    }
    return mapping[name]

# ------------------------
# Sidebar
# ------------------------
with st.sidebar:
    st.header("Start / End")
    preset_from = st.selectbox("Preset start", ["Tokyo Station", "Shinjuku Station", "Shibuya Crossing", "Osaka Station", "Nagoya Station"], index=0)
    preset_to   = st.selectbox("Preset end",   ["Shibuya Crossing", "Shinjuku Station", "Tokyo Station", "Osaka Station", "Nagoya Station"], index=1)
    custom_from = st.text_input("...or custom start (address / landmark)")
    custom_to   = st.text_input("...or custom end (address / landmark)")

    st.divider()
    st.header("Options")
    use_alts = st.checkbox("Show alternative routes (if available)", value=True)
    show_steps = st.checkbox("Show turn-by-turn steps", value=True)

# ------------------------
# Session state for clicks
# ------------------------
if "click_history" not in st.session_state:
    st.session_state["click_history"] = []  # [(lat, lon), ...]

# Start/end from text or preset first
start = geocode_place(custom_from) if custom_from.strip() else preset_geo(preset_from)
end   = geocode_place(custom_to)   if custom_to.strip()   else preset_geo(preset_to)

# If we have two clicks, override by clicks
if len(st.session_state["click_history"]) == 2:
    start, end = st.session_state["click_history"]

center = ((start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0)
m = folium.Map(location=center, zoom_start=13, tiles="OpenStreetMap")

# Always draw current start/end + (later) route
folium.Marker(start, tooltip="Start", icon=folium.Icon(color="green")).add_to(m)
folium.Marker(end, tooltip="End", icon=folium.Icon(color="red")).add_to(m)

# Compute route
data = osrm_route(start, end, alternatives=use_alts, steps=show_steps)
routes = []
if data.get("code") == "Ok":
    routes = data["routes"]
    for idx, rt in enumerate(routes):
        folium.GeoJson(rt["geometry"], name=f"route {idx+1}").add_to(m)
else:
    st.warning(f"OSRM routing failed: {data.get('message')}")

st.markdown("**Tip:** 地図クリックで起点・終点を更新（最後の2点が採用されます）。クリック直後に画面が更新されない場合は自動でリランします。")

# IMPORTANT: use 'last_clicked' (not 'last_object_clicked') and trigger a rerun
info = st_folium(m, width=None, height=560, key="map-main")
clicked = info.get("last_clicked")
if clicked and isinstance(clicked, dict) and "lat" in clicked and "lng" in clicked:
    hist = st.session_state["click_history"]
    hist.append((clicked["lat"], clicked["lng"]))
    st.session_state["click_history"] = hist[-2:]
    # Force immediate rerun so the new route appears right away
    st.rerun()

# ------------------------
# Summary / exports
# ------------------------
if routes:
    st.subheader("📈 Route summary")
    route_summaries = []
    for idx, rt in enumerate(routes):
        distance_km = rt["distance"]/1000.0
        duration_min = rt["duration"]/60.0
        route_summaries.append({
            "route": idx+1,
            "distance_km": round(distance_km, 2),
            "duration_min": round(duration_min, 1),
            "gpx": gpx_from_geojson_line(rt["geometry"]["coordinates"], name=f"route_{idx+1}")
        })
    st.dataframe(pd.DataFrame(route_summaries)[["route","distance_km","duration_min"]], hide_index=True)

    for rs in route_summaries:
        st.download_button(
            label=f"⬇️ Download GPX for route {rs['route']}",
            data=rs["gpx"].encode("utf-8"),
            file_name=f"osm_route_{rs['route']}.gpx",
            mime="application/gpx+xml"
        )

    if show_steps:
        st.subheader("🧭 Turn-by-turn (route 1)")
        steps_rows = []
        for leg in routes[0].get("legs", []):
            for s in leg.get("steps", []):
                inst = s.get("maneuver", {}).get("instruction", "")
                dist_m = s.get("distance", 0.0)
                dur_s = s.get("duration", 0.0)
                steps_rows.append({"instruction": inst, "distance_m": round(dist_m,1), "duration_s": round(dur_s,1)})
        if steps_rows:
            st.dataframe(pd.DataFrame(steps_rows), hide_index=True)
        else:
            st.info("No step details available.")
