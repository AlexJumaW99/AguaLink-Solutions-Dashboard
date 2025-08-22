"""
Home Page - Manitoba Municipalities & Incidents Map

This module contains the home page function that displays the main map interface.
"""
import json
import os
import streamlit as st
import folium
from streamlit_folium import st_folium
import osmnx as ox
import geopandas as gpd

# Import helpers from utils folder
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
    
    # Add Manitoba boundary outline
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

def load_default_incidents():
    """Load the default incidents data from file"""
    inc_default = "data/incidents_dummy.geojson"
    if os.path.exists(inc_default):
        with open(inc_default, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"type": "FeatureCollection", "features": []}

def create_metric_card_html():
    """Create custom CSS for metric cards with hover effects"""
    return """
    <style>
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 10px;
        padding: 20px;
        color: white;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        transition: all 0.3s ease;
        height: 100%;
        display: flex;
        flex-direction: column;
        justify-content: center;
    }
    
    .metric-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 8px 15px rgba(0, 0, 0, 0.2);
        background: linear-gradient(135deg, #764ba2 0%, #667eea 100%);
    }
    
    .metric-card.municipalities {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    }
    .metric-card.municipalities:hover {
        background: linear-gradient(135deg, #764ba2 0%, #667eea 100%);
    }
    
    .metric-card.population {
        background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
    }
    .metric-card.population:hover {
        background: linear-gradient(135deg, #f5576c 0%, #f093fb 100%);
    }
    
    .metric-card.wildfires {
        background: linear-gradient(135deg, #fa709a 0%, #fee140 100%);
    }
    .metric-card.wildfires:hover {
        background: linear-gradient(135deg, #fee140 0%, #fa709a 100%);
    }
    
    .metric-card.floods {
        background: linear-gradient(135deg, #30cfd0 0%, #330867 100%);
    }
    .metric-card.floods:hover {
        background: linear-gradient(135deg, #330867 0%, #30cfd0 100%);
    }
    
    .metric-card.datasource {
        background: linear-gradient(135deg, #a8edea 0%, #fed6e3 100%);
        color: #333;
    }
    .metric-card.datasource:hover {
        background: linear-gradient(135deg, #fed6e3 0%, #a8edea 100%);
    }
    
    .metric-value {
        font-size: 2em;
        font-weight: bold;
        margin: 5px 0;
    }
    
    .metric-label {
        font-size: 0.9em;
        opacity: 0.9;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    
    .metric-icon {
        font-size: 1.5em;
        margin-bottom: 10px;
    }
    </style>
    """

