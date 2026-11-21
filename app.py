
from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st


# ==============================================================
# 1. CONFIGURATION
# ==============================================================

st.set_page_config(
    page_title="DrainZ 2.0 | Industrial Monitoring",
    page_icon="💧",
    layout="wide",
    initial_sidebar_state="expanded"
)

FEATURES = ["fill_rate", "empty_rate", "run_time", "flow", "current"]

FEATURE_LABELS = {
    "fill_rate": "Filling rate",
    "empty_rate": "Emptying rate",
    "run_time": "Pump runtime",
    "flow": "Mean outlet flow",
    "current": "Mean motor current"
}

NONE = "No fault"
R_MILD = "Mild discharge restriction"
R_SEV = "Severe discharge restriction"
P2 = "Degraded pump"
P1 = "Pump not running"
INFLOW = "Abnormal inflow"
FROZEN = "Frozen level sensor"
DISC = "Disconnected level sensor"

FAULTS = [NONE, R_MILD, R_SEV, P2, P1, INFLOW, FROZEN, DISC]

C_RESTRICTION = "Discharge restriction"
C_P2 = "Pump degradation"
C_P1 = "Pump not running"
C_INFLOW = "Abnormal inflow"
C_OVERFLOW = "Imminent overflow"
C_SENSOR = "Level sensor fault"
C_UNKNOWN = "Unclassified deviation"

EXPECTED_CAUSE = {
    R_MILD: C_RESTRICTION,
    R_SEV: C_RESTRICTION,
    P2: C_P2,
    P1: C_P1,
    INFLOW: C_INFLOW,
    FROZEN: C_SENSOR,
    DISC: C_SENSOR
}


@dataclass
class Config:
    dt: float = 2.0
    tank_height: float = 60.0
    fs1: float = 40.0
    fs2: float = 10.0
    fs3: float = 50.0
    n_persist: int = 3
    baseline_cycles: int = 30
    k_sigma: float = 3.0
    run_current_threshold: float = 0.3
    startup_delay: float = 6.0


# ==============================================================
# 2. MODERN INTERFACE
# ==============================================================

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
}

.stApp {
    background: #101820;
    color: #e8eef2;
}

[data-testid="stSidebar"] {
    background: #151f29;
    border-right: 1px solid #293744;
}

.block-container {
    max-width: 1650px;
    padding-top: 1.6rem;
    padding-bottom: 3rem;
}

h1, h2, h3 {
    color: #edf3f7;
    letter-spacing: -0.5px;
}

p, li {
    color: #c1cbd3;
}

[data-testid="stMetric"] {
    background: #192631;
    border: 1px solid #2a3a47;
    border-radius: 12px;
    padding: 17px 18px;
}

[data-testid="stMetricLabel"] {
    color: #92a4b1;
    font-size: 12px;
}

[data-testid="stMetricValue"] {
    color: #f0f5f8;
    font-size: 27px;
    font-weight: 700;
}

[data-testid="stMetricDelta"] {
    font-size: 11px;
}

.panel {
    background: #192631;
    border: 1px solid #2b3c49;
    border-radius: 13px;
    padding: 20px;
}

.panel-title {
    font-size: 13px;
    font-weight: 700;
    color: #dce6ec;
    letter-spacing: 0.7px;
    margin-bottom: 15px;
}

.eyebrow {
    color: #83a0b1;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1.8px;
}

.muted {
    color: #8da0ad;
    font-size: 12px;
}

.big-number {
    color: #f2f6f8;
    font-size: 27px;
    font-weight: 700;
}

.cyan {
    color: #64c8d8;
}

.green {
    color: #65c99b;
}

.amber {
    color: #e7b765;
}

.red {
    color: #ed7777;
}

.tag {
    display: inline-block;
    padding: 5px 10px;
    border-radius: 6px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.8px;
    background: #243541;
    color: #9eb4c1;
}

.status-dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    margin-right: 7px;
}

div[data-testid="stTabs"] button {
    color: #9fb0bc;
}

div[data-testid="stTabs"] button[aria-selected="true"] {
    color: #70cbd9;
    border-bottom-color: #70cbd9;
}

.stButton button {
    border-radius: 8px;
    font-weight: 600;
    min-height: 38px;
}

div[data-testid="stDataFrame"] {
    border: 1px solid #2b3c49;
    border-radius: 9px;
    overflow: hidden;
}

hr {
    border-color: #293a47;
}

