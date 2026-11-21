"""
DrainZ 2.0 - Oily-Water Sump Monitoring and Fault Diagnosis
============================================================
Streamlit dashboard for the PFE proposal "Monitoring and Fault Diagnosis of an
Oily-Water Sump and Its Pumping Station" (extension of the DrainZ prototype).

What it does
------------
1. Reads three measurements (level, outlet flow, pump current) + pump run signal
   + high-high float switch FS3, either from a built-in simulator or from the
   Arduino Mega over USB serial.
2. Detects each fill -> pump -> empty cycle and extracts 5 features.
3. Learns a baseline from 30 healthy cycles (band = mean +/- 3 standard deviations).
4. Applies the engineering rule table with a persistence filter (N cycles) and
   raises Warning / Critical alarms with a probable cause.
5. Computes the validation metrics of the proposal: false alarms, wrong cause,
   detection delay and warning lead time versus the FS3 level switch.

Run:  streamlit run app.py
Serial line format expected from the Arduino (one line per sample, ~every 2 s):
      level_cm,flow_lpm,current_a,run,fs3        e.g.  27.4,7.52,2.21,1,0
"""
from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

# =============================================================================
# 1. CONFIGURATION AND VOCABULARY
# =============================================================================


@dataclass
class Config:
    dt: float = 2.0                  # sample period [s]
    tank_height: float = 60.0        # [cm]
    fs1: float = 40.0                # start level  (pump ON)  [cm]
    fs2: float = 10.0                # stop level   (pump OFF) [cm]
    fs3: float = 50.0                # high-high switch        [cm]
    n_persist: int = 3               # N consecutive cycles before a warning
    baseline_cycles: int = 30        # healthy cycles used for the baseline
    k_sigma: float = 3.0             # band half-width in standard deviations
    run_current_threshold: float = 0.3   # [A] below = pump not running
    startup_delay: float = 6.0       # [s] allowed between command and current


FEATURES = ["fill_rate", "empty_rate", "run_time", "flow", "current"]
FEATURE_LABELS = {
    "fill_rate": "Fill rate (cm/s)",
    "empty_rate": "Emptying rate, gross (cm/s)",
    "run_time": "Pump run time (s)",
    "flow": "Mean outlet flow (L/min)",
    "current": "Mean pump current (A)",
}

# Injectable faults (simulator)
NONE = "No fault"
R_MILD = "Discharge restriction (mild)"
R_SEV = "Discharge restriction (severe)"
P2 = "Pump degraded (weak pump)"
P1 = "Pump not running (power cut)"
INFLOW = "Abnormal inflow"
FROZEN = "Level sensor frozen"
DISC = "Level sensor disconnected"
FAULTS = [NONE, R_MILD, R_SEV, P2, P1, INFLOW, FROZEN, DISC]

# Diagnosis vocabulary (rule table of the proposal, Section 6)
C_RESTRICTION = "Discharge restriction"
C_P2 = "Pump malfunction P2 (degraded)"
C_P1 = "Pump malfunction P1 (not running)"
C_INFLOW = "Abnormal inflow"
C_OVERFLOW = "Imminent overflow (FS3)"
C_SENSOR = "Sensor fault"
C_UNKNOWN = "Unclassified deviation"

EXPECTED_CAUSE = {R_MILD: C_RESTRICTION, R_SEV: C_RESTRICTION, P2: C_P2,
                  P1: C_P1, INFLOW: C_INFLOW, FROZEN: C_SENSOR, DISC: C_SENSOR}

# =============================================================================
# 2. DATA SOURCES
# =============================================================================


