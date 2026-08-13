"""
extract_amps_ports_full_wg1170.py

Extracts WGMS AMPS power products for WG1170:
    1. Full one-row-per-port table from output-power-status JSON
    2. Total vehicle output power (W) per hourly sample
    3. Solar power generated (W) per timestamp

Inputs:
    - waveglider-amps-output-power-status_*.json
    - waveglider-amps-solar_*.json

Units:
    avgPower and panelPower are used as reported. avgPower was previously
    verified to already be in Watts (avgVoltage * avgCurrent matches the
    reported avgPower within normal rounding error), so no conversion is
    applied here.

Outputs:
    amps_power_output/wg1170/all_ports_domain_slot_port_power.csv
    amps_power_output/wg1170/total_output_power_watts.csv
    amps_power_output/wg1170/solar_power_watts.csv
    amps_power_output/wg1170/total_battery_power_watts.csv
"""

import json
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Sensor lookup table (Slot/Port -> Sensor Name), same as before.
# Ports not in this map are still included in the output, just with
# sensor left blank -- see the write-up on unlabeled ports (domain 1,
# module 32, etc.) from the previous analysis.
# ---------------------------------------------------------------------------
SENSOR_MAP = {
    (1, 1): "GPSWaves",
    (1, 2): "Iridium",
    (1, 3): "SMC",
    (1, 7): "ADCP",
    (1, 4): "CR6",
    (5, 1): "SPN1 Heater",
    (5, 2): "SPN1",
    (5, 3): "Vaisala WXT530 Heater",
    (5, 5): "RBR CTD",
    (5, 4): "Vaisala WXT530",
    (5, 6): "Gill R3-50",
    (7, 4): "AIS",
    (4, 5): "airmarWaterspeedDevice",
    (4, 1): "Airmar WS200",
    (32, 3): "VMC",
    (32, 106): "CCU: Tegra TX1 SOM module",
    (32, 110): "CCU: UARTs, HS/LS USB Hubs, Ethernet",
    (32, 1): "CCU: UNKNOWN",
    (32, 108): "CCU: mSATA Drive, SDCARD, discrete ICs",
    (4, 3): "lightBar",
    (7, 2): "pCO2",
}


def load_record_data_from_files(file_paths: list[Path]) -> list[dict]:
    """Load and concatenate WGMS JSON recordData from multiple files.
    
    Handles both:
    - {"recordData": [...]} (dict structure)
    - [...] (list structure, e.g., empty files or direct arrays)
    """
    all_records: list[dict] = []
    for file_path in file_paths:
        with open(file_path) as f:
            payload = json.load(f)
        
        # Handle both dict with "recordData" key and direct list
        if isinstance(payload, dict):
            records = payload.get("recordData", [])
        elif isinstance(payload, list):
            records = payload
        else:
            records = []
        
        all_records.extend(records)
    return all_records


def melt_ports(records: list[dict], port_fields: list[str], max_slots: int) -> pd.DataFrame:
    """Unpivot the wide 'portN / moduleN / avgPowerN ...' JSON records into
    one row per real port. Empty slots (portNumber == 0 and
    moduleNumber == 0) are dropped."""
    numbered_prefixes = tuple(port_fields) + ("portNumber", "moduleNumber")
    rows = []
    for rec in records:
        base = {
            k: v
            for k, v in rec.items()
            if k != "recordData"
            and not any(k.startswith(p) and k[len(p):].isdigit() for p in numbered_prefixes)
        }
        for i in range(1, max_slots + 1):
            port_num = rec.get(f"portNumber{i}")
            module_num = rec.get(f"moduleNumber{i}")
            if not port_num and not module_num:
                continue  # unused slot
            row = dict(base)
            row["portNumber"] = port_num
            row["moduleNumber"] = module_num
            for field in port_fields:
                row[field] = rec.get(f"{field}{i}")
            rows.append(row)
    return pd.DataFrame(rows)


def load_output_power(file_paths: list[Path]) -> pd.DataFrame:
    raw = load_record_data_from_files(file_paths)

    fields = ["portStatus", "avgPower", "avgVoltage", "avgCurrent", "sampleTime"]
    df = melt_ports(raw, fields, max_slots=33)

    df["timeStamp"] = pd.to_datetime(df["timeStamp"])
    df["sampleHour"] = df["timeStamp"].dt.floor("h")

    df["sensor"] = df.apply(
        lambda r: SENSOR_MAP.get((int(r["moduleNumber"]), int(r["portNumber"]))),
        axis=1,
    )
    return df


def load_solar_power(file_paths: list[Path]) -> pd.DataFrame:
    raw = load_record_data_from_files(file_paths)

    fields = [
        "portStatus", "boostPower", "boostVoltage", "boostCurrent",
        "panelPower", "panelVoltage", "panelCurrent", "boostRatio", "sampleTime",
    ]
    df = melt_ports(raw, fields, max_slots=4)

    df["timeStamp"] = pd.to_datetime(df["timeStamp"])
    df["sampleHour"] = df["timeStamp"].dt.floor("h")
    return df


def load_summary_amps(file_paths: list[Path]) -> pd.DataFrame:
    """Load WGMS summary AMPS records (waveglider-amps_*.json)."""
    raw = load_record_data_from_files(file_paths)
    return pd.DataFrame(raw)


