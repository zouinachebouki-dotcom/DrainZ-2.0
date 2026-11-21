
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta

# =========================================================
# PAGE CONFIGURATION
# =========================================================
st.set_page_config(
    page_title="DrainZ 2.0 | Process Monitoring",
    page_icon="⚙",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =========================================================
# INDUSTRIAL THEME
# =========================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}
.stApp {
    background: #0b1118;
    color: #e6edf3;
}
[data-testid="stSidebar"] {
    background: #111c27;
    border-right: 1px solid #263746;
}
[data-testid="stSidebar"] * {
    color: #dce6ed;
}
.block-container {
    padding-top: 1.5rem;
    padding-bottom: 2rem;
    max-width: 1600px;
}
h1, h2, h3 {
    color: #edf3f7;
    letter-spacing: -0.5px;
}
.section-label {
    color: #8fa5b5;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 1.5px;
    margin: 18px 0 10px 0;
}
.panel {
    background: #14212d;
    border: 1px solid #263b4b;
    border-radius: 10px;
    padding: 17px 19px;
}
.metric-card {
    background: linear-gradient(145deg, #182735, #14212b);
    border: 1px solid #2b4050;
    border-radius: 10px;
    padding: 17px 18px;
    min-height: 112px;
}
.metric-label {
    color: #9aafbd;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: .7px;
    text-transform: uppercase;
}
.metric-value {
    color: #f0f5f8;
    font-size: 27px;
    font-weight: 700;
    margin-top: 9px;
}
.metric-unit {
    color: #8da4b4;
    font-size: 13px;
    font-weight: 500;
}
.muted {
    color: #8fa4b3;
    font-size: 12px;
}
.status-normal {
    color: #57cf98;
    font-weight: 700;
}
.status-warning {
    color: #f4bd55;
    font-weight: 700;
}
.status-critical {
    color: #ff7070;
    font-weight: 700;
}
div[data-testid="stMetric"] {
    background: #162430;
    border: 1px solid #2b4050;
    border-radius: 9px;
    padding: 14px 16px;
}
div[data-testid="stMetricLabel"] {
    color: #9aafbd;
}
div[data-testid="stMetricValue"] {
    color: #f0f5f8;
}
.stButton button {
    border-radius: 7px;
    font-weight: 600;
}
hr {
    border-color: #263746;
}
footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:
    st.markdown("## ⚙ DRAINZ **2.0**")
    st.caption("INDUSTRIAL MONITORING SYSTEM")
    st.divider()

    page = st.radio(
        "NAVIGATION",
        [
            "Process Overview",
            "Instrumentation",
            "Fault Diagnosis",
            "Historical Trends",
            "System Information"
        ],
        label_visibility="visible"
    )

    st.divider()
    st.markdown("### FACILITY")
    st.markdown("**Facility 01**")
    st.caption("Oily-water collection and transfer")

    st.markdown("### COMMUNICATION")
    st.markdown(
        '<span class="status-normal">● SIMULATION ACTIVE</span>',
        unsafe_allow_html=True
    )
    st.caption("No physical controller connected")

    st.divider()
    st.caption("DRAINZ 2.0 · ACADEMIC PFE PROTOTYPE")
    st.caption("Monitoring and fault diagnosis")

# =========================================================
# SIMULATION CONTROLS
# =========================================================
if "level" not in st.session_state:
    st.session_state.level = 66.4
    st.session_state.flow = 20.1
    st.session_state.current = 4.28
    st.session_state.pump = True

with st.sidebar:
    with st.expander("SIMULATION CONTROLS", expanded=False):
        st.caption("Adjust values to demonstrate operating conditions.")

        st.session_state.level = st.slider(
            "Sump level (%)", 0, 100,
            int(st.session_state.level)
        )
        st.session_state.flow = st.slider(
            "Discharge flow (m³/h)", 0.0, 35.0,
            float(st.session_state.flow), 0.5
        )
        st.session_state.current = st.slider(
            "Motor current (A)", 0.0, 10.0,
            float(st.session_state.current), 0.1
        )
        st.session_state.pump = st.toggle(
            "Pump running",
            value=st.session_state.pump
        )

        if st.button("Reset normal conditions", use_container_width=True):
            st.session_state.level = 66.4
            st.session_state.flow = 20.1
            st.session_state.current = 4.28
            st.session_state.pump = True
            st.rerun()

level = float(st.session_state.level)
flow = float(st.session_state.flow)
current = float(st.session_state.current)
pump_on = bool(st.session_state.pump)

# =========================================================
# DIAGNOSTIC RULES - ILLUSTRATIVE
# =========================================================
diagnosis = "Normal operating conditions"
severity = "NORMAL"
recommendation = "Continue normal monitoring."

if level >= 90:
    diagnosis = "High sump level"
    severity = "CRITICAL"
    recommendation = "Inspect the pumping and discharge system."

elif pump_on and flow < 10:
    diagnosis = "Possible low discharge / restriction"
    severity = "WARNING"
    recommendation = "Check discharge line, valves and pump condition."

elif pump_on and level > 75 and flow < 15:
    diagnosis = "Possible insufficient pumping"
    severity = "WARNING"
    recommendation = "Investigate pump performance and hydraulic conditions."

elif pump_on and current > 7:
    diagnosis = "Abnormally high motor current"
    severity = "WARNING"
    recommendation = "Inspect motor load and mechanical condition."

elif not pump_on and level >= 75:
    diagnosis = "High level while pump is stopped"
    severity = "WARNING"
    recommendation = "Check pump availability and operating command."

# =========================================================
# TOP HEADER
# =========================================================
header_left, header_right = st.columns([3, 1])

with header_left:
    st.markdown("# DrainZ 2.0")
    st.markdown(
        '<div class="muted">INTELLIGENT INDUSTRIAL DRAINAGE '
        '& PUMP MONITORING SYSTEM</div>',
        unsafe_allow_html=True
    )

with header_right:
    st.markdown(
        f'<div style="text-align:right;padding-top:14px;">'
        f'<span class="status-normal">● SIMULATION MODE</span><br>'
        f'<span class="muted">{datetime.now().strftime("%d %b %Y · %H:%M")}</span>'
        f'</div>',
        unsafe_allow_html=True
    )

st.divider()

# =========================================================
# REUSABLE PROCESS DIAGRAM
# =========================================================
def process_diagram(level_value, flow_value, current_value, pump_status):
    fig = go.Figure()

    # Inlet pipe
    fig.add_shape(
        type="line", x0=0.5, y0=5.0, x1=3.2, y1=5.0,
        line=dict(color="#4c9fbd", width=12)
    )

    # Sump vessel
    fig.add_shape(
        type="rect", x0=3.2, y0=1.0, x1=6.0, y1=6.7,
        line=dict(color="#b5c5cf", width=3),
        fillcolor="#172735"
    )

    # Liquid inside sump
    liquid_top = 1.1 + 5.45 * level_value / 100
    fig.add_shape(
        type="rect", x0=3.28, y0=1.08, x1=5.92, y1=liquid_top,
        line=dict(width=0),
        fillcolor="rgba(35,145,190,0.58)"
    )

    # Liquid level line
    fig.add_shape(
        type="line", x0=3.3, y0=liquid_top, x1=5.9, y1=liquid_top,
        line=dict(color="#56c6e5", width=2, dash="dash")
    )

    # Suction pipe
    fig.add_shape(
        type="line", x0=6.0, y0=2.0, x1=7.2, y1=2.0,
        line=dict(color="#4c9fbd", width=10)
    )

    # Pump body
    pump_color = "#43bd86" if pump_status else "#758493"
    fig.add_shape(
        type="circle", x0=7.0, y0=1.25, x1=8.5, y1=2.75,
        line=dict(color=pump_color, width=3),
        fillcolor="#203a42"
    )

    # Pump impeller symbol
    fig.add_shape(
        type="circle", x0=7.48, y0=1.73, x1=8.02, y1=2.27,
        line=dict(color="#dce9ef", width=2),
        fillcolor="#527080"
    )

    # Discharge pipe
    fig.add_shape(
        type="line", x0=8.5, y0=2.0, x1=12.2, y1=2.0,
        line=dict(color="#4c9fbd", width=10)
    )

    # Flow transmitter location
    fig.add_shape(
        type="circle", x0=9.7, y0=1.55, x1=10.6, y1=2.45,
        line=dict(color="#f0c36b", width=2),
        fillcolor="#172735"
    )

    # Level transmitter bubble
    fig.add_shape(
        type="circle", x0=4.0, y0=7.05, x1=4.75, y1=7.8,
        line=dict(color="#e7bd69", width=2),
        fillcolor="#172735"
    )

    # Instrument and process labels
    annotations = [
        dict(x=1.7, y=5.45, text="INLET",
             showarrow=False, font=dict(color="#b9c9d3", size=12)),
        dict(x=4.6, y=6.95, text="COLLECTION SUMP · TK-101",
             showarrow=False, font=dict(color="#e7edf1", size=12)),
        dict(x=4.37, y=7.42, text="LT",
             showarrow=False, font=dict(color="#f0c36b", size=13)),
        dict(x=4.6, y=liquid_top - 0.3,
             text=f"{level_value:.1f}%",
             showarrow=False, font=dict(color="white", size=17)),
        dict(x=7.75, y=3.0, text="P-101",
             showarrow=False, font=dict(color="#e7edf1", size=12)),
        dict(x=7.75, y=2.0, text="P",
             showarrow=False, font=dict(color="white", size=22)),
        dict(x=7.75, y=0.85,
             text="RUNNING" if pump_status else "STOPPED",
             showarrow=False, font=dict(color=pump_color, size=12)),
        dict(x=10.15, y=2.95, text="FT-101",
             showarrow=False, font=dict(color="#e7edf1", size=12)),
        dict(x=10.15, y=2.0, text="FT",
             showarrow=False, font=dict(color="#f0c36b", size=12)),
        dict(x=11.4, y=2.5, text="DISCHARGE",
             showarrow=False, font=dict(color="#b9c9d3", size=12)),
        dict(x=6.4, y=1.45, text="SUCTION",
             showarrow=False, font=dict(color="#8fa5b5", size=10))
    ]

    fig.update_layout(
        annotations=annotations,
        height=450,
        margin=dict(l=10, r=10, t=20, b=15),
        xaxis=dict(visible=False, range=[0, 12.7]),
        yaxis=dict(visible=False, range=[0.4, 8.2]),
        plot_bgcolor="#14212d",
        paper_bgcolor="#14212d",
        showlegend=False,
        dragmode=False
    )
    return fig

# =========================================================
# PAGE 1 - PROCESS OVERVIEW
# =========================================================
if page == "Process Overview":

    st.markdown('<div class="section-label">01 / PROCESS MEASUREMENTS</div>',
                unsafe_allow_html=True)

    m1, m2, m3, m4 = st.columns(4)

    with m1:
        st.metric("SUMP LEVEL", f"{level:.1f} %", "LT-101")
    with m2:
        st.metric("DISCHARGE FLOW", f"{flow:.1f} m³/h", "FT-101")
    with m3:
        st.metric("MOTOR CURRENT", f"{current:.2f} A", "AIT-101")
    with m4:
        st.metric("PUMP STATUS", "RUNNING" if pump_on else "STOPPED",
                  "P-101")

    st.markdown('<div class="section-label">02 / HYDRAULIC PROCESS OVERVIEW</div>',
                unsafe_allow_html=True)

    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.plotly_chart(
        process_diagram(level, flow, current, pump_on),
        use_container_width=True,
        config={"displayModeBar": False}
    )
    st.markdown(
        '<div class="muted">Process representation: inlet → collection '
        'sump → transfer pump → discharge. Instrument tags are proposed '
        'identifiers for this prototype.</div>',
        unsafe_allow_html=True
    )
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="section-label">03 / SYSTEM DIAGNOSTICS</div>',
                unsafe_allow_html=True)

    left, right = st.columns([2, 1])

    with left:
        if severity == "NORMAL":
            st.success("NORMAL OPERATION  |  " + diagnosis)
        elif severity == "WARNING":
            st.warning("WARNING  |  " + diagnosis)
        else:
            st.error("CRITICAL ALARM  |  " + diagnosis)

        st.markdown("**Suggested inspection:** " + recommendation)

    with right:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown("**EQUIPMENT STATUS**")
        st.markdown(
            f'<span class="status-normal">● LT-101</span> '
            f'<span class="muted">Level measurement</span><br>'
            f'<span class="status-normal">● FT-101</span> '
            f'<span class="muted">Flow measurement</span><br>'
            f'<span class="status-normal">● AIT-101</span> '
            f'<span class="muted">Current measurement</span><br>'
            f'<span style="color:{pump_color if False else "#43bd86" if pump_on else "#8997a3"}">'
            f'● P-101</span> <span class="muted">Transfer pump</span>',
            unsafe_allow_html=True
        )
        st.markdown('</div>', unsafe_allow_html=True)

# =========================================================
# PAGE 2 - INSTRUMENTATION
# =========================================================
elif page == "Instrumentation":

    st.markdown("## Instrumentation")
    st.caption("FIELD MEASUREMENTS AND EQUIPMENT STATUS")

    instruments = pd.DataFrame([
        ["LT-101", "Level transmitter", f"{level:.1f} %", "Sump"],
        ["FT-101", "Flow transmitter", f"{flow:.1f} m³/h", "Discharge"],
        ["AIT-101", "Motor current", f"{current:.2f} A", "Pump motor"],
        ["P-101", "Transfer pump", "RUNNING" if pump_on else "STOPPED", "Equipment"]
    ], columns=["TAG", "DESCRIPTION", "VALUE", "LOCATION"])

    st.dataframe(instruments, use_container_width=True, hide_index=True)

    st.markdown("### Measurement details")
    a, b = st.columns(2)
    with a:
        st.metric("Level transmitter · LT-101", f"{level:.1f} %")
        st.metric("Flow transmitter · FT-101", f"{flow:.1f} m³/h")
    with b:
        st.metric("Motor current · AIT-101", f"{current:.2f} A")
        st.metric("Transfer pump · P-101",
                  "RUNNING" if pump_on else "STOPPED")

    st.info(
        "The current dashboard uses simulated measurements. "
        "Actual instrument ranges and tag conventions must be confirmed "
        "during detailed design."
    )

# =========================================================
# PAGE 3 - FAULT DIAGNOSIS
# =========================================================
elif page == "Fault Diagnosis":

    st.markdown("## Fault Diagnosis")
    st.caption("RULE-BASED MONITORING · PRELIMINARY DIAGNOSTIC LOGIC")

    if severity == "NORMAL":
        st.success("NORMAL — " + diagnosis)
    elif severity == "WARNING":
        st.warning("WARNING — " + diagnosis)
    else:
        st.error("CRITICAL — " + diagnosis)

    st.markdown("### Current operating conditions")
    st.write(f"- Sump level: **{level:.1f}%**")
    st.write(f"- Discharge flow: **{flow:.1f} m³/h**")
    st.write(f"- Motor current: **{current:.2f} A**")
    st.write(f"- Pump state: **{'Running' if pump_on else 'Stopped'}**")

    st.markdown("### Diagnostic interpretation")
    st.info(diagnosis)
    st.markdown("**Suggested inspection:** " + recommendation)

    st.markdown("### Diagnostic scenarios")
    scenarios = pd.DataFrame([
        ["Level rises + discharge flow falls",
         "Possible restriction or insufficient pumping"],
        ["Pump running + no discharge flow",
         "Possible pump, valve or discharge problem"],
        ["Motor current unusually high",
         "Possible overload or mechanical issue"],
        ["High level while pump is stopped",
         "Pump availability or control issue"]
    ], columns=["OBSERVED BEHAVIOUR", "POSSIBLE INTERPRETATION"])

    st.dataframe(scenarios, use_container_width=True, hide_index=True)

    st.warning(
        "These are preliminary diagnostic hypotheses, not definitive "
        "fault identification or certified safety protection."
    )

# =========================================================
# PAGE 4 - HISTORICAL TRENDS
# =========================================================
elif page == "Historical Trends":

    st.markdown("## Historical Trends")
    st.caption("ILLUSTRATIVE SIMULATED MEASUREMENT HISTORY")

    rng = np.random.default_rng(12)
    times = [datetime.now() - timedelta(minutes=29-i) for i in range(30)]

    level_data = np.clip(
        level + np.cumsum(rng.normal(0, 0.8, 30)), 0, 100
    )
    flow_data = np.clip(
        flow + rng.normal(0, 1.2, 30), 0, 35
    )
    current_data = np.clip(
        current + rng.normal(0, 0.12, 30), 0, 10
    )

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=times, y=level_data,
        name="Sump level (%)",
        line=dict(color="#42b7d5", width=3)
    ))
    fig.update_layout(
        template="plotly_dark",
        height=350,
        paper_bgcolor="#14212d",
        plot_bgcolor="#14212d",
        yaxis_title="Level (%)",
        margin=dict(l=10, r=10, t=30, b=10)
    )
    st.plotly_chart(fig, use_container_width=True)

    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(
        x=times, y=flow_data,
        name="Flow rate",
        line=dict(color="#5acb95", width=3)
    ))
    fig2.update_layout(
        template="plotly_dark",
        height=300,
        paper_bgcolor="#14212d",
        plot_bgcolor="#14212d",
        yaxis_title="Flow (m³/h)",
        margin=dict(l=10, r=10, t=30, b=10)
    )
    st.plotly_chart(fig2, use_container_width=True)

    fig3 = go.Figure()
    fig3.add_trace(go.Scatter(
        x=times, y=current_data,
        name="Motor current",
        line=dict(color="#e9b65d", width=3)
    ))
    fig3.update_layout(
        template="plotly_dark",
        height=300,
        paper_bgcolor="#14212d",
        plot_bgcolor="#14212d",
        yaxis_title="Current (A)",
        margin=dict(l=10, r=10, t=30, b=10)
    )
    st.plotly_chart(fig3, use_container_width=True)

