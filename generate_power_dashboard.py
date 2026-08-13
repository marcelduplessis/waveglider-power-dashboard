#!/usr/bin/env python3
"""Generate interactive Wave Glider power dashboards from CSV outputs.

This script reproduces the plotting/export workflow from power_analysis.ipynb
as a standalone job suitable for cron.

Outputs (under exports/):
- wg1169_power_interactive.html
- wg1169_power_interactive_embed.html
- wg1170_power_interactive.html
- wg1170_power_interactive_embed.html
- wg_power_dashboard_combined.html
"""

from pathlib import Path
from typing import Dict, List

import pandas as pd
import plotly.graph_objects as go


PALETTE = [
    "#0072B2",  # blue
    "#E69F00",  # orange
    "#009E73",  # bluish green
    "#D55E00",  # vermillion
    "#CC79A7",  # reddish purple
    "#56B4E9",  # sky blue
    "#F0E442",  # yellow
    "#000000",  # black
    "#332288",  # indigo
    "#88CCEE",  # light blue
    "#44AA99",  # teal
    "#117733",  # green
    "#999933",  # olive
    "#AA4499",  # magenta
]


def _load_inputs(glider_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    sensor = pd.read_csv(glider_dir / "all_ports_domain_slot_port_power.csv")
    solar = pd.read_csv(glider_dir / "solar_power_watts.csv")
    total = pd.read_csv(glider_dir / "total_output_power_watts.csv")
    return sensor, solar, total


def _build_figure(sensor_pwr_out: pd.DataFrame, solar_pwr_in: pd.DataFrame, total_pwr_out: pd.DataFrame, glider_label: str) -> go.Figure:
    plot_df = sensor_pwr_out.copy()
    plot_df["sampleHour"] = pd.to_datetime(plot_df["sampleHour"])
    plot_df = plot_df[plot_df["avg_power_W"] > 0.2].copy()

    plot_df["component"] = plot_df["sensor"].fillna("").astype(str).str.strip()
    empty_component = plot_df["component"].eq("")
    plot_df.loc[empty_component, "component"] = (
        "D" + plot_df.loc[empty_component, "domain"].astype(str)
        + "-S" + plot_df.loc[empty_component, "slot"].astype(str)
        + "-P" + plot_df.loc[empty_component, "port"].astype(str)
    )

    stacked = (
        plot_df.pivot_table(
            index="sampleHour",
            columns="component",
            values="avg_power_W",
            aggfunc="sum",
            fill_value=0,
        )
        .sort_index()
    )

    if stacked.empty:
        raise ValueError(f"No stacked data available for {glider_label}")

    solar_line = solar_pwr_in.copy()
    solar_line["sampleHour"] = pd.to_datetime(solar_line["timeStamp"]).dt.floor("h")
    solar_line = (
        solar_line.groupby("sampleHour", as_index=False)["solar_power_W"]
        .mean()
        .rename(columns={"solar_power_W": "solar_gain_W"})
    )

    usage_line = total_pwr_out.copy()
    usage_line["sampleHour"] = pd.to_datetime(usage_line["timestamp"]).dt.floor("h")
    usage_line = (
        usage_line.groupby("sampleHour", as_index=False)["total_output_power_W"]
        .mean()
        .rename(columns={"total_output_power_W": "total_usage_W"})
    )

    line_df = (
        stacked.reset_index()[["sampleHour"]]
        .merge(usage_line, on="sampleHour", how="left")
        .merge(solar_line, on="sampleHour", how="left")
    )

    bar_colors = [PALETTE[i % len(PALETTE)] for i in range(stacked.shape[1])]

    available_days = sorted(stacked.index.normalize().unique())
    today = pd.Timestamp.today().normalize()
    default_day = today if today in available_days else available_days[-1]

    fig = go.Figure()
    day_meta: Dict[str, Dict[str, object]] = {}

    for day in available_days:
        day_mask = stacked.index.normalize() == day
        day_stacked = stacked.loc[day_mask]
        day_lines = line_df[line_df["sampleHour"].dt.normalize() == day]

        daily_total_used_wh = day_lines["total_usage_W"].fillna(0).sum()
        daily_total_gained_wh = day_lines["solar_gain_W"].fillna(0).sum()

        day_label = pd.Timestamp(day).strftime("%Y-%m-%d")
        trace_indices: List[int] = []

        for i, component in enumerate(stacked.columns):
            fig.add_trace(
                go.Bar(
                    x=day_stacked.index,
                    y=day_stacked[component],
                    name=str(component),
                    marker_color=bar_colors[i],
                    visible=(day == default_day),
                    hovertemplate="%{x|%-d/%m %H:%M}<br>"
                    + str(component)
                    + ": %{y:.2f} W<extra></extra>",
                )
            )
            trace_indices.append(len(fig.data) - 1)

        fig.add_trace(
            go.Scatter(
                x=day_lines["sampleHour"],
                y=day_lines["total_usage_W"],
                mode="lines+markers",
                name="Total power usage (W)",
                line=dict(color="#3A506B", width=2.2),
                marker=dict(size=6),
                visible=(day == default_day),
                hovertemplate="%{x|%-d/%m %H:%M}<br>Total usage: %{y:.2f} W<extra></extra>",
            )
        )
        trace_indices.append(len(fig.data) - 1)

        fig.add_trace(
            go.Scatter(
                x=day_lines["sampleHour"],
                y=day_lines["solar_gain_W"],
                mode="lines+markers",
                name="Solar power gain (W)",
                line=dict(color="#E09F3E", width=2.2),
                marker=dict(size=6),
                visible=(day == default_day),
                hovertemplate="%{x|%-d/%m %H:%M}<br>Solar gain: %{y:.2f} W<extra></extra>",
            )
        )
        trace_indices.append(len(fig.data) - 1)

        day_meta[day_label] = {
            "trace_indices": trace_indices,
            "title": (
                f"{glider_label}: Average Power Usage (Watts) with Total Usage and Solar Gain<br>"
                f"Date: {day_label} | Daily gained: {daily_total_gained_wh:.1f} Wh | Daily used: {daily_total_used_wh:.1f} Wh"
            ),
        }

    buttons = []
    for day_label, meta in day_meta.items():
        visible = [False] * len(fig.data)
        for idx in meta["trace_indices"]:
            visible[idx] = True

        buttons.append(
            dict(
                label=day_label,
                method="update",
                args=[{"visible": visible}, {"title": meta["title"]}],
            )
        )

    default_label = pd.Timestamp(default_day).strftime("%Y-%m-%d")

    fig.update_layout(
        barmode="stack",
        title=day_meta[default_label]["title"],
        xaxis_title="",
        yaxis_title="Power output (W)",
        legend_title="Series",
        hovermode="x unified",
        template="plotly_white",
        height=620,
        margin=dict(l=50, r=260, t=120, b=90),
        updatemenus=[
            dict(
                type="dropdown",
                direction="down",
                x=1.01,
                y=1.16,
                xanchor="left",
                yanchor="top",
                showactive=True,
                buttons=buttons,
            )
        ],
        annotations=[
            dict(
                x=1.01,
                y=1.2,
                xref="paper",
                yref="paper",
                text="Select date",
                showarrow=False,
                align="left",
            )
        ],
    )
    fig.update_xaxes(tickformat="%-d/%m %H:%M", tickangle=90)

    return fig


def _export_figure(fig: go.Figure, export_dir: Path, prefix: str) -> tuple[Path, Path]:
    full_path = export_dir / f"{prefix}_interactive.html"
    embed_path = export_dir / f"{prefix}_interactive_embed.html"

    fig.write_html(full_path, full_html=True, include_plotlyjs="cdn")
    fig.write_html(embed_path, full_html=False, include_plotlyjs=False)
    return full_path, embed_path


def _write_combined_dashboard(export_dir: Path) -> Path:
    wg1169_embed = (export_dir / "wg1169_power_interactive_embed.html").read_text(encoding="utf-8")
    wg1170_embed = (export_dir / "wg1170_power_interactive_embed.html").read_text(encoding="utf-8")

    combined_out = export_dir / "wg_power_dashboard_combined.html"
    combined_html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Wave Glider Power Dashboard</title>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; padding: 24px; background: #f8fafc; }}
    .wrap {{ max-width: 1400px; margin: 0 auto; }}
    h1 {{ margin: 0 0 8px 0; }}
    p {{ margin: 0 0 24px 0; color: #334155; }}
    .panel {{ background: white; border-radius: 14px; box-shadow: 0 2px 12px rgba(0,0,0,0.08); padding: 16px; margin-bottom: 20px; }}
    .panel h2 {{ margin: 0 0 12px 0; }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Wave Glider Power Dashboard</h1>
    <p>Interactive daily power summaries for WG1169 and WG1170.</p>

    <section class="panel">
      <h2>WG1169</h2>
      {wg1169_embed}
    </section>

    <section class="panel">
      <h2>WG1170</h2>
      {wg1170_embed}
    </section>
  </div>
</body>
</html>
"""
    combined_out.write_text(combined_html, encoding="utf-8")
    return combined_out


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    amps_dir = script_dir / "amps_power_output"
    export_dir = script_dir / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)

    wg_targets = [
        ("wg1169", "WG1169"),
        ("wg1170", "WG1170"),
    ]

    for folder_name, label in wg_targets:
        glider_dir = amps_dir / folder_name
        sensor_df, solar_df, total_df = _load_inputs(glider_dir)
        fig = _build_figure(sensor_df, solar_df, total_df, label)

        full_path, embed_path = _export_figure(fig, export_dir, folder_name)
        print(f"Saved: {full_path}")
        print(f"Saved: {embed_path}")

    combined_out = _write_combined_dashboard(export_dir)
    print(f"Saved: {combined_out}")


if __name__ == "__main__":
    main()
