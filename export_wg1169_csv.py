"""Export WG1169 AirSea, waves, and weather data to CSV files."""

from __future__ import annotations

import argparse
import json
from glob import glob
from pathlib import Path

import pandas as pd


PROJECT_RELATIVE_PATH = Path("My Drive/projects/2026-whirls")
GOOGLE_DRIVE_ROOTS = (
    Path("/Users/xduplm/Google Drive"),
    Path("/Users/xduplm/Library/CloudStorage/GoogleDrive-marceldpl10@gmail.com"),
)


def find_project_root() -> Path:
    for drive_root in GOOGLE_DRIVE_ROOTS:
        project_root = drive_root / PROJECT_RELATIVE_PATH
        if project_root.exists():
            return project_root
    raise FileNotFoundError("Could not find the 2026-whirls project in Google Drive")


def load_json_records(pattern: str, source_name: str) -> pd.DataFrame:
    files = sorted(Path(path) for path in glob(pattern))
    if not files:
        raise FileNotFoundError(f"No files matched pattern: {pattern}")

    records = []
    for file_path in files:
        with file_path.open(encoding="utf-8") as file:
            data = json.load(file)
        if isinstance(data, list):
            records.extend(row for row in data if isinstance(row, dict))

    if not records:
        raise ValueError(f"Files were found, but no valid {source_name} records were present")
    return pd.DataFrame(records)


def clean_time(df: pd.DataFrame) -> pd.DataFrame:
    df["timeStamp"] = pd.to_datetime(df["timeStamp"], errors="coerce")
    return (
        df.dropna(subset=["timeStamp"])
        .sort_values("timeStamp")
        .drop_duplicates(subset=["timeStamp"], keep="last")
        .reset_index(drop=True)
    )


def convert_numeric_columns(df: pd.DataFrame, columns: list[str]) -> None:
    for column in columns:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")


def load_weather(pattern: str) -> pd.DataFrame:
    weather = load_json_records(pattern, "weather")
    weather = clean_time(weather)
    convert_numeric_columns(
        weather,
        [
            "latitude",
            "longitude",
            "avgTemp(C)",
            "avgPress(mbar)",
            "avgWindSpeed(kt)",
            "stdDevWindSpeed(kt)",
            "avgWindDir(deg)",
            "stdDevWindDir(deg)",
            "gustTime(hour)",
            "gustTime(minute)",
            "gustSpeed(kt)",
            "gustDir(deg)",
            "numValidWindSamples",
        ],
    )
    weather = weather.rename(
        columns={
            "avgTemp(C)": "air_temperature",
            "avgPress(mbar)": "air_pressure",
            "avgWindSpeed(kt)": "wind_speed_kt",
            "stdDevWindSpeed(kt)": "wind_speed_std",
            "avgWindDir(deg)": "wind_dir_deg",
            "stdDevWindDir(deg)": "wind_dir_std_deg",
            "gustSpeed(kt)": "gust_speed_kt",
            "gustDir(deg)": "gust_dir_deg",
            "gustTime(hour)": "gust_hour",
            "gustTime(minute)": "gust_minute",
            "numValidWindSamples": "num_valid_wind_samples",
        }
    )
    weather["wind_speed_ms"] = weather["wind_speed_kt"] * 0.514444
    return weather


def load_waves(pattern: str) -> pd.DataFrame:
    waves = load_json_records(pattern, "wave")
    waves = clean_time(waves)
    convert_numeric_columns(
        waves,
        [
            "latitude",
            "longitude",
            "hs (m)",
            "ta (s)",
            "tp (s)",
            "dp (deg)",
            "samples",
            "fs (Hz)",
            "sample Gaps",
        ],
    )
    waves = waves.rename(
        columns={
            "hs (m)": "significant_wave_height_m",
            "ta (s)": "average_wave_period_s",
            "tp (s)": "peak_wave_period_s",
            "dp (deg)": "peak_wave_direction_deg",
            "samples": "n_samples",
            "fs (Hz)": "sampling_frequency_hz",
            "sample Gaps": "sample_gaps",
        }
    )
    measurement_columns = [
        "significant_wave_height_m",
        "average_wave_period_s",
        "peak_wave_period_s",
        "peak_wave_direction_deg",
    ]
    waves[measurement_columns] = waves[measurement_columns].replace([9999.0, -9999.0], pd.NA)
    return waves


def export_csv_files(output_dir: Path) -> None:
    project_root = find_project_root()
    source_dir = project_root / "data/wg1169/json"
    output_dir.mkdir(parents=True, exist_ok=True)

    datasets = {
        "airsea.csv": pd.read_csv(source_dir / "AirSeaWHIRLS_Decoded.csv"),
        "waves.csv": load_waves(str(source_dir / "waveglider-waves_*.json")),
        "weather.csv": load_weather(str(source_dir / "waveglider-weather_*.json")),
    }
    for filename, dataframe in datasets.items():
        output_path = output_dir / filename
        dataframe.to_csv(output_path, index=False)
        print(f"Wrote {len(dataframe):,} rows to {output_path}")


def parse_args() -> argparse.Namespace:
    project_root = find_project_root()
    default_output = project_root / (
        "platforms/wavegliders/waveglider-power-dashboard/"
        "amps_power_output/wg1169"
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_output,
        help=f"CSV destination (default: {default_output})",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    export_csv_files(args.output_dir)