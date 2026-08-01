import streamlit as st
import requests

st.set_page_config(
    page_title="PyMudCement Optima Pro",
    page_icon="🛢️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🛢️ PyMudCement Optima Pro")
st.markdown("---")

BACKEND_URL = "http://127.0.0.1:8000"

st.sidebar.header("⚙️ Simulation Parameters")
flow_rate = st.sidebar.number_input("Flow Rate (GPM)", min_value=50.0, max_value=1200.0, value=450.0, step=10.0)
total_depth = st.sidebar.number_input("Total Depth / TVD (ft)", min_value=1000.0, max_value=30000.0, value=8000.0, step=100.0)
mud_weight = st.sidebar.number_input("Surface Mud Weight (ppg)", min_value=7.0, max_value=22.0, value=10.0, step=0.1)

st.sidebar.markdown("---")
st.sidebar.header("🧪 Fluid Rheology")
pv = st.sidebar.number_input("Plastic Viscosity (cP)", min_value=1.0, max_value=100.0, value=20.0, step=1.0)
yp = st.sidebar.number_input("Yield Point (lb/100ft²)", min_value=0.0, max_value=80.0, value=15.0, step=1.0)

st.subheader("📐 Multi-Segment Wellbore Geometry")

default_segments = [
    {"name": "Drill Pipe", "top_md": 0.0, "bottom_md": max(0.0, total_depth - 1000.0), "pipe_od": 5.0, "pipe_id": 4.276, "hole_id": 8.5},
    {"name": "BHA / HWDP", "top_md": max(0.0, total_depth - 1000.0), "bottom_md": total_depth, "pipe_od": 5.0, "pipe_id": 3.0, "hole_id": 8.5}
]

segment_df = st.data_editor(
    default_segments,
    num_rows="dynamic",
    column_config={
        "name": st.column_config.TextColumn("Segment Name", required=True),
        "top_md": st.column_config.NumberColumn("Top MD (ft)", min_value=0.0, format="%.1f"),
        "bottom_md": st.column_config.NumberColumn("Bottom MD (ft)", min_value=0.0, format="%.1f"),
        "pipe_od": st.column_config.NumberColumn("Pipe OD (in)", min_value=1.0, format="%.3f"),
        "pipe_id": st.column_config.NumberColumn("Pipe ID (in)", min_value=0.5, format="%.3f"),
        "hole_id": st.column_config.NumberColumn("Hole / Casing ID (in)", min_value=1.0, format="%.3f"),
    },
    use_container_width=True
)

# Parse data_editor list cleanly into payload schema
clean_segments = []
if isinstance(segment_df, list):
    clean_segments = segment_df
elif hasattr(segment_df, "to_dict"):
    clean_segments = segment_df.to_dict(orient="records")

payload = {
    "flow_rate_gpm": flow_rate,
    "total_depth_ft": total_depth,
    "surface_mud_weight_ppg": mud_weight,
    "plastic_viscosity_cp": pv,
    "yield_point_lb_100ft2": yp,
    "segments": clean_segments
}

st.markdown("---")
col_calc, col_pdf = st.columns([1, 1])

with col_calc:
    run_btn = st.button("🚀 Run Hydraulics & AI Analysis", use_container_width=True)

if run_btn:
    try:
        res = requests.post(f"{BACKEND_URL}/api/v1/hydraulics/calculate", json=payload)
        if res.status_code == 200:
            st.session_state["physics_data"] = res.json()
        else:
            st.error(f"Engine Error: {res.text}")
    except Exception as e:
        st.error(f"Failed to connect to backend server at {BACKEND_URL}: {str(e)}")

if "physics_data" in st.session_state:
    data = st.session_state["physics_data"]
    physics = data.get("physics_results", {})
    diagnostics = data.get("diagnostics", {})

    st.subheader("📊 Physics Output")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("ECD", f"{physics.get('equivalent_circulating_density_ecd_ppg', 0.0):.2f} ppg")
    m2.metric("SPP", f"{physics.get('standpipe_pressure_spp_psi', 0.0):.1f} psi")
    m3.metric("Annular Loss", f"{physics.get('total_annular_pressure_loss_psi', 0.0):.1f} psi")
    m4.metric("Pipe Loss", f"{physics.get('total_pipe_pressure_loss_psi', 0.0):.1f} psi")

    st.subheader("🤖 AI Diagnostic Blueprint")
    severity = diagnostics.get("severity", "GREEN")
    if severity == "RED":
        st.error(f"**Hazard Alert:** {diagnostics.get('matched_hazard')}")
    elif severity == "YELLOW":
        st.warning(f"**Warning:** {diagnostics.get('matched_hazard')}")
    else:
        st.success("**Status:** Normal Operating Envelope")

    st.write(f"**Diagnosis:** {diagnostics.get('detailed_diagnosis')}")

with col_pdf:
    st.subheader("📄 Report Export")
    if st.button("📥 Generate Official PDF Report", use_container_width=True):
        try:
            pdf_res = requests.post(f"{BACKEND_URL}/api/v1/hydraulics/export-pdf", json=payload)
            if pdf_res.status_code == 200:
                st.download_button(
                    label="💾 Download Optima Pro Report (PDF)",
                    data=pdf_res.content,
                    file_name="PyMudCement_OptimaPro_Report.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
                st.success("PDF report generated successfully!")
            else:
                st.error(f"Failed to compile PDF: {pdf_res.text}")
        except Exception as e:
            st.error(f"Error connecting to backend export service: {str(e)}")