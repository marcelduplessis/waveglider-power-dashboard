#!/usr/bin/env python3
"""
power_analysis.py

Standalone script version of power_analysis.ipynb.
Generates interactive Plotly dashboards for waveglider power analysis with:
    - 4 stacked subplots (Power Sources/Flows, Total Battery Power,
        Full Mission Battery, Sensor Data Availability)
  - Day slider for temporal navigation
  - Per-glider and combined HTML exports
  - Dynamic return-to-origin button for PG Obs integration
"""

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def main():
    """Run the power analysis pipeline."""
    
    # ========== Configuration ==========
    BASE_DIR = Path(__file__).parent
    AMPS_DIR = BASE_DIR / 'amps_power_output'
    EXPORT_DIR = BASE_DIR / 'exports'
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Colorblind-friendly palette (Okabe-Ito + extensions)
    PALETTE = [
        '#0072B2',  # blue
        '#E69F00',  # orange
        '#009E73',  # bluish green
        '#D55E00',  # vermillion
        '#CC79A7',  # reddish purple
        '#56B4E9',  # sky blue
        '#F0E442',  # yellow
        '#000000',  # black
        '#332288',  # indigo
        '#88CCEE',  # light blue
        '#44AA99',  # teal
        '#117733',  # green
        '#999933',  # olive
        '#AA4499',  # magenta
    ]
    
    GLIDERS = {
        'wg1169': 'WG1169 - Vetkoek',
        'wg1170': 'WG1170 - Melktert',
    }
    
    # Options: 'both', 'wg1169', 'wg1170'
    ANALYSIS_TARGET = 'both'
    
    # Fallback destination if browser history is not available.
    PG_OBS_FALLBACK_URL = 'https://obs.polargliders.com/'
    LAST_UPDATED = datetime.now(timezone.utc).strftime('%d-%b %Y %H:%M:%S UTC')

    # ========== Helper Functions ==========
    
    def load_glider_data(glider_key: str):
        """Load all data files for a glider."""
        glider_dir = AMPS_DIR / glider_key
        sensor_pwr_out = pd.read_csv(glider_dir / 'all_ports_domain_slot_port_power.csv')
        solar_pwr_in = pd.read_csv(glider_dir / 'solar_power_watts.csv')
        total_pwr_out = pd.read_csv(glider_dir / 'total_output_power_watts.csv')
        battery_pwr = pd.read_csv(glider_dir / 'total_battery_power_watts.csv')
        sensor_data = {
            'airsea': pd.read_csv(glider_dir / 'airsea.csv'),
            'waves': pd.read_csv(glider_dir / 'waves.csv'),
            'weather': pd.read_csv(glider_dir / 'weather.csv'),
        }
        if glider_key == 'wg1170':
            sensor_data['vegas'] = pd.read_csv(glider_dir / 'vegas.csv')
        return sensor_pwr_out, solar_pwr_in, total_pwr_out, battery_pwr, sensor_data


    def build_sensor_availability(sensor_data, include_pco2=False):
        """Build timestamp/sensor rows where the requested measurement is valid."""
        sensor_specs = [
            ('GPSWaves', 'waves', 'timeStamp', 'significant_wave_height_m', False),
            ('SPN1', 'airsea', 'Logger_DateTime', 'SPN1_Raw_Total_Avg', False),
            ('RBR CTD', 'airsea', 'Logger_DateTime', 'RBR_Temp_Avg', False),
            ('Vaisala', 'airsea', 'Logger_DateTime', 'wind_speed_Max', False),
            ('Gill R3-50', 'airsea', 'Logger_DateTime', 'Ux_gill_Avg', False),
            ('Airmar WS200', 'weather', 'timeStamp', 'wind_speed_kt', False),
        ]
        if include_pco2:
            sensor_specs.append(
                ('pCO2', 'vegas', 'sensor_time', 'Ocean CO2 Ave', True)
            )

        availability = []
        for sensor, source, time_column, value_column, dayfirst in sensor_specs:
            dataframe = sensor_data[source]
            values = pd.to_numeric(dataframe[value_column], errors='coerce')
            valid_values = values.notna()
            timestamps = pd.to_datetime(
                dataframe.loc[valid_values, time_column],
                errors='coerce',
                dayfirst=dayfirst,
            )
            valid_rows = pd.DataFrame({
                'timestamp': timestamps,
                'value': values.loc[valid_values],
            }).dropna(subset=['timestamp'])
            valid_rows['sensor'] = sensor
            availability.append(
                valid_rows[['timestamp', 'sensor', 'value']]
            )

        return pd.concat(availability, ignore_index=True).sort_values('timestamp')
    
    
    def build_power_figure(sensor_pwr_out, solar_pwr_in, total_pwr_out, battery_pwr, sensor_availability, glider_label, threshold_w=0.2):
        """Build the 4-subplot interactive power analysis figure with day slider."""
        plot_df = sensor_pwr_out.copy()
        plot_df['sampleHour'] = pd.to_datetime(plot_df['sampleHour'])
        plot_df = plot_df[plot_df['avg_power_W'] > threshold_w].copy()

        plot_df['component'] = plot_df['sensor'].fillna('').astype(str).str.strip()
        empty_component = plot_df['component'].eq('')
        plot_df.loc[empty_component, 'component'] = (
            'D' + plot_df.loc[empty_component, 'domain'].astype(str)
            + '-S' + plot_df.loc[empty_component, 'slot'].astype(str)
            + '-P' + plot_df.loc[empty_component, 'port'].astype(str)
        )

        stacked = (
            plot_df.pivot_table(
                index='sampleHour',
                columns='component',
                values='avg_power_W',
                aggfunc='sum',
                fill_value=0,
            )
            .sort_index()
        )

        solar_line = solar_pwr_in.copy()
        solar_line['sampleHour'] = pd.to_datetime(solar_line['timeStamp']).dt.floor('h')
        solar_line = (
            solar_line.groupby('sampleHour', as_index=False)['solar_power_W']
            .mean()
            .rename(columns={'solar_power_W': 'solar_gain_W'})
        )

        usage_line = total_pwr_out.copy()
        usage_line['sampleHour'] = pd.to_datetime(usage_line['timestamp']).dt.floor('h')
        usage_line = (
            usage_line.groupby('sampleHour', as_index=False)['total_output_power_W']
            .mean()
            .rename(columns={'total_output_power_W': 'total_usage_W'})
        )

        battery_series = battery_pwr.copy()
        battery_series['timestamp'] = pd.to_datetime(battery_series['timestamp'])
        battery_series = battery_series.sort_values('timestamp')
        battery_series['day'] = battery_series['timestamp'].dt.normalize()

        battery_line = battery_series.copy()
        battery_line['sampleHour'] = battery_line['timestamp'].dt.floor('h')
        battery_line = (
            battery_line.groupby('sampleHour', as_index=False)['total_battery_power_W']
            .mean()
        )

        line_df = (
            stacked.reset_index()[['sampleHour']]
            .merge(usage_line, on='sampleHour', how='left')
            .merge(solar_line, on='sampleHour', how='left')
            .merge(battery_line, on='sampleHour', how='left')
        )

        bar_colors = [PALETTE[i % len(PALETTE)] for i in range(stacked.shape[1])]
        available_days = sorted(stacked.index.normalize().unique())
        today = pd.Timestamp.today().normalize()
        default_day = today if today in available_days else available_days[-1]

        fig = make_subplots(
            rows=4,
            cols=1,
            shared_xaxes=False,
            vertical_spacing=0.07,
            row_heights=[0.39, 0.18, 0.23, 0.2],
            subplot_titles=(
                'Power Sources and Flows',
                'Total Battery Power',
                'Full Mission Battery Power (selected day shaded)',
                'Sensor Data Availability',
            ),
        )

        fig.add_trace(
            go.Scatter(
                x=battery_series['timestamp'],
                y=battery_series['total_battery_power_W'],
                mode='lines',
                name='Mission battery power (W)',
                line=dict(color='#5B8E7D', width=1.8),
                visible=True,
                hovertemplate='%{x|%Y-%m-%d %H:%M}<br>Mission battery: %{y:.2f} W<extra></extra>',
            ),
            row=3,
            col=1,
        )
        mission_trace_idx = len(fig.data) - 1

        fig.add_trace(
            go.Scatter(
                x=sensor_availability['timestamp'],
                y=sensor_availability['sensor'],
                customdata=sensor_availability['value'],
                mode='markers',
                name='Sensor data available',
                marker=dict(color='#009E73', symbol='square', size=6),
                visible=True,
                hovertemplate=(
                    '%{x|%Y-%m-%d %H:%M}<br>'
                    '%{y}: data available<br>'
                    'Value: %{customdata:.3f}<extra></extra>'
                ),
            ),
            row=4,
            col=1,
        )
        availability_trace_idx = len(fig.data) - 1

        day_meta = {}

        for day in available_days:
            day_mask = stacked.index.normalize() == day
            day_stacked = stacked.loc[day_mask]
            day_lines = line_df[line_df['sampleHour'].dt.normalize() == day]

            daily_total_used_wh = day_lines['total_usage_W'].fillna(0).sum()
            daily_total_gained_wh = day_lines['solar_gain_W'].fillna(0).sum()

            day_battery = battery_series[battery_series['day'] == day]
            if day_battery.empty:
                battery_start = 0.0
                battery_end = 0.0
                daily_battery_gain_loss = 0.0
            else:
                battery_start = float(day_battery['total_battery_power_W'].iloc[0])
                battery_end = float(day_battery['total_battery_power_W'].iloc[-1])
                daily_battery_gain_loss = battery_end - battery_start

            battery_subplot_title = (
                f'Total Battery Power | Start: {battery_start:.1f} W | '
                f'End: {battery_end:.1f} W | Daily gain/loss: {daily_battery_gain_loss:+.1f} W'
            )

            day_start = pd.Timestamp(day)
            day_end = day_start + pd.Timedelta(days=1)

            day_label = day_start.strftime('%Y-%m-%d')
            trace_indices = []

            for i, component in enumerate(stacked.columns):
                fig.add_trace(
                    go.Bar(
                        x=day_stacked.index,
                        y=day_stacked[component],
                        name=str(component),
                        marker_color=bar_colors[i],
                        visible=(day == default_day),
                        hovertemplate='%{x|%-d/%m %H:%M}<br>' + str(component) + ': %{y:.2f} W<extra></extra>',
                    ),
                    row=1,
                    col=1,
                )
                trace_indices.append(len(fig.data) - 1)

            fig.add_trace(
                go.Scatter(
                    x=day_lines['sampleHour'],
                    y=day_lines['total_usage_W'],
                    mode='lines+markers',
                    name='Total power usage (W)',
                    line=dict(color='#3A506B', width=2.2),
                    marker=dict(size=6),
                    visible=(day == default_day),
                    hovertemplate='%{x|%-d/%m %H:%M}<br>Total usage: %{y:.2f} W<extra></extra>',
                ),
                row=1,
                col=1,
            )
            trace_indices.append(len(fig.data) - 1)

            fig.add_trace(
                go.Scatter(
                    x=day_lines['sampleHour'],
                    y=day_lines['solar_gain_W'],
                    mode='lines+markers',
                    name='Solar power gain (W)',
                    line=dict(color='#E09F3E', width=2.2),
                    marker=dict(size=6),
                    visible=(day == default_day),
                    hovertemplate='%{x|%-d/%m %H:%M}<br>Solar gain: %{y:.2f} W<extra></extra>',
                ),
                row=1,
                col=1,
            )
            trace_indices.append(len(fig.data) - 1)

            fig.add_trace(
                go.Scatter(
                    x=day_lines['sampleHour'],
                    y=day_lines['total_battery_power_W'],
                    mode='lines+markers',
                    name='Total battery power (W)',
                    line=dict(color='#6C5CE7', width=2.2),
                    marker=dict(size=6),
                    visible=(day == default_day),
                    hovertemplate='%{x|%-d/%m %H:%M}<br>Battery power: %{y:.2f} W<extra></extra>',
                ),
                row=2,
                col=1,
            )
            trace_indices.append(len(fig.data) - 1)

            day_meta[day_label] = {
                'trace_indices': trace_indices,
                'title': (
                    f'{glider_label}: Average Power Usage (Watts) with Total Usage and Solar Gain<br>'
                    f'Date: {day_label} | Daily gained: {daily_total_gained_wh:.1f} Wh | Daily used: {daily_total_used_wh:.1f} Wh'
                ),
                'battery_subplot_title': battery_subplot_title,
                'day_start': day_start,
                'day_end': day_end,
            }

        fig.add_vrect(
            x0=default_day,
            x1=default_day + pd.Timedelta(days=1),
            fillcolor='#6C757D',
            opacity=0.18,
            line_width=0,
            row=3,
            col=1,
        )
        fig.add_vrect(
            x0=default_day,
            x1=default_day + pd.Timedelta(days=1),
            fillcolor='#6C757D',
            opacity=0.18,
            line_width=0,
            row=4,
            col=1,
        )

        slider_steps = []
        day_labels = [pd.Timestamp(day).strftime('%Y-%m-%d') for day in available_days]
        default_day_label = pd.Timestamp(default_day).strftime('%Y-%m-%d')
        default_idx = day_labels.index(default_day_label)

        for day_label in day_labels:
            meta = day_meta[day_label]
            visible = [False] * len(fig.data)
            visible[mission_trace_idx] = True
            visible[availability_trace_idx] = True
            for idx in meta['trace_indices']:
                visible[idx] = True

            slider_steps.append(
                dict(
                    label=day_label,
                    method='update',
                    args=[
                        {'visible': visible},
                        {
                            'title': meta['title'],
                            'annotations[1].text': meta['battery_subplot_title'],
                            'shapes[0].x0': meta['day_start'],
                            'shapes[0].x1': meta['day_end'],
                            'shapes[1].x0': meta['day_start'],
                            'shapes[1].x1': meta['day_end'],
                        },
                    ],
                )
            )

        fig.update_layout(
            barmode='stack',
            title=day_meta[default_day_label]['title'],
            xaxis_title='',
            yaxis_title='Power output (W)',
            legend_title='Series',
            hovermode='x unified',
            template='plotly_white',
            height=1380,
            margin=dict(l=60, r=130, t=130, b=190),
            sliders=[
                dict(
                    active=default_idx,
                    x=0.11,
                    y=-0.16,
                    len=0.75,
                    currentvalue=dict(prefix='Date: ', visible=True),
                    pad=dict(t=8, b=0),
                    steps=slider_steps,
                )
            ],
        )

        fig.layout.annotations[1].text = day_meta[default_day_label]['battery_subplot_title']

        top_middle_time_format = '%H:%M'
        fig.update_xaxes(tickformat=top_middle_time_format, tickangle=0, showticklabels=True, automargin=True, row=1, col=1)
        fig.update_xaxes(matches='x', row=2, col=1)
        fig.update_xaxes(tickformat=top_middle_time_format, tickangle=0, showticklabels=True, automargin=True, row=2, col=1)
        fig.update_xaxes(showticklabels=False, row=3, col=1)
        fig.update_xaxes(matches='x3', tickformat='%Y-%m-%d', tickangle=45, title_text='Time (UTC)', row=4, col=1)

        fig.update_yaxes(title_text='Power output (W)', row=1, col=1)
        fig.update_yaxes(title_text='Battery power (W)', row=2, col=1)
        fig.update_yaxes(title_text='Battery power (W)', row=3, col=1)
        sensor_order = ['GPSWaves', 'SPN1', 'RBR CTD', 'Vaisala', 'Gill R3-50', 'Airmar WS200']
        if 'pCO2' in sensor_availability['sensor'].values:
            sensor_order.append('pCO2')
        fig.update_yaxes(
            categoryorder='array',
            categoryarray=list(reversed(sensor_order)),
            row=4,
            col=1,
        )

        return fig

    
    def export_glider_figure(fig, glider_key: str):
        """Export figure to standalone and embedded HTML."""
        full_html = EXPORT_DIR / f'{glider_key}_power_interactive.html'
        embed_html = EXPORT_DIR / f'{glider_key}_power_interactive_embed.html'

        fig.write_html(full_html, full_html=True, include_plotlyjs='cdn')
        fig.write_html(embed_html, full_html=False, include_plotlyjs=False)

        print(f'Saved: {full_html}')
        print(f'Saved: {embed_html}')
        return full_html, embed_html

    
    # ========== Main Pipeline ==========
    
    print("Loading and processing data...")
    
    figures = {}
    export_paths = {}

    if ANALYSIS_TARGET == 'both':
        selected_glider_keys = list(GLIDERS.keys())
    elif ANALYSIS_TARGET in GLIDERS:
        selected_glider_keys = [ANALYSIS_TARGET]
    else:
        raise ValueError(
            "ANALYSIS_TARGET must be one of: 'both', 'wg1169', 'wg1170'"
        )

    for glider_key in selected_glider_keys:
        glider_label = GLIDERS[glider_key]
        print(f"\nProcessing {glider_label}...")
        sensor_pwr_out, solar_pwr_in, total_pwr_out, battery_pwr, sensor_data = load_glider_data(glider_key)
        sensor_availability = build_sensor_availability(
            sensor_data,
            include_pco2=(glider_key == 'wg1170'),
        )
        fig = build_power_figure(
            sensor_pwr_out,
            solar_pwr_in,
            total_pwr_out,
            battery_pwr,
            sensor_availability,
            glider_label,
        )
        
        full_html, embed_html = export_glider_figure(fig, glider_key)
        figures[glider_key] = fig
        export_paths[glider_key] = {
            'full': full_html,
            'embed': embed_html,
        }

    # ========== Build Combined Dashboard ==========
    
    print("\nBuilding combined dashboard...")
    
    combined_out = EXPORT_DIR / 'wg_power_dashboard.html'

    panel_sections = []
    for glider_key, paths in export_paths.items():
        embed_html = paths['embed'].read_text(encoding='utf-8')
        glider_label = GLIDERS.get(glider_key, glider_key.upper())
        panel_sections.append(
            f"""
    <section class="panel">
      <h2>{glider_label}</h2>
      {embed_html}
    </section>
            """.strip()
        )

    panels_html = "\n\n".join(panel_sections)
    selected_labels = ", ".join([GLIDERS[k] for k in export_paths.keys()])

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
    .return-btn {{
      display: inline-block;
      margin: -8px 0 20px 0;
      padding: 8px 14px;
      border-radius: 8px;
      border: 1px solid #334155;
      background: #ffffff;
      color: #1e293b;
      text-decoration: none;
      font-size: 0.92rem;
      font-weight: 600;
      cursor: pointer;
    }}
    .return-btn:hover {{
      background: #f1f5f9;
    }}
        .creator-credit {{
            margin: 20px 0 4px;
            color: #64748b;
            font-size: 0.82rem;
            text-align: center;
        }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Wave Glider Power Dashboard</h1>
    <p>Interactive daily power summaries for Polar Gliders' Wave Gliders: {selected_labels}.</p>
    <p>Times are in Coordinated Universal Time (UTC). Last updated: {LAST_UPDATED}</p>
    <a id="returnToPgObs" class="return-btn" href="{PG_OBS_FALLBACK_URL}">Return To PG Obs Page</a>

    {panels_html}
        <footer class="creator-credit">Created by Marcel du Plessis and Johan Edholm</footer>
  </div>

  <script>
    (function () {{
      var fallbackUrl = {PG_OBS_FALLBACK_URL!r};
      var btn = document.getElementById('returnToPgObs');
      if (!btn) return;

      btn.addEventListener('click', function (event) {{
        event.preventDefault();
        if (window.history.length > 1) {{
          window.history.back();
        }} else {{
          window.location.href = fallbackUrl;
        }}
      }});
    }})();
  </script>
</body>
</html>
"""

    combined_out.write_text(combined_html, encoding='utf-8')
    print(f'Saved: {combined_out}')

    print('Combined dashboard generation complete.')
    print(f'Export directory: {EXPORT_DIR}')


if __name__ == '__main__':
    main()
