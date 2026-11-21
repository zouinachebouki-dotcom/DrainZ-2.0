
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta

# ============================================================
# 1. PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="DrainZ 2.0 | Industrial Monitoring",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================
# 2. INDUSTRIAL SCADA THEME
# ============================================================

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

.stApp {
    background-color: #0b1118;
    color: #e6edf3;
}

[data-testid="stSidebar"] {
    background-color: #111c27;
    border-right: 1px solid #263746;
}

.block-container {
    padding-top: 1.5rem;
    padding-bottom: 2rem;
    max-width: 1600px;
}

h1, h2, h3 {
    color: #edf3f7;
}

.section-label {
    color: #91a9b9;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 1.5px;
    margin-top: 22px;
    margin-bottom: 12px;
}

.panel {
    background: #14212d;
    border: 1px solid #263b4b;
    border-radius: 10px;
    padding: 18px;
}

.metric-card {
    background: #172633;
    border: 1px solid #2b4050;
    border-radius: 10px;
    padding: 17px;
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
    background: #172633;
    border: 1px solid #2b4050;
    border-radius: 9px;
    padding: 14px;
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

footer {
    visibility: hidden;
}
</style>
""", unsafe_allow_html=True)


# ============================================================
# 3. SIMULATION SCENARIOS
# ============================================================

SCENARIOS = {
    "Normal operation": {
        "level": 45.0,
        "flow": 20.0,
        "current": 4.2,
        "pump": True
    },

    "Partial discharge blockage": {
        "level": 82.0,
        "flow": 6.0,
        "current": 5.4,
        "pump": True
    },

    "Pump malfunction": {
        "level": 88.0,
        "flow": 2.0,
        "current": 1.5,
        "pump": True
    },

    "Pump stopped / high level": {
        "level": 86.0,
        "flow": 0.0,
        "current": 0.0,
        "pump": False
    },

    "Abnormal inflow": {
        "level": 88.0,
        "flow": 20.0,
        "current": 4.2,
        "pump": True
    }
}


# ============================================================
# 4. SESSION STATE
# ============================================================

defaults = {
    "level": 45.0,
    "flow": 20.0,
    "current": 4.2,
    "pump": True,
    "scenario": "Normal operation"
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


def apply_scenario():
    values = SCENARIOS[st.session_state.scenario]

    st.session_state.level = values["level"]
    st.session_state.flow = values["flow"]
    st.session_state.current = values["current"]
    st.session_state.pump = values["pump"]


# ============================================================
# 5. SIDEBAR NAVIGATION
# ============================================================

with st.sidebar:

    st.markdown("## ⚙ DRAINZ 2.0")
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
        ]
    )

    st.divider()

    st.markdown("### FACILITY")
    st.markdown("**Facility 01**")
    st.caption("Industrial drainage and pumping")

    st.markdown("### COMMUNICATION")
    st.markdown(
        '<span class="status-normal">● SIMULATION ACTIVE</span>',
        unsafe_allow_html=True
    )
    st.caption("No physical controller connected")

    st.divider()

    st.markdown("### FAULT SIMULATION")

    st.selectbox(
        "Select operating scenario",
        list(SCENARIOS.keys()),
        key="scenario"
    )

    if st.button("Apply selected scenario", use_container_width=True):
        apply_scenario()
        st.rerun()

    st.caption("You can also modify the measurements manually.")

    st.slider(
        "Sump level (%)",
        0, 100,
        key="level"
    )

    st.slider(
        "Discharge flow (m³/h)",
        0.0, 35.0,
        step=0.5,
        key="flow"
    )

    st.slider(
        "Motor current (A)",
        0.0, 10.0,
        step=0.1,
        key="current"
    )

    st.toggle(
        "Pump running",
        key="pump"
    )

    st.divider()

    st.caption("DRAINZ 2.0 · MASTER PFE PROTOTYPE")
    st.caption("Monitoring and fault diagnosis")


# ============================================================
# 6. CURRENT MEASUREMENTS
# ============================================================

level = float(st.session_state.level)
flow = float(st.session_state.flow)
current = float(st.session_state.current)
pump_on = bool(st.session_state.pump)


# ============================================================
# 7. DIAGNOSTIC ENGINE
# ============================================================

diagnosis = "Normal operating conditions"
severity = "NORMAL"
recommendation = "Continue normal monitoring."

observations = []
fault_code = "OK-000"

if level >= 90:

    diagnosis = "Critical sump level"
    severity = "CRITICAL"
    fault_code = "ALM-001"

    recommendation = (
        "Inspect pump availability and discharge conditions. "
        "Verify the high-level condition."
    )

    observations = [
        "Sump level has reached the critical threshold.",
        "The available storage capacity is reduced.",
        "Overflow risk may increase if accumulation continues."
    ]

elif pump_on and flow < 5 and current < 2.5:

    diagnosis = "Possible pump malfunction"
    severity = "WARNING"
    fault_code = "FLT-002"

    recommendation = (
        "Inspect pump operation, motor, suction conditions "
        "and discharge line."
    )

    observations = [
        "Pump is indicated as running.",
        "Discharge flow is very low.",
        "Motor current is also unusually low in this scenario.",
        "The combination suggests possible ineffective pumping."
    ]

elif pump_on and flow < 10 and level > 65:

    diagnosis = "Possible discharge blockage"
    severity = "WARNING"
    fault_code = "FLT-003"

    recommendation = (
        "Inspect discharge piping, valves and possible "
        "hydraulic restrictions."
    )

    observations = [
        "Pump is running.",
        "Discharge flow is below the illustrative threshold.",
        "Sump level is elevated.",
        "The combination suggests insufficient discharge."
    ]

elif not pump_on and level >= 75:

    diagnosis = "Pump stopped with high sump level"
    severity = "WARNING"
    fault_code = "FLT-004"

    recommendation = (
        "Check pump availability, electrical supply "
        "and operating command."
    )

    observations = [
        "Pump is stopped.",
        "Sump level is elevated.",
        "Accumulation may continue without pumping."
    ]

elif st.session_state.scenario == "Abnormal inflow":

    diagnosis = "Possible abnormal inflow"
    severity = "WARNING"
    fault_code = "FLT-005"

    recommendation = (
        "Review sump level trends and investigate "
        "upstream drainage sources."
    )

    observations = [
        "Sump level is elevated.",
        "Pump is running and discharge flow is present.",
        "Excessive inflow is a possible explanation.",
        "A level trend is required to confirm this hypothesis."
    ]

else:

    observations = [
        "Sump level is within the illustrative operating range.",
        "Discharge flow and pump status appear consistent.",
        "No abnormal condition detected by the current rules."
    ]


# ============================================================
# 8. HEADER
# ============================================================

header_left, header_right = st.columns([3, 1])

with header_left:

    st.markdown("# DrainZ 2.0")

    st.markdown(
        '<div class="muted">'
        'INTELLIGENT INDUSTRIAL DRAINAGE & PUMP MONITORING SYSTEM'
        '</div>',
        unsafe_allow_html=True
    )

with header_right:

    st.markdown(
        '<div style="text-align:right;padding-top:12px;">'
        '<span class="status-normal">● SIMULATION MODE</span><br>'
        f'<span class="muted">{datetime.now().strftime("%d %b %Y · %H:%M:%S")}</span>'
        '</div>',
        unsafe_allow_html=True
    )

st.divider()


# ============================================================
# 9. HYDRAULIC PROCESS DIAGRAM
# ============================================================

def process_diagram(level_value, flow_value, current_value, pump_status):

    fig = go.Figure()

    pump_color = "#43bd86" if pump_status else "#8796a3"

    liquid_top = 1.1 + 5.45 * level_value / 100

    # Inlet pipe
    fig.add_shape(
        type="line",
        x0=0.5, y0=5.0,
        x1=3.2, y1=5.0,
        line=dict(color="#4c9fbd", width=11)
    )

    # Sump
    fig.add_shape(
        type="rect",
        x0=3.2, y0=1.0,
        x1=6.0, y1=6.7,
        line=dict(color="#b5c5cf", width=3),
        fillcolor="#172735"
    )

    # Liquid
    fig.add_shape(
        type="rect",
        x0=3.28, y0=1.08,
        x1=5.92, y1=liquid_top,
        line=dict(width=0),
        fillcolor="rgba(35,145,190,0.65)"
    )

    # Liquid level
    fig.add_shape(
        type="line",
        x0=3.3, y0=liquid_top,
        x1=5.9, y1=liquid_top,
        line=dict(color="#56c6e5", width=2, dash="dash")
    )

    # Suction pipe
    fig.add_shape(
        type="line",
        x0=6.0, y0=2.0,
        x1=7.2, y1=2.0,
        line=dict(color="#4c9fbd", width=10)
    )

    # Pump
    fig.add_shape(
        type="circle",
        x0=7.0, y0=1.25,
        x1=8.5, y1=2.75,
        line=dict(color=pump_color, width=3),
        fillcolor="#203a42"
    )

    # Pump center
    fig.add_shape(
        type="circle",
        x0=7.48, y0=1.73,
        x1=8.02, y1=2.27,
        line=dict(color="#dce9ef", width=2),
        fillcolor="#527080"
    )

    # Discharge pipe
    fig.add_shape(
        type="line",
        x0=8.5, y0=2.0,
        x1=12.2, y1=2.0,
        line=dict(color="#4c9fbd", width=10)
    )

    # Flow transmitter
    fig.add_shape(
        type="circle",
        x0=9.7, y0=1.55,
        x1=10.6, y1=2.45,
        line=dict(color="#f0c36b", width=2),
        fillcolor="#172735"
    )

    # Level transmitter
    fig.add_shape(
        type="circle",
        x0=4.0, y0=7.05,
        x1=4.75, y1=7.8,
        line=dict(color="#e7bd69", width=2),
        fillcolor="#172735"
    )

    annotations = [
        dict(x=1.7, y=5.45, text="INLET",
             showarrow=False,
             font=dict(color="#b9c9d3", size=12)),

        dict(x=4.6, y=6.95, text="COLLECTION SUMP · TK-101",
             showarrow=False,
             font=dict(color="#e7edf1", size=12)),

        dict(x=4.37, y=7.42, text="LT",
             showarrow=False,
             font=dict(color="#f0c36b", size=13)),

        dict(x=4.6, y=liquid_top - 0.3,
             text=f"{level_value:.1f}%",
             showarrow=False,
             font=dict(color="white", size=17)),

        dict(x=7.75, y=3.0, text="P-101",
             showarrow=False,
             font=dict(color="#e7edf1", size=12)),

        dict(x=7.75, y=2.0, text="P",
             showarrow=False,
             font=dict(color="white", size=22)),

        dict(x=7.75, y=0.85,
             text="RUNNING" if pump_status else "STOPPED",
             showarrow=False,
             font=dict(color=pump_color, size=12)),

        dict(x=10.15, y=2.95, text="FT-101",
             showarrow=False,
             font=dict(color="#e7edf1", size=12)),

        dict(x=10.15, y=2.0, text="FT",
             showarrow=False,
             font=dict(color="#f0c36b", size=12)),

        dict(x=11.4, y=2.5, text="DISCHARGE",
             showarrow=False,
             font=dict(color="#b9c9d3", size=12)),

        dict(x=6.4, y=1.45, text="SUCTION",
             showarrow=False,
             font=dict(color="#8fa5b5", size=10))
    ]

    fig.update_layout(
        annotations=annotations,
        height=440,
        margin=dict(l=10, r=10, t=20, b=15),
        xaxis=dict(visible=False, range=[0, 12.7]),
        yaxis=dict(visible=False, range=[0.4, 8.2]),
        plot_bgcolor="#14212d",
        paper_bgcolor="#14212d",
        showlegend=False,
        dragmode=False
    )

    return fig


# ============================================================
# 10. PAGE: PROCESS OVERVIEW
# ============================================================

if page == "Process Overview":

    st.markdown(
        '<div class="section-label">01 / PROCESS MEASUREMENTS</div>',
        unsafe_allow_html=True
    )

    m1, m2, m3, m4 = st.columns(4)

    m1.metric("SUMP LEVEL", f"{level:.1f} %", "LT-101")
    m2.metric("DISCHARGE FLOW", f"{flow:.1f} m³/h", "FT-101")
    m3.metric("MOTOR CURRENT", f"{current:.2f} A", "AIT-101")
    m4.metric(
        "PUMP STATUS",
        "RUNNING" if pump_on else "STOPPED",
        "P-101"
    )

    st.markdown(
        '<div class="section-label">02 / HYDRAULIC PROCESS OVERVIEW</div>',
        unsafe_allow_html=True
    )

    st.markdown('<div class="panel">', unsafe_allow_html=True)

    st.plotly_chart(
        process_diagram(level, flow, current, pump_on),
        use_container_width=True,
        config={"displayModeBar": False}
    )

    st.markdown(
        '<div class="muted">'
        'PROCESS: INLET → COLLECTION SUMP → TRANSFER PUMP → DISCHARGE'
        '</div>',
        unsafe_allow_html=True
    )

    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown(
        '<div class="section-label">03 / SYSTEM DIAGNOSTICS</div>',
        unsafe_allow_html=True
    )

    left, right = st.columns([2, 1])

    with left:

        if severity == "NORMAL":
            st.success("NORMAL OPERATION | " + diagnosis)

        elif severity == "WARNING":
            st.warning("WARNING | " + diagnosis)

        else:
            st.error("CRITICAL ALARM | " + diagnosis)

        st.markdown("**Recommended inspection:**")
        st.write(recommendation)

    with right:

        st.markdown('<div class="panel">', unsafe_allow_html=True)

        st.markdown("**EQUIPMENT STATUS**")

        st.markdown(
            f'<span class="status-normal">● LT-101</span> '
            'Level measurement<br>'
            '<span class="status-normal">● FT-101</span> '
            'Flow measurement<br>'
            '<span class="status-normal">● AIT-101</span> '
            'Current measurement<br>'
            f'<span style="color:{ "#43bd86" if pump_on else "#8796a3"}">'
            '● P-101</span> Transfer pump',
            unsafe_allow_html=True
        )

        st.markdown('</div>', unsafe_allow_html=True)


# ============================================================
# 11. PAGE: INSTRUMENTATION
# ============================================================

elif page == "Instrumentation":

    st.markdown("## Instrumentation")
    st.caption("FIELD MEASUREMENTS AND EQUIPMENT STATUS")

    instruments = pd.DataFrame([
        ["LT-101", "Level transmitter", f"{level:.1f} %", "Collection sump"],
        ["FT-101", "Flow transmitter", f"{flow:.1f} m³/h", "Discharge line"],
        ["AIT-101", "Motor current", f"{current:.2f} A", "Pump motor"],
        ["P-101", "Transfer pump",
         "RUNNING" if pump_on else "STOPPED", "Pump station"]
    ], columns=["TAG", "DESCRIPTION", "VALUE", "LOCATION"])

    st.dataframe(
        instruments,
        use_container_width=True,
        hide_index=True
    )

    st.markdown("### Measurement details")

    c1, c2 = st.columns(2)

    with c1:
        st.metric("LT-101 · Sump level", f"{level:.1f}%")
        st.metric("FT-101 · Discharge flow", f"{flow:.1f} m³/h")

    with c2:
        st.metric("AIT-101 · Motor current", f"{current:.2f} A")
        st.metric(
            "P-101 · Pump status",
            "RUNNING" if pump_on else "STOPPED"
        )

    st.info(
        "Measurements are simulated. Sensor ranges, installation "
        "locations and industrial tag conventions must be confirmed "
        "during detailed engineering."
    )


# ============================================================
# 12. PAGE: FAULT DIAGNOSIS
# ============================================================

elif page == "Fault Diagnosis":

    st.markdown("## Fault Diagnosis")

    st.caption(
        "ENGINEERING RULES · OPERATING CONDITION ANALYSIS"
    )

    st.markdown("### Current diagnostic result")

    if severity == "NORMAL":
        st.success("NORMAL OPERATION | " + diagnosis)

    elif severity == "WARNING":
        st.warning("WARNING | " + diagnosis)

    else:
        st.error("CRITICAL ALARM | " + diagnosis)

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Sump level", f"{level:.1f}%")
    c2.metric("Discharge flow", f"{flow:.1f} m³/h")
    c3.metric("Motor current", f"{current:.2f} A")
    c4.metric("Pump status", "RUNNING" if pump_on else "STOPPED")

    st.divider()

    left, right = st.columns([3, 2])

    with left:

        st.markdown("### Diagnostic observations")

        for observation in observations:
            st.markdown("- " + observation)

        st.markdown("### Recommended inspection")
        st.info(recommendation)

    with right:

        st.markdown("### Diagnostic summary")

        st.markdown(f"**Fault code:** `{fault_code}`")
        st.markdown(f"**Scenario:** {st.session_state.scenario}")
        st.markdown(f"**Severity:** {severity}")
        st.markdown(f"**Suspected condition:** {diagnosis}")

        st.caption(
            "This is a preliminary rule-based diagnosis, "
            "not a confirmed fault."
        )

    st.divider()

    st.markdown("### Diagnostic logic")

    rules = pd.DataFrame([
        [
            "Critical level",
            "Level ≥ 90%",
            "Critical level alarm"
        ],
        [
            "Possible blockage",
            "Pump ON + low flow + elevated level",
            "Inspect discharge line"
        ],
        [
            "Possible pump malfunction",
            "Pump ON + very low flow + low current",
            "Inspect pump and motor"
        ],
        [
            "Pump stopped",
            "Pump OFF + level ≥ 75%",
            "Check pump availability"
        ],
        [
            "Possible abnormal inflow",
            "Elevated/rising level despite pumping",
            "Investigate upstream flow"
        ]
    ], columns=[
        "CONDITION",
        "OBSERVED BEHAVIOUR",
        "SUGGESTED ACTION"
    ])

    st.dataframe(
        rules,
        use_container_width=True,
        hide_index=True
    )

    st.warning(
        "Diagnostic thresholds are illustrative and must be "
        "validated experimentally. A single measurement snapshot "
        "cannot always distinguish between different faults."
    )


# ============================================================
# 13. PAGE: HISTORICAL TRENDS
# ============================================================

elif page == "Historical Trends":

    st.markdown("## Historical Trends")

    st.caption(
        "ILLUSTRATIVE SIMULATED MEASUREMENT HISTORY"
    )

    rng = np.random.default_rng(12)

    times = [
        datetime.now() - timedelta(minutes=29-i)
        for i in range(30)
    ]

    level_data = np.clip(
        level + np.cumsum(rng.normal(0, 0.8, 30)),
        0, 100
    )

    flow_data = np.clip(
        flow + rng.normal(0, 1.2, 30),
        0, 35
    )

    current_data = np.clip(
        current + rng.normal(0, 0.12, 30),
        0, 10
    )

    def trend_chart(times, values, title, color, unit):

        fig = go.Figure()

        fig.add_trace(
            go.Scatter(
                x=times,
                y=values,
                mode="lines",
                name=title,
                line=dict(color=color, width=3),
                fill="tozeroy",
                fillcolor="rgba(66,183,213,0.07)"
            )
        )

        fig.update_layout(
            template="plotly_dark",
            height=320,
            paper_bgcolor="#14212d",
            plot_bgcolor="#14212d",
            title=title,
            yaxis_title=unit,
            margin=dict(l=10, r=10, t=45, b=10),
            showlegend=False
        )

        return fig

    st.plotly_chart(
        trend_chart(
            times, level_data,
            "Sump Level Trend",
            "#42b7d5", "Level (%)"
        ),
        use_container_width=True
    )

    st.plotly_chart(
        trend_chart(
            times, flow_data,
            "Discharge Flow Trend",
            "#5acb95", "Flow (m³/h)"
        ),
        use_container_width=True
    )

    st.plotly_chart(
        trend_chart(
            times, current_data,
            "Motor Current Trend",
            "#e9b65d", "Current (A)"
        ),
        use_container_width=True
    )

    st.info(
        "These trends are generated for demonstration and are "
        "not actual sensor history."
    )


# ============================================================
# 14. PAGE: SYSTEM INFORMATION
# ============================================================

elif page == "System Information":

    st.markdown("## System Information")

    st.caption(
        "PROJECT DESCRIPTION AND TECHNICAL ARCHITECTURE"
    )

    st.markdown("### Project purpose")

    st.write(
        "DrainZ 2.0 is a proposed intelligent multi-sensor "
        "monitoring and fault diagnosis system for industrial "
        "drainage networks and wastewater pumping stations "
        "in Oil & Gas facilities."
    )

    st.markdown("### Main objectives")

    st.markdown("""
    - Monitor the level of collected industrial wastewater.
    - Monitor pump discharge flow and operating conditions.
    - Detect abnormal hydraulic and pumping behaviour.
    - Provide early warnings and diagnostic recommendations.
    - Visualize operating measurements and historical trends.
    """)

    st.markdown("### Proposed architecture")

    architecture = pd.DataFrame([
        ["Field layer", "Level, flow and motor-current measurements"],
        ["Acquisition", "Arduino or ESP32 prototype controller"],
        ["Communication", "LoRa, Wi-Fi or wired connection"],
        ["Supervision", "Python-based monitoring dashboard"],
        ["Diagnosis", "Engineering rules and trend analysis"],
        ["Industrial deployment", "PLC / SCADA integration concept"]
    ], columns=["LAYER", "FUNCTION"])

    st.dataframe(
        architecture,
        use_container_width=True,
        hide_index=True
    )

    st.markdown("### Proposed technologies")

    technologies = pd.DataFrame([
        ["Controller", "Arduino / ESP32"],
        ["Level measurement", "Ultrasonic sensor for prototype"],
        ["Flow measurement", "Suitable water flow sensor"],
        ["Current measurement", "Low-voltage current sensor"],
        ["Programming", "Python"],
        ["Dashboard", "Streamlit"],
        ["Visualization", "Plotly"],
        ["Industrial concept", "PLC / SCADA"]
    ], columns=["COMPONENT", "TECHNOLOGY"])

    st.dataframe(
        technologies,
        use_container_width=True,
        hide_index=True
    )

    st.markdown("### Project limitations")

    st.write(
        "This application currently operates using simulated data. "
        "It is not connected to real industrial instruments and "
        "does not replace certified protection systems, pump "
        "interlocks or industrial safety systems."
    )


# ============================================================
# 15. FOOTER
# ============================================================

st.divider()

st.markdown(
    '<div style="text-align:center;color:#708595;font-size:11px;">'
    'DRAINZ 2.0 · MASTER PFE PROTOTYPE · SIMULATED DATA · '
    'NOT FOR INDUSTRIAL CONTROL'
    '</div>',
    unsafe_allow_html=True
)