class SumpSimulator:
    """Simple physical model of the bench rig (tank + pump + rig controller)."""

    AREA_CM2 = 250.0       # tank cross-section
    INFLOW_CM_S = 0.15     # normal inflow expressed as level rise
    PUMP_LPM = 7.5         # nominal pump flow
    PUMP_AMPS = 2.2        # nominal pump current
    # fault -> (flow factor, current factor, inflow factor)
    EFFECTS = {R_MILD: (0.65, 1.05, 1.0), R_SEV: (0.45, 1.10, 1.0),
               P2: (0.60, 0.70, 1.0), INFLOW: (1.0, 1.0, 1.6)}

    def __init__(self, cfg: Config, seed: Optional[int] = None):
        self.cfg = cfg
        self.rng = np.random.default_rng(seed)
        self.t = 0.0
        self.level = cfg.fs2 + 2.0
        self.cmd_on = False
        self.cycle_factor = 1.0
        self.fault = NONE
        self.frozen_value = None

    def inject(self, fault: str) -> None:
        self.fault = fault
        if fault == FROZEN:
            self.frozen_value = self.level

    def step(self) -> dict:
        c, n = self.cfg, self.rng.normal
        # Rig controller: simple hysteresis on FS1 / FS2 (acts on the true level)
        if not self.cmd_on and self.level >= c.fs1:
            self.cmd_on = True
        elif self.cmd_on and self.level <= c.fs2:
            self.cmd_on = False
            self.cycle_factor = 1.0 + n(0, 0.04)   # normal inflow variation

        flow_f, cur_f, in_f = self.EFFECTS.get(self.fault, (1.0, 1.0, 1.0))
        running = self.cmd_on and self.fault != P1
        true_flow = self.PUMP_LPM * flow_f if running else 0.0
        out_rate = true_flow * 1000.0 / 60.0 / self.AREA_CM2
        in_rate = self.INFLOW_CM_S * in_f * self.cycle_factor
        self.level = float(np.clip(self.level + (in_rate - out_rate) * c.dt, 0, c.tank_height))
        self.t += c.dt

        # Measured values (what the Arduino would see)
        if self.fault == DISC:
            lvl = float("nan")
        elif self.fault == FROZEN:
            lvl = self.frozen_value
        else:
            lvl = self.level + n(0, 0.15)
        flow = true_flow * (1 + n(0, 0.02)) if running else abs(n(0, 0.02))
        cur = self.PUMP_AMPS * cur_f * (1 + n(0, 0.02)) if running else abs(n(0, 0.01))
        return {"t": self.t, "level": lvl, "flow": flow, "current": cur,
                "run": int(self.cmd_on), "fs3": int(self.level >= c.fs3)}


class SerialSource:
    """Reads 'level,flow,current,run,fs3' lines from the Arduino Mega."""

    def __init__(self, port: str, baud: int = 115200):
        import serial  # imported lazily so the simulator works without pyserial
        self.ser = serial.Serial(port, baud, timeout=0.2)
        self.t0 = time.time()

    def read_samples(self) -> list[dict]:
        out = []
        while self.ser.in_waiting:
            line = self.ser.readline().decode(errors="ignore").strip()
            try:
                lvl, flow, cur, run, fs3 = line.split(",")
                out.append({"t": time.time() - self.t0, "level": float(lvl), "flow": float(flow),
                            "current": float(cur), "run": int(float(run)), "fs3": int(float(fs3))})
            except ValueError:
                continue  # ignore incomplete / corrupted lines
        return out

# =============================================================================
# 3. MONITORING ENGINE (cycle detection + baseline + rules + alarms)
# =============================================================================


@dataclass
class Alarm:
    t: float
    severity: str
    cause: str
    message: str
    level: float = float("nan")


def classify(flags: dict) -> Optional[str]:
    """Rule table (Section 6). flags: -1 below band, 0 inside, +1 above."""
    fill, empty, rt, flow, cur = (flags[f] for f in FEATURES)
    if flow < 0 and cur < 0 and rt > 0:
        return C_P2
    if flow < 0 and empty < 0 and cur >= 0:
        return C_RESTRICTION
    if fill > 0 and empty == 0 and flow == 0 and cur == 0:
        return C_INFLOW
    if any(flags.values()):
        return C_UNKNOWN
    return None


