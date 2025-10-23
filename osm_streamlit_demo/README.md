
# OSM + Open Data Streamlit Demo

A minimal Streamlit app that queries OpenStreetMap via Overpass and visualizes results on a Folium map.

## How to run

```bash
# 1) Create and activate a virtual env (optional but recommended)
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# 2) Install dependencies
pip install -r requirements.txt

# 3) Launch
streamlit run app.py
```

## Features
- Geocode a place (Nominatim) and search within a radius
- Toggle layers like **traffic signals**, **bus stops**, and **bicycle parking**
- Marker clustering + optional heatmaps
- Export results as CSV

## Customize
Open `app.py` and edit the `filters` in the sidebar code to any OSM tag
(e.g., `amenity=hospital`, `amenity=school`, `shop=convenience`).

**Tip:** Be gentle with the public Overpass API; keep the radius reasonable.
