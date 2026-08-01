# PyMudCement Optima Pro 🛢️

**PyMudCement Optima Pro** is an enterprise-grade drilling hydraulics calculation engine and automated telemetry diagnostic framework built for oil and gas operations. The platform integrates industrial fluid rheology physics models, multi-segment wellbore geometry analysis, automated hazard diagnostics, and real-time report generation into a web interface and FastAPI backend.

---

## 🌟 Key Features

* **Multi-Rheology Hydraulics Physics Engine**:
  * Supports Newtonian, Bingham Plastic, Power Law, and Herschel-Bulkley fluid models.
  * Calculates Equivalent Circulating Density (ECD), Standpipe Pressure (SPP), annular pressure loss, and pipe friction pressure drop.
  * Bit hydraulics evaluation (Total Nozzle Area, Jet Velocity, Hydraulic Horsepower, Jet Impact Force).
* **Multi-Segment Wellbore Geometry**:
  * Dynamic, flexible wellbore segmentation (Drill Pipe, HWDP, Drill Collars, BHA, Casings, and Open Hole configurations).
  * Segment-by-segment pressure drop and local ECD gradient tracking.
* **AI Telemetry Diagnostics**:
  * Automated telemetry health and safety bounds analysis.
  * Dynamic hazard alerts (e.g., Excessive ECD, formation fracturing risk, SPP over-pressurization warnings).
  * Real-time operational recommendations for drilling fluids engineers.
* **Authentication & Role-Based Access Control (RBAC)**:
  * Secure JWT (OAuth2) bearer token authentication framework (`Passlib`, `Bcrypt`, `python-jose`).
  * User management and well project persistence using asynchronous SQLAlchemy and SQLite/PostgreSQL.
* **Interactive Frontend UI**:
  * Streamlit dashboard for parameter manipulation, multi-segment configuration, interactive table editor, and visual physics output display.
* **Automated PDF Export**:
  * Dynamic PDF reporting system powered by ReportLab for audit-ready compliance documentation.

---

## 🏗️ Architecture Overview