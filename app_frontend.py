# app_frontend.py (Your Streamlit File)
import streamlit as st
import requests

# Point this to your FastAPI backend server URL
BACKEND_URL = "http://localhost:8000"

# Initialize token storage in Streamlit's session state if not already present
if "access_token" not in st.session_state:
    st.session_state.access_token = None
if "refresh_token" not in st.session_state:
    st.session_state.refresh_token = None

# --- Component 1: The Login Sidebar Interface ---
def render_login_sidebar():
    st.sidebar.title("🔐 Account Authentication")
   
    if st.session_state.access_token is None:
        username = st.sidebar.text_input("Username")
        password = st.sidebar.text_input("Password", type="password")
       
        if st.sidebar.button("Login to Platform"):
            # FastAPI expects OAuth2PasswordRequestForm data as standard form-url-encoded data
            login_data = {"username": username, "password": password}
           
            try:
                response = requests.post(f"{BACKEND_URL}/auth/login", data=login_data)
               
                if response.status_code == 200:
                    tokens = response.json()
                    st.session_state.access_token = tokens["access_token"]
                    st.session_state.refresh_token = tokens["refresh_token"]
                    st.sidebar.success(f"Logged in as {username}!")
                    st.rerun()
                else:
                    st.sidebar.error("Invalid credentials. Please try again.")
            except requests.exceptions.ConnectionError:
                st.sidebar.error("Cannot connect to backend server. Is FastAPI running?")
    else:
        st.sidebar.success("Status: Authenticated ✅")
        if st.sidebar.button("Log Out"):
            st.session_state.access_token = None
            st.session_state.refresh_token = None
            st.rerun()

# --- Component 2: Sending Authenticated Calculation Requests ---
def run_hydraulics_calculation(payload_dict):
    """Sends the validated engineering data along with your authorization token."""
    if st.session_state.access_token is None:
        st.error("🔒 Access Denied: You must be logged in to execute engineering calculations.")
        return None
       
    # Inject the JWT token securely into the HTTP request headers
    headers = {
        "Authorization": f"Bearer {st.session_state.access_token}"
    }
   
    try:
        response = requests.post(
            f"{BACKEND_URL}/api/v1/hydraulics/solve",
            json=payload_dict,
            headers=headers
        )
       
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 403:
            st.error("🚫 Permission Error: Your account role does not have permission to run calculations.")
            return None
        else:
            st.error(f"Calculation failed: {response.json().get('detail')}")
            return None
           
    except requests.exceptions.ConnectionError:
        st.error("Backend communication link failure.")
        return None

# --- Main Streamlit App Execution Layout ---
render_login_sidebar()

st.title("PyMudCement Optima Pro Platform")

# Example calculation trigger in your UI
if st.button("Run Simulation"):
    # Sample mock payload matching your backend's exact Pydantic schema structure
    simulation_payload = {
        "flow_rate_gpm": 450.0,
        "total_tvd_ft": 8000.0,
        "historical_esd_ppg": 10.2,
        "wellbore_segments": [
            {"top_md": 0.0, "bottom_md": 4000.0, "tvd": 4000.0, "hole_id": 12.25, "pipe_od": 5.0},
            {"top_md": 4000.0, "bottom_md": 8000.0, "tvd": 8000.0, "hole_id": 8.5, "pipe_od": 5.0}
        ],
        "rheology_config": {
            "model_type": "herschel_bulkley",
            "theta_600": 52.0,
            "theta_300": 31.0,
            "theta_3": 2.5
        }
    }
   
    with st.spinner("Processing advanced downhole hydraulics loops..."):
        results = run_hydraulics_calculation(simulation_payload)
       
    if results:
        st.write("### Physics Engine Metrics", results["physics_metrics"])
        st.write("### AI Diagnostic Insights", results["ai_diagnostic_report"])