class Monitor:
    PRIMARY = {C_RESTRICTION: "flow", C_P2: "flow", C_INFLOW: "fill_rate"}

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.cycles: list[dict] = []
        self.baseline_rows: list[dict] = []
        self.bands: Optional[dict] = None
        self.learning = True
        self.alarms: list[Alarm] = []
        # cycle detector
        self.prev_run = 0
        self.fill_start = None
        self.run_start = None
        self.fill_rate = None
        self.flows: list[float] = []
        self.currents: list[float] = []
        # persistence
        self.streak = 0
        self.streak_cause: Optional[str] = None
        self.warn_z = 0.0
        self.escalated = False
        # safety conditions
        self.active_fs3 = False
        self.active_p1 = False
        self.cmd_since: Optional[float] = None
        # sensor checks
        self.sensor_fault = False
        self._lvl_buf: deque = deque(maxlen=15)
        self._bad = 0
        # validation metrics
        self.truth_active = False
        self.expected: Optional[str] = None
        self.inject_t = None
        self.inject_cycles = 0
        self.first_detect_t = None
        self.first_detect_cycles = None
        self.fs3_t = None
        self.false_alarms = 0
        self.wrong_cause = 0
        self.normal_cycles = 0

    # ---------------------------------------------------------------- status
    def status_info(self) -> tuple[str, Optional[str]]:
        if self.active_fs3:
            return "CRITICAL", C_OVERFLOW
        if self.active_p1:
            return "CRITICAL", C_P1
        if self.escalated and self.streak_cause:
            return "CRITICAL", self.streak_cause
        if self.learning:
            return "LEARNING", None
        if self.sensor_fault:
            return "WARNING", C_SENSOR
        if self.streak >= self.cfg.n_persist and self.streak_cause:
            return "WARNING", self.streak_cause
        return "NORMAL", None

    # --------------------------------------------------- validation bookkeeping
    def mark_injection(self, t: float, expected: str) -> None:
        self.truth_active, self.expected, self.inject_t = True, expected, t
        self.inject_cycles = len(self.cycles)
        self.first_detect_t = self.first_detect_cycles = self.fs3_t = None
        self.wrong_cause = 0

    def mark_cleared(self) -> None:
        self.truth_active = False

    def evaluation(self) -> dict:
        delay_s = (self.first_detect_t - self.inject_t) if self.first_detect_t is not None else None
        lead = (self.fs3_t - self.first_detect_t) if (self.fs3_t and self.first_detect_t is not None) else None
        return {"expected": self.expected, "delay_s": delay_s, "delay_cycles": self.first_detect_cycles,
                "fs3_reached": self.fs3_t is not None, "lead_s": lead,
                "false_alarms": self.false_alarms, "normal_cycles": self.normal_cycles,
                "wrong_cause": self.wrong_cause}

    # ----------------------------------------------------------------- alarms
    def _raise(self, t: float, severity: str, cause: str, message: str, level: float = float("nan")) -> None:
        self.alarms.append(Alarm(t, severity, cause, message, level))
        if not self.truth_active:
            self.false_alarms += 1
            return
        if cause == C_OVERFLOW and self.fs3_t is None:
            self.fs3_t = t
        if cause == self.expected and self.first_detect_t is None:
            self.first_detect_t = t
            self.first_detect_cycles = len(self.cycles) - self.inject_cycles
        elif cause not in (self.expected, C_OVERFLOW):
            self.wrong_cause += 1

    # -------------------------------------------------------- per-sample logic
    def update(self, s: dict) -> None:
        t, lvl, flow, cur = s["t"], s["level"], s["flow"], s["current"]
        run, fs3 = int(s["run"]), bool(s["fs3"])
        self._check_sensor(t, lvl)
        self._check_pump_start(t, run, cur, lvl)
        self._check_fs3(t, fs3, lvl)
        if self.sensor_fault:           # do not analyse cycles with a bad level signal
            self.fill_start = self.run_start = self.fill_rate = None
            self.prev_run = run
            return
        self._detect_cycle(t, lvl, flow, cur, run)
        self.prev_run = run

    def _check_sensor(self, t, lvl) -> None:
        self._lvl_buf.append(lvl)
        bad = lvl is None or (isinstance(lvl, float) and math.isnan(lvl)) or lvl < 0
        self._bad = self._bad + 1 if bad else 0
        arr = np.array(self._lvl_buf, dtype=float)
        frozen = len(arr) == self._lvl_buf.maxlen and np.isfinite(arr).all() and np.ptp(arr) == 0
        now = self._bad >= 3 or frozen
        if now and not self.sensor_fault:
            kind = "disconnected" if self._bad >= 3 else "frozen"
            self._raise(t, "Warning", C_SENSOR, f"Level sensor looks {kind}; cycle analysis suspended.")
        self.sensor_fault = now

    def _check_pump_start(self, t, run, cur, lvl) -> None:
        if run and cur < self.cfg.run_current_threshold:
            self.cmd_since = t if self.cmd_since is None else self.cmd_since
            if t - self.cmd_since >= self.cfg.startup_delay and not self.active_p1:
                self.active_p1 = True
                self._raise(t, "Critical", C_P1,
                            "Pump commanded ON but current stays below the running threshold.", lvl)
        else:
            self.cmd_since, self.active_p1 = None, False

    def _check_fs3(self, t, fs3, lvl) -> None:
        if fs3 and not self.active_fs3:
            self._raise(t, "Critical", C_OVERFLOW, "High-high switch FS3 operated. Act now.", lvl)
        self.active_fs3 = fs3

    def _detect_cycle(self, t, lvl, flow, cur, run) -> None:
        if run and not self.prev_run:                       # pump starts: fill phase ends
            self.fill_rate = None
            if self.fill_start is not None and t > self.fill_start[0]:
                self.fill_rate = (lvl - self.fill_start[1]) / (t - self.fill_start[0])
            self.run_start, self.flows, self.currents = (t, lvl), [], []
        if run:
            self.flows.append(flow)
            self.currents.append(cur)
        if not run and self.prev_run:                       # pump stops: cycle complete
            if self.run_start and self.fill_rate is not None and self.flows:
                run_time = t - self.run_start[0]
                net = (self.run_start[1] - lvl) / run_time
                self._on_cycle(t, {"fill_rate": self.fill_rate,
                                   "empty_rate": net + self.fill_rate,   # gross emptying rate
                                   "run_time": run_time,
                                   "flow": float(np.mean(self.flows)),
                                   "current": float(np.mean(self.currents))})
            self.fill_start, self.run_start, self.fill_rate = (t, lvl), None, None

    # ------------------------------------------------------------ cycle logic
    def _compute_bands(self) -> None:
        df = pd.DataFrame(self.baseline_rows)
        self.bands = {}
        for f in FEATURES:
            mean = float(df[f].mean())
            sd = max(float(df[f].std(ddof=1)), 0.01 * abs(mean))   # floor against zero spread
            self.bands[f] = (mean, sd, mean - self.cfg.k_sigma * sd, mean + self.cfg.k_sigma * sd)

    def _on_cycle(self, t: float, feats: dict) -> None:
        row = {"cycle": len(self.cycles) + 1, "t_min": t / 60.0, **feats,
               "phase": "baseline" if self.learning else "monitoring",
               "fault_injected": self.truth_active, "deviation": "", "cause": ""}
        if self.learning:
            self.baseline_rows.append(feats)
            if len(self.baseline_rows) >= self.cfg.baseline_cycles:
                self._compute_bands()
                self.learning = False
            self.cycles.append(row)
            return

        flags, zs = {}, {}
        for f in FEATURES:
            mean, sd, lo, hi = self.bands[f]
            flags[f] = -1 if feats[f] < lo else (1 if feats[f] > hi else 0)
            zs[f] = (feats[f] - mean) / sd
        cause = classify(flags)
        row["deviation"] = ", ".join(f"{f}{'-' if v < 0 else '+'}" for f, v in flags.items() if v)
        row["cause"] = cause or ""
        row["flags"] = flags
        if not self.truth_active:
            self.normal_cycles += 1
        self.cycles.append(row)
        self._persistence(t, cause, flags, zs)

    def _persistence(self, t, cause, flags, zs) -> None:
        n = self.cfg.n_persist
        if cause is None:
            self.streak, self.streak_cause, self.escalated = 0, None, False
            return
        if cause == self.streak_cause:
            self.streak += 1
        else:
            self.streak, self.streak_cause, self.escalated = 1, cause, False
        pf = self.PRIMARY.get(cause) or max(zs, key=lambda k: abs(zs[k]))
        if self.streak == n:
            self.warn_z = abs(zs[pf])
            self._raise(t, "Warning", cause,
                        f"Deviation persists for {n} cycles ({', '.join(f for f, v in flags.items() if v)}). "
                        "Inspect at next opportunity.")
        elif self.streak >= 2 * n and not self.escalated and abs(zs[pf]) >= self.warn_z:
            self.escalated = True
            self._raise(t, "Critical", cause, f"Warning persists and keeps worsening ({self.streak} cycles). Act now.")

    # ------------------------------------------------------------- dataframes
    def cycles_df(self) -> pd.DataFrame:
        if not self.cycles:
            return pd.DataFrame()
        return pd.DataFrame(self.cycles).drop(columns=["flags"], errors="ignore")

    def alarms_df(self) -> pd.DataFrame:
        return pd.DataFrame([{"time_min": round(a.t / 60, 2), "severity": a.severity,
                              "cause": a.cause, "message": a.message} for a in self.alarms])

