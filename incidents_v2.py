"""
Manitoba Municipalities & Incidents – Streamlit Map with Province Mask

This app shows:
  • Manitoba city/town polygons (from your GeoJSON) with clickable popups
  • Wildfire & flood incidents from a separate file (polygons + marker icons)
  • Manitoba-only focus with mask covering areas outside the province

Helpers live in utils.py to keep this file concise.
"""
import json
import os
import streamlit as st
import folium
from streamlit_folium import st_folium
import osmnx as ox
import geopandas as gpd

# Import helpers from utils.py
from utils.utils import (
    iter_coords,
    get_bounds,
    centroid_of_feature,
    style_for_feature,
    make_muni_style,
    load_svg_icon,
    icon_for_feature,
    normalize_muni_properties,
    split_incidents,
    muni_passes,
)

# -------------------------- Manitoba Boundary Function --------------------------
@st.cache_data
def get_manitoba_boundary():
    """Get Manitoba's boundary using OSMnx"""
    try:
        # Download Manitoba's boundary polygon
        manitoba = ox.geocode_to_gdf("Manitoba, Canada")
        return manitoba
    except:
        st.error("Could not fetch Manitoba boundary. Check internet connection.")
        return None

def add_manitoba_mask(m, manitoba_gdf):
    """Add a mask that covers everything outside Manitoba"""
    if manitoba_gdf is None:
        return
    
    # Get Manitoba geometry coordinates
    manitoba_geom = manitoba_gdf.geometry.iloc[0]
    
    # Handle single polygon or multipolygon
    if hasattr(manitoba_geom, 'exterior'):
        # Single polygon
        manitoba_coords = [[list(coord)[::-1] for coord in manitoba_geom.exterior.coords]]
    else:
        # MultiPolygon - use the largest one
        largest = max(manitoba_geom.geoms, key=lambda x: x.area)
        manitoba_coords = [[list(coord)[::-1] for coord in largest.exterior.coords]]
    
    # Create the mask (world with Manitoba hole)
    mask_geojson = {
        "type": "Feature",
        "properties": {},
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [[-180, -90], [180, -90], [180, 90], [-180, 90], [-180, -90]],
                [coord[::-1] for coord in manitoba_coords[0]]  # Hole for Manitoba
            ]
        }
    }
    
    # Add the mask with no highlight effect
    folium.GeoJson(
        mask_geojson,
        style_function=lambda x: {
            'fillColor': '#f0f0f0',
            'color': '#f0f0f0',
            'weight': 0,
            'fillOpacity': 0.8
        },
        highlight_function=lambda x: {
            'fillColor': '#f0f0f0',
            'color': '#f0f0f0',
            'weight': 0,
            'fillOpacity': 0.8
        },
        name="Outside Manitoba Mask"
    ).add_to(m)
    
    # Add Manitoba boundary outline (optional - can be commented out if you don't want the blue border)
    folium.GeoJson(
        manitoba_gdf.to_json(),
        style_function=lambda x: {
            'fillColor': 'transparent',
            'color': '#0066cc',
            'weight': 2,
            'fillOpacity': 0
        },
        highlight_function=lambda x: {
            'fillColor': 'transparent',
            'color': '#0066cc',
            'weight': 2,
            'fillOpacity': 0
        },
        name="Manitoba Boundary"
    ).add_to(m)

# -------------------------- App Setup --------------------------
st.set_page_config(page_title="Manitoba Municipalities & Incidents", layout="wide")
st.title("Manitoba Cities/Towns + Wildfires & Floods")
st.caption("Click municipal polygons for details • Wildfire/Flood markers (local SVGs) • Incident polygons from a separate file")

# -------------------------- Load Manitoba Boundary --------------------------
with st.spinner("Loading Manitoba boundary..."):
    manitoba_boundary = get_manitoba_boundary()

# -------------------------- Sidebar: Municipality data --------------------------
st.sidebar.header("Municipality Data")
muni_default = "data/mb_with_winnipeg.geojson"
muni_upload = st.sidebar.file_uploader("Upload Cities/Towns GeoJSON (optional)", type=["geojson","json"])

if muni_upload is not None:
    muni = json.load(muni_upload)
    muni_src = "Using uploaded municipality file"