def build_full_port_table(output_long: pd.DataFrame) -> pd.DataFrame:
    """Full Domain / Slot / Port / Power / Voltage table, one row per port
    per reported timestamp, including unlabeled ports."""
    table = output_long.rename(
        columns={
            "timeStamp": "timestamp",
            "powerDomain": "domain",
            "moduleNumber": "slot",
            "portNumber": "port",
            "avgPower": "avg_power_W",
            "avgVoltage": "avg_voltage_V",
            "avgCurrent": "avg_current_A",
            "portStatus": "port_status",
        }
    )[
        [
            "timestamp",
            "sampleHour",
            "domain",
            "slot",
            "port",
            "sensor",
            "avg_power_W",
            "avg_voltage_V",
            "avg_current_A",
            "port_status",
        ]
    ]
    return table.sort_values(["timestamp", "domain", "slot", "port"]).reset_index(drop=True)


def build_total_output_power(output_long: pd.DataFrame) -> pd.DataFrame:
    """Total vehicle output power (W) per hourly sample, summed across all
    ports/domains reported in that hour."""
    totals = (
        output_long.groupby("sampleHour")["avgPower"]
        .sum()
        .reset_index()
        .rename(columns={"sampleHour": "timestamp", "avgPower": "total_output_power_W"})
    )
    return totals


def build_solar_power(solar_long: pd.DataFrame) -> pd.DataFrame:
    """Total solar power generated (W) per timestamp, summed across all
    active solar panel ports."""
    totals = (
        solar_long[solar_long["panelPower"] > 0]
        .groupby("timeStamp")["panelPower"]
        .sum()
        .reset_index()
        .rename(columns={"timeStamp": "timeStamp", "panelPower": "solar_power_W"})
    )
    return totals


def build_total_battery_power(summary_amps: pd.DataFrame) -> pd.DataFrame:
    """Total battery power per glider timestamp.

    The summary AMPS report field is named totalBatteryPower. These values are
    reported in milliwatts in the WGMS summary payload, so this converts them
    to watts for output consistency.
    """
    required_cols = {"gliderTimeStamp", "totalBatteryPower"}
    missing = required_cols - set(summary_amps.columns)
    if missing:
        raise KeyError(f"Missing required summary AMPS fields: {sorted(missing)}")

    battery = summary_amps[["gliderTimeStamp", "totalBatteryPower"]].copy()
    battery["timestamp"] = pd.to_datetime(battery["gliderTimeStamp"])
    battery = battery.dropna(subset=["timestamp", "totalBatteryPower"])
    battery["total_battery_power_W"] = pd.to_numeric(battery["totalBatteryPower"], errors="coerce") / 1000.0
    battery = battery.dropna(subset=["total_battery_power_W"])

    return (
        battery[["timestamp", "total_battery_power_W"]]
        .sort_values("timestamp")
        .reset_index(drop=True)
    )


def main():
    data_dir = Path("/Users/xduplm/Google Drive/My Drive/projects/2026-whirls/data/wg1170/json/")
    output_files = sorted(data_dir.glob("waveglider-amps-output-power-status_*.json"))
    solar_files = sorted(data_dir.glob("waveglider-amps-solar_*.json"))
    summary_files = sorted(data_dir.glob("waveglider-amps_*.json"))

    if not output_files:
        raise FileNotFoundError(f"No output-power-status JSON files found in {data_dir}")
    if not solar_files:
        raise FileNotFoundError(f"No solar JSON files found in {data_dir}")
    if not summary_files:
        raise FileNotFoundError(f"No summary AMPS JSON files found in {data_dir}")

    print(f"Found {len(output_files)} output-power-status files")
    print(f"Found {len(solar_files)} solar files")
    print(f"Found {len(summary_files)} summary AMPS files")

    output_long = load_output_power(output_files)
    solar_long = load_solar_power(solar_files)
    summary_amps = load_summary_amps(summary_files)

    full_table = build_full_port_table(output_long)
    total_power = build_total_output_power(output_long)
    solar_power = build_solar_power(solar_long)
    battery_power = build_total_battery_power(summary_amps)

    print(f"Total rows: {len(full_table)}")
    print(full_table.head(20).to_string(index=False))

    out_dir = Path("/Users/xduplm/Google Drive/My Drive/projects/2026-whirls/platforms/wavegliders/waveglider-power-dashboard/amps_power_output/wg1170/")
    out_dir.mkdir(exist_ok=True)
    full_out_path = out_dir / "all_ports_domain_slot_port_power.csv"
    total_out_path = out_dir / "total_output_power_watts.csv"
    solar_out_path = out_dir / "solar_power_watts.csv"
    battery_out_path = out_dir / "total_battery_power_watts.csv"

    full_table.to_csv(full_out_path, index=False)
    total_power.to_csv(total_out_path, index=False)
    solar_power.to_csv(solar_out_path, index=False)
    battery_power.to_csv(battery_out_path, index=False)

    print(f"\nSaved full Domain/Slot/Port power table to {full_out_path}")
    print(f"Saved total output power table to {total_out_path}")
    print(f"Saved solar power table to {solar_out_path}")
    print(f"Saved total battery power table to {battery_out_path}")


if __name__ == "__main__":
    main()