# =============================================================================
# 4. APPLICATION STATE
# =============================================================================


def new_system(source: str, port: str = "", baud: int = 115200, prelearn: bool = True) -> None:
    ss = st.session_state
    cfg = Config()
    ss.cfg, ss.mon, ss.hist, ss.source = cfg, Monitor(cfg), deque(maxlen=2000), source
    ss.serial_error = None
    if source == "Simulator":
        ss.sim = SumpSimulator(cfg, seed=7)
        ss.link = None
        if prelearn:
            for _ in range(200_000):
                if not ss.mon.learning:
                    break
                s = ss.sim.step()
                ss.mon.update(s)
                ss.hist.append(s)
    else:
        ss.sim = None
        try:
            ss.link = SerialSource(port, baud)
        except Exception as exc:  # noqa: BLE001
            ss.link, ss.serial_error = None, str(exc)


def advance(n_steps: int) -> None:
    ss = st.session_state
    if ss.source == "Simulator":
        for _ in range(n_steps):
            s = ss.sim.step()
            ss.mon.update(s)
            ss.hist.append(s)
    elif ss.link is not None:
        for s in ss.link.read_samples():
            ss.mon.update(s)
            ss.hist.append(s)

# =============================================================================
# 5. CHARTS
# =============================================================================


def show(fig: go.Figure, key: str) -> None:
    try:
        st.plotly_chart(fig, width="stretch", key=key)
    except TypeError:                                  # older Streamlit versions
        st.plotly_chart(fig, use_container_width=True, key=key)


