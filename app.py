
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

st.set_page_config(
    page_title="DrainZ 2.0 | Industrial Monitoring",
    page_icon="⚙️",
    layout="wide"
)

# ---------- STYLE ----------
st.markdown("""
<style>
.stApp {background-color: #101820; color: #e8edf2;}
[data-testid="stMetric"] {
    background: #1c2935;
    padding: 18px;
    border: 1px solid #344454;
    border-radius: 10px;
}
h1, h2, h3 {color: #e8edf2;}
.small {color: #9eafbd; font-size: 13px;}
</style>
""", unsafe_allow_html=True)

# ---------- SIMULATED DATA ----------
rng = np.random.default_rng()
level = float(np.clip(64 + rng.normal(0, 2), 0, 100))
flow = float(max(0, 18 + rng.normal(0, 1.5)))
current = float(max(0, 4.2 + rng.normal(0, 0.2)))
pump_on = level > 35

if flow < 12 and pump_on:
    diagnosis = "Possible discharge restriction"
    severity = "WARNING"
elif level > 85:
    diagnosis = "High sump level"
    severity = "CRITICAL"
else:
    diagnosis = "Normal operating conditions"
    severity = "NORMAL"

# ---------- HEADER ----------
st.title("⚙️ DrainZ 2.0")
st.markdown("**INTELLIGENT INDUSTRIAL DRAINAGE & PUMP MONITORING SYSTEM**")
st.caption("Oil & Gas | Sump Monitoring | Pump Fault Diagnosis")

st.warning(
    "DEMONSTRATION MODE — All measurements are simulated. "
    "No physical sensors are connected."
)

c1, c2, c3 = st.columns(3)
c1.metric("SYSTEM STATUS", "ONLINE", "Simulation")
c2.metric("DATE", datetime.now().strftime("%d %b %Y"))
c3.metric("DIAGNOSTIC", severity)

st.divider()

# ---------- MAIN MEASUREMENTS ----------
st.subheader("01 | PROCESS MEASUREMENTS")

a, b, c, d = st.columns(4)
a.metric("Sump Level", f"{level:.1f} %")
b.metric("Discharge Flow", f"{flow:.1f} m³/h")
c.metric("Pump Current", f"{current:.2f} A")
d.metric("Pump Status", "RUNNING" if pump_on else "STOPPED")

st.divider()

# ---------- PROCESS SCHEMATIC ----------
st.subheader("02 | PROCESS OVERVIEW")

fig = go.Figure()

# Pipes
fig.add_shape(type="line", x0=0.5, y0=2.5, x1=3, y1=2.5,
              line=dict(color="#4aa3c7", width=12))
fig.add_shape(type="line", x0=5, y0=2.5, x1=8.5, y1=2.5,
              line=dict(color="#4aa3c7", width=12))

# Sump
fig.add_shape(type="rect", x0=3, y0=0.5, x1=5, y1=3.8,
              line=dict(color="#d8e1e8", width=3),
              fillcolor="#1c2935")

# Water level
water_top = 0.5 + 3.3 * level / 100
fig.add_shape(type="rect", x0=3.05, y0=0.55, x1=4.95,
              y1=water_top, line=dict(width=0),
              fillcolor="rgba(40,150,200,0.65)")

# Pump symbol
fig.add_shape(type="circle", x0=6.2, y0=1.9, x1=7.1, y1=2.8,
              line=dict(color="#64c68b", width=3),
              fillcolor="#263c45")

fig.add_annotation(x=1.6, y=2.9, text="INLET",
                   showarrow=False, font=dict(color="white"))
fig.add_annotation(x=4, y=4.15, text="COLLECTION SUMP",
                   showarrow=False, font=dict(color="white"))
fig.add_annotation(x=4, y=water_top, text=f"{level:.1f}%",
                   showarrow=False, font=dict(color="white"))
fig.add_annotation(x=6.65, y=2.35, text="P",
                   showarrow=False, font=dict(size=22, color="white"))
fig.add_annotation(x=6.65, y=1.45, text="TRANSFER PUMP",
                   showarrow=False, font=dict(color="white"))
fig.add_annotation(x=8, y=2.9, text="DISCHARGE",
                   showarrow=False, font=dict(color="white"))

fig.update_layout(
    height=390,
    xaxis=dict(visible=False, range=[0, 9]),
    yaxis=dict(visible=False, range=[0, 4.8]),
    plot_bgcolor="#101820",
    paper_bgcolor="#101820",
    margin=dict(l=10, r=10, t=20, b=10)
)
st.plotly_chart(fig, use_container_width=True)

st.divider()

# ---------- DIAGNOSIS ----------
st.subheader("03 | INTELLIGENT FAULT DIAGNOSIS")

if severity == "NORMAL":
    st.success("NORMAL — " + diagnosis)
elif severity == "WARNING":
    st.warning("WARNING — " + diagnosis)
else:
    st.error("CRITICAL — " + diagnosis)

st.caption(
    "Diagnostic examples are preliminary engineering rules, "
    "not validated industrial protection functions."
)

# ---------- HISTORICAL TRENDS ----------
st.subheader("04 | HISTORICAL MEASUREMENTS")

time = pd.date_range(end=datetime.now(), periods=30, freq="min")
history = pd.DataFrame({
    "Time": time,
    "Level (%)": np.clip(
        level + np.cumsum(rng.normal(0, 1, 30)), 0, 100
    ),
    "Flow (m³/h)": np.clip(
        flow + rng.normal(0, 1.5, 30), 0, None
    )
})

chart = go.Figure()
chart.add_trace(go.Scatter(
    x=history["Time"], y=history["Level (%)"],
    name="Sump Level", line=dict(width=3)
))
chart.add_trace(go.Scatter(
    x=history["Time"], y=history["Flow (m³/h)"],
    name="Flow Rate", yaxis="y2"
))
chart.update_layout(
    height=350,
    template="plotly_dark",
    paper_bgcolor="#101820",
    plot_bgcolor="#1c2935",
    yaxis=dict(title="Level (%)"),
    yaxis2=dict(title="Flow (m³/h)", overlaying="y", side="right"),
    legend=dict(orientation="h", y=1.12)
)
st.plotly_chart(chart, use_container_width=True)

st.divider()
st.caption(
    "DrainZ 2.0 | Academic PFE Prototype | "
    "Simulation only — not connected to industrial equipment"
)
