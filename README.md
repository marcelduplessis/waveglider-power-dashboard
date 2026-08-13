# Waveglider Power Analysis Pipeline

Complete automated pipeline for extracting AMPS data and generating interactive power analysis dashboards for WG1169 and WG1170.

## Overview

The pipeline consists of three main stages:

1. **Data Fetch** (optional): `waveglider-data-wg1169.py` & `waveglider-data-wg1170.py`
   - Fetches latest waveglider WGMS data
   - Skipped silently if scripts don't exist

2. **AMPS Extraction**: `extract_amps_ports_full_wg1169.py` & `extract_amps_ports_full_wg1170.py`
   - Extracts power data from WGMS JSON outputs
   - Generates CSV files for solar power, total usage, and battery power
   - Outputs: `amps_power_output/{wg1169,wg1170}/`

3. **Dashboard Generation**: `power_analysis.py`
   - Builds interactive Plotly figures with 3 stacked subplots
   - Day navigation slider
   - Generates per-glider and combined HTML exports
   - Exports: `exports/`

## Running the Pipeline

### Option 1: Shell Script (Recommended)

```bash
cd /Users/xduplm/Desktop/whirls/platforms/wavegliders/power-analysis
./run_pipeline.sh
```

### Option 2: Direct Python

```bash
cd /Users/xduplm/Desktop/whirls/platforms/wavegliders/power-analysis
python3 run_full_pipeline.py
```

### Option 3: Individual Steps

```bash
# Extract AMPS data
python3 extract_amps_ports_full_wg1169.py
python3 extract_amps_ports_full_wg1170.py

# Generate dashboards
python3 power_analysis.py
```

## Files

- **run_pipeline.sh**: Shell wrapper that calls the Python orchestrator
- **run_full_pipeline.py**: Main orchestrator; handles step ordering and error handling
- **power_analysis.py**: Standalone Python version of power_analysis.ipynb
- **power_analysis.ipynb**: Original Jupyter notebook (kept for reference)
- **extract_amps_ports_full_wg*.py**: AMPS data extraction scripts

## Configuration

Edit `power_analysis.py` to change:
- `ANALYSIS_TARGET`: `'both'`, `'wg1169'`, or `'wg1170'`
- `PG_OBS_FALLBACK_URL`: URL for "Return To PG Obs" button fallback

## Output

All exports are written to `exports/`:

- `wg1169_power_interactive.html` - Standalone WG1169 dashboard
- `wg1169_power_interactive_embed.html` - Embeddable WG1169 dashboard
- `wg1170_power_interactive.html` - Standalone WG1170 dashboard
- `wg1170_power_interactive_embed.html` - Embeddable WG1170 dashboard
- `wg_power_dashboard_combined.html` - Combined single-page dashboard

## Logs

Execution logs are saved to `logs/` with timestamp: `pipeline_YYYYMMDD_HHMMSS.log`

## Exit Codes

- `0` - All steps successful
- `1` - Data fetch failed (if scripts exist)
- `2` - AMPS extraction failed
- `3` - Power analysis failed

## Notes

- Times in all dashboards are in UTC
- "Return To PG Obs" button uses browser history if available, otherwise falls back to homepage
- Plots include hover tooltips and interactive legend controls
- Data files are expected at: `amps_power_output/{wg1169,wg1170}/{csv-files}`