else:
    if os.path.exists(muni_default):
        with open(muni_default, "r", encoding="utf-8") as f:
            muni = json.load(f)
        muni_src = f'Loaded local file: "{muni_default}"'
    else:
        st.error("No municipality file found. Upload a GeoJSON via the sidebar.")
        st.stop()
st.sidebar.markdown(f"**{muni_src}**")

# -------------------------- Sidebar: Incidents data --------------------------
st.sidebar.header("Incidents Data")
inc_default = "data/incidents_dummy.geojson"
inc_upload = st.sidebar.file_uploader("Upload incidents (GeoJSON or custom JSON)", type=["geojson","json"])

if inc_upload is not None:
    incidents_data = json.load(inc_upload)
    inc_src = "Using uploaded incidents file"
else:
    if os.path.exists(inc_default):
        with open(inc_default, "r", encoding="utf-8") as f:
            incidents_data = json.load(f)
        inc_src = f'Loaded local file: "{inc_default}"'
    else:
        incidents_data = {"type":"FeatureCollection","features":[]}
        inc_src = "No incidents file found (empty)"
st.sidebar.markdown(f"**{inc_src}**")

# -------------------------- Municipality filters --------------------------
muni_feats = muni.get("features", [])
normalize_muni_properties(muni_feats)

st.sidebar.header("Municipality Filters")
statuses = sorted({f["properties"].get("status", "Unknown") for f in muni_feats})
pops = [f["properties"].get("population_2021") for f in muni_feats if isinstance(f["properties"].get("population_2021"), (int, float))]
pop_min = int(min(pops)) if pops else 0
pop_max = int(max(pops)) if pops else 0
sel_status = st.sidebar.multiselect("Status", options=statuses, default=statuses)
sel_pop = st.sidebar.slider("Population (2021) range", min_value=pop_min, max_value=pop_max, value=(pop_min, pop_max), step=1)

muni_filtered = [f for f in muni_feats if muni_passes(f, sel_status, sel_pop)]
st.sidebar.write(f"**Selected places:** {len(muni_filtered)} / {len(muni_feats)}")

# -------------------------- Incident filters & split --------------------------
st.sidebar.header("Incident Filters")
show_wf = st.sidebar.checkbox("Show Wildfires", value=True)
show_fl = st.sidebar.checkbox("Show Floods", value=True)
inc_status_filter = st.sidebar.multiselect("Incident status", options=["confirmed","suspected"], default=["confirmed","suspected"])

# Manitoba Mask Toggle
st.sidebar.header("Map Display")
show_mask = st.sidebar.checkbox("Show Manitoba Focus Mask", value=True, help="Adds a gray overlay outside Manitoba province")

wf_features, fl_features = split_incidents(incidents_data, inc_status_filter)

# Metrics
total_pop = sum(f["properties"].get("population_2021", 0) for f in muni_filtered if isinstance(f["properties"].get("population_2021"), (int, float)))
colA, colB, colC, colD = st.columns(4)
with colA:
    st.metric("Municipalities", len(muni_filtered))
with colB:
    st.metric("Selected Population (2021)", f"{total_pop:,}")
with colC:
    st.metric("Wildfires (shown)", len(wf_features) if show_wf else 0)
with colD:
    st.metric("Floods (shown)", len(fl_features) if show_fl else 0)

# -------------------------- Load local SVG icons --------------------------
# Expect SVGs in ./images relative to this script; fall back gracefully.
fire_icon_path  = os.path.join("images", "fire-svgrepo-com.svg")
flood_icon_path = os.path.join("images", "water-fee-svgrepo-com.svg")
fire_svg_icon  = load_svg_icon(fire_icon_path, size=(30, 30))
flood_svg_icon = load_svg_icon(flood_icon_path, size=(30, 30))

