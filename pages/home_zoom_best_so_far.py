"""
Enhanced home.py with comprehensive map state persistence and zoom-to-feature functionality.

Key Features:
1. Map viewport persistence across Streamlit reruns
2. Zoom-to-feature on marker/polygon clicks
3. Seamless user experience with retained map context
"""
import json
import os
import streamlit as st
import folium
from streamlit_folium import st_folium
import osmnx as ox
import geopandas as gpd
import numpy as np

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

# -------------------------- Map State Management --------------------------

def initialize_map_state():
    """Initialize map state in session_state if not present"""
    if 'map_state' not in st.session_state:
        st.session_state.map_state = {
            'center': [53.7609, -98.8139],  # Default Manitoba center
            'zoom': 5,
            'bounds': None,
            'last_clicked_feature': None,
            'zoom_to_feature': False
        }

def update_map_state_from_interaction(map_data):
    """Update map state based on user interaction with the map"""
    if map_data and 'center' in map_data:
        # Update center and zoom from map interaction
        st.session_state.map_state['center'] = [
            map_data['center']['lat'], 
            map_data['center']['lng']
        ]
        st.session_state.map_state['zoom'] = map_data['zoom']
        # Clear bounds when user manually interacts with map
        st.session_state.map_state['bounds'] = None
        st.session_state.map_state['zoom_to_feature'] = False
        
        # st.json()

def calculate_feature_bounds(feature):
    """Calculate bounds for a single feature (municipality or incident)"""
    geom = feature.get('geometry', {})
    if not geom:
        return None
    
    coords = []
    for lon, lat in iter_coords(geom):
        coords.append([lat, lon])
    
    if not coords:
        return None
    
    lats = [c[0] for c in coords]
    lons = [c[1] for c in coords]
    
    # Calculate bounds with some padding
    lat_padding = (max(lats) - min(lats)) * 0.1 or 0.01
    lon_padding = (max(lons) - min(lons)) * 0.1 or 0.01
    
    return [
        [min(lats) - lat_padding, min(lons) - lon_padding],  # Southwest
        [max(lats) + lat_padding, max(lons) + lon_padding]   # Northeast
    ]

def find_clicked_feature(clicked_lat, clicked_lng, muni_features, wf_features, fl_features):
    """Find which feature was clicked based on coordinates"""
    
    def point_in_polygon_bounds(lat, lng, feature):
        """Check if point is roughly within feature bounds (simplified)"""
        geom = feature.get('geometry', {})
        if not geom:
            return False, float('inf')
        
        # Get feature centroid
        center_lat, center_lon = centroid_of_feature(feature)
        
        # Calculate distance from click to centroid
        distance = np.sqrt((lat - center_lat)**2 + (lng - center_lon)**2)
        
        # For polygons, check if click is within reasonable bounds
        coords = list(iter_coords(geom))
        if coords:
            lats = [c[1] for c in coords]
            lons = [c[0] for c in coords]
            lat_range = max(lats) - min(lats)
            lon_range = max(lons) - min(lons)
            max_range = max(lat_range, lon_range)
            
            # Consider it a match if within the feature's bounding area
            if (min(lats) <= lat <= max(lats) and 
                min(lons) <= lng <= max(lons)):
                return True, distance
            
            # Or if very close to centroid (for markers)
            if distance < max(0.05, max_range * 0.5):
                return True, distance
        
        return False, distance
    
    best_feature = None
    best_distance = float('inf')
    
    # Check all feature types
    all_features = [
        (muni_features, 'municipality'),
        (wf_features, 'wildfire'),
        (fl_features, 'flood')
    ]
    
    for features, feature_type in all_features:
        for feature in features:
            is_match, distance = point_in_polygon_bounds(clicked_lat, clicked_lng, feature)
            if is_match and distance < best_distance:
                best_distance = distance
                best_feature = (feature, feature_type)
    
    return best_feature