def live_figure(df: pd.DataFrame, cfg: Config, mon: Monitor) -> go.Figure:
    x = df["t"] / 60.0
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.07,
                        row_heights=[0.5, 0.25, 0.25],
                        subplot_titles=("Sump level (cm)", "Outlet flow (L/min)", "Pump current (A)"))
    fig.add_trace(go.Scatter(x=x, y=df["level"], name="Level", line=dict(width=2, color="#1565c0")), 1, 1)
    for label, y, col in (("FS1 start", cfg.fs1, "#2e7d32"), ("FS2 stop", cfg.fs2, "#6d4c41"),
                          ("FS3 high-high", cfg.fs3, "#c62828")):
        fig.add_hline(y=y, line_dash="dash", line_color=col, annotation_text=label,
                      annotation_position="top left", row=1, col=1)
    fig.add_trace(go.Scatter(x=x, y=df["flow"], name="Flow", line=dict(color="#00838f")), 2, 1)
    fig.add_trace(go.Scatter(x=x, y=df["current"], name="Current", line=dict(color="#ef6c00")), 3, 1)
    t0 = df["t"].iloc[0]
    for a in mon.alarms:
        if a.t >= t0 and not math.isnan(a.level):
            fig.add_trace(go.Scatter(x=[a.t / 60], y=[a.level], mode="markers", name=a.cause, showlegend=False,
                                     marker=dict(size=11, symbol="x", color="#c62828")), 1, 1)
    if mon.inject_t is not None and mon.inject_t >= t0:
        fig.add_vline(x=mon.inject_t / 60, line_dash="dot", line_color="#6a1b9a", row="all", col=1)
    fig.update_xaxes(title_text="Time (min)", row=3, col=1)
    fig.update_yaxes(range=[0, cfg.tank_height], row=1, col=1)
    fig.update_layout(height=620, margin=dict(l=10, r=10, t=40, b=10), showlegend=False)
    return fig


def feature_figure(feature: str, cdf: pd.DataFrame, bands: dict) -> go.Figure:
    mean, sd, lo, hi = bands[feature]
    fig = go.Figure()
    fig.add_hrect(y0=lo, y1=hi, fillcolor="#2e7d32", opacity=0.12, line_width=0)
    fig.add_hline(y=mean, line_dash="dot", line_color="#2e7d32")
    colors = ["#9e9e9e" if p == "baseline" else ("#c62828" if (v < lo or v > hi) else "#1565c0")
              for p, v in zip(cdf["phase"], cdf[feature])]
    fig.add_trace(go.Scatter(x=cdf["cycle"], y=cdf[feature], mode="lines+markers",
                             line=dict(color="#90a4ae", width=1), marker=dict(color=colors, size=7)))
    fig.update_layout(title=FEATURE_LABELS[feature], height=260, margin=dict(l=10, r=10, t=40, b=10),
                      showlegend=False, xaxis_title="Cycle")
    return fig

