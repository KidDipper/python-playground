
import streamlit as st
from streamlit_folium import st_folium
import folium
from folium.plugins import MarkerCluster, HeatMap
import requests
import pandas as pd
from typing import Tuple, Dict, Any, List

st.set_page_config(page_title="OSM + Open Data Hands-on", layout="wide")

st.title("🗺️ OSM + Open Data Hands-on (Streamlit)")
st.caption("Query OpenStreetMap (via Overpass API) for nearby features and visualize them on a map.")

# ------------------------
# Helpers
# ------------------------
@st.cache_data(show_spinner=False)
def geocode_place(q: str) -> Tuple[float, float]:
    """Geocode a place name using Nominatim (OSM). Returns (lat, lon)."""
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": q,
        "format": "json",
        "addressdetails": 0,
        "limit": 1,
    }
    r = requests.get(url, params=params, headers={"User-Agent": "streamlit-osm-demo"} , timeout=20)
    r.raise_for_status()
    data = r.json()
    if not data:
        raise ValueError("No results from geocoding.")
    return float(data[0]["lat"]), float(data[0]["lon"])


def _overpass_query(query: str) -> Dict[str, Any]:
    url = "https://overpass-api.de/api/interpreter"
    r = requests.post(url, data=query.encode("utf-8"), headers={"User-Agent": "streamlit-osm-demo"}, timeout=60)
    r.raise_for_status()
    return r.json()


@st.cache_data(show_spinner=True, ttl=5*60)
def fetch_overpass_amenities(center: Tuple[float, float], radius_m: int, filters: List[str]) -> Dict[str, pd.DataFrame]:
    """Fetch nodes/ways around center within radius for each filter (e.g., highway=traffic_signals)."""
    lat, lon = center
    results: Dict[str, pd.DataFrame] = {}
    for f in filters:
        # Overpass QL: around:<radius>,<lat>,<lon>
        q = f"""
        [out:json][timeout:60];
        (
          node[{f}](around:{radius_m},{lat},{lon});
          way[{f}](around:{radius_m},{lat},{lon});
          relation[{f}](around:{radius_m},{lat},{lon});
        );
        out center;  // center gives centroid for ways/relations
        """
        try:
            data = _overpass_query(q)
            rows = []
            for el in data.get("elements", []):
                if "lat" in el and "lon" in el:
                    lat_el, lon_el = el["lat"], el["lon"]
                else:
                    # way/relation: use center if provided
                    c = el.get("center")
                    if not c:
                        continue
                    lat_el, lon_el = c["lat"], c["lon"]
                tags = el.get("tags", {})
                rows.append({
                    "id": el.get("id"),
                    "type": el.get("type"),
                    "lat": lat_el,
                    "lon": lon_el,
                    "tags": tags,
                    "name": tags.get("name"),
                    "source_filter": f,
                })
            df = pd.DataFrame(rows)
        except Exception as e:
            st.warning(f"Failed to fetch {f}: {e}")
            df = pd.DataFrame(columns=["id","type","lat","lon","tags","name","source_filter"])
        results[f] = df
    return results


def to_heatmap_points(df: pd.DataFrame) -> List[List[float]]:
    if df.empty:
        return []
    return df[["lat","lon"]].dropna().values.tolist()


# ------------------------
# Sidebar controls
# ------------------------
with st.sidebar:
    st.header("🔎 Search / Area")
    preset = st.selectbox(
        "Choose a preset area",
        [
            "Tokyo Station, Japan",
            "Shinjuku, Tokyo, Japan",
            "Osaka Station, Japan",
            "Nagoya Station, Japan",
            "Shibuya Crossing, Tokyo, Japan",
        ],
        index=0,
    )
    custom = st.text_input("...or search any place (Nominatim):", "", help="City, station, address, landmark, etc.")
    radius = st.slider("Search radius (meters)", min_value=300, max_value=5000, value=1500, step=100)

    st.header("🧩 Data layers (OSM)")
    layer_signals = st.checkbox("Traffic signals (highway=traffic_signals)", value=True)
    layer_bus = st.checkbox("Bus stops (highway=bus_stop OR public_transport=platform)", value=False)
    layer_bike = st.checkbox("Bicycle parking (amenity=bicycle_parking)", value=False)

    st.caption("Note: Queries go to the public Overpass API. Please use moderate radius to avoid rate-limits.")

# Pick center
query_place = custom.strip() if custom.strip() else preset
try:
    center = geocode_place(query_place)
except Exception as e:
    st.error(f"Geocoding failed: {e}")
    st.stop()

st.write(f"**Center:** {query_place} → {center[0]:.5f}, {center[1]:.5f}  |  **Radius:** ~{radius} m")

# Build filters
filters = []
if layer_signals:
    filters.append('highway="traffic_signals"')