def zoom_to_feature(feature, feature_type):
    """Set map state to zoom to a specific feature"""
    bounds = calculate_feature_bounds(feature)
    if bounds:
        st.session_state.map_state['bounds'] = bounds
        st.session_state.map_state['zoom_to_feature'] = True
        
        # Update center to feature center
        center_lat = (bounds[0][0] + bounds[1][0]) / 2
        center_lon = (bounds[0][1] + bounds[1][1]) / 2
        st.session_state.map_state['center'] = [center_lat, center_lon]
        
        # Store clicked feature info
        feature_name = feature.get('properties', {}).get('name', f'Unknown {feature_type}')
        st.session_state.map_state['last_clicked_feature'] = {
            'name': feature_name,
            'type': feature_type
        }

# -------------------------- Existing helper functions (unchanged) --------------------------

@st.cache_data
def get_manitoba_boundary():
    """Get Manitoba's boundary using OSMnx"""
    try:
        manitoba = ox.geocode_to_gdf("Manitoba, Canada")
        return manitoba
    except:
        st.error("Could not fetch Manitoba boundary. Check internet connection.")
        return None

def add_manitoba_mask(m, manitoba_gdf):
    """Add a mask that covers everything outside Manitoba"""
    if manitoba_gdf is None:
        return
    
    manitoba_geom = manitoba_gdf.geometry.iloc[0]
    
    if hasattr(manitoba_geom, 'exterior'):
        manitoba_coords = [[list(coord)[::-1] for coord in manitoba_geom.exterior.coords]]
    else:
        largest = max(manitoba_geom.geoms, key=lambda x: x.area)
        manitoba_coords = [[list(coord)[::-1] for coord in largest.exterior.coords]]
    
    mask_geojson = {
        "type": "Feature",
        "properties": {},
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [[-180, -90], [180, -90], [180, 90], [-180, 90], [-180, -90]],
                [coord[::-1] for coord in manitoba_coords[0]]
            ]
        }
    }
    
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

# -------------------------- Main Home Page Function --------------------------

