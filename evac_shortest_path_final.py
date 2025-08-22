import streamlit as st
import folium
from streamlit_folium import st_folium
import osmnx as ox
import networkx as nx
import pandas as pd

# Configure the Streamlit page
st.set_page_config(page_title="Shortest Path Navigator - Winnipeg", layout="wide")
st.title("🗺️ Shortest Path Navigator")
st.markdown("Find the shortest driving route between any two locations in Winnipeg")

# Initialize session state
if "start_location" not in st.session_state:
    st.session_state.start_location = ""
if "end_location" not in st.session_state:
    st.session_state.end_location = ""
if "route_calculated" not in st.session_state:
    st.session_state.route_calculated = False
if "map_data" not in st.session_state:
    st.session_state.map_data = None

@st.cache_data(show_spinner=False)
def geocode_location(location_name):
    """Geocode a location name to coordinates"""
    try:
        return ox.geocode(location_name)
    except:
        return None

@st.cache_data(show_spinner=False)
def get_graph(center_point, dist=15000):
    """Get the street network graph"""
    return ox.graph_from_point(center_point, dist=dist, network_type='drive')

def find_shortest_route(start_name, end_name, search_radius=15000):
    """
    Find the shortest route between two locations using Dijkstra's algorithm.
    This is the core logic from dijkstra_short_path_best_func.py
    """
    # Geocode the locations
    start_point = geocode_location(start_name)
    end_point = geocode_location(end_name)
    
    if not start_point or not end_point:
        return None, None, None, None, None
    
    # Calculate center point for graph generation
    center_point = (
        (start_point[0] + end_point[0]) / 2,
        (start_point[1] + end_point[1]) / 2
    )
    
    # Generate street network graph
    graph = get_graph(center_point, dist=search_radius)
    
    # Find nearest nodes in the graph
    origin_node = ox.distance.nearest_nodes(graph, start_point[1], start_point[0])
    destination_node = ox.distance.nearest_nodes(graph, end_point[1], end_point[0])
    
    # Calculate shortest path using Dijkstra's algorithm
    try:
        route = nx.shortest_path(graph, origin_node, destination_node, 
                                weight='length', method='dijkstra')
        route_length_m = nx.shortest_path_length(graph, origin_node, destination_node, 
                                                weight='length', method='dijkstra')
        
        # Get route coordinates for visualization
        route_coords = [(graph.nodes[node]['y'], graph.nodes[node]['x']) 
                       for node in route]
        
        return graph, route_coords, route_length_m, start_point, end_point
    
    except nx.NetworkXNoPath:
        return graph, None, None, start_point, end_point

def create_route_map(graph, route_coords, route_length_m, start_point, end_point, 
                    start_name, end_name, show_network=True):
    """
    Create an interactive Folium map with the route.
    Combines the best visualization from both files.
    """
    if route_coords:
        # Center map on the middle of the route
        center_point = (
            (start_point[0] + end_point[0]) / 2,
            (start_point[1] + end_point[1]) / 2
        )
    else:
        center_point = start_point if start_point else (49.8951, -97.1384)
    
    # Create the base map
    m = folium.Map(
        location=center_point,
        zoom_start=13,
        tiles='cartodbpositron',
        zoom_control=True,
        scrollWheelZoom=True,
        dragging=True
    )
    
    # Optionally show the street network
    if show_network and graph:
        edges_gdf = ox.graph_to_gdfs(graph, nodes=False, edges=True)
        for _, row in edges_gdf.iterrows():
            coords = [(lat, lon) for lon, lat in row['geometry'].coords]
            folium.PolyLine(coords, color='#d3d3d3', weight=1, opacity=0.3).add_to(m)
    
    # Draw the shortest route
    if route_coords:
        folium.PolyLine(
            route_coords, 
            color='#0066ff', 
            weight=5, 
            opacity=0.8,
            popup=f"Distance: {route_length_m/1000:.2f} km"
        ).add_to(m)
    
    # Add markers for start and end points
    if start_point:
        folium.Marker(
            location=start_point,
            icon=folium.Icon(color='green', icon='play', prefix='fa'),
            popup=f"<b>Start:</b><br>{start_name}",
            tooltip="Start Location"
        ).add_to(m)
    
    if end_point:
        folium.Marker(
            location=end_point,
            icon=folium.Icon(color='red', icon='stop', prefix='fa'),
            popup=f"<b>End:</b><br>{end_name}",
            tooltip="End Location"
        ).add_to(m)
    
    return m