if layer_bus:
    # combine OR by fetching both
    filters.append('highway="bus_stop"')
    filters.append('public_transport="platform"')
if layer_bike:
    filters.append('amenity="bicycle_parking"')

if not filters:
    st.info("Select at least one data layer from the sidebar.")
    st.stop()

# Fetch
data_map = fetch_overpass_amenities(center, radius, filters)

# ------------------------
# Map rendering
# ------------------------
m = folium.Map(location=center, zoom_start=15, tiles="OpenStreetMap")
folium.Circle(location=center, radius=radius, color="#3388ff", fill=False, weight=2).add_to(m)

# One marker cluster per logical layer-group
clusters = {}

def add_layer_group(name: str) -> MarkerCluster:
    fg = folium.FeatureGroup(name=name, show=True)
    mc = MarkerCluster(name=name)
    fg.add_child(mc)
    m.add_child(fg)
    clusters[name] = mc
    return mc

if layer_signals:
    mc = add_layer_group("Traffic signals")
    df = data_map.get('highway="traffic_signals"', pd.DataFrame())
    for _, row in df.iterrows():
        popup = folium.Popup(html=f"<b>Traffic signal</b><br>ID: {row['id']}<br>{row.get('name') or ''}", max_width=250)
        folium.Marker(location=(row["lat"], row["lon"]), popup=popup, icon=folium.Icon(icon="lightbulb", prefix="fa")).add_to(mc)
    # optional heatmap
    HeatMap(to_heatmap_points(df), name="Signals heat").add_to(m)

if layer_bus:
    # bus_stop
    mc1 = add_layer_group("Bus stops (highway=bus_stop)")
    df1 = data_map.get('highway="bus_stop"', pd.DataFrame())
    for _, row in df1.iterrows():
        popup = folium.Popup(html=f"<b>Bus stop</b><br>ID: {row['id']}<br>{row.get('name') or ''}", max_width=250)
        folium.Marker(location=(row["lat"], row["lon"]), popup=popup, icon=folium.Icon(icon="bus", prefix="fa")).add_to(mc1)
    # platform
    mc2 = add_layer_group("PT platforms (public_transport=platform)")
    df2 = data_map.get('public_transport="platform"', pd.DataFrame())
    for _, row in df2.iterrows():
        popup = folium.Popup(html=f"<b>Platform</b><br>ID: {row['id']}<br>{row.get('name') or ''}", max_width=250)
        folium.Marker(location=(row["lat"], row["lon"]), popup=popup, icon=folium.Icon(icon="train", prefix="fa")).add_to(mc2)

if layer_bike:
    mc = add_layer_group("Bicycle parking")
    df = data_map.get('amenity="bicycle_parking"', pd.DataFrame())
    for _, row in df.iterrows():
        popup = folium.Popup(html=f"<b>Bicycle parking</b><br>ID: {row['id']}<br>{row.get('name') or ''}", max_width=250)
        folium.Marker(location=(row["lat"], row["lon"]), popup=popup, icon=folium.Icon(icon="bicycle", prefix="fa")).add_to(mc)
    HeatMap(to_heatmap_points(df), name="Bicycle parking heat").add_to(m)

folium.LayerControl(collapsed=False).add_to(m)

# Render and capture map interaction
with st.spinner("Rendering map..."):
    map_state = st_folium(m, width=None, height=650)

# ------------------------
# Data tables and export
# ------------------------
st.subheader("📊 Results")
tabs = st.tabs([f"Layer {i+1}" for i in range(len(filters))])

for i, f in enumerate(filters):
    with tabs[i]:
        df = data_map.get(f, pd.DataFrame())
        st.write(f"**Filter:** `{f}`  |  **Count:** {len(df)}")
        if len(df) > 0:
            st.dataframe(df[["id", "type", "lat", "lon", "name"]])
            # download buttons
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button("⬇️ Download CSV", data=csv, file_name=f"osm_{f.replace('"','').replace('=','-')}.csv", mime="text/csv")
        else:
            st.info("No features found for this layer in the current radius.")

st.markdown("""
---
### ℹ️ Notes
- This demo uses **OpenStreetMap** data via the public **Overpass API** and **Nominatim** geocoding. Please keep searches modest to avoid rate-limits.
- You can adapt the filters to any OSM tag, e.g. `amenity=hospital`, `amenity=school`, `shop=convenience`, etc.
- Idea starters for next steps:
  - Join with your city’s **open data portal** (traffic counts, crash data, signal timings) and render as additional layers.
  - Add **routing** or **isochrones** (e.g., OSRM/GraphHopper APIs) to evaluate accessibility.
  - Compute analytics like nearest bus stop to each POI, density per km², etc.
""")
