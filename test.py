import streamlit as st
import folium
from streamlit_folium import st_folium
import json
import numpy as np
from datetime import datetime

# Page configuration
st.set_page_config(
    page_title="Manitoba Wildfire Monitoring",
    page_icon="🔥",
    layout="wide"
)

st.title("🔥 Manitoba Wildfire Monitoring System")

# Load GeoJSON data
@st.cache_data
def load_geojson_data():
    try:
        with open("data/upload_example.geojson", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        st.error("Could not find data/incidents.geojson file. Please ensure the file exists in the data directory.")
        return None

def calculate_bounds(coordinates):
    """Calculate the bounding box for polygon coordinates"""
    # Flatten the coordinates if it's a nested polygon
    if isinstance(coordinates[0][0][0], list):
        # Multi-polygon
        flat_coords = []
        for polygon in coordinates:
            flat_coords.extend(polygon[0])
    else:
        # Single polygon
        flat_coords = coordinates[0]
    
    lons = [coord[0] for coord in flat_coords]
    lats = [coord[1] for coord in flat_coords]
    
    return {
        'min_lat': min(lats),
        'max_lat': max(lats),
        'min_lon': min(lons),
        'max_lon': max(lons),
        'center_lat': (min(lats) + max(lats)) / 2,
        'center_lon': (min(lons) + max(lons)) / 2
    }

def calculate_zoom_level(bounds):
    """Calculate appropriate zoom level based on bounds"""
    lat_diff = bounds['max_lat'] - bounds['min_lat']
    lon_diff = bounds['max_lon'] - bounds['min_lon']
    
    # Calculate zoom based on the larger dimension
    max_diff = max(lat_diff, lon_diff)
    
    if max_diff > 5:
        return 6
    elif max_diff > 2:
        return 8
    elif max_diff > 1:
        return 9
    elif max_diff > 0.5:
        return 10
    elif max_diff > 0.2:
        return 11
    elif max_diff > 0.1:
        return 12
    else:
        return 13

# Initialize session state
if 'selected_fire' not in st.session_state:
    st.session_state.selected_fire = None

# Load data
geojson_data = load_geojson_data()

if geojson_data is None:
    st.stop()

# Manitoba center coordinates
manitoba_center = [55.0, -98.0]
default_zoom = 6

# Determine map center and zoom based on selected fire
if st.session_state.selected_fire:
    selected_feature = None
    for feature in geojson_data['features']:
        if feature['properties']['name'] == st.session_state.selected_fire:
            selected_feature = feature
            break
    
    if selected_feature:
        bounds = calculate_bounds(selected_feature['geometry']['coordinates'])
        map_center = [bounds['center_lat'], bounds['center_lon']]
        map_zoom = calculate_zoom_level(bounds)
    else:
        map_center = manitoba_center
        map_zoom = default_zoom
else:
    map_center = manitoba_center
    map_zoom = default_zoom

# Create the map
m = folium.Map(
    location=map_center,
    zoom_start=map_zoom,
    tiles='OpenStreetMap'
)

# Add Manitoba boundary (approximate)
manitoba_bounds = [
    [60.0, -102.0],  # Northwest
    [60.0, -89.0],   # Northeast
    [49.0, -89.0],   # Southeast
    [49.0, -102.0],  # Southwest
    [60.0, -102.0]   # Close polygon
]

folium.Polygon(
    locations=[[lat, lon] for lat, lon in manitoba_bounds],
    color='blue',
    weight=2,
    opacity=0.6,
    fill=False,
    popup='Manitoba Province Boundary'
).add_to(m)

# Process and add incidents to map
wildfire_count = 0
flood_count = 0

for feature in geojson_data['features']:
    props = feature['properties']
    coords = feature['geometry']['coordinates']
    
    # Calculate center of the incident area
    bounds = calculate_bounds(coords)
    center_lat = bounds['center_lat']
    center_lon = bounds['center_lon']
    
    # Determine icon and color based on incident type
    if props['type'] == 'wildfire':
        icon_name = 'fire'
        icon_color = 'red' if props['status'] == 'confirmed' else 'orange'
        wildfire_count += 1
    elif props['type'] == 'flood':
        icon_name = 'tint'
        icon_color = 'blue' if props['status'] == 'confirmed' else 'lightblue'
        flood_count += 1
    
    # Create popup content
    status_emoji = "✅" if props['status'] == 'confirmed' else "⚠️"
    popup_content = f"""
    <b>{props['name']}</b><br>
    Type: {props['type'].title()}<br>
    Status: {status_emoji} {props['status'].title()}<br>
    Started: {datetime.fromisoformat(props['started_at'].replace('Z', '+00:00')).strftime('%Y-%m-%d %H:%M')}<br>
    Description: {props['description']}
    """
    
    # Add marker
    folium.Marker(
        location=[center_lat, center_lon],
        popup=folium.Popup(popup_content, max_width=300),
        tooltip=f"Click to zoom to {props['name']}",
        icon=folium.Icon(
            icon=icon_name,
            prefix='fa',
            color=icon_color
        )
    ).add_to(m)
    
    # Add polygon outline
    if feature['geometry']['type'] == 'Polygon':
        # Convert coordinates to [lat, lon] format for folium
        polygon_coords = [[lat, lon] for lon, lat in coords[0]]
        
        folium.Polygon(
            locations=polygon_coords,
            color=icon_color,
            weight=2,
            opacity=0.8,
            fill=True,
            fillOpacity=0.2,
            popup=props['name']
        ).add_to(m)

# Display the map and capture interactions
st.subheader("Interactive Incident Map")

col1, col2, col3 = st.columns([1, 2, 1])

with col1:
    st.metric("Active Wildfires", wildfire_count)
    st.metric("Flood Areas", flood_count)

with col2:
    # Display the map
    map_data = st_folium(
        m, 
        width=700, 
        height=500,
        returned_objects=["last_object_clicked"]
    )

with col3:
    if st.session_state.selected_fire:
        st.success(f"🔍 Zoomed to: {st.session_state.selected_fire}")
        if st.button("Reset View"):
            st.session_state.selected_fire = None
            st.rerun()

# Handle marker clicks
if map_data['last_object_clicked'] is not None:
    clicked_lat = map_data['last_object_clicked']['lat']
    clicked_lng = map_data['last_object_clicked']['lng']
    
    # Find which incident was clicked based on proximity to center
    clicked_incident = None
    min_distance = float('inf')
    
    for feature in geojson_data['features']:
        bounds = calculate_bounds(feature['geometry']['coordinates'])
        center_lat = bounds['center_lat']
        center_lon = bounds['center_lon']
        
        # Calculate distance from clicked point to incident center
        distance = np.sqrt((clicked_lat - center_lat)**2 + (clicked_lng - center_lon)**2)
        
        if distance < min_distance and distance < 0.1:  # Within reasonable proximity
            min_distance = distance
            clicked_incident = feature['properties']['name']
    
    # Update selected fire if a new one was clicked
    if clicked_incident and clicked_incident != st.session_state.selected_fire:
        st.session_state.selected_fire = clicked_incident
        st.rerun()

# Display incident details
st.subheader("📊 Incident Summary")

# Create tabs for different incident types
tab1, tab2 = st.tabs(["🔥 Wildfires", "🌊 Floods"])

with tab1:
    wildfire_features = [f for f in geojson_data['features'] if f['properties']['type'] == 'wildfire']
    for feature in wildfire_features:
        props = feature['properties']
        status_color = "🟢" if props['status'] == 'confirmed' else "🟡"
        
        with st.expander(f"{status_color} {props['name']} ({props['status'].title()})"):
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**Started:** {datetime.fromisoformat(props['started_at'].replace('Z', '+00:00')).strftime('%Y-%m-%d %H:%M')}")
                st.write(f"**Status:** {props['status'].title()}")
            with col2:
                st.write(f"**Description:** {props['description']}")
                if st.button(f"Zoom to {props['name']}", key=f"zoom_{props['name']}"):
                    st.session_state.selected_fire = props['name']
                    st.rerun()

with tab2:
    flood_features = [f for f in geojson_data['features'] if f['properties']['type'] == 'flood']
    for feature in flood_features:
        props = feature['properties']
        status_color = "🟢" if props['status'] == 'confirmed' else "🟡"
        
        with st.expander(f"{status_color} {props['name']} ({props['status'].title()})"):
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**Started:** {datetime.fromisoformat(props['started_at'].replace('Z', '+00:00')).strftime('%Y-%m-%d %H:%M')}")
                st.write(f"**Status:** {props['status'].title()}")
            with col2:
                st.write(f"**Description:** {props['description']}")

# Instructions
with st.expander("ℹ️ How to Use"):
    st.markdown("""
    1. **View incidents**: The map shows all wildfire and flood incidents in Manitoba
    2. **Click markers**: Click on any fire/flood marker to zoom into that specific area
    3. **Reset view**: Use the "Reset View" button to return to the full Manitoba view
    4. **Explore details**: Use the tabs below to see detailed information about each incident
    5. **Direct zoom**: Use the "Zoom to" buttons in the incident details to navigate directly to specific areas
    """)

st.markdown("---")
st.caption("Manitoba Emergency Management • Real-time Incident Monitoring")