# =============================================================================
# 6. PAGE
# =============================================================================

st.set_page_config(page_title="DrainZ 2.0 | Sump Monitor", page_icon="💧", layout="wide")
ss = st.session_state
if "mon" not in ss:
    new_system("Simulator")
    ss.running = True

st.title("💧 DrainZ 2.0: Oily-Water Sump Monitor")
st.caption("Early fault diagnosis of a sump and its pumping station using level, flow and pump current. "
           "Advisory function only: it never controls the pump.")

# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.header("Control panel")
    source = st.radio("Data source", ["Simulator", "Arduino (serial)"], index=0 if ss.source == "Simulator" else 1)
    port, baud = "", 115200
    if source == "Arduino (serial)":
        port = st.text_input("Serial port", value="COM3", help="e.g. COM3 (Windows) or /dev/ttyUSB0 (Linux)")
        baud = st.selectbox("Baud rate", [9600, 57600, 115200], index=2)
        if st.button("Connect"):
            new_system("Arduino (serial)", port, baud)
        if ss.serial_error:
            st.error(f"Connection failed: {ss.serial_error}")
    elif ss.source != "Simulator":
        new_system("Simulator")

    ss.running = st.toggle("Live updates", value=ss.get("running", True))
    speed = st.slider("Simulation speed (steps per refresh)", 5, 60, 20, disabled=source != "Simulator")
    window = st.select_slider("Chart window (min)", options=[5, 10, 15, 30, 60], value=15)
    ss.cfg.n_persist = st.slider("Persistence N (cycles)", 1, 6, ss.cfg.n_persist,
                                 help="A deviation must persist for N consecutive cycles before a warning.")

    if source == "Simulator":
        st.divider()
        st.subheader("Fault injection")
        if ss.mon.learning:
            st.info("Baseline is still being learned. Inject faults after it is complete.")
        fault = st.selectbox("Scenario", FAULTS, disabled=ss.mon.learning)
        c1, c2 = st.columns(2)
        if c1.button("Inject", disabled=ss.mon.learning, type="primary"):
            ss.sim.inject(fault)
            if fault == NONE:
                ss.mon.mark_cleared()
            else:
                ss.mon.mark_injection(ss.sim.t, EXPECTED_CAUSE[fault])
        if c2.button("Clear fault", disabled=ss.mon.learning):
            ss.sim.inject(NONE)
            ss.mon.mark_cleared()
        st.caption(f"Active fault: **{ss.sim.fault}**")
    st.divider()
    if st.button("Reset system"):
        new_system(source, port, baud)
        st.rerun()


