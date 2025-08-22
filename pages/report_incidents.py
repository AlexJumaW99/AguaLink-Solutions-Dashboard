"""
Report Incidents Page - Upload and manage incident data

This module contains the report incidents page function for uploading incident data.
"""
import json
import streamlit as st
import pandas as pd
from datetime import datetime
import os

def load_default_incidents():
    """Load the default incidents data from file"""
    inc_default = "data/incidents_dummy.geojson"
    if os.path.exists(inc_default):
        with open(inc_default, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"type": "FeatureCollection", "features": []}

def parse_incidents_data(data):
    """Parse and validate incidents data"""
    try:
        # Check if it's a valid GeoJSON
        if "type" in data and data["type"] == "FeatureCollection":
            features = data.get("features", [])
            return True, data, f"Valid GeoJSON with {len(features)} features"
        # Check if it's a custom JSON format that can be converted
        elif isinstance(data, dict) and "incidents" in data:
            # Convert custom format to GeoJSON if needed
            features = []
            for incident in data["incidents"]:
                if "geometry" in incident:
                    features.append({
                        "type": "Feature",
                        "geometry": incident["geometry"],
                        "properties": {k: v for k, v in incident.items() if k != "geometry"}
                    })
            geojson = {
                "type": "FeatureCollection",
                "features": features
            }
            return True, geojson, f"Custom JSON converted to GeoJSON with {len(features)} features"
        else:
            return False, None, "Invalid format: Expected GeoJSON or custom JSON with 'incidents' key"
    except Exception as e:
        return False, None, f"Error parsing data: {str(e)}"

def merge_incidents_data(existing_data, new_data):
    """
    Merge new incidents with existing incidents data.
    Checks for duplicates based on geometry and key properties.
    """
    if not existing_data:
        return new_data
    
    # Create a set of existing incident signatures for duplicate detection
    existing_signatures = set()
    for feature in existing_data.get("features", []):
        props = feature.get("properties", {})
        geom = feature.get("geometry", {})
        # Create a signature based on name, type, and first coordinate
        coords_str = str(geom.get("coordinates", [])[:1]) if geom else ""
        signature = f"{props.get('name', '')}-{props.get('type', '')}-{coords_str}"
        existing_signatures.add(signature)
    
    # Merge non-duplicate features
    merged_features = existing_data.get("features", []).copy()
    new_features_added = 0
    duplicates_found = 0
    
    for feature in new_data.get("features", []):
        props = feature.get("properties", {})
        geom = feature.get("geometry", {})
        coords_str = str(geom.get("coordinates", [])[:1]) if geom else ""
        signature = f"{props.get('name', '')}-{props.get('type', '')}-{coords_str}"
        
        if signature not in existing_signatures:
            merged_features.append(feature)
            existing_signatures.add(signature)
            new_features_added += 1
        else:
            duplicates_found += 1
    
    result = {
        "type": "FeatureCollection",
        "features": merged_features
    }
    
    return result, new_features_added, duplicates_found

def display_incidents_summary(data, title="Incident Summary"):
    """Display a summary of the incidents data"""
    if not data or "features" not in data:
        return
    
    features = data["features"]
    if not features:
        st.info("No incidents found in the data")
        return
    
    # Extract incident types and counts
    incident_types = {}
    incident_statuses = {}
    
    for feature in features:
        props = feature.get("properties", {})
        
        # Get incident type
        inc_type = props.get("type", "Unknown")
        incident_types[inc_type] = incident_types.get(inc_type, 0) + 1
        
        # Get incident status
        status = props.get("status") or props.get("confidence", "Unknown")
        incident_statuses[status] = incident_statuses.get(status, 0) + 1
    
    # Display summary metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Incidents", len(features))
    with col2:
        st.metric("Incident Types", len(incident_types))
    with col3:
        st.metric("Status Categories", len(incident_statuses))
    
    # Display breakdown
    st.subheader(f"📊 {title}")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**By Type:**")
        for inc_type, count in sorted(incident_types.items()):
            if inc_type.lower() == "wildfire":
                st.write(f"🔥 {inc_type}: {count}")
            elif inc_type.lower() == "flood":
                st.write(f"💧 {inc_type}: {count}")
            else:
                st.write(f"• {inc_type}: {count}")
    
    with col2:
        st.write("**By Status:**")
        for status, count in sorted(incident_statuses.items()):
            if status.lower() == "confirmed":
                st.write(f"✅ {status}: {count}")
            elif status.lower() == "suspected":
                st.write(f"⚠️ {status}: {count}")
            else:
                st.write(f"• {status}: {count}")
    
    # Show sample data
    with st.expander("View Sample Incident Data"):
        sample_data = []
        for i, feature in enumerate(features[:10]):  # Show first 10
            props = feature.get("properties", {})
            sample_data.append({
                "Name": props.get("name", f"Incident {i+1}"),
                "Type": props.get("type", "Unknown"),
                "Status": props.get("status") or props.get("confidence", "Unknown"),
                "Started": props.get("started_at", "N/A"),
                "Description": (props.get("description", "N/A")[:50] + "...") if len(props.get("description", "")) > 50 else props.get("description", "N/A")
            })
        df = pd.DataFrame(sample_data)
        st.dataframe(df, use_container_width=True)
        
        if len(features) > 10:
            st.info(f"Showing first 10 of {len(features)} incidents")

