# PyMudCement Optima Pro 

**Intelligent Mud & Cement Design Suite**  
PENG 258 — Drilling Engineering 1 Capstone Project  
Department of Petroleum and Natural Gas Engineering · UENR

---

## Overview

PyMudCement Optima Pro is a Streamlit-based engineering application that automates drilling-fluid hydraulics and primary cementing design. It replaces error-prone hand calculations with a modular, validated Python backend aligned to SPE competencies and the PENG 258 syllabus.

The software covers two core pillars:

| Pillar | Capabilities |
|--------|--------------|
| **Drilling Fluids & Hydraulics** | Mud-weight window, rheology (PV/YP), annular & pipe pressure losses, ECD (TVD-based), hole cleaning, bit hydraulics, laminar/turbulent regime detection |
| **Cementing Engineering** | Annular volumes with washout, lead/tail slurry, spacer & displacement, additive lookup by BHT, plug-bumping pressure, P&A / side-track plugs |

---

## Features

- **Authentication** — secure login / registration with hashed passwords
- **Mud-report parser** — upload CSV/Excel mud reports; auto-fill PV, YP, MW
- **Pore / fracture gradient editor** — depth-dependent safe operating window
- **Multi-segment wellbore model** — drill pipe, HWDP, collars / BHA
- **TVD-aware ECD** — hydrostatic and ECD calculations use True Vertical Depth
- **Flow-regime switching** — Reynolds-number check (laminar ↔ turbulent)
- **3D well trajectory** — interactive Plotly visualisation
- **AI co-pilot diagnostics** — severity-coded alerts and actionable recommendations
- **Primary cementing design** — dynamic volumes (no hard-coded spacer)
- **Additive database** — temperature-based retarder / accelerator suggestions
- **P&A plug design** — volume, sacks, hydrostatic gain
- **Industry benchmark comparison** — slurry volumes vs reference cases
- **Branded PDF export** — compliance-style field report with logo watermark
- **Light / dark theme** — fully compatible with Streamlit’s native theme toggle

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| UI | Streamlit |
| Physics / cementing engines | Pure Python + NumPy |
| Data models | Pydantic |
| Database / auth | SQLAlchemy (async) + password hashing |
| Charts | Plotly |
| PDF reports | ReportLab |
| Deployment | Streamlit Community Cloud (optional) |

---

## Project Structure

```
pymudcement-optima-pro/
├── app.py                  # Main Streamlit frontend
├── physics.py              # Hydraulics engine (ECD, friction, bit, regime)
├── cementing_engine.py     # Primary cementing + P&A volumes
├── pdf_generator.py        # Branded PDF report builder
├── mud_parser.py           # Mud-report CSV/Excel parser
├── gradients.py            # Pore / fracture pressure profile
├── benchmarks.py           # Industry volume comparison
├── database.py             # Async SQLAlchemy models & session
├── auth.py                 # Password hashing / verification
├── logo.png                # Application branding
├── requirements.txt
└── README.md
```

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/<your-org>/pymudcement-optima-pro.git
cd pymudcement-optima-pro
```

### 2. Create a virtual environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

Typical packages:

```
streamlit
pandas
numpy
plotly
pydantic
sqlalchemy
aiosqlite
passlib
bcrypt
reportlab
openpyxl
```

### 4. Run the application

```bash
streamlit run app.py
```

The app opens in your browser at `http://localhost:8501`.

---

## Quick Start

1. **Register / Login** with an email and password.
2. **Sidebar** — set MD, TVD, flow rate, mud weight, PV, YP, rheology model.
3. Optionally upload a mud report (CSV/Excel) to auto-fill fluid properties.
4. Enter pore-pressure and fracture-gradient points in the gradient editor.
5. **Tab 1 – Hydraulics Matrix** — define wellbore segments and click **Run Engineering Calculations**.
6. Review ECD, standpipe pressure, annular loss, bit loss, segment breakdown, and formation-integrity warnings.
7. **Tab 4 – Cementing Design** — enter casing/hole geometry, slurry densities, spacer coverage; run the job design.
8. **Tab 5 – PDF Export** — generate and download a branded field report.

---

## Engineering Notes

### ECD uses True Vertical Depth

```
ECD (ppg) = MW + ΔP_annulus / (0.052 × TVD)
```

Measured depth is used only for segment lengths; hydrostatic and ECD calculations always use TVD, consistent with the syllabus equation \(P_{hyd} = \rho \cdot g \cdot z\).

### Annular volume (cementing)

```
V (bbl) = (Dh² − Dc²) × L / 1029.4 × (1 + We)
```

Matches the syllabus SI form after conversion to oilfield units. Spacer volume is calculated from annular geometry (or an optional user override) — no hard-coded constants.

### Flow regime

Reynolds number is evaluated for pipe and annulus. Laminar handbook formulas are used below Re ≈ 2100; a turbulent approximation is applied above that threshold.

---

## Syllabus Alignment (PENG 258)

| Requirement | Implementation |
|-------------|----------------|
| Minimum mud weight vs pore pressure | Gradient profile + safe-window alerts |
| Rheology (PV / YP) from mud reports | Parser + Bingham / Power-Law / HB models |
| System hydraulics & ECD | Multi-segment engine with TVD |
| Hole-cleaning check | Annular velocity vs slip velocity |
| Cement volumetrics (lead / tail / spacer / displacement) | `CementingEngine.design_primary_job` |
| Additive lookup by temperature | Built-in additive database |
| Plug bumping pressure | Hydrostatic differential + safety margin |
| P&A / side-track plugs | Dedicated sub-module |
| Digital cementing job procedure sheet | PDF export |
| Live demo | Streamlit UI (local or Cloud) |



## License

This project was developed for academic assessment under PENG 258.  
All rights reserved for educational use within UENR.