# ----------------------------------------------------------------- dashboard
def dashboard() -> None:
    ss = st.session_state
    mon, cfg = ss.mon, ss.cfg
    if ss.running:
        advance(speed)

    status, cause = mon.status_info()
    if status == "LEARNING":
        st.info(f"🧠 Learning baseline: {len(mon.baseline_rows)}/{cfg.baseline_cycles} healthy cycles recorded.")
    elif status == "NORMAL":
        st.success("🟢 NORMAL: system behaves like the baseline.")
    elif status == "WARNING":
        st.warning(f"🟠 WARNING: probable cause **{cause}**. Inspect at the next opportunity.")
    else:
        st.error(f"🔴 CRITICAL: **{cause}**. Act now.")

    if not ss.hist:
        st.info("Waiting for data...")
        return
    last = ss.hist[-1]
    prev = ss.hist[-2] if len(ss.hist) > 1 else last
    lvl = last["level"]
    k = st.columns(5)
    k[0].metric("Level (cm)", "n/a" if math.isnan(lvl) else f"{lvl:.1f}",
                None if math.isnan(lvl) or math.isnan(prev["level"]) else f"{lvl - prev['level']:+.2f}")
    k[1].metric("Outlet flow (L/min)", f"{last['flow']:.2f}")
    k[2].metric("Pump current (A)", f"{last['current']:.2f}")
    k[3].metric("Pump command", "ON" if last["run"] else "OFF")
    k[4].metric("Cycles recorded", len(mon.cycles))

    tab_live, tab_cycles, tab_alarms, tab_eval, tab_about = st.tabs(
        ["📈 Live", "🔁 Cycle analysis", "🚨 Alarms", "✅ Validation metrics", "ℹ️ About"])

    with tab_live:
        df = pd.DataFrame(ss.hist)
        df = df[df["t"] >= df["t"].iloc[-1] - window * 60]
        show(live_figure(df, cfg, mon), "live")

    with tab_cycles:
        cdf = mon.cycles_df()
        if mon.bands is None or cdf.empty:
            st.info("Cycle features appear here once the first cycles are completed.")
        else:
            cols = st.columns(3)
            for i, f in enumerate(FEATURES):
                with cols[i % 3]:
                    show(feature_figure(f, cdf, mon.bands), f"feat_{f}")
            with cols[2]:
                st.caption("Green band = baseline mean ± 3σ. Grey dots = baseline cycles, "
                           "red dots = outside the band.")
            st.dataframe(cdf.round(3).iloc[::-1], hide_index=True)
            st.download_button("Download cycles (CSV)", cdf.to_csv(index=False), "cycles.csv", "text/csv")

    with tab_alarms:
        adf = mon.alarms_df()
        if adf.empty:
            st.info("No alarm so far.")
        else:
            st.dataframe(adf.iloc[::-1], hide_index=True)
            st.download_button("Download alarm log (CSV)", adf.to_csv(index=False), "alarms.csv", "text/csv")

    with tab_eval:
        ev = mon.evaluation()
        st.markdown("Metrics defined in Section 12 of the proposal, computed from the logged injection time.")
        m = st.columns(4)
        m[0].metric("False alarms", ev["false_alarms"], help="Alarms raised in fault-free periods")
        per100 = 100 * ev["false_alarms"] / ev["normal_cycles"] if ev["normal_cycles"] else 0
        m[1].metric("Normal cycles evaluated", ev["normal_cycles"], f"{per100:.1f} false alarms / 100 cycles",
                    delta_color="off")
        m[2].metric("Wrong-cause alarms", ev["wrong_cause"])
        m[3].metric("Injected fault", ss.sim.fault if ss.sim else "n/a")
        if mon.inject_t is None:
            st.info("Inject a fault from the side panel to measure detection delay and warning lead time.")
        else:
            d = st.columns(3)
            d[0].metric("Detection delay",
                        "not yet" if ev["delay_s"] is None else f"{ev['delay_s'] / 60:.1f} min",
                        None if ev["delay_cycles"] is None else f"{ev['delay_cycles']} cycles", delta_color="off")
            d[1].metric("FS3 reached", "yes" if ev["fs3_reached"] else "no")
            d[2].metric("Warning lead time vs FS3",
                        "n/a" if ev["lead_s"] is None else f"{ev['lead_s'] / 60:.1f} min",
                        help="A plain level switch gives zero lead time.")
            st.caption("Results from a few runs give a rough picture only. Report them as counts (k of n).")

    with tab_about:
        st.markdown(
            """
**Rule table** (persistence of N cycles, thresholds from the 30-cycle baseline)

| Observed pattern | Probable cause | Alarm |
|---|---|---|
| Flow and emptying rate below band, current normal or above | Discharge restriction | Warning |
| Flow and current below band, run time above band | Pump malfunction P2 (degraded) | Warning |
| Pump commanded ON, current below running threshold | Pump malfunction P1 (not running) | Critical |
| Fill rate above band, everything else normal | Abnormal inflow | Warning |
| Level reaches FS3 | Imminent overflow | Critical |

**Industrial equivalent:** transmitters (4-20 mA) to a PLC/RTU, this logic as a function block,
alarms and history in SCADA.

**Arduino serial format** (one line per sample): `level_cm,flow_lpm,current_a,run,fs3`

The rules point to a *probable cause* to investigate, not a certain diagnosis. Rig tests use clean water;
thresholds do not transfer directly to an oily stream or an industrial pump.
""")


st.fragment(run_every=1.0 if ss.running else None)(dashboard)()