def home_page():
    """Main function for the Home Page - called by st.Page"""
    
    st.title("Manitoba Cities/Towns + Wildfires & Floods")
    st.caption("Click municipal polygons for details • Wildfire/Flood markers (local SVGs) • Incident polygons from a separate file")

    # Add custom CSS for metric cards
    st.markdown(create_metric_card_html(), unsafe_allow_html=True)

    # -------------------------- Load Manitoba Boundary --------------------------
    with st.spinner("Loading Manitoba boundary..."):
        manitoba_boundary = get_manitoba_boundary()

    # -------------------------- Sidebar: Municipality Info --------------------------
    with st.sidebar:
        # Load Municipality data (fixed file only)
        muni_default = "data/mb_with_winnipeg.geojson"
        
        if os.path.exists(muni_default):
            with open(muni_default, "r", encoding="utf-8") as f:
                muni = json.load(f)
        else:
            st.error(f"Municipality file not found: {muni_default}")
            st.stop()

        # Initialize and load incidents data
        if 'incidents_data' not in st.session_state:
            st.session_state.incidents_data = load_default_incidents()
            st.session_state.incidents_source = "default"
        
        incidents_data = st.session_state.incidents_data
        
        # Display incident data status
        st.header("📊 Incident Data Status")
        if st.session_state.incidents_source == "default":
            st.info("Using default incident data")
        else:
            total_sources = 1 + len(st.session_state.get('upload_history', []))
            st.success(f"Using merged data from {total_sources} source(s)")
            
        # Show incident count
        incident_count = len(incidents_data.get("features", []))
        st.metric("Total Incidents", incident_count)
        
        # Option to reset data
        if st.session_state.incidents_source != "default":
            if st.button("🔄 Reset to Default Data", type="secondary", use_container_width=True):
                st.session_state.incidents_data = load_default_incidents()
                st.session_state.incidents_source = "default"
                if 'upload_history' in st.session_state:
                    del st.session_state.upload_history
                st.success("Reset to default incident data!")
                st.rerun()

        st.divider()

        # Municipality filters
        muni_feats = muni.get("features", [])
        normalize_muni_properties(muni_feats)

        st.header("🎯 Municipality Filters")
        statuses = sorted({f["properties"].get("status", "Unknown") for f in muni_feats})
        pops = [f["properties"].get("population_2021") for f in muni_feats if isinstance(f["properties"].get("population_2021"), (int, float))]
        pop_min = int(min(pops)) if pops else 0
        pop_max = int(max(pops)) if pops else 0
        
        sel_status = st.multiselect("Status", options=statuses, default=statuses)
        sel_pop = st.slider("Population (2021) range", min_value=0, max_value=pop_max, value=(pop_min, pop_max), step=1)

        muni_filtered = [f for f in muni_feats if muni_passes(f, sel_status, sel_pop)]
        st.write(f"**Selected places:** {len(muni_filtered)} / {len(muni_feats)}")
        
        # Display warnings when no municipalities are selected
        if len(muni_filtered) == 0:
            if len(sel_status) == 0:
                st.warning("⚠️ Please select at least one municipality status to see boundaries and population data on the map")
            elif sel_pop[1] == 0:
                st.warning("⚠️ Please increase the population range to see municipality data on the map")
            else:
                st.warning("⚠️ No municipalities match the current filter criteria")

        st.divider()

        # Incident filters
        st.header("🔥💧 Incident Filters")
        show_wf = st.checkbox("Show Wildfires", value=True)
        show_fl = st.checkbox("Show Floods", value=True)
        inc_status_filter = st.multiselect("Incident status", options=["confirmed","suspected"], default=["confirmed","suspected"])

        st.divider()

        # Map Display options
        st.header("🗺️ Map Display")
        show_mask = st.checkbox("Show Manitoba Focus Mask", value=True, help="Adds a gray overlay outside Manitoba province")

    # -------------------------- Main Content Area --------------------------
    
    # Split incidents by type
    wf_features, fl_features = split_incidents(incidents_data, inc_status_filter)

    # Calculate metrics
    total_pop = sum(f["properties"].get("population_2021", 0) for f in muni_filtered if isinstance(f["properties"].get("population_2021"), (int, float)))
    wf_count = len(wf_features) if show_wf else 0
    fl_count = len(fl_features) if show_fl else 0
    source_label = "Default" if st.session_state.incidents_source == "default" else "Merged"
    
    # Display beautified metric cards
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.markdown(f"""
        <div class="metric-card municipalities">
            <div class="metric-icon">🏛️</div>
            <div class="metric-value">{len(muni_filtered)}</div>
            <div class="metric-label">Municipalities</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class="metric-card population">
            <div class="metric-icon">👥</div>
            <div class="metric-value">{total_pop:,}</div>
            <div class="metric-label">Total Population (2021)</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div class="metric-card wildfires">
            <div class="metric-icon">🔥</div>
            <div class="metric-value">{wf_count}</div>
            <div class="metric-label">Wildfires</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        st.markdown(f"""
        <div class="metric-card floods">
            <div class="metric-icon">💧</div>
            <div class="metric-value">{fl_count}</div>
            <div class="metric-label">Floods</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col5:
        st.markdown(f"""
        <div class="metric-card datasource">
            <div class="metric-icon">📁</div>
            <div class="metric-value">{source_label}</div>
            <div class="metric-label">Data Source</div>
        </div>
        """, unsafe_allow_html=True)
    
    # Add some spacing after the cards
    st.markdown("<br>", unsafe_allow_html=True)

    # Load local SVG icons
    fire_icon_path = os.path.join("images", "fire-svgrepo-com.svg")
    flood_icon_path = os.path.join("images", "water-fee-svgrepo-com.svg")
    fire_svg_icon = load_svg_icon(fire_icon_path, size=(30, 30))
    flood_svg_icon = load_svg_icon(flood_icon_path, size=(30, 30))

    # Create and display the map
    st.subheader("🔍 Interactive Map")
    
    # Add info about data freshness
    if st.session_state.incidents_source != "default" and 'upload_history' in st.session_state:
        last_upload = st.session_state.upload_history[-1]
        st.info(f"📌 Map includes {last_upload['new_incidents']} new incident(s) from last upload: {last_upload['filename']} at {last_upload['timestamp']}")
    
    # Display info message when no municipality data is shown
    if len(muni_filtered) == 0:
        st.info("ℹ️ Municipality boundaries and population data are currently filtered out. Showing incident data only.")
    
    # Calculate map center and zoom
    if manitoba_boundary is not None:
        ctr_lat, ctr_lon = 53.7609, -98.8139
        zoom_level = 5
    else:
        # Use all features for bounds if no municipalities are selected
        if muni_filtered:
            feats_for_bounds = muni_filtered
        elif wf_features or fl_features:
            # Use incident features for bounds if no municipalities
            feats_for_bounds = wf_features + fl_features
        else:
            # Fallback to all municipality features
            feats_for_bounds = muni_feats
        
        if feats_for_bounds:
            south_west, north_east = get_bounds(feats_for_bounds)
            ctr_lat = (south_west[0] + north_east[0]) / 2
            ctr_lon = (south_west[1] + north_east[1]) / 2
        else:
            # Default Manitoba center
            ctr_lat, ctr_lon = 53.7609, -98.8139
        zoom_level = 5
    
    # Initialize map
    m = folium.Map(
        location=[ctr_lat, ctr_lon], 
        zoom_start=zoom_level, 
        control_scale=True, 
        tiles="OpenStreetMap"
    )

    # Add Manitoba mask if enabled
    if show_mask and manitoba_boundary is not None:
        add_manitoba_mask(m, manitoba_boundary)

    # Add municipalities layer only if there are filtered municipalities
    if len(muni_filtered) > 0:
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

    # Add wildfire markers
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
            # Add source indicator for merged data
            source_indicator = " [User Added]" if st.session_state.incidents_source == "merged" and props.get("user_added", False) else ""
            html = f"<b>{name}{source_indicator}</b><br>Type: Wildfire<br>Confidence: {conf}<br>Started: {started}<br>Details: {desc}"
            folium.Marker(
                location=(lat, lon),
                icon=icon_for_feature(props, fire_icon=fire_svg_icon),
                tooltip=f"{name} • {conf}",
                popup=folium.Popup(html, max_width=350)
            ).add_to(wf_layer)
        wf_layer.add_to(m)

    # Add flood markers
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
            # Add source indicator for merged data
            source_indicator = " [User Added]" if st.session_state.incidents_source == "merged" and props.get("user_added", False) else ""
            html = f"<b>{name}{source_indicator}</b><br>Type: Flood<br>Confidence: {conf}<br>Started: {started}<br>Details: {desc}"
            folium.Marker(
                location=(lat, lon),
                icon=icon_for_feature(props, flood_icon=flood_svg_icon),
                tooltip=f"{name} • {conf}",
                popup=folium.Popup(html, max_width=350)
            ).add_to(fl_layer)
        fl_layer.add_to(m)

    # Fit map bounds
    if manitoba_boundary is not None and show_mask:
        bounds = manitoba_boundary.total_bounds
        m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])
    else:
        # Determine what features to use for bounds
        if muni_filtered:
            feats_for_bounds = muni_filtered
        elif show_wf and wf_features:
            feats_for_bounds = wf_features
        elif show_fl and fl_features:
            feats_for_bounds = fl_features
        else:
            feats_for_bounds = []
        
        if feats_for_bounds:
            south_west, north_east = get_bounds(feats_for_bounds)
            m.fit_bounds([south_west, north_east])

    # Add layer control and render map
    folium.LayerControl(collapsed=True).add_to(m)
    st_folium(m, width=None, height=720, key="main_map")

    # Display warnings about missing data
    if len(muni_filtered) == 0:
        st.info("💡 Tip: Adjust the municipality filters in the sidebar to display boundary and population data on the map.")
    
    if show_wf and len(wf_features) == 0:
        st.warning("No wildfires matched the current incident status filter, or none found in the file.")
    
    if show_fl and len(fl_features) == 0:
        st.warning("No floods matched the current incident status filter, or none found in the file.")
    
    if not show_wf and not show_fl:
        st.warning("⚠️ Both wildfire and flood displays are disabled. Enable at least one in the sidebar to see incident data.")