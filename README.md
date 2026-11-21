# DrainZ 2.0: Oily-Water Sump Monitor

Streamlit dashboard for early fault diagnosis of an oily-water sump and its pumping
station (Oil & Gas use case), built from three measurements: **level, outlet flow and
pump current**. It is the software part of a PFE project extending the DrainZ prototype.

> Advisory monitoring only. It never controls the pump and is not a certified protection system.

## Features
- Cycle detection (fill -> pump -> empty) with 5 features per cycle
- Baseline learned from 30 healthy cycles (mean ± 3σ bands)
- Rule-based diagnosis with a persistence filter (N cycles): discharge restriction,
  pump degraded (P2), pump not running (P1), abnormal inflow, imminent overflow (FS3)
- Sensor checks (disconnected / frozen level signal)
- Warning and Critical alarms with probable cause, CSV export
- Validation metrics: false alarms, wrong cause, detection delay, warning lead time vs FS3
- Built-in simulator with fault injection, or live data from an Arduino Mega over USB

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Use with the Arduino Mega
Select **Arduino (serial)** in the side panel, enter the port and click **Connect**.
The Arduino must print one line every ~2 s:

```
level_cm,flow_lpm,current_a,run,fs3
27.4,7.52,2.21,1,0
```

## Deploy for free (Streamlit Community Cloud)
1. Push `app.py`, `requirements.txt` and `README.md` to a public GitHub repository.
2. Go to share.streamlit.io, sign in with GitHub, choose the repository and `app.py`, then Deploy.
   (The simulator works online. Serial mode only works when running locally.)

## Industrial equivalent
Transmitters (4-20 mA) -> PLC/RTU -> rules as a function block -> SCADA alarms and historian.

## Limitations
Clean-water bench rig, small DC pump, laboratory conditions. Thresholds and persistence
settings must be retuned on real plant data.