def home_page():
    """Main function for the Home Page with enhanced map state persistence"""
    
    # Initialize map state
    initialize_map_state()
    
    st.title("Manitoba Cities/Towns + Wildfires & Floods")
    st.caption("Click municipal polygons for details • Wildfire/Flood markers (local SVGs) • Incident polygons from a separate file")

    # Add custom CSS for metric cards
    st.markdown(create_metric_card_html(), unsafe_allow_html=True)

    # Display current map state info (for debugging/user feedback)
    if st.session_state.map_state['last_clicked_feature']:
        clicked_info = st.session_state.map_state['last_clicked_feature']
        st.info(f"🎯 Currently focused on: {clicked_info['name']} ({clicked_info['type']})")

    # Reset view button
    col_reset, col_spacer = st.columns([1, 4])
    with col_reset:
        if st.button("🔄 Reset Map View", help="Reset map to default Manitoba view"):
            st.session_state.map_state = {
                'center': [53.7609, -98.8139],
                'zoom': 5,
                'bounds': None,
                'last_clicked_feature': None,
                'zoom_to_feature': False
            }
            st.rerun()

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
            <div class="metric-icon">🛖</div>
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
            <div class="metric-icon">📄</div>
            <div class="metric-value">{source_label}</div>
            <div class="metric-label">Data Source</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)

    # Load local SVG icons
    fire_icon_path = os.path.join("images", "fire-svgrepo-com.svg")
    flood_icon_path = os.path.join("images", "water-fee-svgrepo-com.svg")
    fire_svg_icon = load_svg_icon(fire_icon_path, size=(30, 30))
    flood_svg_icon = load_svg_icon(flood_icon_path, size=(30, 30))

    # Create and display the map
    st.subheader("🗺️ Interactive Map")
    
    # Add info about data freshness
    if st.session_state.incidents_source != "default" and 'upload_history' in st.session_state:
        last_upload = st.session_state.upload_history[-1]
        st.info(f"📌 Map includes {last_upload['new_incidents']} new incident(s) from last upload: {last_upload['filename']} at {last_upload['timestamp']}")
    
    # Display info message when no municipality data is shown
    if len(muni_filtered) == 0:
        st.info("ℹ️ Municipality boundaries and population data are currently filtered out. Showing incident data only.")
    
    # -------------------------- Map Creation with State Persistence --------------------------
    
    # Use stored map state for center and zoom
    map_center = st.session_state.map_state['center']
    map_zoom = st.session_state.map_state['zoom']
    
    # Initialize map with persisted state
    m = folium.Map(
        location=map_center, 
        zoom_start=map_zoom, 
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
            source_indicator = " [User Added]" if st.session_state.incidents_source == "merged" and props.get("user_added", False) else ""
            html = f"<b>{name}{source_indicator}</b><br>Type: Wildfire<br>Confidence: {conf}<br>Started: {started}<br>Details: {desc}<br><i>Click to zoom to this feature</i>"
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
            source_indicator = " [User Added]" if st.session_state.incidents_source == "merged" and props.get("user_added", False) else ""
            html = f"<b>{name}{source_indicator}</b><br>Type: Flood<br>Confidence: {conf}<br>Started: {started}<br>Details: {desc}<br><i>Click to zoom to this feature</i>"
            folium.Marker(
                location=(lat, lon),
                icon=icon_for_feature(props, flood_icon=flood_svg_icon),
                tooltip=f"{name} • {conf}",
                popup=folium.Popup(html, max_width=350)
            ).add_to(fl_layer)
        fl_layer.add_to(m)

    # Apply bounds if zooming to feature
    if st.session_state.map_state['zoom_to_feature'] and st.session_state.map_state['bounds']:
        m.fit_bounds(st.session_state.map_state['bounds'])
        # Reset the zoom_to_feature flag after applying
        st.session_state.map_state['zoom_to_feature'] = False
    else:
        # Fit map bounds based on available data only if no specific zoom target
        if manitoba_boundary is not None and show_mask and not st.session_state.map_state['last_clicked_feature']:
            bounds = manitoba_boundary.total_bounds
            m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])
        elif not st.session_state.map_state['last_clicked_feature']:
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

    # Add layer control
    folium.LayerControl(collapsed=True).add_to(m)
    
    # Render map and capture interactions
    map_data = st_folium(
        m, 
        width=None, 
        height=720, 
        key="main_map",
        returned_objects=["last_object_clicked", "center", "zoom", "bounds"]
    )

    # -------------------------- Handle Map Interactions --------------------------
    
    # Update map state from user interaction (pan/zoom)
    if map_data:
        update_map_state_from_interaction(map_data)
    
    # Handle clicks on features (markers/polygons)
    if map_data and map_data.get('last_object_clicked'):
        clicked_lat = map_data['last_object_clicked']['lat']
        clicked_lng = map_data['last_object_clicked']['lng']
        
        # Find which feature was clicked
        clicked_feature_info = find_clicked_feature(
            clicked_lat, clicked_lng, 
            muni_filtered, wf_features, fl_features
        )
        
        if clicked_feature_info:
            feature, feature_type = clicked_feature_info
            zoom_to_feature(feature, feature_type)
            st.rerun()  # Trigger rerun to apply zoom

    # Display warnings about missing data
    if len(muni_filtered) == 0:
        st.info("💡 Tip: Adjust the municipality filters in the sidebar to display boundary and population data on the map.")
    
    if show_wf and len(wf_features) == 0:
        st.warning("No wildfires matched the current incident status filter, or none found in the file.")
    
    if show_fl and len(fl_features) == 0:
        st.warning("No floods matched the current incident status filter, or none found in the file.")
    
    if not show_wf and not show_fl:
        st.warning("⚠️ Both wildfire and flood displays are disabled. Enable at least one in the sidebar to see incident data.")

    # Add usage instructions
    with st.expander("ℹ️ Map Interaction Guide"):
        st.markdown("""
        **🗺️ Map Navigation:**
        - **Pan & Zoom**: Click and drag to pan, use mouse wheel to zoom
        - **Reset View**: Click the "🔄 Reset Map View" button to return to default Manitoba view
        
        **🎯 Click-to-Zoom Features:**
        - **Municipality Polygons**: Click any city/town boundary to zoom to that area
        - **Incident Markers**: Click wildfire 🔥 or flood 💧 markers to zoom to that incident
        - **Incident Areas**: Click the colored polygon areas to zoom to the incident boundaries
        
        **💾 State Persistence:**
        - Your map position and zoom level are automatically saved
        - Adjusting filters won't reset your map view
        - The map remembers your last viewed location across page refreshes
        
        **🔄 Sidebar Filters:**
        - Municipality, wildfire, and flood filters update the map without losing your position
        - Use the incident status filter to show/hide confirmed vs suspected incidents
        """)