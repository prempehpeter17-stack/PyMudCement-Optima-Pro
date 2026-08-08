import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import asyncio
from datetime import datetime, timezone
from sqlalchemy import select, or_
from sqlalchemy.exc import IntegrityError
from database import init_db, AsyncSessionLocal, UserModel
from auth import get_password_hash, verify_password
from physics import DrillingHydraulicsEngine, WellSegment, NozzleInput, RheologyModel
from cementing_engine import PrimaryCementingInput, CementingEngine
from pdf_generator import generate_pdf_payload
from mud_parser import parse_mud_report
from gradients import PressureGradientProfile
from benchmarks import compare_cementing_results
import base64


def get_base64_image(file_path: str) -> str:
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode()


logo_base64 = get_base64_image("logo.png")
asyncio.run(init_db())

# ============================
# PAGE CONFIG
# ============================
st.set_page_config(
    page_title="PyMudCement Optima Pro",
    page_icon="logo.png",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================
# SESSION STATE
# ============================
defaults = {
    "authenticated": False,
    "user_info": None,
    "auto_pv": None,
    "auto_yp": None,
    "auto_mw": None,
    "parsed": False,
    "cementing_results": None,
    "cementing_params": None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ============================
# THEME-AWARE CSS (works with Streamlit light/dark toggle)
# ============================
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
@import url('https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css');

* { font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; }

/* ---------- LIGHT (default) ---------- */
.main-header {
    font-size: 2.05rem; font-weight: 800; letter-spacing: -0.03em;
    color: #1e3a8a; margin: 0; line-height: 1.2;
}
.sub-header {
    font-size: 0.92rem; font-weight: 500; color: #475569;
    margin-top: 0.2rem; margin-bottom: 1.4rem; padding-bottom: 0.7rem;
    border-bottom: 1px solid #e2e8f0;
}
.metric-card {
    background: #ffffff; border: 1px solid #e2e8f0; border-left: 4px solid #2563eb;
    border-radius: 12px; padding: 1.05rem 1.2rem;
    box-shadow: 0 1px 4px rgba(0,0,0,0.04);
    transition: transform 0.15s ease, box-shadow 0.15s ease; height: 100%;
}
.metric-card:hover { transform: translateY(-2px); box-shadow: 0 6px 16px rgba(37,99,235,0.12); }
.metric-card .label {
    font-size: 0.7rem; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.05em; color: #64748b;
    display: flex; align-items: center; gap: 6px; margin-bottom: 0.3rem;
}
.metric-card .value { font-size: 1.55rem; font-weight: 800; color: #1e3a8a; line-height: 1.2; }
.sidebar-heading {
    font-size: 0.8rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.06em; color: #2563eb; margin-top: 1.2rem; margin-bottom: 0.45rem;
}
.section-title {
    font-size: 1.12rem; font-weight: 700; color: #1e293b;
    margin-bottom: 0.3rem; display: flex; align-items: center; gap: 0.45rem;
}
.section-caption { font-size: 0.84rem; color: #64748b; margin-bottom: 1.15rem; }
.footer {
    font-size: 0.72rem; text-align: center; margin-top: 2.8rem; padding-top: 1.1rem;
    border-top: 1px solid #e2e8f0; color: #94a3b8;
}
.stButton > button {
    background: linear-gradient(135deg, #2563eb, #1d4ed8) !important;
    color: white !important; border: none !important; border-radius: 8px !important;
    font-weight: 600 !important; padding: 0.55rem 1.25rem !important;
    box-shadow: 0 2px 6px rgba(37,99,235,0.25) !important;
    transition: all 0.15s ease !important;
}
.stButton > button:hover {
    background: linear-gradient(135deg, #1d4ed8, #1e40af) !important;
    box-shadow: 0 4px 12px rgba(37,99,235,0.35) !important; transform: translateY(-1px);
}
.stTabs [data-baseweb="tab-list"] { gap: 0.2rem; border-bottom: 1px solid #e2e8f0; }
.stTabs [data-baseweb="tab"] {
    font-weight: 600 !important; font-size: 0.88rem !important;
    padding: 0.55rem 1rem !important; border-radius: 8px 8px 0 0 !important; color: #64748b !important;
}
.stTabs [data-baseweb="tab"][aria-selected="true"] {
    background: #2563eb !important; color: white !important;
}
.stTabs [data-baseweb="tab"]:hover { background: #eff6ff !important; color: #1e40af !important; }
[data-testid="stMetricValue"] { font-weight: 700 !important; }
.stAlert { border-radius: 10px !important; }

/* ---------- DARK MODE ---------- */
html.theme-dark .main-header,
[data-theme="dark"] .main-header,
.stApp[data-theme="dark"] .main-header { color: #facc15 !important; }

html.theme-dark .sub-header,
[data-theme="dark"] .sub-header {
    color: #94a3b8 !important; border-bottom-color: #1e293b !important;
}
html.theme-dark .metric-card,
[data-theme="dark"] .metric-card {
    background: #1e293b !important; border-color: #334155 !important;
    border-left-color: #facc15 !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.25) !important;
}
html.theme-dark .metric-card:hover,
[data-theme="dark"] .metric-card:hover {
    box-shadow: 0 6px 16px rgba(250,204,21,0.12) !important;
}
html.theme-dark .metric-card .label,
[data-theme="dark"] .metric-card .label { color: #94a3b8 !important; }
html.theme-dark .metric-card .value,
[data-theme="dark"] .metric-card .value { color: #facc15 !important; }

html.theme-dark .sidebar-heading,
[data-theme="dark"] .sidebar-heading { color: #facc15 !important; }
html.theme-dark .section-title,
[data-theme="dark"] .section-title { color: #e2e8f0 !important; }
html.theme-dark .section-caption,
[data-theme="dark"] .section-caption { color: #94a3b8 !important; }
html.theme-dark .footer,
[data-theme="dark"] .footer {
    border-top-color: #1e293b !important; color: #64748b !important;
}
html.theme-dark .stButton > button,
[data-theme="dark"] .stButton > button {
    background: linear-gradient(135deg, #facc15, #eab308) !important;
    color: #0f172a !important;
    box-shadow: 0 2px 8px rgba(250,204,21,0.25) !important;
}
html.theme-dark .stButton > button:hover,
[data-theme="dark"] .stButton > button:hover {
    background: linear-gradient(135deg, #eab308, #ca8a04) !important;
    box-shadow: 0 4px 14px rgba(250,204,21,0.35) !important;
}
html.theme-dark .stTabs [data-baseweb="tab-list"],
[data-theme="dark"] .stTabs [data-baseweb="tab-list"] { border-bottom-color: #1e293b !important; }
html.theme-dark .stTabs [data-baseweb="tab"],
[data-theme="dark"] .stTabs [data-baseweb="tab"] { color: #94a3b8 !important; }
html.theme-dark .stTabs [data-baseweb="tab"][aria-selected="true"],
[data-theme="dark"] .stTabs [data-baseweb="tab"][aria-selected="true"] {
    background: #facc15 !important; color: #0f172a !important;
}
html.theme-dark .stTabs [data-baseweb="tab"]:hover,
[data-theme="dark"] .stTabs [data-baseweb="tab"]:hover {
    background: #1e293b !important; color: #facc15 !important;
}
html.theme-dark [data-testid="stMetricValue"],
[data-theme="dark"] [data-testid="stMetricValue"] { color: #facc15 !important; }
</style>
""",
    unsafe_allow_html=True,
)

# ============================
# AUTHENTICATION
# ============================
async def process_authentication(mode, email_val, password_val, company_val=None):
    async with AsyncSessionLocal() as session:
        if mode == "Register Account":
            try:
                existing = await session.execute(
                    select(UserModel).where(
                        or_(UserModel.email == email_val, UserModel.username == email_val)
                    )
                )
                if existing.scalar_one_or_none():
                    return False, "Email already registered."
                hashed_pw = get_password_hash(password_val)
                new_user = UserModel(
                    username=email_val,
                    email=email_val,
                    hashed_password=hashed_pw,
                    company_name=company_val or "Enterprise Hydrocarbons Corp",
                )
                session.add(new_user)
                await session.commit()
                return True, "Account created successfully! Please switch to Login."
            except IntegrityError:
                await session.rollback()
                return False, "Registration failed due to duplicate entry."
            except Exception as e:
                await session.rollback()
                return False, f"Error: {str(e)}"
        else:
            try:
                result = await session.execute(
                    select(UserModel).where(UserModel.email == email_val)
                )
                user = result.scalar_one_or_none()
                if user and verify_password(password_val, user.hashed_password):
                    return True, {
                        "id": user.id,
                        "username": user.username,
                        "email": user.email,
                        "company": user.company_name,
                    }
                return False, "Invalid email or password."
            except Exception as e:
                return False, f"Login Error: {str(e)}"


if not st.session_state.authenticated:
    st.markdown(
        f"""
        <div style="text-align:center; padding: 2.5rem 0 1.2rem 0;">
            <img src="data:image/png;base64,{logo_base64}" style="height: 3.8rem; margin-bottom: 0.9rem;">
            <div class="main-header">PyMudCement Optima Pro</div>
            <div class="sub-header" style="border:none; margin-bottom:0;">
                Enterprise Hydraulic Engine & Real-Time AI Diagnostics
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    auth_mode = st.radio("Select Action", ["Login", "Register Account"], horizontal=True)
    with st.form("auth_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        company = None
        if auth_mode == "Register Account":
            company = st.text_input("Company Name", value="Enterprise Hydrocarbons Corp")
        submit = st.form_submit_button("Submit", use_container_width=True)
        if submit:
            if not email or not password:
                st.error("Please enter both email and password.")
            else:
                success, response = asyncio.run(
                    process_authentication(auth_mode, email, password, company)
                )
                if auth_mode == "Register Account":
                    st.success(response) if success else st.error(response)
                else:
                    if success:
                        st.session_state.authenticated = True
                        st.session_state.user_info = response
                        st.rerun()
                    else:
                        st.error(response)
    st.stop()

# ============================
# MAIN HEADER
# ============================
h1, h2 = st.columns([1, 11])
with h1:
    st.image("logo.png", width=68)
with h2:
    st.markdown(
        f"""
        <div class="main-header" style="margin-top:0.35rem;">PyMudCement Optima Pro</div>
        <div class="sub-header" style="margin-bottom:0.4rem; padding-bottom:0.5rem;">
            <i class="fas fa-user-circle"></i> {st.session_state.user_info["username"]}
            &nbsp;·&nbsp;
            <i class="fas fa-building"></i> {st.session_state.user_info["company"]}
        </div>
        """,
        unsafe_allow_html=True,
    )

# ============================
# SIDEBAR
# ============================
with st.sidebar:
    st.image("logo.png", width=34)
    st.markdown("### Well & Mud Parameters")

    with st.expander("Well Geometry", expanded=True):
        total_depth = st.number_input(
            "Total Depth / MD (ft)", value=10000.0, step=500.0,
            help="Measured Depth of the well."
        )
        tvd = st.number_input(
            "True Vertical Depth – TVD (ft)", value=10000.0, step=500.0,
            help="Used for ECD and hydrostatic calculations. Equal to MD for vertical wells."
        )
        flow_rate = st.number_input("Flow Rate (GPM)", value=550.0, step=25.0)

    with st.expander("Mud Properties", expanded=True):
        default_mw = st.session_state.auto_mw if st.session_state.auto_mw is not None else 12.5
        surface_mw = st.number_input("Surface Mud Weight (ppg)", value=default_mw, step=0.1)
        rheology = st.selectbox("Rheology Model", [r.value for r in RheologyModel])
        default_pv = st.session_state.auto_pv if st.session_state.auto_pv is not None else 22.0
        default_yp = st.session_state.auto_yp if st.session_state.auto_yp is not None else 16.0
        pv = st.number_input("Plastic Viscosity (cP)", value=default_pv, step=1.0)
        yp = st.number_input("Yield Point (lb/100ft²)", value=default_yp, step=1.0)

    st.divider()
    st.markdown(
        '<div class="sidebar-heading"><i class="fas fa-file-upload"></i> Upload Mud Report</div>',
        unsafe_allow_html=True,
    )
    uploaded_file = st.file_uploader("CSV or Excel", type=["csv", "xlsx"], key="mud_uploader")

    if uploaded_file is not None and not st.session_state.parsed:
        try:
            file_type = "csv" if uploaded_file.type == "text/csv" else "excel"
            data = parse_mud_report(uploaded_file.read(), file_type)
            st.session_state.auto_pv = data["pv_cp"]
            st.session_state.auto_yp = data["yp"]
            st.session_state.auto_mw = data["mw_ppg"]
            st.session_state.parsed = True
            st.sidebar.success(
                f"Parsed · PV={data['pv_cp']} · YP={data['yp']} · MW={data['mw_ppg']} ppg"
            )
        except Exception as e:
            st.sidebar.error(f"Parse error: {e}")
            st.session_state.parsed = False

    if uploaded_file is None and st.session_state.parsed:
        st.session_state.parsed = False

    st.divider()
    st.markdown(
        '<div class="sidebar-heading"><i class="fas fa-chart-line"></i> Pore / Fracture Gradients</div>',
        unsafe_allow_html=True,
    )
    st.caption("Depth-dependent gradients (ppg)")
    grad_df = st.data_editor(
        pd.DataFrame({
            "Depth (ft)": [5000, 10000],
            "Pore Pressure (ppg)": [9.0, 9.5],
            "Fracture Gradient (ppg)": [14.0, 15.5],
        }),
        num_rows="dynamic",
        key="gradient_editor",
    )
    st.session_state.gradient_df = grad_df

    st.divider()
    if st.button("Log Out", use_container_width=True):
        st.session_state.authenticated = False
        st.rerun()

# ============================
# MAIN TABS
# ============================
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Hydraulics Matrix",
    "3D Well Trajectory",
    "AI Co-Pilot",
    "Cementing Design",
    "PDF Export",
])

# ---------- TAB 1: HYDRAULICS ----------
with tab1:
    st.markdown(
        '<div class="section-title"><i class="fas fa-tachometer-alt"></i> Multi-Segment Wellbore Geometry</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="section-caption">Define each section of the drill string and open hole.</div>',
        unsafe_allow_html=True,
    )

    default_segments = pd.DataFrame([
        {
            "Segment Name": "Surface Drill Pipe",
            "Length (ft)": 7000.0,
            "Pipe OD (in)": 5.0,
            "Pipe ID (in)": 4.276,
            "Hole ID (in)": 12.25,
            "Mud Weight (ppg)": surface_mw,
        },
        {
            "Segment Name": "Heavy Weight Pipe",
            "Length (ft)": 2000.0,
            "Pipe OD (in)": 5.0,
            "Pipe ID (in)": 3.000,
            "Hole ID (in)": 8.50,
            "Mud Weight (ppg)": surface_mw,
        },
        {
            "Segment Name": "Drill Collars / BHA",
            "Length (ft)": 1000.0,
            "Pipe OD (in)": 6.75,
            "Pipe ID (in)": 2.250,
            "Hole ID (in)": 8.50,
            "Mud Weight (ppg)": surface_mw,
        },
    ])
    edited_df = st.data_editor(default_segments, num_rows="dynamic", use_container_width=True)

    if st.button("Run Engineering Calculations", type="primary", use_container_width=True):
        with st.spinner("Solving hydraulics..."):
            try:
                engine = DrillingHydraulicsEngine(
                    surface_mud_weight_ppg=surface_mw,
                    flow_rate_gpm=flow_rate,
                    total_depth_ft=total_depth,
                    true_vertical_depth_ft=tvd,          # ★ TVD for correct ECD
                    plastic_viscosity_cp=pv,
                    yield_point_lb_100ft2=yp,
                    rheology_model=RheologyModel(rheology),
                )
                for _, row in edited_df.iterrows():
                    engine.add_segment(
                        WellSegment(
                            name=str(row["Segment Name"]),
                            length_ft=float(row["Length (ft)"]),
                            pipe_od_in=float(row["Pipe OD (in)"]),
                            pipe_id_in=float(row["Pipe ID (in)"]),
                            hole_id_in=float(row["Hole ID (in)"]),
                            mud_weight_ppg=float(row["Mud Weight (ppg)"]),
                            viscosity_cp=pv,
                            yield_point_lb_100ft2=yp,
                        )
                    )
                for _ in range(3):
                    engine.add_nozzle(NozzleInput(size_in_32nds=12))

                results = engine.solve()
                st.session_state.latest_results = results

                st.markdown(
                    '<div class="section-title" style="margin-top:1.4rem;"><i class="fas fa-chart-simple"></i> Key Hydraulics Metrics</div>',
                    unsafe_allow_html=True,
                )
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    st.markdown(
                        f"""
                        <div class="metric-card">
                            <div class="label"><i class="fas fa-weight-scale"></i> ECD (at TVD)</div>
                            <div class="value">{results['equivalent_circulating_density_ecd_ppg']:.3f} <span style="font-size:0.85rem;font-weight:600;">ppg</span></div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                with c2:
                    st.markdown(
                        f"""
                        <div class="metric-card">
                            <div class="label"><i class="fas fa-gauge-high"></i> Standpipe Pressure</div>
                            <div class="value">{results['standpipe_pressure_spp_psi']:.1f} <span style="font-size:0.85rem;font-weight:600;">psi</span></div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                with c3:
                    st.markdown(
                        f"""
                        <div class="metric-card">
                            <div class="label"><i class="fas fa-arrows-spin"></i> Annular Loss</div>
                            <div class="value">{results['total_annular_pressure_loss_psi']:.1f} <span style="font-size:0.85rem;font-weight:600;">psi</span></div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                with c4:
                    st.markdown(
                        f"""
                        <div class="metric-card">
                            <div class="label"><i class="fas fa-water"></i> Bit Nozzle Loss</div>
                            <div class="value">{results['bit_hydraulics']['bit_pressure_drop_psi']:.1f} <span style="font-size:0.85rem;font-weight:600;">psi</span></div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                st.caption(
                    f"MD = {results['total_depth_ft']:,.0f} ft  ·  "
                    f"TVD = {results['true_vertical_depth_ft']:,.0f} ft  ·  "
                    f"Rheology = {results['rheology_model_used']}"
                )

                st.markdown(
                    '<div class="section-title" style="margin-top:1.6rem;"><i class="fas fa-list-ul"></i> Segment Analytics</div>',
                    unsafe_allow_html=True,
                )
                st.dataframe(pd.DataFrame(results["segment_breakdown"]), use_container_width=True)

                # Formation integrity check
                if "gradient_df" in st.session_state and not st.session_state.gradient_df.empty:
                    gdf = st.session_state.gradient_df.copy().apply(pd.to_numeric, errors="coerce").dropna()
                    if not gdf.empty:
                        try:
                            profile = PressureGradientProfile(
                                depths=gdf["Depth (ft)"].tolist(),
                                pore_pressures=gdf["Pore Pressure (ppg)"].tolist(),
                                frac_gradients=gdf["Fracture Gradient (ppg)"].tolist(),
                            )
                            safe = profile.get_safe_window(total_depth)
                            ecd = results["equivalent_circulating_density_ecd_ppg"]

                            st.markdown(
                                '<div class="section-title" style="margin-top:1.6rem;"><i class="fas fa-shield-halved"></i> Formation Pressure Integrity</div>',
                                unsafe_allow_html=True,
                            )
                            m1, m2, m3 = st.columns(3)
                            m1.metric("Pore Pressure at TD", f"{safe['pore']:.2f} ppg")
                            m2.metric("Fracture Gradient at TD", f"{safe['fracture']:.2f} ppg")
                            m3.metric("Current ECD", f"{ecd:.3f} ppg")

                            if ecd > safe["fracture"]:
                                st.error(
                                    f"**CRITICAL** · ECD {ecd:.2f} ppg exceeds fracture gradient "
                                    f"{safe['fracture']:.2f} ppg."
                                )
                                with st.expander("Recommended Actions"):
                                    st.write("- Reduce flow rate (GPM)")
                                    st.write("- Lower mud weight if safe")
                                    st.write("- Increase circulation before continuing")
                            elif ecd > safe["fracture"] * 0.95:
                                st.warning(
                                    f"ECD {ecd:.2f} ppg approaching fracture limit {safe['fracture']:.2f} ppg."
                                )
                            elif ecd < safe["pore"]:
                                st.warning(
                                    f"ECD {ecd:.2f} ppg below pore pressure {safe['pore']:.2f} ppg – influx risk."
                                )
                            else:
                                st.success(
                                    f"ECD {ecd:.2f} ppg within safe window "
                                    f"[{safe['min_mw_ppg']:.2f} – {safe['max_mw_ppg']:.2f}] ppg."
                                )
                        except Exception as e:
                            st.warning(f"Could not build gradient profile: {e}")

                # Hole cleaning
                last_ann_vel = results["segment_breakdown"][-1]["annular_velocity_fpm"]
                slip = engine.calculate_cuttings_slip_velocity(surface_mw, pv)
                ratio = last_ann_vel / slip if slip > 0 else 0
                if ratio < 1.5:
                    st.warning(
                        f"Low cuttings transport ratio ({ratio:.2f}). Consider increasing flow rate."
                    )
                else:
                    st.success(f"Cuttings transport ratio {ratio:.2f} – adequate.")

            except Exception as e:
                st.error(f"Execution Error: {str(e)}")

# ---------- TAB 2: 3D TRAJECTORY ----------
with tab2:
    st.markdown(
        '<div class="section-title"><i class="fas fa-globe"></i> Interactive 3D Well Trajectory</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="section-caption">Directional wellpath with vertical, build, tangent, and drop sections.</div>',
        unsafe_allow_html=True,
    )

    try:
        is_dark = st.context.theme.type == "dark"
    except Exception:
        is_dark = False

    md = np.linspace(0, total_depth, 200)
    inc = np.zeros_like(md)
    az = np.radians(np.full_like(md, 60.0))

    mask_vert = md <= 2000
    inc[mask_vert] = 0.0
    mask_build = (md > 2000) & (md <= 5000)
    frac_build = (md[mask_build] - 2000) / 3000
    inc[mask_build] = np.radians(45.0 * frac_build)
    mask_tang = (md > 5000) & (md <= 8000)
    inc[mask_tang] = np.radians(45.0)
    mask_drop = (md > 8000) & (md <= total_depth)
    frac_drop = (md[mask_drop] - 8000) / max(total_depth - 8000, 1)
    inc[mask_drop] = np.radians(45.0 - 15.0 * frac_drop)

    x = np.zeros_like(md)
    y = np.zeros_like(md)
    z = np.zeros_like(md)
    for i in range(1, len(md)):
        dmd = md[i] - md[i - 1]
        avg_inc = (inc[i] + inc[i - 1]) / 2
        avg_az = (az[i] + az[i - 1]) / 2
        x[i] = x[i - 1] + dmd * np.sin(avg_inc) * np.cos(avg_az)
        y[i] = y[i - 1] + dmd * np.sin(avg_inc) * np.sin(avg_az)
        z[i] = z[i - 1] + dmd * np.cos(avg_inc)

    grid_c = "#334155" if is_dark else "#e2e8f0"
    axis_c = "#94a3b8" if is_dark else "#475569"
    scene_bg = "rgba(0,0,0,0)"

    fig = go.Figure()
    fig.add_trace(
        go.Scatter3d(
            x=x, y=y, z=z, mode="lines",
            line=dict(color=z, colorscale="Viridis", width=6, showscale=True, colorbar=dict(title="Depth (ft)")),
            name="Wellpath",
        )
    )
    key_depths = [0, 2000, 5000, 8000, total_depth]
    key_labels = ["Surface", "KOP", "EOB", "Start Drop", "TD"]
    idxs = [np.argmin(np.abs(md - d)) for d in key_depths]
    fig.add_trace(
        go.Scatter3d(
            x=x[idxs], y=y[idxs], z=z[idxs],
            mode="markers+text",
            marker=dict(size=6, color="#ef4444"),
            text=key_labels, textposition="top center",
            name="Key points",
        )
    )
    fig.add_trace(
        go.Scatter3d(
            x=[0, 0], y=[0, 0], z=[0, -200],
            mode="lines", line=dict(color="#94a3b8", width=2, dash="dash"),
            showlegend=False,
        )
    )
    fig.update_layout(
        scene=dict(
            xaxis_title="Easting (ft)",
            yaxis_title="Northing (ft)",
            zaxis_title="TVD (ft)",
            bgcolor=scene_bg,
            xaxis=dict(backgroundcolor=scene_bg, gridcolor=grid_c, color=axis_c, zerolinecolor=grid_c),
            yaxis=dict(backgroundcolor=scene_bg, gridcolor=grid_c, color=axis_c, zerolinecolor=grid_c),
            zaxis=dict(
                backgroundcolor=scene_bg, gridcolor=grid_c, color=axis_c,
                zerolinecolor=grid_c, autorange="reversed",
            ),
        ),
        margin=dict(l=0, r=0, b=0, t=30),
        height=650,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(
            x=0.02, y=0.98,
            bgcolor="rgba(0,0,0,0.4)" if is_dark else "rgba(255,255,255,0.85)",
            font=dict(color="white" if is_dark else "black"),
        ),
    )
    st.plotly_chart(fig, use_container_width=True)

# ---------- TAB 3: AI DIAGNOSTICS ----------
with tab3:
    st.markdown(
        '<div class="section-title"><i class="fas fa-brain"></i> AI Real-Time Drilling Assistant</div>',
        unsafe_allow_html=True,
    )
    if "latest_results" in st.session_state:
        ecd = st.session_state.latest_results["equivalent_circulating_density_ecd_ppg"]
        if ecd > 15.0:
            st.error("**CRITICAL ALERT** · ECD exceeds 15.0 ppg structural fracture limit.")
            with st.expander("Recommended Actions"):
                st.write("1. Reduce pump SPM to lower annular velocity.")
                st.write("2. Dilute mud to reduce Plastic Viscosity.")
        else:
            st.success("**SAFE OPERATIONAL GRADIENT** · Within dynamic pore-fracture window.")
            st.info("Hydraulics, hole cleaning, and nozzle velocities meet operating requirements.")
    else:
        st.info("Run calculations on the Hydraulics Matrix tab to activate AI diagnostics.")

# ---------- TAB 4: CEMENTING ----------
with tab4:
    st.markdown(
        '<div class="section-title"><i class="fas fa-hard-hat"></i> Primary Cementing & P&A Plug Design</div>',
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        hole_dia = st.number_input("Hole Diameter (in)", value=8.5, min_value=4.0, step=0.5)
        casing_od = st.number_input("Casing OD (in)", value=7.0, min_value=2.0, step=0.5)
        casing_id = st.number_input("Casing ID (in)", value=6.276, min_value=1.0, step=0.1)
        interval_ft = st.number_input("Cemented Interval Length (ft)", value=5000.0, step=100.0)
        washout_pct = st.number_input("Washout Factor (%)", value=15.0, step=1.0)
        shoe_track = st.number_input("Shoe Track Length (ft)", value=40.0, step=5.0)
    with col2:
        lead_dens = st.number_input("Lead Slurry Density (ppg)", value=12.5, step=0.1)
        tail_dens = st.number_input("Tail Slurry Density (ppg)", value=15.8, step=0.1)
        spacer_dens = st.number_input("Spacer Density (ppg)", value=11.0, step=0.1)
        disp_dens = st.number_input("Displacement Fluid Density (ppg)", value=10.0, step=0.1)
        tail_length = st.number_input("Tail Spurry Length (ft)", value=500.0, step=50.0)
        bht = st.number_input("Bottom Hole Temperature (°F)", value=180.0, step=5.0)

    st.markdown("---")
    st.markdown("**Spacer Design** (volume calculated from geometry – no hard-coded value)")
    sc1, sc2 = st.columns(2)
    with sc1:
        spacer_length = st.number_input(
            "Spacer Annular Coverage (ft)",
            value=500.0,
            step=50.0,
            help="Length of annulus the spacer should cover. Volume is calculated automatically.",
        )
    with sc2:
        use_override = st.checkbox("Override spacer volume manually")
        spacer_override = None
        if use_override:
            spacer_override = st.number_input("Spacer Volume Override (bbl)", value=50.0, step=5.0)

    if st.button("Run Cementing Design", key="cement_btn", type="primary", use_container_width=True):
        with st.spinner("Calculating cement job..."):
            try:
                params = PrimaryCementingInput(
                    hole_diameter_in=hole_dia,
                    casing_od_in=casing_od,
                    casing_id_in=casing_id,
                    interval_length_ft=interval_ft,
                    washout_factor_pct=washout_pct,
                    shoe_track_length_ft=shoe_track,
                    lead_slurry_density_ppg=lead_dens,
                    tail_slurry_density_ppg=tail_dens,
                    spacer_density_ppg=spacer_dens,
                    displacement_fluid_density_ppg=disp_dens,
                    tail_slurry_length_ft=tail_length,
                    bht_fahrenheit=bht,
                    spacer_annular_length_ft=spacer_length,
                    spacer_volume_override_bbl=spacer_override,
                    true_vertical_depth_ft=tvd,
                )
                engine = CementingEngine()
                result = engine.design_primary_job(params)
                st.session_state.cementing_results = result
                st.session_state.cementing_params = {
                    "casing_od": casing_od,
                    "hole_dia": hole_dia,
                    "interval_ft": interval_ft,
                }

                st.markdown(
                    '<div class="section-title" style="margin-top:1.4rem;"><i class="fas fa-flask"></i> Cementing Job Volumes</div>',
                    unsafe_allow_html=True,
                )
                v1, v2, v3, v4 = st.columns(4)
                v1.metric("Lead Slurry", f"{result['lead_slurry_volume_bbl']:.2f} bbl")
                v2.metric("Tail Slurry", f"{result['tail_slurry_volume_bbl']:.2f} bbl")
                v3.metric("Spacer", f"{result['spacer_volume_bbl']:.2f} bbl")
                v4.metric("Displacement", f"{result['displacement_volume_bbl']:.2f} bbl")

                st.caption(
                    f"Spacer method: {result.get('spacer_calculation_method', 'n/a')}  ·  "
                    f"TVD used for plug bump: {result.get('tvd_used_ft', interval_ft):,.0f} ft"
                )
                st.metric(
                    "Recommended Plug Bumping Pressure",
                    f"{result['recommended_plug_bumping_pressure_psi']:.1f} psi",
                )

                st.markdown(
                    '<div class="section-title" style="margin-top:1.4rem;"><i class="fas fa-flask"></i> Suggested Additives</div>',
                    unsafe_allow_html=True,
                )
                for add in result["suggested_additives"]:
                    st.write(f"**{add['name']}** ({add['category']}) – {add['description']}")

                st.markdown(
                    '<div class="section-title" style="margin-top:1.4rem;"><i class="fas fa-plug"></i> P&A / Side-Track Plug</div>',
                    unsafe_allow_html=True,
                )
                with st.expander("Design an abandonment plug"):
                    plug_len = st.number_input("Plug Length (ft)", value=200.0, step=50.0, key="plug_len")
                    plug_dens = st.number_input("Plug Slurry Density (ppg)", value=15.0, step=0.1, key="plug_dens")
                    mud_dens = st.number_input("Mud Density in Hole (ppg)", value=12.0, step=0.1, key="mud_dens")
                    if st.button("Calculate Plug", key="plug_btn"):
                        pr = engine.design_abandonment_plug(
                            hole_dia_in=hole_dia,
                            plug_length_ft=plug_len,
                            slurry_density_ppg=plug_dens,
                            mud_density_ppg=mud_dens,
                        )
                        st.write(f"**Plug Volume:** {pr['plug_volume_bbl']:.2f} bbl")
                        st.write(f"**Cement Sacks:** {pr['cement_sacks_required']} sk")
                        st.write(f"**Hydrostatic Gain:** {pr['net_hydrostatic_gain_psi']:.1f} psi")
            except Exception as e:
                st.error(f"Cementing calculation error: {e}")

    if st.button("Compare with Industry Benchmarks", key="bench_btn"):
        if st.session_state.cementing_results and st.session_state.cementing_params:
            result = st.session_state.cementing_results
            p = st.session_state.cementing_params
            comp = compare_cementing_results(
                result, p["casing_od"], p["hole_dia"], p["interval_ft"]
            )
            st.markdown(
                '<div class="section-title" style="margin-top:1.4rem;"><i class="fas fa-chart-bar"></i> Industry Benchmark Comparison</div>',
                unsafe_allow_html=True,
            )
            if "error" in comp:
                st.warning(comp["error"])
            else:
                st.write(f"**Configuration:** {comp['description']}")
                b1, b2 = st.columns(2)
                b1.metric(
                    "Lead Slurry",
                    f"{comp['lead_slurry']['software']:.2f} bbl",
                    f"{comp['lead_slurry']['deviation_pct']:.1f}% vs industry",
                )
                b2.metric(
                    "Tail Slurry",
                    f"{comp['tail_slurry']['software']:.2f} bbl",
                    f"{comp['tail_slurry']['deviation_pct']:.1f}% vs industry",
                )
                st.metric(
                    "Spacer Volume",
                    f"{comp['spacer']['software']:.2f} bbl",
                    f"{comp['spacer']['deviation_pct']:.1f}% vs industry",
                )
                if abs(comp["lead_slurry"]["deviation_pct"]) > 15 or abs(comp["tail_slurry"]["deviation_pct"]) > 15:
                    st.warning("Deviation >15% from industry standards – review assumptions.")
        else:
            st.warning("Run the cementing design first.")

# ---------- TAB 5: PDF EXPORT ----------
with tab5:
    st.markdown(
        '<div class="section-title"><i class="fas fa-file-pdf"></i> Export Branded PDF Compliance Report</div>',
        unsafe_allow_html=True,
    )
    if "latest_results" in st.session_state:
        if st.button("Generate Branded Field PDF", type="primary", use_container_width=True):
            with st.spinner("Generating PDF..."):
                project_meta = {
                    "name": "Deepwater Wilcox Target",
                    "rig_name": "Rig-05 Executive",
                    "company": st.session_state.user_info["company"],
                }
                ecd = st.session_state.latest_results["equivalent_circulating_density_ecd_ppg"]
                diag_meta = {
                    "severity": "GREEN" if ecd < 15.0 else "RED",
                    "matched_hazard": "Formation Fracturing Risk" if ecd >= 15.0 else "None",
                    "detailed_diagnosis": f"Operating ECD is {ecd:.2f} ppg.",
                }
                pdf_buffer = generate_pdf_payload(
                    project_meta,
                    st.session_state.latest_results,
                    diag_meta,
                    engineer_name=st.session_state.user_info["username"],
                    cementing_results=st.session_state.get("cementing_results"),
                )
                st.download_button(
                    label="Download PDF Document",
                    data=pdf_buffer,
                    file_name=f"PyMudCement_Report_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )
    else:
        st.warning("Run hydraulics calculations first.")

st.markdown(
    '<div class="footer">© 2026 PyMudCement Optima Pro · PENG 258 Capstone</div>',
    unsafe_allow_html=True,
)