# -------------------------- Map --------------------------
left, center, right = st.columns([1, 6, 1])
with center:
    # Use Manitoba's center if available, otherwise calculate from features
    if manitoba_boundary is not None:
        # Manitoba's center
        ctr_lat, ctr_lon = 53.7609, -98.8139
        zoom_level = 10
    else:
        # Calculate from municipality features
        feats_for_bounds = muni_filtered if muni_filtered else muni_feats
        south_west, north_east = get_bounds(feats_for_bounds)
        ctr_lat = (south_west[0] + north_east[0]) / 2
        ctr_lon = (south_west[1] + north_east[1]) / 2
        zoom_level = 10
    
    m = folium.Map(
        location=[ctr_lat, ctr_lon], 
        zoom_start=zoom_level, 
        control_scale=True, 
        tiles="OpenStreetMap"
    )

    # Add Manitoba mask if enabled
    if show_mask and manitoba_boundary is not None:
        add_manitoba_mask(m, manitoba_boundary)

    # Municipalities: clickable polygons + popup
    muni_popup = folium.GeoJsonPopup(
        fields=["name", "status", "population_2021"],
        aliases=["Name", "Status", "Population (2021)"],
        localize=True,
        labels=True,
        style="background-color:white; font-size:14px;"
    )
    muni_tooltip = folium.GeoJsonTooltip(
        fields=["name", "status", "population_2021"],
        aliases=["Name", "Status", "Population (2021)"],
        localize=True,
        sticky=False,
    )
    folium.GeoJson(
        {"type": "FeatureCollection", "features": muni_filtered},
        name="Municipal Boundaries",
        style_function=make_muni_style,
        tooltip=muni_tooltip,
        popup=muni_popup,
        highlight_function=lambda x: {"weight": 3},
    ).add_to(m)

    # Wildfires
    if show_wf:
        wf_layer = folium.FeatureGroup(name="Wildfires", show=True)
        for f in wf_features:
            props = f.get("properties", {})
            # Polygon
            folium.GeoJson(
                f,
                style_function=lambda _f, p=props: style_for_feature(p),
                highlight_function=lambda x: {"weight": 3}
            ).add_to(wf_layer)
            # Marker at centroid
            lat, lon = centroid_of_feature(f)
            name = props.get("name", "Wildfire")
            conf = (props.get("status") or props.get("confidence") or "unknown").title()
            started = props.get("started_at", "")
            desc = props.get("description", "")
            html = f"<b>{name}</b><br>Type: Wildfire<br>Confidence: {conf}<br>Started: {started}<br>Details: {desc}"
            folium.Marker(
                location=(lat, lon),
                icon=icon_for_feature(props, fire_icon=fire_svg_icon),
                tooltip=f"{name} • {conf}",
                popup=folium.Popup(html, max_width=350)
            ).add_to(wf_layer)
        wf_layer.add_to(m)

    # Floods
    if show_fl:
        fl_layer = folium.FeatureGroup(name="Floods", show=True)
        for f in fl_features:
            props = f.get("properties", {})
            # Polygon
            folium.GeoJson(
                f,
                style_function=lambda _f, p=props: style_for_feature(p),
                highlight_function=lambda x: {"weight": 3}
            ).add_to(fl_layer)
            # Marker at centroid
            lat, lon = centroid_of_feature(f)
            name = props.get("name", "Flood")
            conf = (props.get("status") or props.get("confidence") or "unknown").title()
            started = props.get("started_at", "")
            desc = props.get("description", "")
            html = f"<b>{name}</b><br>Type: Flood<br>Confidence: {conf}<br>Started: {started}<br>Details: {desc}"
            folium.Marker(
                location=(lat, lon),
                icon=icon_for_feature(props, flood_icon=flood_svg_icon),
                tooltip=f"{name} • {conf}",
                popup=folium.Popup(html, max_width=350)
            ).add_to(fl_layer)
        fl_layer.add_to(m)

    # Fit to Manitoba bounds if available, otherwise fit to municipalities
    if manitoba_boundary is not None and show_mask:
        bounds = manitoba_boundary.total_bounds  # minx, miny, maxx, maxy
        m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])
    else:
        # Fit to municipalities
        feats_for_bounds = muni_filtered if muni_filtered else muni_feats
        if feats_for_bounds:
            south_west, north_east = get_bounds(feats_for_bounds)
            m.fit_bounds([south_west, north_east])

    folium.LayerControl(collapsed=True).add_to(m)
    st_folium(m, width=None, height=720)

# Diagnostics if nothing shows
if show_wf and len(wf_features) == 0:
    st.warning("No wildfires matched the current incident status filter, or none found in the file.")
if show_fl and len(fl_features) == 0:
    st.warning("No floods matched the current incident status filter, or none found in the file.")