# =========================================================
# PAGE 5 - SYSTEM INFORMATION
# =========================================================
elif page == "System Information":

    st.markdown("## System Information")
    st.caption("PROJECT DESCRIPTION AND TECHNICAL ARCHITECTURE")

    st.markdown("### Project purpose")
    st.write(
        "DrainZ 2.0 is a proposed intelligent monitoring and fault "
        "diagnosis system for industrial drainage networks and "
        "wastewater pumping stations in Oil & Gas facilities."
    )

    st.markdown("### Proposed architecture")
    st.markdown("""
    1. **Field layer:** level, flow and motor-current measurements.
    2. **Acquisition layer:** Arduino or ESP32 prototype controller.
    3. **Communication layer:** suitable wired or wireless link.
    4. **Supervision layer:** Python-based monitoring dashboard.
    5. **Diagnostic layer:** engineering rules and trend analysis.
    """)

    st.markdown("### Proposed technologies")
    tech = pd.DataFrame([
        ["Controller", "Arduino / ESP32"],
        ["Level measurement", "Ultrasonic sensor for prototype"],
        ["Flow measurement", "Suitable water flow sensor for prototype"],
        ["Current measurement", "Low-voltage motor current sensor"],
        ["Software", "Python and Streamlit"],
        ["Data visualization", "Plotly"],
        ["Industrial concept", "PLC / SCADA architecture"]
    ], columns=["COMPONENT", "PROPOSED TECHNOLOGY"])

    st.dataframe(tech, use_container_width=True, hide_index=True)

    st.markdown("### Important limitation")
    st.write(
        "This version is a visual and functional simulation prototype. "
        "It is not connected to real industrial instruments and does "
        "not replace pump protections, PLC interlocks or safety systems."
    )

# =========================================================
# FOOTER
# =========================================================
st.divider()
st.markdown(
    '<div style="text-align:center;color:#708595;font-size:11px;">'
    'DRAINZ 2.0 · MASTER PFE PROTOTYPE · SIMULATED DATA · '
    'NOT FOR INDUSTRIAL CONTROL</div>',
    unsafe_allow_html=True
)