def report_incidents_page():
    """Main function for the Report Incidents page - called by st.Page"""
    
    st.title("🚨 Report Incidents")
    st.markdown("""
    Upload incident data to be added to the map. New incidents will be appended to existing data.
    """)
    
    # Initialize incidents data in session state if not present
    if 'incidents_data' not in st.session_state:
        st.session_state.incidents_data = load_default_incidents()
        st.session_state.incidents_source = "default"
    
    # Create tabs for better organization
    tab1, tab2, tab3 = st.tabs(["📤 Upload Data", "📋 Current Data", "❓ Help & Guidelines"])
    
    with tab1:
        st.header("Upload Additional Incident Data")
        st.info("📌 New incidents will be added to existing data, not replace it.")
        
        # File uploader with improved UI
        col1, col2 = st.columns([2, 1])
        
        with col1:
            uploaded_file = st.file_uploader(
                "Choose a GeoJSON or JSON file",
                type=["geojson", "json"],
                help="Upload a file containing wildfire, flood, or other incident data",
                label_visibility="collapsed"
            )
        
        with col2:
            st.info("📁 Supported formats:\n- GeoJSON (.geojson)\n- JSON (.json)")
        
        if uploaded_file is not None:
            # Add a process button for explicit action
            if st.button("🔄 Process & Add Incidents", type="primary", use_container_width=True):
                with st.spinner("Processing and merging incident data..."):
                    try:
                        # Load and parse the file
                        new_incidents_data = json.load(uploaded_file)
                        
                        # Validate and process the data
                        is_valid, processed_data, message = parse_incidents_data(new_incidents_data)
                        
                        if is_valid:
                            # Merge with existing data
                            merged_data, new_count, dupe_count = merge_incidents_data(
                                st.session_state.incidents_data, 
                                processed_data
                            )
                            
                            # Update session state
                            st.session_state.incidents_data = merged_data
                            st.session_state.incidents_source = "merged"
                            
                            # Track upload history
                            if 'upload_history' not in st.session_state:
                                st.session_state.upload_history = []
                            
                            st.session_state.upload_history.append({
                                'filename': uploaded_file.name,
                                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                'new_incidents': new_count,
                                'duplicates': dupe_count
                            })
                            
                            # Display results
                            st.success(f"✅ Successfully processed {uploaded_file.name}")
                            
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("New Incidents Added", new_count)
                            with col2:
                                st.metric("Duplicates Skipped", dupe_count)
                            with col3:
                                st.metric("Total Incidents Now", len(merged_data.get("features", [])))
                            
                            if new_count > 0:
                                st.balloons()
                                st.success(f"🎉 Added {new_count} new incident(s) to the map!")
                            elif dupe_count > 0:
                                st.warning("All incidents in this file were duplicates and already exist.")
                            
                            # Show updated summary
                            st.divider()
                            display_incidents_summary(merged_data, "Updated Incident Breakdown")
                            
                        else:
                            st.error(f"❌ {message}")
                            
                    except json.JSONDecodeError as e:
                        st.error(f"Failed to parse JSON file: {e}")
                    except Exception as e:
                        st.error(f"Error processing file: {e}")
    
    with tab2:
        st.header("Current Incident Data Status")
        
        # Display data source info
        if st.session_state.incidents_source == "default":
            st.info("📊 Showing default incident data from: `data/incidents_dummy.geojson`")
        else:
            st.success("📊 Showing merged incident data (default + uploaded)")
        
        # Display current data metrics
        current_data = st.session_state.incidents_data
        if current_data and "features" in current_data:
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("📍 Total Features", len(current_data.get('features', [])))
            
            with col2:
                sources = 1 if st.session_state.incidents_source == "default" else len(st.session_state.get('upload_history', [])) + 1
                st.metric("📁 Data Sources", sources)
            
            with col3:
                last_update = st.session_state.upload_history[-1]['timestamp'] if 'upload_history' in st.session_state and st.session_state.upload_history else "N/A"
                st.metric("⏰ Last Update", last_update if last_update != "N/A" else "Default data")
            
            st.divider()
            
            # Show summary of current data
            display_incidents_summary(current_data, "Current Data Breakdown")
            
            # Upload history
            if 'upload_history' in st.session_state and st.session_state.upload_history:
                st.divider()
                st.subheader("📜 Upload History")
                history_df = pd.DataFrame(st.session_state.upload_history)
                st.dataframe(history_df, use_container_width=True, hide_index=True)
            
            # Action buttons
            st.divider()
            col1, col2, col3 = st.columns([1, 1, 1])
            
            with col1:
                if st.button("🔄 Reset to Default", type="secondary", use_container_width=True):
                    st.session_state.incidents_data = load_default_incidents()
                    st.session_state.incidents_source = "default"
                    if 'upload_history' in st.session_state:
                        del st.session_state.upload_history
                    st.success("Reset to default incident data!")
                    st.rerun()
            
            with col2:
                # Option to view raw data
                if st.button("👁️ View Raw JSON", use_container_width=True):
                    st.session_state.show_raw_json = not st.session_state.get('show_raw_json', False)
            
            with col3:
                # Download current merged data
                st.download_button(
                    label="💾 Download Current Data",
                    data=json.dumps(current_data, indent=2),
                    file_name=f"merged_incidents_{datetime.now().strftime('%Y%m%d_%H%M%S')}.geojson",
                    mime="application/json",
                    use_container_width=True
                )
            
            if st.session_state.get('show_raw_json', False):
                st.json(current_data, expanded=False)
        else:
            st.warning("📭 No incident data available")
    
    with tab3:
        st.header("📋 File Format Guidelines")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("GeoJSON Format")
            st.markdown("""
            Your GeoJSON file should follow this structure:
            ```json
            {
              "type": "FeatureCollection",
              "features": [
                {
                  "type": "Feature",
                  "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[lon, lat], ...]]
                  },
                  "properties": {
                    "name": "Incident Name",
                    "type": "wildfire" or "flood",
                    "status": "confirmed" or "suspected",
                    "started_at": "2024-01-01",
                    "description": "Details..."
                  }
                }
              ]
            }
            ```
            """)
        
        with col2:
            st.subheader("Custom JSON Format")
            st.markdown("""
            Alternatively, use a custom format:
            ```json
            {
              "incidents": [
                {
                  "name": "Incident Name",
                  "type": "wildfire",
                  "status": "confirmed",
                  "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[lon, lat], ...]]
                  }
                }
              ]
            }
            ```
            """)
        
        st.divider()
        
        st.subheader("📝 Supported Properties")
        
        properties_df = pd.DataFrame({
            "Property": ["name", "type", "status/confidence", "started_at", "description"],
            "Description": [
                "Incident identifier or name",
                "Type of incident (wildfire, flood, etc.)",
                "Status (confirmed, suspected, etc.)",
                "Date when incident started",
                "Additional details about the incident"
            ],
            "Example": [
                "North Winnipeg Fire",
                "wildfire",
                "confirmed",
                "2024-03-15",
                "Large wildfire affecting 500 hectares"
            ]
        })
        
        st.dataframe(properties_df, use_container_width=True, hide_index=True)
        
        st.divider()
        
        # Tips section
        st.subheader("💡 Tips for Best Results")
        st.markdown("""
        - **Appending Data**: New incidents are automatically added to existing data
        - **Duplicate Detection**: System checks for duplicates based on name, type, and location
        - **Coordinate Format**: Use longitude, latitude order (e.g., [-97.1384, 49.8951] for Winnipeg)
        - **Polygon Closure**: Ensure polygon coordinates form a closed loop
        - **Status Values**: Use "confirmed" or "suspected" for best compatibility
        - **Type Values**: Use "wildfire" or "flood" for automatic icon assignment
        """)
        
        # Example data download
        st.divider()
        st.subheader("📥 Example Data")
        
        example_geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[
                            [-97.2, 49.9],
                            [-97.1, 49.9],
                            [-97.1, 49.8],
                            [-97.2, 49.8],
                            [-97.2, 49.9]
                        ]]
                    },
                    "properties": {
                        "name": "Example Wildfire",
                        "type": "wildfire",
                        "status": "confirmed",
                        "started_at": "2024-03-15",
                        "description": "Example wildfire incident near Winnipeg"
                    }
                },
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[
                            [-98.5, 53.5],
                            [-98.4, 53.5],
                            [-98.4, 53.4],
                            [-98.5, 53.4],
                            [-98.5, 53.5]
                        ]]
                    },
                    "properties": {
                        "name": "Example Flood",
                        "type": "flood",
                        "status": "suspected",
                        "started_at": "2024-04-01",
                        "description": "Example flood incident in northern Manitoba"
                    }
                }
            ]
        }
        
        st.download_button(
            label="📥 Download Example GeoJSON",
            data=json.dumps(example_geojson, indent=2),
            file_name="example_incidents.geojson",
            mime="application/json",
            use_container_width=True
        )