# Main UI Layout
col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("📍 Route Settings")
    
    # Input fields for locations
    start_location = st.text_input(
        "Start Location",
        value=st.session_state.start_location,
        placeholder="e.g., RBC Convention Centre, Manitoba, Canada",
        help="Enter the starting point for your route"
    )
    
    end_location = st.text_input(
        "End Location",
        value=st.session_state.end_location,
        placeholder="e.g., The Forks, Winnipeg, Canada",
        help="Enter the destination for your route"
    )
    
    # Advanced settings in an expander
    with st.expander("⚙️ Advanced Settings"):
        search_radius = st.slider(
            "Search Radius (km)",
            min_value=5,
            max_value=30,
            value=15,
            step=5,
            help="Radius around the midpoint to search for roads"
        )
        show_network = st.checkbox(
            "Show Street Network",
            value=False,
            help="Display all streets in the search area (may slow down the map)"
        )
    
    # Calculate route button
    calculate_button = st.button(
        "🚗 Calculate Shortest Route",
        type="primary",
        disabled=(not start_location or not end_location),
        use_container_width=True
    )
    
    # Example routes
    st.subheader("📌 Example Routes")
    examples = {
        "Convention Centre to The Forks": {
            "start": "RBC Convention Centre, Manitoba, Canada",
            "end": "The Forks, Winnipeg, Canada"
        },
        "Airport to Downtown": {
            "start": "Winnipeg Richardson International Airport, Canada",
            "end": "Portage and Main, Winnipeg, Canada"
        },
        "University to St. Vital": {
            "start": "University of Manitoba, Winnipeg, Canada",
            "end": "St. Vital Centre, Winnipeg, Canada"
        }
    }
    
    for name, locations in examples.items():
        if st.button(name, use_container_width=True):
            st.session_state.start_location = locations["start"]
            st.session_state.end_location = locations["end"]
            st.rerun()

with col2:
    st.subheader("🗺️ Interactive Map")
    
    # Calculate route when button is clicked
    if calculate_button:
        st.session_state.start_location = start_location
        st.session_state.end_location = end_location
        
        with st.spinner("🔍 Finding the shortest route using Dijkstra's algorithm..."):
            graph, route_coords, route_length_m, start_point, end_point = find_shortest_route(
                start_location, 
                end_location, 
                search_radius * 1000
            )
            
            if route_coords:
                st.session_state.route_calculated = True
                st.session_state.map_data = {
                    'graph': graph,
                    'route_coords': route_coords,
                    'route_length_m': route_length_m,
                    'start_point': start_point,
                    'end_point': end_point,
                    'start_name': start_location,
                    'end_name': end_location,
                    'show_network': show_network
                }
            else:
                st.error("❌ Could not find a route between these locations. Try increasing the search radius or checking the location names.")
                st.session_state.route_calculated = False
    
    # Display the map
    if st.session_state.route_calculated and st.session_state.map_data:
        data = st.session_state.map_data
        
        # Show route statistics
        col_stat1, col_stat2, col_stat3 = st.columns(3)
        with col_stat1:
            st.metric("📏 Distance", f"{data['route_length_m']/1000:.2f} km")
        with col_stat2:
            # Estimate travel time (assuming average speed of 40 km/h in city)
            travel_time_min = (data['route_length_m']/1000) / 40 * 60
            st.metric("⏱️ Est. Time", f"{travel_time_min:.0f} min")
        with col_stat3:
            # Estimate fuel consumption (assuming 8L/100km)
            fuel_consumption = (data['route_length_m']/1000) * 0.08
            st.metric("⛽ Est. Fuel", f"{fuel_consumption:.1f} L")
        
        # Create and display the map
        route_map = create_route_map(
            data['graph'],
            data['route_coords'],
            data['route_length_m'],
            data['start_point'],
            data['end_point'],
            data['start_name'],
            data['end_name'],
            data['show_network']
        )
        
        st_folium(route_map, height=600, width=None, returned_objects=[])
        
        # Route details expander
        with st.expander("📋 Route Details"):
            st.write(f"**From:** {data['start_name']}")
            st.write(f"**To:** {data['end_name']}")
            st.write(f"**Total Distance:** {data['route_length_m']/1000:.2f} kilometers")
            st.write(f"**Number of waypoints:** {len(data['route_coords'])}")
            st.write(f"**Algorithm used:** Dijkstra's shortest path")
    else:
        # Show default map of Winnipeg
        default_map = folium.Map(
            location=(49.8951, -97.1384),
            zoom_start=11,
            tiles='cartodbpositron'
        )
        st_folium(default_map, height=600, width=None, returned_objects=[])
        st.info("👆 Enter locations and click 'Calculate Shortest Route' to see the path")

# Footer
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center'>
        <p>Built with ❤️ using Streamlit, OSMnx, NetworkX, and Folium</p>
        <p>Using Dijkstra's algorithm for optimal pathfinding on OpenStreetMap data</p>
    </div>
    """,
    unsafe_allow_html=True
)