footer {
    visibility: hidden;
}
</style>
""", unsafe_allow_html=True)


# ==============================================================
# 3. SIMULATOR
# ==============================================================

class SumpSimulator:

    AREA_CM2 = 250.0
    INFLOW_CM_S = 0.15
    PUMP_LPM = 7.5
    PUMP_AMPS = 2.2

    EFFECTS = {
        R_MILD: (0.65, 1.05, 1.0),
        R_SEV: (0.45, 1.10, 1.0),
        P2: (0.60, 0.70, 1.0),
        INFLOW: (1.0, 1.0, 1.6)
    }

    def __init__(self, cfg, seed=7):
        self.cfg = cfg
        self.rng = np.random.default_rng(seed)
        self.t = 0.0
        self.level = cfg.fs2 + 2
        self.cmd_on = False
        self.cycle_factor = 1.0
        self.fault = NONE
        self.frozen_value = None

    def inject(self, fault):
        self.fault = fault
        if fault == FROZEN:
            self.frozen_value = self.level

    def step(self):

        c = self.cfg
        n = self.rng.normal

        if not self.cmd_on and self.level >= c.fs1:
            self.cmd_on = True

        elif self.cmd_on and self.level <= c.fs2:
            self.cmd_on = False
            self.cycle_factor = 1 + n(0, 0.04)

        flow_factor, current_factor, inflow_factor = (
            self.EFFECTS.get(self.fault, (1.0, 1.0, 1.0))
        )

        running = self.cmd_on and self.fault != P1

        true_flow = self.PUMP_LPM * flow_factor if running else 0.0

        out_rate = true_flow * 1000 / 60 / self.AREA_CM2
        in_rate = self.INFLOW_CM_S * inflow_factor * self.cycle_factor

        self.level = float(np.clip(
            self.level + (in_rate - out_rate) * c.dt,
            0,
            c.tank_height
        ))

        self.t += c.dt

        if self.fault == DISC:
            measured_level = float("nan")
        elif self.fault == FROZEN:
            measured_level = self.frozen_value
        else:
            measured_level = self.level + n(0, 0.15)

        measured_flow = (
            true_flow * (1 + n(0, 0.02))
            if running else abs(n(0, 0.02))
        )

        measured_current = (
            self.PUMP_AMPS * current_factor * (1 + n(0, 0.02))
            if running else abs(n(0, 0.01))
        )

        return {
            "t": self.t,
            "level": measured_level,
            "flow": measured_flow,
            "current": measured_current,
            "run": int(self.cmd_on),
            "fs3": int(self.level >= c.fs3)
        }


# ==============================================================
# 4. ARDUINO SERIAL INPUT
# ==============================================================

class SerialSource:

    def __init__(self, port, baud=115200):
        import serial
        self.ser = serial.Serial(port, baud, timeout=0.2)
        self.t0 = time.time()

    def read_samples(self):

        samples = []

        while self.ser.in_waiting:

            line = self.ser.readline().decode(
                errors="ignore"
            ).strip()

            try:
                lvl, flow, cur, run, fs3 = line.split(",")

                samples.append({
                    "t": time.time() - self.t0,
                    "level": float(lvl),
                    "flow": float(flow),
                    "current": float(cur),
                    "run": int(float(run)),
                    "fs3": int(float(fs3))
                })

            except (ValueError, TypeError):
                continue

        return samples


# ==============================================================
# 5. DIAGNOSTIC ENGINE
# ==============================================================

@dataclass
class Alarm:
    t: float
    severity: str
    cause: str
    message: str
    level: float = float("nan")


def classify(flags):

    fill = flags["fill_rate"]
    empty = flags["empty_rate"]
    runtime = flags["run_time"]
    flow = flags["flow"]
    current = flags["current"]

    if flow < 0 and current < 0 and runtime > 0:
        return C_P2

    if flow < 0 and empty < 0 and current >= 0:
        return C_RESTRICTION

    if fill > 0 and empty == 0 and flow == 0 and current == 0:
        return C_INFLOW

    if any(flags.values()):
        return C_UNKNOWN

    return None


class Monitor:

    PRIMARY = {
        C_RESTRICTION: "flow",
        C_P2: "flow",
        C_INFLOW: "fill_rate"
    }

    def __init__(self, cfg):

        self.cfg = cfg

        self.cycles = []
        self.baseline_rows = []
        self.bands = None
        self.learning = True

        self.alarms = []

        self.prev_run = 0
        self.fill_start = None
        self.run_start = None
        self.fill_rate = None

        self.flows = []
        self.currents = []

        self.streak = 0
        self.streak_cause = None
        self.warn_z = 0
        self.escalated = False

        self.active_fs3 = False
        self.active_p1 = False
        self.cmd_since = None

        self.sensor_fault = False
        self.sensor_kind = None
        self.level_buffer = deque(maxlen=15)
        self.bad_samples = 0

        self.truth_active = False
        self.expected = None
        self.inject_t = None
        self.inject_cycles = 0

        self.first_detect_t = None
        self.first_detect_cycles = None
        self.fs3_t = None

        self.false_alarms = 0
        self.wrong_cause = 0
        self.normal_cycles = 0

    def status_info(self):

        if self.active_fs3:
            return "CRITICAL", C_OVERFLOW

        if self.active_p1:
            return "CRITICAL", C_P1

        if self.escalated and self.streak_cause:
            return "CRITICAL", self.streak_cause

        if self.sensor_fault:
            return "WARNING", C_SENSOR

        if self.learning:
            return "LEARNING", None

        if self.streak >= self.cfg.n_persist:
            return "WARNING", self.streak_cause

        return "NORMAL", None

    def mark_injection(self, t, expected):

        self.truth_active = True
        self.expected = expected
        self.inject_t = t
        self.inject_cycles = len(self.cycles)

        self.first_detect_t = None
        self.first_detect_cycles = None
        self.fs3_t = None
        self.wrong_cause = 0

    def mark_cleared(self):
        self.truth_active = False

    def evaluation(self):

        delay = (
            self.first_detect_t - self.inject_t
            if self.first_detect_t is not None else None
        )

        lead = (
            self.fs3_t - self.first_detect_t
            if self.fs3_t is not None
            and self.first_detect_t is not None else None
        )

        return {
            "expected": self.expected,
            "delay_s": delay,
            "delay_cycles": self.first_detect_cycles,
            "fs3_reached": self.fs3_t is not None,
            "lead_s": lead,
            "false_alarms": self.false_alarms,
            "normal_cycles": self.normal_cycles,
            "wrong_cause": self.wrong_cause
        }

    def raise_alarm(self, t, severity, cause, message, level=float("nan")):

        self.alarms.append(
            Alarm(t, severity, cause, message, level)
        )

        if not self.truth_active:
            self.false_alarms += 1
            return

        if cause == C_OVERFLOW and self.fs3_t is None:
            self.fs3_t = t

        if cause == self.expected and self.first_detect_t is None:

            self.first_detect_t = t
            self.first_detect_cycles = (
                len(self.cycles) - self.inject_cycles
            )

        elif cause not in (self.expected, C_OVERFLOW):
            self.wrong_cause += 1

    def update(self, sample):

        t = sample["t"]
        lvl = sample["level"]
        flow = sample["flow"]
        cur = sample["current"]

        run = int(sample["run"])
        fs3 = bool(sample["fs3"])

        self.check_sensor(t, lvl)
        self.check_pump_start(t, run, cur, lvl)
        self.check_fs3(t, fs3, lvl)

        if self.sensor_fault:
            self.fill_start = None
            self.run_start = None
            self.fill_rate = None
            self.prev_run = run
            return

        self.detect_cycle(t, lvl, flow, cur, run)
        self.prev_run = run

    def check_sensor(self, t, lvl):

        self.level_buffer.append(lvl)

        bad = (
            lvl is None
            or not np.isfinite(lvl)
            or lvl < 0
            or lvl > self.cfg.tank_height + 5
        )

        self.bad_samples = self.bad_samples + 1 if bad else 0

        arr = np.asarray(self.level_buffer, dtype=float)

        frozen = (
            len(arr) == self.level_buffer.maxlen
            and np.isfinite(arr).all()
            and np.ptp(arr) == 0
        )

        detected = self.bad_samples >= 3 or frozen

        if detected and not self.sensor_fault:

            self.sensor_kind = (
                "disconnected" if self.bad_samples >= 3 else "frozen"
            )

            self.raise_alarm(
                t,
                "Warning",
                C_SENSOR,
                f"Level sensor appears {self.sensor_kind}. "
                "Cycle analysis suspended.",
                lvl
            )

        self.sensor_fault = detected

        if not detected:
            self.sensor_kind = None

    def check_pump_start(self, t, run, cur, lvl):

        if run and cur < self.cfg.run_current_threshold:

            self.cmd_since = (
                t if self.cmd_since is None else self.cmd_since
            )

            if (
                t - self.cmd_since >= self.cfg.startup_delay
                and not self.active_p1
            ):

                self.active_p1 = True

                self.raise_alarm(
                    t,
                    "Critical",
                    C_P1,
                    "Pump command is ON but motor current "
                    "remains below the running threshold.",
                    lvl
                )

        else:
            self.cmd_since = None
            self.active_p1 = False

    def check_fs3(self, t, fs3, lvl):

        if fs3 and not self.active_fs3:

            self.raise_alarm(
                t,
                "Critical",
                C_OVERFLOW,
                "High-high level switch FS3 activated. "
                "Immediate inspection required.",
                lvl
            )

        self.active_fs3 = fs3

    def detect_cycle(self, t, lvl, flow, cur, run):

        if run and not self.prev_run:

            self.fill_rate = None

            if self.fill_start is not None:

                start_t, start_level = self.fill_start

                if t > start_t:
                    self.fill_rate = (
                        lvl - start_level
                    ) / (t - start_t)

            self.run_start = (t, lvl)
            self.flows = []
            self.currents = []

        if run:
            self.flows.append(flow)
            self.currents.append(cur)

        if not run and self.prev_run:

            if (
                self.run_start
                and self.fill_rate is not None
                and self.flows
            ):

                run_time = t - self.run_start[0]

                net_empty = (
                    self.run_start[1] - lvl
                ) / run_time

                features = {
                    "fill_rate": self.fill_rate,
                    "empty_rate": net_empty + self.fill_rate,
                    "run_time": run_time,
                    "flow": float(np.mean(self.flows)),
                    "current": float(np.mean(self.currents))
                }

                self.on_cycle(t, features)

            self.fill_start = (t, lvl)
            self.run_start = None
            self.fill_rate = None

    def compute_bands(self):

        df = pd.DataFrame(self.baseline_rows)
        self.bands = {}

        for f in FEATURES:

            mean = float(df[f].mean())

            sd = max(
                float(df[f].std(ddof=1)),
                0.01 * abs(mean),
                0.001
            )

            self.bands[f] = (
                mean,
                sd,
                mean - self.cfg.k_sigma * sd,
                mean + self.cfg.k_sigma * sd
            )

    def on_cycle(self, t, features):

        row = {
            "cycle": len(self.cycles) + 1,
            "time_min": t / 60,
            **features,
            "phase": "baseline" if self.learning else "monitoring",
            "fault_injected": self.truth_active,
            "deviation": "",
            "cause": ""
        }

        if self.learning:

            self.baseline_rows.append(features)

            if len(self.baseline_rows) >= self.cfg.baseline_cycles:
                self.compute_bands()
                self.learning = False

            self.cycles.append(row)
            return

        flags = {}
        zs = {}

        for f in FEATURES:

            mean, sd, low, high = self.bands[f]

            flags[f] = (
                -1 if features[f] < low
                else 1 if features[f] > high
                else 0
            )

            zs[f] = (features[f] - mean) / sd

        cause = classify(flags)

        row["deviation"] = ", ".join(
            f"{f}{'-' if v < 0 else '+'}"
            for f, v in flags.items() if v
        )

        row["cause"] = cause or ""
        row["flags"] = flags

        if not self.truth_active:
            self.normal_cycles += 1

        self.cycles.append(row)

        self.persistence(t, cause, flags, zs)

    def persistence(self, t, cause, flags, zs):

        n = self.cfg.n_persist

        if cause is None:

            self.streak = 0
            self.streak_cause = None
            self.escalated = False
            return

        if cause == self.streak_cause:
            self.streak += 1

        else:
            self.streak = 1
            self.streak_cause = cause
            self.escalated = False

        primary = self.PRIMARY.get(cause)

        if primary is None:
            primary = max(zs, key=lambda k: abs(zs[k]))

        z_value = abs(zs[primary])

        if self.streak == n:

            self.warn_z = z_value

            self.raise_alarm(
                t,
                "Warning",
                cause,
                f"Deviation persisted for {n} consecutive cycles. "
                "Inspect the equipment."
            )

        elif (
            self.streak >= 2 * n
            and not self.escalated
            and z_value >= self.warn_z
        ):

            self.escalated = True

            self.raise_alarm(
                t,
                "Critical",
                cause,
                f"Deviation persisted for {self.streak} cycles "
                "and continues to worsen."
            )

    def cycles_df(self):

        if not self.cycles:
            return pd.DataFrame()

        return pd.DataFrame(self.cycles).drop(
            columns=["flags"], errors="ignore"
        )

    def alarms_df(self):

        return pd.DataFrame([
            {
                "time_min": round(a.t / 60, 2),
                "severity": a.severity,
                "cause": a.cause,
                "message": a.message
            }
            for a in self.alarms
        ])


# ==============================================================
# 6. SESSION STATE AND SYSTEM CONTROL
# ==============================================================

def new_system(source="Simulator", port="", baud=115200):

    ss = st.session_state
    cfg = Config()

    ss.cfg = cfg
    ss.mon = Monitor(cfg)
    ss.hist = deque(maxlen=3000)
    ss.source = source
    ss.serial_error = None

    if source == "Simulator":

        ss.sim = SumpSimulator(cfg)

        # Generate a healthy baseline automatically.
        for _ in range(200000):

            if not ss.mon.learning:
                break

            sample = ss.sim.step()
            ss.mon.update(sample)
            ss.hist.append(sample)

        ss.link = None

    else:

        ss.sim = None

        try:
            ss.link = SerialSource(port, baud)

        except Exception as exc:
            ss.link = None
            ss.serial_error = str(exc)


def advance_system(steps):

    ss = st.session_state

    if ss.source == "Simulator":

        for _ in range(steps):

            sample = ss.sim.step()
            ss.mon.update(sample)
            ss.hist.append(sample)

    elif ss.link is not None:

        for sample in ss.link.read_samples():

            ss.mon.update(sample)
            ss.hist.append(sample)


if "mon" not in st.session_state:
    new_system("Simulator")
    st.session_state.running = True


# ==============================================================
# 7. CHART HELPERS
# ==============================================================

CHART_LAYOUT = dict(
    paper_bgcolor="#192631",
    plot_bgcolor="#192631",
    font=dict(color="#b9c7d0", family="DM Sans"),
    margin=dict(l=15, r=15, t=45, b=15),
    hovermode="x unified"
)


def render_chart(fig, key):

    fig.update_layout(**CHART_LAYOUT)

    try:
        st.plotly_chart(
            fig,
            width="stretch",
            key=key,
            config={"displayModeBar": False}
        )
    except TypeError:
        st.plotly_chart(
            fig,
            use_container_width=True,
            key=key,
            config={"displayModeBar": False}
        )


def process_diagram(level, pump_on, flow):

    fig = go.Figure()

    liquid_y = 1 + 4.7 * np.clip(
        level / 60, 0, 1
    )

    pump_color = "#64c99a" if pump_on else "#788b99"

    # Inlet
    fig.add_shape(
        type="line",
        x0=0.5, y0=4.7,
        x1=3.0, y1=4.7,
        line=dict(color="#65bfd0", width=9)
    )

    # Tank body
    fig.add_shape(
        type="rect",
        x0=3, y0=0.8,
        x1=5.8, y1=6.5,
        line=dict(color="#9aabb6", width=2),
        fillcolor="#17232d"
    )

    # Liquid
    fig.add_shape(
        type="rect",
        x0=3.08, y0=0.88,
        x1=5.72, y1=liquid_y,
        line=dict(width=0),
        fillcolor="rgba(62,164,190,0.55)"
    )

    # Level line
    fig.add_shape(
        type="line",
        x0=3.1, y0=liquid_y,
        x1=5.7, y1=liquid_y,
        line=dict(color="#70d1df", width=2, dash="dash")
    )

    # Suction pipe
    fig.add_shape(
        type="line",
        x0=5.8, y0=1.8,
        x1=7.2, y1=1.8,
        line=dict(color="#65bfd0", width=9)
    )

    # Pump body
    fig.add_shape(
        type="circle",
        x0=7.1, y0=1.0,
        x1=8.8, y1=2.7,
        line=dict(color=pump_color, width=3),
        fillcolor="#243844"
    )

    fig.add_shape(
        type="circle",
        x0=7.65, y0=1.55,
        x1=8.25, y1=2.15,
        line=dict(color="#d4e1e7", width=2),
        fillcolor="#476475"
    )

    # Discharge
    fig.add_shape(
        type="line",
        x0=8.8, y0=1.85,
        x1=12.0, y1=1.85,
        line=dict(color="#65bfd0", width=9)
    )

    # Flow instrument
    fig.add_shape(
        type="circle",
        x0=9.8, y0=1.4,
        x1=10.7, y1=2.3,
        line=dict(color="#e5b66c", width=2),
        fillcolor="#192631"
    )

    annotations = [
        (1.7, 5.2, "INLET"),
        (4.4, 6.9, "COLLECTION SUMP"),
        (4.4, 7.45, "LT-101"),
        (4.4, liquid_y - 0.25, f"{level:.1f} cm"),
        (7.95, 3.15, "P-101"),
        (7.95, 1.85, "P"),
        (7.95, 0.65, "RUNNING" if pump_on else "STOPPED"),
        (10.25, 2.8, "FT-101"),
        (10.25, 1.85, "FT"),
        (11.3, 2.4, "DISCHARGE")
    ]

    for x, y, text in annotations:

        color = "#68cbd9" if text == "FT" else "#d9e3e9"

        if text in ("LT-101", "FT-101"):
            color = "#e5b66c"

        if text in ("RUNNING", "STOPPED"):
            color = pump_color

        fig.add_annotation(
            x=x, y=y, text=text,
            showarrow=False,
            font=dict(size=11, color=color)
        )

    fig.update_layout(
        height=400,
        xaxis=dict(visible=False, range=[0, 12.5]),
        yaxis=dict(visible=False, range=[0, 8]),
        showlegend=False,
        dragmode=False
    )

    return fig


def live_figure(df, cfg, mon):

    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=(
            "Sump level (cm)",
            "Outlet flow (L/min)",
            "Motor current (A)"
        )
    )

    x = df["t"] / 60

    fig.add_trace(
        go.Scatter(
            x=x,
            y=df["level"],
            line=dict(color="#65c6d6", width=2),
            name="Level"
        ),
        row=1, col=1
    )

    for value, label, color in [
        (cfg.fs1, "Pump start", "#66b78e"),
        (cfg.fs2, "Pump stop", "#d3a65f"),
        (cfg.fs3, "High-high", "#e27474")
    ]:

        fig.add_hline(
            y=value,
            line_dash="dash",
            line_color=color,
            annotation_text=label,
            row=1, col=1
        )

    fig.add_trace(
        go.Scatter(
            x=x, y=df["flow"],
            line=dict(color="#78b5d5", width=2),
            name="Flow"
        ),
        row=2, col=1
    )

    fig.add_trace(
        go.Scatter(
            x=x, y=df["current"],
            line=dict(color="#e6b66d", width=2),
            name="Current"
        ),
        row=3, col=1
    )

    fig.update_yaxes(range=[0, cfg.tank_height], row=1, col=1)
    fig.update_xaxes(title_text="Time (min)", row=3, col=1)
    fig.update_layout(height=610, showlegend=False)

    return fig


# ==============================================================
# 8. SIDEBAR
# ==============================================================

ss = st.session_state

with st.sidebar:

    st.markdown("## 💧 DrainZ 2.0")
    st.markdown(
        '<span class="eyebrow">INDUSTRIAL MONITORING</span>',
        unsafe_allow_html=True
    )

    st.divider()

    page = st.radio(
        "WORKSPACE",
        [
            "Overview",
            "Process Monitoring",
            "Fault Diagnosis",
            "Cycle Analysis",
            "Alarm History",
            "Validation",
            "System Configuration"
        ],
        label_visibility="collapsed"
    )

    st.divider()

    st.markdown("**DATA SOURCE**")

    source = st.radio(
        "Source",
        ["Simulator", "Arduino (serial)"],
        index=0 if ss.source == "Simulator" else 1
    )

    port = "COM3"
    baud = 115200

    if source == "Arduino (serial)":

        port = st.text_input(
            "Serial port",
            value="COM3"
        )

        baud = st.selectbox(
            "Baud rate",
            [9600, 57600, 115200],
            index=2
        )

        if st.button("Connect to Arduino", use_container_width=True):

            new_system("Arduino (serial)", port, baud)
            st.rerun()

        if ss.serial_error:
            st.error(ss.serial_error)

    elif ss.source != "Simulator":
        new_system("Simulator")

    st.divider()

    ss.running = st.toggle(
        "Live updates",
        value=ss.get("running", True)
    )

    speed = st.slider(
        "Simulation speed",
        5, 60, 20,
        disabled=ss.source != "Simulator"
    )

    window = st.select_slider(
        "Trend window",
        options=[5, 10, 15, 30, 60],
        value=15
    )

    ss.cfg.n_persist = st.slider(
        "Persistence threshold (cycles)",
        1, 6, ss.cfg.n_persist
    )

    st.divider()

    if ss.source == "Simulator":

        st.markdown("**FAULT INJECTION**")

        if ss.mon.learning:
            st.info("Complete baseline learning before injecting a fault.")

        fault = st.selectbox(
            "Select fault scenario",
            FAULTS,
            disabled=ss.mon.learning
        )

        col_a, col_b = st.columns(2)

        if col_a.button(
            "Inject",
            type="primary",
            disabled=ss.mon.learning,
            use_container_width=True
        ):

            ss.sim.inject(fault)

            if fault == NONE:
                ss.mon.mark_cleared()
            else:
                ss.mon.mark_injection(
                    ss.sim.t,
                    EXPECTED_CAUSE[fault]
                )

        if col_b.button(
            "Clear",
            disabled=ss.mon.learning,
            use_container_width=True
        ):

            ss.sim.inject(NONE)
            ss.mon.mark_cleared()

        st.caption(
            f"Active scenario: {ss.sim.fault}"
        )

    st.divider()

    if st.button("Reset system", use_container_width=True):

        new_system(ss.source, port, baud)
        st.rerun()

    st.markdown(
        '<div class="muted" style="padding-top:15px;">'
        'MASTER PFE PROTOTYPE<br>'
        'Monitoring · Diagnosis · Early Warning'
        '</div>',
        unsafe_allow_html=True
    )


# ==============================================================
# 9. SHARED DATA AND HEADER
# ==============================================================

if ss.running:
    advance_system(speed)

status, cause = ss.mon.status_info()

st.markdown(
    '<div class="eyebrow">OIL & GAS · PROCESS MONITORING PLATFORM</div>',
    unsafe_allow_html=True
)

head1, head2 = st.columns([3, 1])

with head1:
    st.title("DrainZ 2.0")
    st.caption(
        "Oily-water sump monitoring and pumping station fault diagnosis"
    )

with head2:

    if ss.source == "Simulator":
        st.markdown(
            '<div style="text-align:right;padding-top:20px;">'
            '<span class="tag">SIMULATION MODE</span>'
            '</div>',
            unsafe_allow_html=True
        )
    elif ss.link is not None:
        st.markdown(
            '<div style="text-align:right;padding-top:20px;">'
            '<span class="tag">ARDUINO CONNECTED</span>'
            '</div>',
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            '<div style="text-align:right;padding-top:20px;">'
            '<span class="tag">WAITING FOR CONNECTION</span>'
            '</div>',
            unsafe_allow_html=True
        )

st.divider()

if ss.hist:
    last = ss.hist[-1]
else:
    last = {
        "level": float("nan"),
        "flow": 0,
        "current": 0,
        "run": 0,
        "fs3": 0,
        "t": 0
    }

level = last["level"]
flow = last["flow"]
current = last["current"]
pump_command = bool(last["run"])

# Actual pump operation is inferred from command and motor current.
pump_running = (
    pump_command
    and current >= ss.cfg.run_current_threshold
)

# ==============================================================
# 10. GLOBAL ALARM BANNER
# ==============================================================

if status == "LEARNING":

    st.info(
        f"BASELINE LEARNING · "
        f"{len(ss.mon.baseline_rows)}/{ss.cfg.baseline_cycles} "
        "healthy cycles recorded."
    )

elif status == "NORMAL":

    st.success(
        "SYSTEM NORMAL · Measurements are within the learned baseline."
    )

elif status == "WARNING":

    st.warning(
        f"WARNING · {cause} · Inspection recommended."
    )

else:

    st.error(
        f"CRITICAL ALARM · {cause} · Immediate investigation required."
    )


# ==============================================================
# 11. OVERVIEW PAGE
# ==============================================================

if page == "Overview":

    st.markdown(
        '<div class="eyebrow">01 / SYSTEM OVERVIEW</div>',
        unsafe_allow_html=True
    )

    st.markdown("### Current operating conditions")

    k1, k2, k3, k4, k5 = st.columns(5)

    k1.metric(
        "SUMP LEVEL",
        "N/A" if not np.isfinite(level) else f"{level:.1f} cm"
    )

    k2.metric(
        "OUTLET FLOW",
        f"{flow:.2f} L/min"
    )

    k3.metric(
        "MOTOR CURRENT",
        f"{current:.2f} A"
    )

    k4.metric(
        "PUMP CONDITION",
        "RUNNING" if pump_running else (
            "START COMMAND" if pump_command else "STOPPED"
        )
    )

    k5.metric(
        "COMPLETED CYCLES",
        len(ss.mon.cycles)
    )

    st.markdown(
        '<div class="eyebrow" style="margin-top:30px;">'
        '02 / PROCESS FLOW'
        '</div>',
        unsafe_allow_html=True
    )

    left, right = st.columns([2.3, 1])

    with left:

        st.markdown('<div class="panel">', unsafe_allow_html=True)

        st.markdown(
            '<div class="panel-title">HYDRAULIC PROCESS SCHEMATIC</div>',
            unsafe_allow_html=True
        )

        if np.isfinite(level):
            display_level = level
        else:
            display_level = 0

        fig = process_diagram(
            display_level,
            pump_running,
            flow
        )

        render_chart(fig, "process_overview")

        st.markdown(
            '<div class="muted">'
            'INLET → COLLECTION SUMP → TRANSFER PUMP → DISCHARGE'
            '</div>',
            unsafe_allow_html=True
        )

        st.markdown('</div>', unsafe_allow_html=True)

    with right:

        st.markdown('<div class="panel">', unsafe_allow_html=True)

        st.markdown(
            '<div class="panel-title">EQUIPMENT STATUS</div>',
            unsafe_allow_html=True
        )

        equipment = [
            ("LT-101", "Level transmitter"),
            ("FT-101", "Flow transmitter"),
            ("AIT-101", "Motor current"),
            ("P-101", "Transfer pump"),
            ("FS3", "High-high switch")
        ]

        for tag, description in equipment:

            if tag == "FS3":
                good = not bool(last["fs3"])
            elif tag == "P-101":
                good = pump_running
            else:
                good = True

            color = "#65c99b" if good else "#e7b765"

            st.markdown(
                f'<div style="padding:11px 0;border-bottom:1px solid #2b3c49;">'
                f'<span style="color:{color};">●</span> '
                f'<b>{tag}</b><br>'
                f'<span class="muted">{description}</span>'
                f'</div>',
                unsafe_allow_html=True
            )

        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown(
        '<div class="eyebrow" style="margin-top:30px;">'
        '03 / DIAGNOSTIC SUMMARY'
        '</div>',
        unsafe_allow_html=True
    )

    if cause:
        st.markdown(f"**Probable cause:** {cause}")
    else:
        st.markdown("**Probable cause:** No abnormal condition detected.")

    st.caption(
        "The diagnostic engine provides probable causes based on "
        "measurements and operating patterns, not confirmed physical faults."
    )

    if ss.mon.alarms:

        latest_alarm = ss.mon.alarms[-1]

        st.markdown(
            f"**Latest event:** {latest_alarm.cause} — "
            f"{latest_alarm.message}"
        )

    else:
        st.markdown("No alarms have been recorded.")


# ==============================================================
# 12. PROCESS MONITORING
# ==============================================================

elif page == "Process Monitoring":

    st.markdown("## Process Monitoring")

    st.caption(
        "LIVE MEASUREMENTS · LEVEL · FLOW · MOTOR CURRENT"
    )

    if not ss.hist:

        st.info("Waiting for measurement data.")

    else:

        df = pd.DataFrame(ss.hist)

        end_time = df["t"].iloc[-1]

        df = df[
            df["t"] >= end_time - window * 60
        ]

        fig = live_figure(df, ss.cfg, ss.mon)

        render_chart(fig, "process_live")

        st.markdown("### Latest measurements")

        st.dataframe(
            pd.DataFrame([{
                "Level (cm)": level,
                "Flow (L/min)": flow,
                "Current (A)": current,
                "Pump command": "ON" if pump_command else "OFF",
                "Pump inferred state": "RUNNING" if pump_running else "NOT RUNNING",
                "FS3": "ACTIVE" if last["fs3"] else "NORMAL"
            }]),
            use_container_width=True,
            hide_index=True
        )

        st.info(
            "FS1: pump start level · FS2: pump stop level · "
            "FS3: independent high-high level alarm."
        )


# ==============================================================
# 13. FAULT DIAGNOSIS
# ==============================================================

elif page == "Fault Diagnosis":

    st.markdown("## Fault Diagnosis")

    st.caption(
        "ENGINEERING RULES · BASELINE DEVIATION · PERSISTENCE FILTER"
    )

    if status == "NORMAL":
        st.success("No abnormal operating condition detected.")
    elif status == "WARNING":
        st.warning(f"Probable cause: {cause}")
    elif status == "CRITICAL":
        st.error(f"Critical condition: {cause}")
    else:
        st.info("Learning the healthy operating baseline.")

    st.markdown("### Diagnostic measurements")

    a, b, c, d = st.columns(4)

    a.metric("Level", "N/A" if not np.isfinite(level) else f"{level:.1f} cm")
    b.metric("Flow", f"{flow:.2f} L/min")
    c.metric("Current", f"{current:.2f} A")
    d.metric("Pump", "RUNNING" if pump_running else "NOT RUNNING")

    st.divider()

    if cause == C_RESTRICTION:

        st.markdown("### Possible discharge restriction")

        st.write(
            "A reduction in outlet flow together with abnormal "
            "emptying behaviour may indicate a restriction in the "
            "discharge line."
        )

        st.info(
            "Suggested inspection: discharge pipe, valves, "
            "strainers and possible hydraulic obstruction."
        )

    elif cause == C_P2:

        st.markdown("### Possible pump degradation")

        st.write(
            "Reduced flow and motor current, combined with an "
            "abnormal pumping cycle, may indicate degraded pump performance."
        )

        st.info(
            "Suggested inspection: pump condition, impeller, "
            "motor loading and suction conditions."
        )

    elif cause == C_P1:

        st.markdown("### Pump not running")

        st.write(
            "The pump command is active but measured motor current "
            "remains below the running threshold."
        )

        st.info(
            "Suggested inspection: electrical supply, motor circuit, "
            "starter and pump availability."
        )

    elif cause == C_INFLOW:

        st.markdown("### Possible abnormal inflow")

        st.write(
            "An abnormal filling rate may indicate an increase "
            "in incoming wastewater."
        )

        st.info(
            "Suggested inspection: upstream drainage sources "
            "and inlet conditions."
        )

    elif cause == C_SENSOR:

        st.markdown("### Level measurement fault")

        st.write(
            f"The level measurement appears {ss.mon.sensor_kind or 'abnormal'}."
        )

        st.info(
            "Suggested inspection: sensor wiring, power supply, "
            "mounting and measurement signal."
        )

    elif cause == C_OVERFLOW:

        st.markdown("### Imminent overflow")

        st.write(
            "The independent high-high switch FS3 has activated."
        )

        st.error(
            "This condition requires immediate investigation. "
            "The dashboard is advisory and is not a substitute "
            "for a certified high-high protection system."
        )

    else:

        st.markdown("### No confirmed diagnostic result")

        st.write(
            "The current measurements do not establish a specific "
            "fault category. Additional measurements and trend "
            "analysis may be required."
        )

    st.divider()

    st.markdown("### Diagnostic rule table")

    rules = pd.DataFrame([
        ["Low flow + low current + longer runtime",
         "Pump degradation", "Warning"],
        ["Low flow + abnormal emptying + normal/high current",
         "Discharge restriction", "Warning"],
        ["Pump command ON + current below threshold",
         "Pump not running", "Critical"],
        ["Abnormal filling rate",
         "Abnormal inflow", "Warning"],
        ["FS3 activated",
         "Imminent overflow", "Critical"],
        ["Frozen or disconnected level signal",
         "Sensor fault", "Warning"]
    ], columns=[
        "Observed behaviour",
        "Probable cause",
        "Alarm"
    ])

    st.dataframe(
        rules,
        hide_index=True,
        use_container_width=True
    )

    st.caption(
        "The rules are preliminary engineering hypotheses. "
        "They require validation on the physical prototype."
    )


# ==============================================================
# 14. CYCLE ANALYSIS
# ==============================================================

elif page == "Cycle Analysis":

    st.markdown("## Cycle Analysis")

    st.caption(
        "FILLING PHASE · PUMPING PHASE · FEATURE EXTRACTION"
    )

    cdf = ss.mon.cycles_df()

    if cdf.empty:

        st.info(
            "No completed cycles available yet. "
            "Wait for the first fill-pump-empty cycle."
        )

    else:

        st.metric(
            "Recorded cycles",
            len(cdf)
        )

        if ss.mon.bands is None:

            st.info(
                "Baseline learning is in progress."
            )

        else:

            st.markdown("### Extracted features")

            for i in range(0, len(FEATURES), 2):

                cols = st.columns(2)

                for j, f in enumerate(FEATURES[i:i+2]):

                    with cols[j]:

                        mean, sd, low, high = ss.mon.bands[f]

                        fig = go.Figure()

                        fig.add_hrect(
                            y0=low,
                            y1=high,
                            fillcolor="#65c99b",
                            opacity=0.12,
                            line_width=0
                        )

                        fig.add_hline(
                            y=mean,
                            line_dash="dash",
                            line_color="#65c99b"
                        )

                        fig.add_trace(
                            go.Scatter(
                                x=cdf["cycle"],
                                y=cdf[f],
                                mode="lines+markers",
                                line=dict(color="#67c6d5", width=2),
                                marker=dict(size=7)
                            )
                        )

                        fig.update_layout(
                            title=FEATURE_LABELS[f],
                            height=280,
                            showlegend=False
                        )

                        render_chart(fig, f"cycle_{f}")

                        st.caption(
                            f"Baseline mean: {mean:.3f} | "
                            f"Lower: {low:.3f} | "
                            f"Upper: {high:.3f}"
                        )

        st.markdown("### Cycle records")

        st.dataframe(
            cdf.round(3).iloc[::-1],
            use_container_width=True,
            hide_index=True
        )

        st.download_button(
            "Download cycle records",
            cdf.to_csv(index=False),
            file_name="drainz_cycle_records.csv",
            mime="text/csv"
        )


# ==============================================================
# 15. ALARM HISTORY
# ==============================================================

elif page == "Alarm History":

    st.markdown("## Alarm History")

    st.caption(
        "EVENT LOG · WARNING · CRITICAL"
    )

    adf = ss.mon.alarms_df()

    if adf.empty:

        st.success("No alarms recorded.")

    else:

        total = len(adf)

        warnings = len(
            adf[adf["severity"] == "Warning"]
        )

        critical = len(
            adf[adf["severity"] == "Critical"]
        )

        a, b, c = st.columns(3)

        a.metric("TOTAL EVENTS", total)
        b.metric("WARNINGS", warnings)
        c.metric("CRITICAL ALARMS", critical)

        st.markdown("### Event log")

        st.dataframe(
            adf.iloc[::-1],
            use_container_width=True,
            hide_index=True
        )

        st.download_button(
            "Export alarm history",
            adf.to_csv(index=False),
            file_name="drainz_alarm_history.csv",
            mime="text/csv"
        )


# ==============================================================
# 16. VALIDATION
# ==============================================================

elif page == "Validation":

    st.markdown("## System Validation")

    st.caption(
        "FAULT INJECTION · DETECTION PERFORMANCE · FALSE ALARMS"
    )

    ev = ss.mon.evaluation()

    st.markdown("### Current validation run")

    a, b, c, d = st.columns(4)

    a.metric(
        "False alarms",
        ev["false_alarms"]
    )

    false_rate = (
        100 * ev["false_alarms"] / ev["normal_cycles"]
        if ev["normal_cycles"] else 0
    )

    b.metric(
        "Normal cycles",
        ev["normal_cycles"]
    )

    c.metric(
        "Wrong-cause alarms",
        ev["wrong_cause"]
    )

    d.metric(
        "Active scenario",
        ss.sim.fault if ss.sim else "Arduino"
    )

    st.divider()

    st.markdown("### Fault detection performance")

    if ev["delay_s"] is None:

        st.info(
            "Inject a fault in simulation mode to measure "
            "detection delay."
        )

    else:

        x, y, z = st.columns(3)

        x.metric(
            "Detection delay",
            f"{ev['delay_s']:.1f} s",
            f"{ev['delay_cycles']} cycles"
        )

        y.metric(
            "FS3 activated",
            "YES" if ev["fs3_reached"] else "NO"
        )

        z.metric(
            "Warning lead time",
            "N/A" if ev["lead_s"] is None
            else f"{ev['lead_s']:.1f} s"
        )

    st.markdown("### Evaluation definitions")

    metrics = pd.DataFrame([
        ["False alarm count",
         "Alarms raised during periods without injected faults."],
        ["Wrong-cause count",
         "Alarms that do not match the expected injected fault."],
        ["Detection delay",
         "Time between fault injection and first matching alarm."],
        ["Warning lead time",
         "Time between first matching warning and FS3 activation."],
        ["Normal cycles",
         "Completed cycles outside the injected-fault period."]
    ], columns=["Metric", "Definition"])

    st.dataframe(
        metrics,
        use_container_width=True,
        hide_index=True
    )

    st.warning(
        "These metrics are preliminary prototype results. "
        "They should be evaluated over repeated tests and reported "
        "with the number of trials, not treated as proof of "
        "industrial performance."
    )


# ==============================================================
# 17. SYSTEM CONFIGURATION
# ==============================================================

elif page == "System Configuration":

    st.markdown("## System Configuration")

    st.caption(
        "PROJECT ARCHITECTURE · INSTRUMENTATION · BASELINE SETTINGS"
    )

    st.markdown("### Proposed process instruments")

    instruments = pd.DataFrame([
        ["LT-101", "Level transmitter", "Sump", "cm"],
        ["FT-101", "Flow transmitter", "Discharge pipe", "L/min"],
        ["AIT-101", "Motor current measurement", "Pump motor", "A"],
        ["FS1", "Pump start level switch", "Sump", "cm"],
        ["FS2", "Pump stop level switch", "Sump", "cm"],
        ["FS3", "Independent high-high switch", "Sump", "cm"],
        ["P-101", "Transfer pump", "Pump station", "Status"]
    ], columns=[
        "TAG", "DESCRIPTION", "LOCATION", "UNIT"
    ])

    st.dataframe(
        instruments,
        use_container_width=True,
        hide_index=True
    )

    st.markdown("### Current simulation parameters")

    config = pd.DataFrame([
        ["Tank height", ss.cfg.tank_height, "cm"],
        ["Pump start level FS1", ss.cfg.fs1, "cm"],
        ["Pump stop level FS2", ss.cfg.fs2, "cm"],
        ["High-high level FS3", ss.cfg.fs3, "cm"],
        ["Sampling period", ss.cfg.dt, "s"],
        ["Baseline cycles", ss.cfg.baseline_cycles, "cycles"],
        ["Persistence threshold", ss.cfg.n_persist, "cycles"],
        ["Baseline band", ss.cfg.k_sigma, "sigma"]
    ], columns=["PARAMETER", "VALUE", "UNIT"])

    st.dataframe(
        config,
        use_container_width=True,
        hide_index=True
    )

    st.markdown("### Proposed system architecture")

    architecture = [
        ("FIELD LAYER", "Level, flow, current and pump status"),
        ("ACQUISITION", "Arduino Mega / ESP32 prototype"),
        ("COMMUNICATION", "LoRa / serial / wired interface"),
        ("MONITORING", "Python-based dashboard"),
        ("DIAGNOSIS", "Baseline analysis + engineering rules"),
        ("INDUSTRIAL DEPLOYMENT", "PLC / RTU + SCADA")
    ]

    for name, description in architecture:

        st.markdown(
            f'<div class="panel" style="margin-bottom:9px;">'
            f'<span class="cyan"><b>{name}</b></span><br>'
            f'<span class="muted">{description}</span>'
            f'</div>',
            unsafe_allow_html=True
        )

    st.markdown("### Important limitations")

    st.write("""
    - The simulator is a simplified representation of a sump and pump.
    - The baseline is learned from simulated healthy cycles or actual
      healthy prototype measurements.
    - The 3-sigma statistical band is a preliminary anomaly-detection
      method, not a universal industrial threshold.
    - Fault diagnosis indicates probable causes, not guaranteed faults.
    - The application is monitoring and advisory software only.
    - It does not replace PLC interlocks, pump protections or certified
      industrial safety systems.
    - Clean water should be used for laboratory prototype testing.
    """)


# ==============================================================
# 18. FOOTER
# ==============================================================

st.divider()

st.markdown(
    """
    <div style="text-align:center;padding:12px;color:#8194a1;">
        <b>DRAINZ 2.0</b> &nbsp; · &nbsp;
        INDUSTRIAL DRAINAGE MONITORING & FAULT DIAGNOSIS
        <br><br>
        <span style="font-size:11px;">
        MASTER PFE PROTOTYPE · SIMULATED / EXPERIMENTAL DATA
        · ADVISORY SYSTEM ONLY
        </span>
    </div>
    """,
    unsafe_allow_html=True
)


# ==============================================================
# 19. LIVE REFRESH
# ==============================================================

if ss.running:
    time.sleep(0.05)
    st.rerun()
