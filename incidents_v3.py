"""
Manitoba Municipalities & Incidents - Main App Entry Point

This uses Streamlit's native navigation system to handle multiple pages.
"""
import streamlit as st

# Import page functions
from pages.home import home_page
from pages.report_incidents import report_incidents_page

def main():
    # Configure the app
    st.set_page_config(
        page_title="Manitoba Municipalities & Incidents",
        page_icon="🗺️",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Set up page navigation using Streamlit's native system
    pg = st.navigation({
        "Main": [
            st.Page(home_page, title="Home Page", icon="🛖", default=True),
            st.Page(report_incidents_page, title="Report Incidents", icon="🚨")
        ]
    })
    
    # Run the selected page
    pg.run()

if __name__ == "__main__":
    main()