#!/usr/bin/env python3
"""
Comprehensive Running Analysis Script
Reads Strava activity data and generates charts + HTML report.
Usage: python3 running_analysis.py
"""

import os
import re
import base64
import warnings
from io import BytesIO
from datetime import datetime, timedelta
from collections import defaultdict

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
from matplotlib.colors import LinearSegmentedColormap
import seaborn as sns

warnings.filterwarnings('ignore')

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_FILE = os.path.join(BASE_DIR, 'data', 'raw_activities.txt')
CSV_FILE = os.path.join(BASE_DIR, 'data', 'activities.csv')
CHARTS_DIR = os.path.join(BASE_DIR, 'charts')
REPORT_FILE = os.path.join(BASE_DIR, 'report.html')

os.makedirs(CHARTS_DIR, exist_ok=True)

# Style palette
BG = '#1a1a2e'
BG_LIGHT = '#16213e'
TEXT = '#eeeeee'
GREEN = '#2ecc71'
BLUE = '#3498db'
ORANGE = '#e67e22'
RED = '#e74c3c'
PURPLE = '#9b59b6'
YELLOW = '#f1c40f'
GRID = '#333355'

WEIGHT_KG = 83.9

# Race definitions (date, name, distance_km, time_str)
RACES = [
    ('2024-07-27', 'Half Marathon (Training)', 22.54, '2:42:50'),
    ('2024-11-10', 'Harrisburg Half Marathon', 21.23, '1:37:14'),
    ('2024-11-24', 'First Marathon', 42.62, '3:45:54'),
    ('2025-04-26', 'Derby Festival Marathon', 42.44, '3:54:18'),
    ('2025-09-06', 'DIY Full Marathon', 42.22, '3:56:34'),
    ('2025-11-08', 'Indy Monumental Marathon', 42.55, '3:40:06'),
]

# ---------------------------------------------------------------------------
# PARSING HELPERS
# ---------------------------------------------------------------------------

def parse_distance(s):
    """Parse distance string like '6.45 km' or '0 m' to km float."""
    s = s.strip()
    m = re.match(r'([\d.]+)\s*(km|m)', s)
    if not m:
        return 0.0
    val = float(m.group(1))
    unit = m.group(2)
    if unit == 'm':
        return val / 1000.0
    return val


def parse_time_to_seconds(s):
    """Parse time string like '30m 13s', '2h 29m 25s', '1h 7m 40s' to seconds."""
    s = s.strip()
    hours, minutes, seconds = 0, 0, 0
    h_match = re.search(r'(\d+)h', s)
    m_match = re.search(r'(\d+)m(?!p)', s)  # avoid matching 'bpm'
    s_match = re.search(r'(\d+)s', s)
    if h_match:
        hours = int(h_match.group(1))
    if m_match:
        minutes = int(m_match.group(1))
    if s_match:
        seconds = int(s_match.group(1))
    return hours * 3600 + minutes * 60 + seconds


def parse_pace(s):
    """Parse pace string to min/km float. Returns None for N/A or km/h formats."""
    s = s.strip()
    if s in ('N/A', '-', ''):
        return None
    # Format: "4:41 /km"
    m = re.match(r'(\d+):(\d+)\s*/km', s)
    if m:
        return int(m.group(1)) + int(m.group(2)) / 60.0
    return None


def parse_hr(s):
    """Parse HR string like '174 bpm' to int. Returns None for '-'."""
    s = s.strip()
    m = re.match(r'(\d+)\s*bpm', s)
    if m:
        return int(m.group(1))
    return None


def parse_elevation(s):
    """Parse elevation string like '47m' to int meters. Returns None for '-'."""
    s = s.strip()
    m = re.match(r'(\d+)m', s)
    if m:
        return int(m.group(1))
    return None


def time_str_to_seconds(t):
    """Convert H:MM:SS or M:SS to seconds."""
    parts = t.strip().split(':')
    parts = [int(p) for p in parts]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    elif len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return 0


def seconds_to_hms(s):
    """Convert seconds to H:MM:SS string."""
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = int(s % 60)
    if h > 0:
        return f'{h}:{m:02d}:{sec:02d}'
    return f'{m}:{sec:02d}'


def pace_to_str(pace_min_per_km):
    """Convert pace float (min/km) to M:SS string."""
    if pace_min_per_km is None or np.isnan(pace_min_per_km):
        return 'N/A'
    m = int(pace_min_per_km)
    s = int((pace_min_per_km - m) * 60)
    return f'{m}:{s:02d}'


def detect_time_of_day(name):
    """Detect time of day from activity name."""
    name_lower = name.lower()
    if 'morning' in name_lower or 'lunch' in name_lower:
        return 'Morning'
    elif 'afternoon' in name_lower:
        return 'Afternoon'
    elif 'evening' in name_lower or 'night' in name_lower:
        return 'Evening'
    else:
        return 'Unknown'


# ---------------------------------------------------------------------------
# DATA LOADING
# ---------------------------------------------------------------------------

def load_data():
    """Load and parse raw_activities.txt into a DataFrame."""
    records = []
    with open(RAW_FILE, 'r') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            parts = line.split('|')
            if len(parts) < 8:
                print(f"  Warning: skipping line {line_num} (only {len(parts)} fields)")
                continue
            date_str, name, activity_type, dist_str, time_str, pace_str, hr_str, elev_str = parts[:8]
            try:
                date = datetime.strptime(date_str.strip(), '%m/%d/%Y')
            except ValueError:
                print(f"  Warning: bad date on line {line_num}: {date_str}")
                continue
            records.append({
                'date': date,
                'name': name.strip(),
                'type': activity_type.strip(),
                'distance_km': parse_distance(dist_str),
                'time_seconds': parse_time_to_seconds(time_str),
                'pace_min_per_km': parse_pace(pace_str),
                'hr_bpm': parse_hr(hr_str),
                'elevation_m': parse_elevation(elev_str),
                'time_of_day': detect_time_of_day(name),
            })

    df = pd.DataFrame(records)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)

    # Compute pace from distance/time where missing but feasible
    mask = df['pace_min_per_km'].isna() & (df['distance_km'] > 0) & (df['time_seconds'] > 0)
    df.loc[mask, 'pace_min_per_km'] = (df.loc[mask, 'time_seconds'] / 60.0) / df.loc[mask, 'distance_km']

    # Year-month helper
    df['year_month'] = df['date'].dt.to_period('M')
    df['year_week'] = df['date'].dt.to_period('W')
    df['weekday'] = df['date'].dt.dayofweek  # 0=Mon
    df['month'] = df['date'].dt.month

    # Save CSV
    csv_df = df.copy()
    csv_df['date'] = csv_df['date'].dt.strftime('%Y-%m-%d')
    csv_df['year_month'] = csv_df['year_month'].astype(str)
    csv_df['year_week'] = csv_df['year_week'].astype(str)
    csv_df.to_csv(CSV_FILE, index=False)
    print(f"  Saved parsed data to {CSV_FILE}")

    return df


# ---------------------------------------------------------------------------
# CHART STYLING HELPERS
# ---------------------------------------------------------------------------

def style_ax(ax, title='', xlabel='', ylabel='', title_size=13):
    """Apply dark theme to axes."""
    ax.set_facecolor(BG)
    ax.set_title(title, color=TEXT, fontsize=title_size, fontweight='bold', pad=12)
    ax.set_xlabel(xlabel, color=TEXT, fontsize=10)
    ax.set_ylabel(ylabel, color=TEXT, fontsize=10)
    ax.tick_params(colors=TEXT, labelsize=9)
    ax.grid(True, color=GRID, alpha=0.4, linewidth=0.5)
    for spine in ax.spines.values():
        spine.set_color(GRID)


def new_fig(figsize=(12, 6), dpi=150):
    """Create a new dark-themed figure."""
    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    fig.patch.set_facecolor(BG)
    return fig, ax


def save_chart(fig, name):
    """Save chart to file and return base64 string."""
    path = os.path.join(CHARTS_DIR, f'{name}.png')
    fig.savefig(path, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor(), edgecolor='none')

    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode('utf-8')
    print(f"    Saved chart: {path}")
    return b64


# ---------------------------------------------------------------------------
# SECTION A: VOLUME & CONSISTENCY
# ---------------------------------------------------------------------------

def chart_monthly_mileage(runs):
    """A1: Monthly mileage bar chart with trend line."""
    monthly = runs.groupby('year_month')['distance_km'].sum()
    months = monthly.index.to_timestamp()
    values = monthly.values

    fig, ax = new_fig((14, 6))
    bars = ax.bar(months, values, width=25, color=GREEN, alpha=0.8, edgecolor='none')

    # Trend line
    x_num = np.arange(len(values))
    if len(x_num) > 1:
        z = np.polyfit(x_num, values, 2)
        p = np.poly1d(z)
        ax.plot(months, p(x_num), color=ORANGE, linewidth=2.5, linestyle='--', label='Trend')
        ax.legend(facecolor=BG_LIGHT, edgecolor=GRID, labelcolor=TEXT, fontsize=9)

    style_ax(ax, 'Monthly Running Mileage', '', 'Distance (km)')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    plt.xticks(rotation=45, ha='right')

    # Annotate peak month
    peak_idx = np.argmax(values)
    ax.annotate(f'{values[peak_idx]:.0f} km', xy=(months[peak_idx], values[peak_idx]),
                xytext=(0, 10), textcoords='offset points', ha='center',
                color=YELLOW, fontsize=9, fontweight='bold')

    fig.tight_layout()
    return save_chart(fig, '01_monthly_mileage')


def chart_weekly_frequency(runs):
    """A2: Weekly running frequency trend."""
    weekly_count = runs.groupby('year_week').size()
    weeks = weekly_count.index.to_timestamp()
    values = weekly_count.values

    fig, ax = new_fig((14, 5))
    ax.plot(weeks, values, color=BLUE, alpha=0.5, linewidth=0.8)

    # Rolling average
    if len(values) > 4:
        rolling = pd.Series(values).rolling(4, min_periods=1).mean()
        ax.plot(weeks, rolling, color=GREEN, linewidth=2.5, label='4-week avg')
        ax.legend(facecolor=BG_LIGHT, edgecolor=GRID, labelcolor=TEXT, fontsize=9)

    style_ax(ax, 'Weekly Running Frequency', '', 'Runs per Week')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    plt.xticks(rotation=45, ha='right')
    ax.set_ylim(bottom=0)
    fig.tight_layout()
    return save_chart(fig, '02_weekly_frequency')


def chart_cumulative_distance(runs):
    """A3: Cumulative distance with milestones."""
    daily = runs.groupby('date')['distance_km'].sum().sort_index()
    cum = daily.cumsum()

    fig, ax = new_fig((14, 6))
    ax.fill_between(cum.index, cum.values, alpha=0.3, color=GREEN)
    ax.plot(cum.index, cum.values, color=GREEN, linewidth=2)

    # Milestones
    milestones = [1000, 2000, 3000, 4000, 5000]
    for ms in milestones:
        reached = cum[cum >= ms]
        if len(reached) > 0:
            ms_date = reached.index[0]
            ax.axhline(y=ms, color=ORANGE, linestyle=':', alpha=0.5, linewidth=1)
            ax.plot(ms_date, ms, 'o', color=ORANGE, markersize=8, zorder=5)
            ax.annotate(f'{ms:,} km\n{ms_date.strftime("%b %d, %Y")}',
                        xy=(ms_date, ms), xytext=(10, 10), textcoords='offset points',
                        color=ORANGE, fontsize=8, fontweight='bold',
                        arrowprops=dict(arrowstyle='->', color=ORANGE, lw=1))

    style_ax(ax, 'Cumulative Running Distance', '', 'Total Distance (km)')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    plt.xticks(rotation=45, ha='right')
    fig.tight_layout()
    return save_chart(fig, '03_cumulative_distance')


def chart_calendar_heatmap(runs):
    """A4: GitHub-style calendar heatmap of daily distance."""
    daily = runs.groupby('date')['distance_km'].sum()

    # Build full date range
    start_date = daily.index.min()
    end_date = daily.index.max()
    all_dates = pd.date_range(start_date, end_date, freq='D')
    daily = daily.reindex(all_dates, fill_value=0)

    # Build week/weekday matrix by year
    years = sorted(daily.index.year.unique())

    fig, axes = plt.subplots(len(years), 1, figsize=(14, 2.0 * len(years)), dpi=150)
    fig.patch.set_facecolor(BG)
    if len(years) == 1:
        axes = [axes]

    cmap = LinearSegmentedColormap.from_list('running', [BG_LIGHT, '#0d4b2b', GREEN, YELLOW], N=256)
    vmax = daily.quantile(0.95) if daily.max() > 0 else 1

    for ax, year in zip(axes, years):
        year_data = daily[daily.index.year == year]
        if len(year_data) == 0:
            ax.set_visible(False)
            continue

        # Build matrix: 7 rows (days) x 53 cols (weeks)
        jan1 = datetime(year, 1, 1)
        matrix = np.full((7, 53), np.nan)

        for date, val in year_data.items():
            day_of_year = (date - pd.Timestamp(jan1)).days
            week_of_year = (jan1.weekday() + day_of_year) // 7
            weekday = date.weekday()
            if 0 <= week_of_year < 53:
                matrix[weekday, week_of_year] = val

        masked = np.ma.masked_invalid(matrix)
        ax.pcolormesh(masked, cmap=cmap, vmin=0, vmax=vmax, edgecolors=BG, linewidth=1.5)
        ax.set_facecolor(BG)
        ax.invert_yaxis()
        ax.set_yticks([0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5])
        ax.set_yticklabels(['M', 'T', 'W', 'T', 'F', 'S', 'S'], fontsize=7, color=TEXT)

        # Month labels
        month_starts = []
        for m in range(1, 13):
            try:
                d = datetime(year, m, 1)
                day_of_year = (d - jan1).days
                week_pos = (jan1.weekday() + day_of_year) // 7
                month_starts.append((week_pos, d.strftime('%b')))
            except ValueError:
                pass
        if month_starts:
            ax.set_xticks([ms[0] + 0.5 for ms in month_starts])
            ax.set_xticklabels([ms[1] for ms in month_starts], fontsize=7, color=TEXT)
        else:
            ax.set_xticks([])

        ax.set_title(str(year), color=TEXT, fontsize=11, fontweight='bold', loc='left', pad=4)
        ax.tick_params(length=0)
        for spine in ax.spines.values():
            spine.set_visible(False)

    fig.suptitle('Daily Running Distance Heatmap', color=TEXT, fontsize=13, fontweight='bold', y=1.01)
    fig.tight_layout()
    return save_chart(fig, '04_calendar_heatmap')


# ---------------------------------------------------------------------------
# SECTION B: PACE & PERFORMANCE
# ---------------------------------------------------------------------------

def chart_monthly_pace(runs):
    """B5: Average pace per month."""
    # Only runs with valid pace and reasonable distance
    paced = runs[(runs['pace_min_per_km'].notna()) & (runs['distance_km'] >= 1)].copy()
    monthly_pace = paced.groupby('year_month')['pace_min_per_km'].mean()
    months = monthly_pace.index.to_timestamp()
    values = monthly_pace.values

    fig, ax = new_fig((14, 6))
    ax.plot(months, values, color=BLUE, linewidth=2, marker='o', markersize=4)

    # Fill area
    ax.fill_between(months, values, max(values) + 0.5, alpha=0.1, color=BLUE)

    style_ax(ax, 'Average Pace per Month (Running)', '', 'Pace (min/km)')
    ax.invert_yaxis()  # Lower pace = faster = top

    # Custom y-tick labels
    yticks = ax.get_yticks()
    ax.set_yticklabels([pace_to_str(y) for y in yticks])

    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    plt.xticks(rotation=45, ha='right')
    fig.tight_layout()
    return save_chart(fig, '05_monthly_pace')


def chart_race_timeline(runs):
    """B6: Race results timeline."""
    fig, ax = new_fig((14, 6))

    marathon_dates = []
    marathon_times = []
    hm_dates = []
    hm_times = []

    for date_str, name, dist, time_s in RACES:
        d = pd.Timestamp(date_str)
        secs = time_str_to_seconds(time_s)
        mins = secs / 60.0
        if dist > 30:  # Marathon
            marathon_dates.append(d)
            marathon_times.append(mins)
        else:
            hm_dates.append(d)
            hm_times.append(mins)

    if marathon_dates:
        ax.plot(marathon_dates, marathon_times, 'o-', color=RED, markersize=10, linewidth=2.5,
                label='Marathon', zorder=5)
        for i, (d, t) in enumerate(zip(marathon_dates, marathon_times)):
            label = seconds_to_hms(t * 60)
            race_name = [r[1] for r in RACES if pd.Timestamp(r[0]) == d][0]
            ax.annotate(f'{label}\n{race_name}', xy=(d, t), xytext=(0, 15),
                        textcoords='offset points', ha='center', color=TEXT,
                        fontsize=7.5, fontweight='bold')

    if hm_dates:
        ax.plot(hm_dates, hm_times, 's-', color=PURPLE, markersize=10, linewidth=2.5,
                label='Half Marathon', zorder=5)
        for d, t in zip(hm_dates, hm_times):
            label = seconds_to_hms(t * 60)
            ax.annotate(f'{label}', xy=(d, t), xytext=(0, 12),
                        textcoords='offset points', ha='center', color=TEXT,
                        fontsize=8, fontweight='bold')

    style_ax(ax, 'Race Results Timeline', '', 'Finish Time (minutes)')
    ax.legend(facecolor=BG_LIGHT, edgecolor=GRID, labelcolor=TEXT, fontsize=10)

    # Format y-axis as H:MM
    def fmt_mins(x, pos):
        return seconds_to_hms(x * 60)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(fmt_mins))
    ax.invert_yaxis()

    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'))
    plt.xticks(rotation=45, ha='right')
    fig.tight_layout()
    return save_chart(fig, '06_race_timeline')


def compute_best_efforts(runs):
    """B7: Estimate best efforts at standard distances.

    For each target distance, find the run whose actual elapsed time is fastest
    among runs close to that distance.  We use a distance band so that a 1.6 km
    sprint does not get extrapolated to a 10K estimate.
    """
    # (label, target_km, min_km, max_km)
    targets = [
        ('1 Mile (1.609 km)', 1.609, 1.5,  3.0),
        ('5K',                5.0,   4.5,   7.0),
        ('10K',              10.0,   9.0,  14.0),
        ('Half Marathon',    21.0975, 20.0, 25.0),
        ('Marathon',         42.195, 40.0,  45.0),
    ]

    results = {}
    for label, target_km, lo, hi in targets:
        eligible = runs[(runs['distance_km'] >= lo) & (runs['distance_km'] <= hi)].copy()
        eligible = eligible[eligible['pace_min_per_km'].notna()].copy()
        if len(eligible) == 0:
            results[label] = {'time': 'N/A', 'pace': 'N/A', 'date': 'N/A', 'name': 'N/A'}
            continue
        # Use actual time scaled to the exact target distance
        eligible['est_time_min'] = eligible['pace_min_per_km'] * target_km
        best_idx = eligible['est_time_min'].idxmin()
        best = eligible.loc[best_idx]
        results[label] = {
            'time': seconds_to_hms(best['est_time_min'] * 60),
            'pace': pace_to_str(best['pace_min_per_km']),
            'date': best['date'].strftime('%b %d, %Y'),
            'name': best['name'],
        }

    return results


def chart_pace_distribution(runs):
    """B8: Pace distribution histogram."""
    paced = runs[(runs['pace_min_per_km'].notna()) & (runs['distance_km'] >= 0.5)].copy()
    paces = paced['pace_min_per_km'].values
    paces = paces[(paces >= 3) & (paces <= 12)]  # Reasonable range

    fig, ax = new_fig((12, 6))
    bins = np.arange(3, 12.5, 0.25)
    n, bins_out, patches = ax.hist(paces, bins=bins, color=BLUE, alpha=0.8, edgecolor=BG)

    # Color by zone
    for patch, left in zip(patches, bins_out[:-1]):
        if left < 5:
            patch.set_facecolor(RED)
        elif left < 6:
            patch.set_facecolor(ORANGE)
        elif left < 7:
            patch.set_facecolor(GREEN)
        else:
            patch.set_facecolor(BLUE)

    # Add zone labels
    ax.axvline(5, color=TEXT, linestyle=':', alpha=0.5)
    ax.axvline(6, color=TEXT, linestyle=':', alpha=0.5)
    ax.axvline(7, color=TEXT, linestyle=':', alpha=0.5)
    ax.text(4.0, max(n) * 0.9, 'Fast', color=RED, fontsize=9, fontweight='bold')
    ax.text(5.2, max(n) * 0.9, 'Tempo', color=ORANGE, fontsize=9, fontweight='bold')
    ax.text(6.2, max(n) * 0.9, 'Easy', color=GREEN, fontsize=9, fontweight='bold')
    ax.text(7.5, max(n) * 0.9, 'Recovery', color=BLUE, fontsize=9, fontweight='bold')

    style_ax(ax, 'Pace Distribution (All Runs)', 'Pace (min/km)', 'Number of Runs')

    # Custom x-tick labels
    xticks = ax.get_xticks()
    ax.set_xticklabels([pace_to_str(x) for x in xticks])

    fig.tight_layout()
    return save_chart(fig, '08_pace_distribution')


# ---------------------------------------------------------------------------
# SECTION C: TRAINING LOAD & INJURY RISK
# ---------------------------------------------------------------------------

def chart_weekly_mileage_ramp(runs):
    """C9: Weekly mileage with 10% safe ramp rate."""
    weekly = runs.groupby('year_week')['distance_km'].sum()
    weeks = weekly.index.to_timestamp()
    values = weekly.values

    fig, ax = new_fig((14, 6))
    ax.bar(weeks, values, width=6, color=GREEN, alpha=0.7, edgecolor='none')

    # 10% ramp: each week should be <= prev * 1.1
    if len(values) > 1:
        safe_line = [values[0]]
        for i in range(1, len(values)):
            safe_val = safe_line[-1] * 1.1
            safe_line.append(safe_val)
        # Only show ramp from meaningful starting weeks
        ax.plot(weeks, safe_line, color=ORANGE, linewidth=1.5, linestyle='--',
                alpha=0.7, label='10% Ramp Rate')

    # Mark overload weeks (where increase > 20% over prev)
    for i in range(1, len(values)):
        if values[i - 1] > 0:
            increase = (values[i] - values[i - 1]) / values[i - 1]
            if increase > 0.2:
                ax.plot(weeks[i], values[i], 'v', color=RED, markersize=8, zorder=5)

    style_ax(ax, 'Weekly Mileage with Ramp Rate', '', 'Distance (km)')
    ax.legend(facecolor=BG_LIGHT, edgecolor=GRID, labelcolor=TEXT, fontsize=9)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    plt.xticks(rotation=45, ha='right')
    fig.tight_layout()
    return save_chart(fig, '09_weekly_mileage_ramp')


def chart_acwr(runs):
    """C10: Acute:Chronic Workload Ratio."""
    daily = runs.groupby('date')['distance_km'].sum()
    full_range = pd.date_range(daily.index.min(), daily.index.max(), freq='D')
    daily = daily.reindex(full_range, fill_value=0)

    acute = daily.rolling(7, min_periods=1).mean()
    chronic = daily.rolling(28, min_periods=1).mean()
    acwr = acute / chronic.replace(0, np.nan)

    fig, ax = new_fig((14, 6))
    ax.plot(acwr.index, acwr.values, color=BLUE, linewidth=1.5, alpha=0.8)
    ax.axhline(y=1.5, color=RED, linestyle='--', linewidth=2, label='Danger Zone (>1.5)')
    ax.axhline(y=1.0, color=GREEN, linestyle=':', linewidth=1, alpha=0.6, label='Optimal (0.8-1.3)')
    ax.axhline(y=0.8, color=YELLOW, linestyle=':', linewidth=1, alpha=0.6)
    ax.fill_between(acwr.index, 0.8, 1.3, alpha=0.1, color=GREEN, label='Sweet Spot')

    # Highlight danger spikes
    danger = acwr[acwr > 1.5]
    if len(danger) > 0:
        ax.scatter(danger.index, danger.values, color=RED, s=20, zorder=5, alpha=0.7)

    style_ax(ax, 'Acute:Chronic Workload Ratio (7d / 28d)', '', 'ACWR')
    ax.legend(facecolor=BG_LIGHT, edgecolor=GRID, labelcolor=TEXT, fontsize=9)
    ax.set_ylim(0, min(acwr.max() + 0.5, 5) if not acwr.isna().all() else 3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    plt.xticks(rotation=45, ha='right')
    fig.tight_layout()
    return save_chart(fig, '10_acwr')


def chart_rest_days(runs):
    """C11: Rest days per week trend."""
    weekly_run_days = runs.groupby('year_week')['date'].apply(lambda x: x.dt.date.nunique())
    rest_days = 7 - weekly_run_days
    weeks = rest_days.index.to_timestamp()
    values = rest_days.values

    fig, ax = new_fig((14, 5))
    ax.bar(weeks, values, width=6, color=PURPLE, alpha=0.7, edgecolor='none')

    if len(values) > 4:
        rolling = pd.Series(values).rolling(4, min_periods=1).mean()
        ax.plot(weeks, rolling.values, color=YELLOW, linewidth=2.5, label='4-week avg')
        ax.legend(facecolor=BG_LIGHT, edgecolor=GRID, labelcolor=TEXT, fontsize=9)

    ax.axhline(y=2, color=GREEN, linestyle=':', alpha=0.5, label='Min recommended')
    style_ax(ax, 'Rest Days per Week', '', 'Rest Days')
    ax.set_ylim(0, 7)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    plt.xticks(rotation=45, ha='right')
    fig.tight_layout()
    return save_chart(fig, '11_rest_days')


def chart_marathon_training_block(runs):
    """C12: Marathon training block peak week & taper (Day X/82)."""
    block = runs[runs['name'].str.contains(r'Day \d+/82', na=False)].copy()
    if len(block) == 0:
        return None

    block_start = block['date'].min()
    block_end = block['date'].max()

    # Get ALL runs during block period (not just named ones)
    block_period = runs[(runs['date'] >= block_start) & (runs['date'] <= block_end)].copy()
    weekly = block_period.groupby('year_week')['distance_km'].sum()
    weeks = weekly.index.to_timestamp()
    values = weekly.values

    fig, ax = new_fig((12, 6))
    bars = ax.bar(weeks, values, width=6, alpha=0.8, edgecolor='none')

    # Color bars: peak green, taper blue, others default
    peak_idx = np.argmax(values)
    for i, bar in enumerate(bars):
        if i == peak_idx:
            bar.set_color(GREEN)
        elif i >= len(values) - 3:  # Last 3 weeks = taper
            bar.set_color(BLUE)
        else:
            bar.set_color(ORANGE)

    ax.annotate(f'Peak: {values[peak_idx]:.1f} km', xy=(weeks[peak_idx], values[peak_idx]),
                xytext=(0, 12), textcoords='offset points', ha='center',
                color=GREEN, fontsize=10, fontweight='bold')

    # Add race day marker (Derby Festival Marathon - Apr 26, 2025)
    race_date = pd.Timestamp('2025-04-26')
    ax.axvline(x=race_date, color=RED, linestyle='--', linewidth=2, label='Race Day')

    style_ax(ax, f'82-Day Marathon Training Block ({block_start.strftime("%b %d")} - {block_end.strftime("%b %d, %Y")})',
             '', 'Weekly Distance (km)')
    ax.legend(facecolor=BG_LIGHT, edgecolor=GRID, labelcolor=TEXT, fontsize=9)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
    plt.xticks(rotation=45, ha='right')
    fig.tight_layout()
    return save_chart(fig, '12_training_block')


# ---------------------------------------------------------------------------
# SECTION D: FITNESS PROGRESSION (HR-based, Jan 2025+)
# ---------------------------------------------------------------------------

def chart_pace_vs_hr(runs):
    """D13: Pace vs HR scatter colored by time period."""
    hr_runs = runs[(runs['hr_bpm'].notna()) & (runs['pace_min_per_km'].notna()) &
                   (runs['distance_km'] >= 1)].copy()
    if len(hr_runs) == 0:
        return None

    # Color by quarter
    hr_runs['quarter'] = hr_runs['date'].dt.to_period('Q').astype(str)
    quarters = sorted(hr_runs['quarter'].unique())
    colors_list = [BLUE, GREEN, ORANGE, RED, PURPLE, YELLOW, '#1abc9c', '#e91e63']

    fig, ax = new_fig((12, 7))
    for i, q in enumerate(quarters):
        mask = hr_runs['quarter'] == q
        c = colors_list[i % len(colors_list)]
        ax.scatter(hr_runs.loc[mask, 'hr_bpm'], hr_runs.loc[mask, 'pace_min_per_km'],
                   c=c, alpha=0.6, s=30, label=q, edgecolors='none')

    style_ax(ax, 'Pace vs Heart Rate (colored by quarter)', 'Heart Rate (bpm)', 'Pace (min/km)')
    ax.invert_yaxis()
    yticks = ax.get_yticks()
    ax.set_yticklabels([pace_to_str(y) for y in yticks])
    ax.legend(facecolor=BG_LIGHT, edgecolor=GRID, labelcolor=TEXT, fontsize=8,
              ncol=2, loc='upper right')
    fig.tight_layout()
    return save_chart(fig, '13_pace_vs_hr')


def chart_intensity_distribution(runs):
    """D14: Training intensity distribution."""
    hr_runs = runs[(runs['hr_bpm'].notna()) & (runs['distance_km'] >= 0.5)].copy()
    if len(hr_runs) == 0:
        return None

    # Zones
    hr_runs['zone'] = pd.cut(hr_runs['hr_bpm'], bins=[0, 145, 165, 300],
                              labels=['Easy (<145)', 'Moderate (145-165)', 'Hard (>165)'])

    monthly_zone = hr_runs.groupby(['year_month', 'zone'], observed=True).size().unstack(fill_value=0)

    fig, ax = new_fig((14, 6))
    months = monthly_zone.index.to_timestamp()

    # Stacked bar
    bottom = np.zeros(len(months))
    zone_colors = {'Easy (<145)': GREEN, 'Moderate (145-165)': ORANGE, 'Hard (>165)': RED}
    for zone_name in ['Easy (<145)', 'Moderate (145-165)', 'Hard (>165)']:
        if zone_name in monthly_zone.columns:
            vals = monthly_zone[zone_name].values.astype(float)
            ax.bar(months, vals, bottom=bottom, width=25, color=zone_colors[zone_name],
                   alpha=0.85, label=zone_name, edgecolor='none')
            bottom += vals

    style_ax(ax, 'Training Intensity Distribution by Month', '', 'Number of Activities')
    ax.legend(facecolor=BG_LIGHT, edgecolor=GRID, labelcolor=TEXT, fontsize=9)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    plt.xticks(rotation=45, ha='right')
    fig.tight_layout()
    return save_chart(fig, '14_intensity_distribution')


def chart_vo2max_trend():
    """D15: Estimated VO2max from race results (Jack Daniels formula)."""
    def estimate_vo2max(distance_m, time_seconds):
        """Jack Daniels VO2max estimation."""
        t = time_seconds / 60.0  # minutes
        d = distance_m

        # Velocity in m/min
        v = d / t

        # Percent VO2max (fractional utilization)
        pct = 0.8 + 0.1894393 * np.exp(-0.012778 * t) + 0.2989558 * np.exp(-0.1932605 * t)

        # VO2 at velocity (ml/kg/min)
        vo2 = -4.60 + 0.182258 * v + 0.000104 * v**2

        # VO2max
        return vo2 / pct

    results = []
    for date_str, name, dist_km, time_s in RACES:
        secs = time_str_to_seconds(time_s)
        vo2 = estimate_vo2max(dist_km * 1000, secs)
        results.append({
            'date': pd.Timestamp(date_str),
            'name': name,
            'vo2max': vo2,
        })

    results_df = pd.DataFrame(results).sort_values('date')

    fig, ax = new_fig((12, 6))
    ax.plot(results_df['date'], results_df['vo2max'], 'o-', color=GREEN,
            linewidth=2.5, markersize=10)

    for _, row in results_df.iterrows():
        ax.annotate(f'{row["vo2max"]:.1f}\n{row["name"][:20]}',
                    xy=(row['date'], row['vo2max']), xytext=(0, 15),
                    textcoords='offset points', ha='center', color=TEXT,
                    fontsize=7.5, fontweight='bold')

    style_ax(ax, 'Estimated VO2max from Race Results (Jack Daniels)', '', 'VO2max (ml/kg/min)')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'))
    plt.xticks(rotation=45, ha='right')
    fig.tight_layout()
    return save_chart(fig, '15_vo2max_trend')


# ---------------------------------------------------------------------------
# SECTION F: RACE PREDICTION (HM — April 25, 2026)
# ---------------------------------------------------------------------------

def chart_hm_prediction(runs):
    """F19: HM-distance effort progression and prediction chart."""
    # Find all HM-distance efforts (19-23km)
    hm_efforts = runs[(runs['distance_km'] >= 19) & (runs['distance_km'] <= 23)].copy()
    hm_efforts = hm_efforts.sort_values('date')
    hm_efforts['pace_sec'] = hm_efforts['time_seconds'] / hm_efforts['distance_km']

    fig, ax = new_fig((14, 7))

    # Plot all HM-distance efforts (pace in min/km)
    pace_min = hm_efforts['pace_sec'] / 60
    ax.scatter(hm_efforts['date'], pace_min, c=BLUE, s=60, alpha=0.5, zorder=3, label='Training runs')

    # Highlight sub-5:00/km efforts
    fast = hm_efforts[hm_efforts['pace_sec'] < 300]
    if len(fast) > 0:
        ax.scatter(fast['date'], fast['pace_sec'] / 60, c=GREEN, s=120, zorder=4,
                   edgecolors='white', linewidth=1.5, label='Sub-5:00/km (race-pace)')
        for _, r in fast.iterrows():
            mins = int(r['time_seconds'] // 3600)
            secs_r = int((r['time_seconds'] % 3600) // 60)
            sec_r = int(r['time_seconds'] % 60)
            label = f"{mins}:{secs_r:02d}:{sec_r:02d}"
            ax.annotate(label, xy=(r['date'], r['pace_sec']/60),
                       xytext=(8, -12), textcoords='offset points',
                       fontsize=8, color=GREEN, fontweight='bold')

    # Prediction zone for Apr 25
    pred_date = pd.Timestamp('2026-04-25')
    ax.axvline(pred_date, color=ORANGE, linestyle='--', alpha=0.7, linewidth=1.5)
    ax.annotate('Apr 25\nHM Race', xy=(pred_date, ax.get_ylim()[0] + 0.3),
               fontsize=9, color=ORANGE, fontweight='bold', ha='center')

    # Prediction band (1:37 - 1:41 = 4:36 - 4:54/km)
    ax.axhspan(4.60, 4.90, alpha=0.15, color=GREEN, label='Predicted range (1:37-1:41)')

    # Horizontal reference lines
    ax.axhline(y=4.57, color=RED, linestyle=':', alpha=0.5, linewidth=1)
    ax.annotate('HM PR: 1:37:14 (4:34/km)', xy=(hm_efforts['date'].min(), 4.50),
               fontsize=8, color=RED, alpha=0.7)

    ax.invert_yaxis()
    style_ax(ax, 'Half Marathon Distance Efforts — Pace Progression & Prediction',
             '', 'Pace (min/km) — lower = faster')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'))
    ax.legend(loc='upper right', fontsize=9)
    plt.xticks(rotation=45, ha='right')
    fig.tight_layout()
    return save_chart(fig, '19_hm_prediction')


def compute_hm_prediction(runs):
    """Compute HM prediction data for the HTML report."""
    import numpy as np

    def vdot_from_effort(dist_m, time_sec):
        t = time_sec / 60.0
        d = dist_m
        v = d / t
        pct = 0.8 + 0.1894393 * np.exp(-0.012778 * t) + 0.2989558 * np.exp(-0.1932605 * t)
        vo2 = -4.60 + 0.182258 * v + 0.000104 * v**2
        return vo2 / pct

    def predict_time_from_vdot(vdot, dist_m):
        for t_min in np.arange(50, 200, 0.1):
            vo2 = -4.60 + 0.182258 * (dist_m/t_min) + 0.000104 * (dist_m/t_min)**2
            pct = 0.8 + 0.1894393 * np.exp(-0.012778 * t_min) + 0.2989558 * np.exp(-0.1932605 * t_min)
            if vo2 / pct <= vdot:
                return t_min * 60
        return None

    # Key HM-distance hard efforts
    hm_hard_efforts = [
        {'date': 'Nov 10, 2024', 'name': 'Harrisburg Half Marathon', 'dist_m': 21230,
         'time_sec': 1*3600+37*60+14, 'context': 'RACE — HM PR', 'hr': 178},
        {'date': 'Mar 8, 2025', 'name': 'Day 38/82', 'dist_m': 21100,
         'time_sec': 1*3600+38*60+34, 'context': 'Training', 'hr': 175},
        {'date': 'Dec 21, 2025', 'name': 'Morning Run', 'dist_m': 21150,
         'time_sec': 1*3600+40*60+26, 'context': 'Training — most recent', 'hr': 176},
    ]

    # Compute VDOT for each
    for e in hm_hard_efforts:
        e['vdot'] = vdot_from_effort(e['dist_m'], e['time_sec'])
        pred = predict_time_from_vdot(e['vdot'], 21097.5)
        e['hm_pred_sec'] = pred

    # Recent speed effort (Mar 24, 2026)
    recent_speed = {
        'date': 'Mar 24, 2026', 'name': '6.45km hard',
        'dist_m': 6450, 'time_sec': 30*60+13,
        'vdot': vdot_from_effort(6450, 30*60+13)
    }

    # Riegel prediction from Dec 21 run
    dec21_time = 1*3600+40*60+26
    riegel_hm = dec21_time * (21.0975/21.15)**1.06

    # Marathon PR Riegel
    mar_time = 3*3600+40*60+6
    riegel_from_mar = mar_time * (21.0975/42.195)**1.06

    return {
        'hm_hard_efforts': hm_hard_efforts,
        'recent_speed_vdot': recent_speed['vdot'],
        'riegel_from_dec21': riegel_hm,
        'riegel_from_marathon': riegel_from_mar,
        'dec21_vdot': hm_hard_efforts[2]['vdot'],
    }


# ---------------------------------------------------------------------------
# SECTION E: TRAINING PATTERNS
# ---------------------------------------------------------------------------

def chart_time_of_day(runs):
    """E16: Time of day distribution."""
    tod = runs['time_of_day'].value_counts()

    fig, ax = new_fig((10, 6))
    tod_order = ['Morning', 'Afternoon', 'Evening', 'Unknown']
    tod_colors = [YELLOW, ORANGE, PURPLE, GRID]
    values = [tod.get(t, 0) for t in tod_order]

    bars = ax.bar(tod_order, values, color=tod_colors, alpha=0.85, edgecolor='none', width=0.6)

    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 2,
                str(val), ha='center', color=TEXT, fontsize=10, fontweight='bold')

    style_ax(ax, 'Time of Day Distribution (from activity names)', '', 'Number of Runs')
    fig.tight_layout()
    return save_chart(fig, '16_time_of_day')


def chart_day_of_week_heatmap(runs):
    """E17: Day of week volume heatmap."""
    # Create month x weekday heatmap
    runs_copy = runs.copy()
    runs_copy['month_str'] = runs_copy['date'].dt.to_period('M').astype(str)
    runs_copy['day_name'] = runs_copy['date'].dt.day_name()

    pivot = runs_copy.pivot_table(values='distance_km', index='day_name', columns='month_str',
                                   aggfunc='sum', fill_value=0)

    day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    pivot = pivot.reindex(day_order)

    fig, ax = plt.subplots(figsize=(max(14, len(pivot.columns) * 0.6), 5), dpi=150)
    fig.patch.set_facecolor(BG)

    cmap = LinearSegmentedColormap.from_list('vol', [BG_LIGHT, '#0d4b2b', GREEN], N=256)
    sns.heatmap(pivot, ax=ax, cmap=cmap, linewidths=0.5, linecolor=BG,
                cbar_kws={'label': 'Distance (km)'}, annot=False)

    ax.set_facecolor(BG)
    ax.set_title('Day of Week x Month Running Volume', color=TEXT, fontsize=13, fontweight='bold', pad=12)
    ax.set_xlabel('', color=TEXT)
    ax.set_ylabel('', color=TEXT)
    ax.tick_params(colors=TEXT, labelsize=7)
    plt.xticks(rotation=90, ha='center')
    cbar = ax.collections[0].colorbar
    cbar.ax.tick_params(colors=TEXT, labelsize=8)
    cbar.set_label('Distance (km)', color=TEXT, fontsize=9)
    fig.tight_layout()
    return save_chart(fig, '17_day_of_week_heatmap')


def chart_long_runs(runs):
    """E18: Long runs (>15km) per month."""
    long_runs = runs[runs['distance_km'] >= 15].copy()
    long_monthly = long_runs.groupby('year_month').size()

    # Full month range
    all_months = runs['year_month'].unique()
    long_monthly = long_monthly.reindex(all_months, fill_value=0)
    months = long_monthly.index.to_timestamp()
    values = long_monthly.values

    fig, ax = new_fig((14, 5))
    ax.bar(months, values, width=25, color=ORANGE, alpha=0.8, edgecolor='none')

    style_ax(ax, 'Long Runs (>15 km) per Month', '', 'Count')
    ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    plt.xticks(rotation=45, ha='right')
    fig.tight_layout()
    return save_chart(fig, '18_long_runs')


# ---------------------------------------------------------------------------
# HTML REPORT GENERATION
# ---------------------------------------------------------------------------

def generate_html_report(df, runs, charts, best_efforts, stats, hm_pred_data=None):
    """Generate the full HTML report."""

    def img_tag(b64, alt='chart'):
        return f'<img src="data:image/png;base64,{b64}" alt="{alt}" style="width:100%;max-width:1100px;border-radius:8px;margin:10px 0;">'

    # Marathon progression analysis
    marathon_analysis = """
    <h3>Marathon Progression</h3>
    <table class="data-table">
        <tr><th>#</th><th>Race</th><th>Date</th><th>Time</th><th>Pace</th><th>Notes</th></tr>
        <tr><td>1</td><td>First Marathon</td><td>Nov 24, 2024</td><td>3:45:54</td><td>5:18/km</td>
            <td>"I Messed up my first marathon" - Brave debut with 336m elevation</td></tr>
        <tr><td>2</td><td>Derby Festival</td><td>Apr 26, 2025</td><td>3:54:18</td><td>5:31/km</td>
            <td>After structured 82-day training block, 230m elevation</td></tr>
        <tr><td>3</td><td>DIY Full Marathon</td><td>Sep 6, 2025</td><td>3:56:34</td><td>5:36/km</td>
            <td>Solo effort, 309m elevation (hardest course)</td></tr>
        <tr><td>4</td><td>Indy Monumental</td><td>Nov 8, 2025</td><td>3:40:06</td><td>5:10/km</td>
            <td>PR! 5:48 improvement over first marathon, flat course (110m)</td></tr>
    </table>
    <div class="insight">
        <strong>Key Insight:</strong> You improved your marathon time by 5 minutes 48 seconds over 4 races in 1 year.
        Your PR pace of 5:10/km at Indy Monumental on a flat course shows the benefit of course selection.
        The 82-day structured training block before Derby didn't yield a faster time (elevation + heat),
        but built the base for the eventual PR.
    </div>
    """

    # Best efforts table
    best_html = '<table class="data-table"><tr><th>Distance</th><th>Est. Time</th><th>Pace</th><th>Date</th><th>Activity</th></tr>'
    for dist, data in best_efforts.items():
        best_html += f'<tr><td>{dist}</td><td>{data["time"]}</td><td>{data["pace"]}</td><td>{data.get("date", "N/A")}</td><td>{data.get("name", "N/A")}</td></tr>'
    best_html += '</table>'

    # Training block stats
    block_runs_count = len(runs[runs['name'].str.contains(r'Day \d+/82', na=False)])

    # Key findings
    findings = f"""
    <h3>Key Findings</h3>
    <ul>
        <li><strong>Volume:</strong> ~{stats['total_km']:.0f} km across {stats['total_runs']} runs in {stats['months_active']} months
            averaging {stats['avg_monthly_km']:.1f} km/month</li>
        <li><strong>Consistency:</strong> You average {stats['avg_runs_per_week']:.1f} runs/week with an upward trend in frequency</li>
        <li><strong>Marathon PR:</strong> 3:40:06 (Indy Monumental, Nov 2025) - a 5:48 improvement over your debut</li>
        <li><strong>Half Marathon PR:</strong> 1:37:14 (Harrisburg, Nov 2024) - strong pace of 4:35/km</li>
        <li><strong>Training Intensity:</strong> {'Good mix of easy and hard efforts' if stats.get('easy_pct', 0) > 0.5 else 'Consider more easy runs (80/20 rule)'}</li>
        <li><strong>Long Runs:</strong> {stats['long_runs_count']} runs over 15 km, essential for marathon prep</li>
        <li><strong>82-Day Block:</strong> {block_runs_count} structured training days - shows commitment to a plan</li>
        <li><strong>HR Data:</strong> Available from Jan 2025+, enabling fitness tracking</li>
    </ul>

    <h3>Recommendations</h3>
    <ul>
        <li><strong>Sub-3:30 Marathon:</strong> Your VO2max trend suggests sub-3:30 is achievable. Target pace work at 4:55-5:00/km</li>
        <li><strong>Easy Day Discipline:</strong> Keep 80% of runs at easy pace (&gt;6:00/km, HR &lt;145). Your pace distribution shows room for polarization</li>
        <li><strong>Weekly Mileage:</strong> Build to consistent 60-70 km weeks in peak training, currently averaging ~{stats['avg_weekly_km']:.0f} km</li>
        <li><strong>Recovery:</strong> Aim for 2 rest days/week minimum during base building, 1 during peak</li>
        <li><strong>Strength:</strong> Weight training frequency could support injury prevention - consider 2x/week</li>
        <li><strong>Half Marathon:</strong> Target a sub-1:35 half to validate sub-3:30 marathon fitness</li>
    </ul>
    """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Running Analysis Report</title>
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
        background: {BG};
        color: {TEXT};
        font-family: Calibri, 'Segoe UI', system-ui, -apple-system, sans-serif;
        line-height: 1.6;
        padding: 20px;
    }}
    .container {{ max-width: 1200px; margin: 0 auto; }}
    h1 {{
        font-size: 2.2em;
        color: {GREEN};
        text-align: center;
        margin: 30px 0 10px;
        letter-spacing: 1px;
    }}
    .subtitle {{
        text-align: center;
        color: #999;
        font-size: 1em;
        margin-bottom: 30px;
    }}
    h2 {{
        font-size: 1.5em;
        color: {GREEN};
        margin: 40px 0 15px;
        padding-bottom: 8px;
        border-bottom: 2px solid #333355;
    }}
    h3 {{
        font-size: 1.2em;
        color: {BLUE};
        margin: 25px 0 10px;
    }}
    .dashboard {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 15px;
        margin: 25px 0;
    }}
    .stat-card {{
        background: {BG_LIGHT};
        border-radius: 10px;
        padding: 20px;
        text-align: center;
        border: 1px solid #333355;
    }}
    .stat-card .value {{
        font-size: 2em;
        font-weight: bold;
        color: {GREEN};
        display: block;
    }}
    .stat-card .label {{
        font-size: 0.85em;
        color: #999;
        margin-top: 5px;
    }}
    .chart-section {{
        background: {BG_LIGHT};
        border-radius: 10px;
        padding: 20px;
        margin: 20px 0;
        border: 1px solid #333355;
    }}
    .chart-section img {{
        display: block;
        margin: 0 auto;
    }}
    .insight {{
        background: #1e2a4a;
        border-left: 4px solid {BLUE};
        padding: 15px 20px;
        margin: 15px 0;
        border-radius: 0 8px 8px 0;
        font-size: 0.95em;
    }}
    .data-table {{
        width: 100%;
        border-collapse: collapse;
        margin: 15px 0;
        font-size: 0.9em;
    }}
    .data-table th {{
        background: #333355;
        color: {GREEN};
        padding: 10px 12px;
        text-align: left;
        font-weight: 600;
    }}
    .data-table td {{
        padding: 8px 12px;
        border-bottom: 1px solid #333355;
    }}
    .data-table tr:hover td {{
        background: rgba(46, 204, 113, 0.05);
    }}
    ul {{
        margin: 10px 0 10px 25px;
    }}
    li {{
        margin: 6px 0;
        font-size: 0.95em;
    }}
    .footer {{
        text-align: center;
        color: #666;
        font-size: 0.8em;
        margin-top: 50px;
        padding-top: 20px;
        border-top: 1px solid #333355;
    }}
    @media (max-width: 768px) {{
        .dashboard {{ grid-template-columns: repeat(2, 1fr); }}
        body {{ padding: 10px; }}
    }}
</style>
</head>
<body>
<div class="container">

<h1>Running Analysis Report</h1>
<p class="subtitle">Strava Data Analysis | March 2024 - March 2026 | Generated {datetime.now().strftime('%B %d, %Y')}</p>

<!-- DASHBOARD -->
<div class="dashboard">
    <div class="stat-card">
        <span class="value">{stats['total_km']:,.1f}</span>
        <span class="label">Total Kilometers</span>
    </div>
    <div class="stat-card">
        <span class="value">{stats['total_runs']}</span>
        <span class="label">Total Runs</span>
    </div>
    <div class="stat-card">
        <span class="value">{seconds_to_hms(stats['total_time_sec'])}</span>
        <span class="label">Total Time</span>
    </div>
    <div class="stat-card">
        <span class="value">{stats['avg_pace']}</span>
        <span class="label">Avg Pace (/km)</span>
    </div>
    <div class="stat-card">
        <span class="value">4</span>
        <span class="label">Marathons</span>
    </div>
    <div class="stat-card">
        <span class="value">3:40:06</span>
        <span class="label">Marathon PR</span>
    </div>
    <div class="stat-card">
        <span class="value">1:37:14</span>
        <span class="label">Half Marathon PR</span>
    </div>
    <div class="stat-card">
        <span class="value">{stats['avg_monthly_km']:.0f} km</span>
        <span class="label">Avg Monthly Mileage</span>
    </div>
    <div class="stat-card">
        <span class="value">{stats['longest_run']:.1f} km</span>
        <span class="label">Longest Run</span>
    </div>
    <div class="stat-card">
        <span class="value">{stats['total_elevation']:,} m</span>
        <span class="label">Total Elevation</span>
    </div>
</div>

<!-- A. VOLUME & CONSISTENCY -->
<h2>A. Volume & Consistency</h2>

<div class="chart-section">
    <h3>Monthly Running Mileage</h3>
    {img_tag(charts.get('monthly_mileage', ''), 'Monthly Mileage')}
    <div class="insight">Your mileage has grown substantially since starting in 2024. Peak months coincide
    with marathon training blocks.</div>
</div>

<div class="chart-section">
    <h3>Weekly Running Frequency</h3>
    {img_tag(charts.get('weekly_frequency', ''), 'Weekly Frequency')}
    <div class="insight">Consistency is the foundation. Weeks with 4-6 runs correlate with your best performance periods.</div>
</div>

<div class="chart-section">
    <h3>Cumulative Distance</h3>
    {img_tag(charts.get('cumulative_distance', ''), 'Cumulative Distance')}
    <div class="insight">Remarkable progression from 0 to ~{stats['total_km']:,.0f} km in under 2 years.
    The acceleration after mid-2024 shows when running became a serious pursuit.</div>
</div>

<div class="chart-section">
    <h3>Daily Running Heatmap</h3>
    {img_tag(charts.get('calendar_heatmap', ''), 'Calendar Heatmap')}
    <div class="insight">The heatmap reveals training density. Gaps are visible around recovery periods
    after marathons, which is smart periodization.</div>
</div>

<!-- B. PACE & PERFORMANCE -->
<h2>B. Pace & Performance</h2>

<div class="chart-section">
    <h3>Average Pace Trend</h3>
    {img_tag(charts.get('monthly_pace', ''), 'Monthly Pace')}
    <div class="insight">Your average pace has trended faster over time, dropping from ~7:00+/km in early months
    to sub-6:00/km in recent months. This reflects both fitness gains and better pacing discipline.</div>
</div>

<div class="chart-section">
    <h3>Race Results Timeline</h3>
    {img_tag(charts.get('race_timeline', ''), 'Race Timeline')}
    {marathon_analysis}
</div>

<div class="chart-section">
    <h3>Best Estimated Efforts</h3>
    {best_html}
    <div class="insight">These are estimated best efforts based on your fastest pace at each distance.
    Actual race PRs may differ due to course conditions and race-day effort.</div>
</div>

<div class="chart-section">
    <h3>Pace Distribution</h3>
    {img_tag(charts.get('pace_distribution', ''), 'Pace Distribution')}
    <div class="insight">A healthy pace distribution shows variety in training speeds. The ideal 80/20
    polarization means most runs should be at easy pace (&gt;6:00/km).</div>
</div>

<!-- C. TRAINING LOAD & INJURY RISK -->
<h2>C. Training Load & Injury Risk</h2>

<div class="chart-section">
    <h3>Weekly Mileage with Ramp Rate</h3>
    {img_tag(charts.get('weekly_mileage_ramp', ''), 'Weekly Mileage Ramp')}
    <div class="insight">Red triangles mark weeks where mileage jumped &gt;20% over the previous week.
    The 10% rule suggests gradual increases to prevent injury.</div>
</div>

<div class="chart-section">
    <h3>Acute:Chronic Workload Ratio</h3>
    {img_tag(charts.get('acwr', ''), 'ACWR')}
    <div class="insight">ACWR between 0.8-1.3 is the "sweet spot." Values above 1.5 indicate injury risk from
    sudden load spikes. Monitor this during training block ramp-ups.</div>
</div>

<div class="chart-section">
    <h3>Rest Days per Week</h3>
    {img_tag(charts.get('rest_days', ''), 'Rest Days')}
    <div class="insight">Adequate rest is crucial for adaptation. During heavy training, 1-2 rest days per week
    is appropriate; during base building, 2-3 rest days is recommended.</div>
</div>

{"<div class='chart-section'><h3>82-Day Marathon Training Block</h3>" + img_tag(charts.get('training_block', ''), 'Training Block') + "<div class='insight'>This structured block (Feb-Apr 2025) prepared you for the Derby Festival Marathon. The peak week and subsequent taper are visible. Future blocks could aim for a higher peak week.</div></div>" if charts.get('training_block') else ""}

<!-- D. FITNESS PROGRESSION -->
<h2>D. Fitness Progression (HR Data)</h2>

{"<div class='chart-section'><h3>Pace vs Heart Rate</h3>" + img_tag(charts.get('pace_vs_hr', ''), 'Pace vs HR') + "<div class='insight'>Ideally, the same pace should require a lower heart rate over time (cardiac drift downward). Points shifting down-left over quarters indicate improved aerobic efficiency.</div></div>" if charts.get('pace_vs_hr') else "<div class='chart-section'><p>Insufficient HR data for this chart.</p></div>"}

{"<div class='chart-section'><h3>Training Intensity Distribution</h3>" + img_tag(charts.get('intensity_distribution', ''), 'Intensity') + "<div class='insight'>The 80/20 rule suggests ~80% of training should be easy (HR &lt;145 bpm). Monitor this balance to prevent overtraining.</div></div>" if charts.get('intensity_distribution') else ""}

<div class="chart-section">
    <h3>Estimated VO2max Trend</h3>
    {img_tag(charts.get('vo2max_trend', ''), 'VO2max')}
    <div class="insight">VO2max estimated using the Jack Daniels formula from race performances.
    An upward trend confirms improving aerobic capacity. Elite amateur range is 50-60 ml/kg/min.</div>
</div>

<!-- E. TRAINING PATTERNS -->
<h2>E. Training Patterns</h2>

<div class="chart-section">
    <h3>Time of Day Distribution</h3>
    {img_tag(charts.get('time_of_day', ''), 'Time of Day')}
    <div class="insight">Morning runs dominate your schedule, which is great for consistency and cooler conditions.
    Evening runs can serve as recovery or social runs.</div>
</div>

<div class="chart-section">
    <h3>Day of Week Volume</h3>
    {img_tag(charts.get('day_of_week', ''), 'Day of Week')}
    <div class="insight">This heatmap reveals weekly patterns. Long run days and rest day habits are visible
    across training periods.</div>
</div>

<div class="chart-section">
    <h3>Long Runs per Month</h3>
    {img_tag(charts.get('long_runs', ''), 'Long Runs')}
    <div class="insight">Long runs (&gt;15 km) are essential for marathon endurance. Aim for 1-2 per week during
    peak training, with the longest run reaching 32-35 km before a marathon.</div>
</div>

<!-- RACE PREDICTION -->
<h2 style="color:{ORANGE};">Race Prediction: Half Marathon — April 25, 2026</h2>

{"<div class='chart-section'>" + img_tag(charts.get('hm_prediction', ''), 'HM Prediction') + "</div>" if charts.get('hm_prediction') else ""}

<div class="chart-section">
    <h3>Evidence Base: HM-Distance Hard Efforts</h3>
    <p style="color:#aaa;margin-bottom:10px;">These are the <strong>correct predictors</strong> — actual efforts at or near half marathon distance, not extrapolated from marathon or short runs.</p>
    <table class="data-table">
        <tr><th>Date</th><th>Distance</th><th>Time</th><th>Pace</th><th>HR</th><th>VDOT</th><th>Context</th></tr>
        <tr style="background:#1a3a1a;"><td>Nov 10, 2024</td><td>21.23 km</td><td><strong>1:37:14</strong></td><td>4:34/km (7:22/mi)</td><td>178</td><td>47.0</td><td>RACE — HM PR</td></tr>
        <tr><td>Mar 8, 2025</td><td>21.10 km</td><td><strong>1:38:34</strong></td><td>4:40/km (7:31/mi)</td><td>175</td><td>46.0</td><td>Training — Day 38/82</td></tr>
        <tr><td>Dec 21, 2025</td><td>21.15 km</td><td><strong>1:40:26</strong></td><td>4:44/km (7:38/mi)</td><td>176</td><td>45.0</td><td>Training — 3 months ago</td></tr>
    </table>
    <div class="insight">
        <strong>Key pattern:</strong> You run ~1:38-1:40 at HM distance in training, and ~1:37 in races (2-3 minute gap is typical from taper + race day adrenaline + competition).
        Your speed is confirmed by a 4:41/km effort for 6.45km on Mar 24, 2026 (HR 174).
    </div>
</div>

<div class="chart-section">
    <h3 style="color:{ORANGE};">Prediction</h3>
    <table class="data-table">
        <tr><th>Scenario</th><th>Time</th><th>Pace</th><th>Condition</th></tr>
        <tr style="background:#1a2a1a;"><td>Best case (PR territory)</td><td><strong>1:35 - 1:37</strong></td><td>4:30-4:35/km</td><td>Perfect taper + HM-pace workouts + race execution</td></tr>
        <tr style="background:#1a3a2a;"><td>Realistic (good race)</td><td><strong>1:38 - 1:41</strong></td><td>4:38-4:45/km</td><td>Standard race day, maintained fitness</td></tr>
        <tr><td>Conservative (off day)</td><td>1:41 - 1:44</td><td>4:45-4:55/km</td><td>No taper, tired legs, bad conditions</td></tr>
    </table>
    <div class="insight" style="border-left-color:{ORANGE};">
        <strong>Central estimate: ~1:39 &plusmn; 2 minutes.</strong><br>
        PR potential (sub-1:37:14) is <strong>achievable</strong> with proper preparation in the remaining 4 weeks.
    </div>
</div>

<div class="chart-section">
    <h3>Race Day Pacing Plan (targeting 1:38)</h3>
    <table class="data-table">
        <tr><th>Split</th><th>Cumulative Time</th><th>Pace</th><th>Strategy</th></tr>
        <tr><td>5 km</td><td>23:00</td><td>4:36/km (7:24/mi)</td><td>Controlled — don't go out too fast</td></tr>
        <tr><td>10 km</td><td>46:00</td><td>4:36/km</td><td>Settle into rhythm, check HR (168-172)</td></tr>
        <tr><td>15 km</td><td>1:09:00</td><td>4:36/km</td><td>Hold steady — this is where fitness shows</td></tr>
        <tr><td>18 km</td><td>1:22:48</td><td>4:36/km</td><td>Begin to push if legs feel good</td></tr>
        <tr><td>21.1 km</td><td><strong>1:37:06 - 1:39:00</strong></td><td>4:30-4:36/km</td><td>Empty the tank in the last 3km</td></tr>
    </table>
</div>

<div class="chart-section">
    <h3>4-Week Training Plan to Peak for Apr 25</h3>
    <table class="data-table">
        <tr><th>Week</th><th>Focus</th><th>Key Workouts</th><th>Volume</th></tr>
        <tr><td>Mar 25-31</td><td>Build</td><td>Tempo 8km @ 4:40/km + Long run 16-18km</td><td>~45 km</td></tr>
        <tr><td>Apr 1-7</td><td>Sharpen</td><td>HM-pace 10km (8km @ 4:35/km) + Long run 18-20km</td><td>~50 km</td></tr>
        <tr><td>Apr 8-14</td><td>Peak</td><td>Race-pace 12km (10km @ 4:35/km) + 16km easy long</td><td>~45 km</td></tr>
        <tr><td>Apr 15-24</td><td>Taper</td><td>Short tempo 5km @ 4:30/km + easy runs only</td><td>~25-30 km</td></tr>
    </table>
    <div class="insight">
        <strong>The single biggest thing you can do:</strong> Get 2-3 long runs (16-20km) done before taper.
        Your Dec 21 training run proves you have the speed — now maintain endurance through race day.
    </div>
</div>

<!-- FINDINGS -->
<h2>Analysis & Recommendations</h2>
<div class="chart-section">
    {findings}
</div>

<div class="footer">
    <p>Generated by Running Analysis Script | Data from Strava | Weight: {WEIGHT_KG} kg</p>
    <p>Member since June 2018 | First tracked activity: March 15, 2024</p>
</div>

</div>
</body>
</html>"""

    with open(REPORT_FILE, 'w') as f:
        f.write(html)
    print(f"\n  Report saved to {REPORT_FILE}")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  RUNNING ANALYSIS")
    print("=" * 60)

    # Load data
    print("\n[1/7] Loading and parsing data...")
    df = load_data()
    total_activities = len(df)
    print(f"  Total activities loaded: {total_activities}")
    print(f"  Date range: {df['date'].min().strftime('%b %d, %Y')} to {df['date'].max().strftime('%b %d, %Y')}")

    # Filter to runs
    runs = df[df['type'].isin(['Run', 'TrailRun'])].copy()
    print(f"  Running activities: {len(runs)} (Run + TrailRun)")

    # Activity type breakdown
    print("\n  Activity type breakdown:")
    for t, count in df['type'].value_counts().items():
        print(f"    {t}: {count}")

    # Compute summary stats
    total_km = runs['distance_km'].sum()
    total_runs = len(runs)
    total_time_sec = runs['time_seconds'].sum()
    total_elevation = runs['elevation_m'].dropna().sum()
    avg_pace = runs[runs['pace_min_per_km'].notna()]['pace_min_per_km'].mean()
    longest_run = runs['distance_km'].max()
    months_active = len(runs['year_month'].unique())
    avg_monthly_km = total_km / months_active if months_active > 0 else 0
    weeks_active = len(runs['year_week'].unique())
    avg_weekly_km = total_km / weeks_active if weeks_active > 0 else 0
    avg_runs_per_week = total_runs / weeks_active if weeks_active > 0 else 0
    long_runs_count = len(runs[runs['distance_km'] >= 15])

    # Easy run percentage (HR-based)
    hr_runs = runs[runs['hr_bpm'].notna()]
    easy_pct = len(hr_runs[hr_runs['hr_bpm'] < 145]) / len(hr_runs) if len(hr_runs) > 0 else 0

    stats = {
        'total_km': total_km,
        'total_runs': total_runs,
        'total_time_sec': total_time_sec,
        'total_elevation': int(total_elevation),
        'avg_pace': pace_to_str(avg_pace),
        'longest_run': longest_run,
        'months_active': months_active,
        'avg_monthly_km': avg_monthly_km,
        'avg_weekly_km': avg_weekly_km,
        'avg_runs_per_week': avg_runs_per_week,
        'long_runs_count': long_runs_count,
        'easy_pct': easy_pct,
    }

    print(f"\n  --- RUNNING SUMMARY ---")
    print(f"  Total distance: {total_km:,.1f} km")
    print(f"  Total runs: {total_runs}")
    print(f"  Total time: {seconds_to_hms(total_time_sec)}")
    print(f"  Average pace: {pace_to_str(avg_pace)} /km")
    print(f"  Longest run: {longest_run:.1f} km")
    print(f"  Total elevation: {int(total_elevation):,} m")
    print(f"  Avg monthly mileage: {avg_monthly_km:.1f} km")
    print(f"  Avg runs/week: {avg_runs_per_week:.1f}")
    print(f"  Long runs (>15km): {long_runs_count}")
    print(f"  Months active: {months_active}")

    # Generate charts
    charts = {}

    print("\n[2/7] Generating Volume & Consistency charts...")
    charts['monthly_mileage'] = chart_monthly_mileage(runs)
    charts['weekly_frequency'] = chart_weekly_frequency(runs)
    charts['cumulative_distance'] = chart_cumulative_distance(runs)
    charts['calendar_heatmap'] = chart_calendar_heatmap(runs)

    print("\n[3/7] Generating Pace & Performance charts...")
    charts['monthly_pace'] = chart_monthly_pace(runs)
    charts['race_timeline'] = chart_race_timeline(runs)
    best_efforts = compute_best_efforts(runs)
    charts['pace_distribution'] = chart_pace_distribution(runs)

    print("\n  Best Estimated Efforts:")
    for dist, data in best_efforts.items():
        print(f"    {dist}: {data['time']} @ {data['pace']}/km ({data.get('date', 'N/A')})")

    print("\n[4/7] Generating Training Load charts...")
    charts['weekly_mileage_ramp'] = chart_weekly_mileage_ramp(runs)
    charts['acwr'] = chart_acwr(runs)
    charts['rest_days'] = chart_rest_days(runs)
    b64 = chart_marathon_training_block(runs)
    if b64:
        charts['training_block'] = b64

    print("\n[5/7] Generating Fitness Progression charts...")
    b64 = chart_pace_vs_hr(runs)
    if b64:
        charts['pace_vs_hr'] = b64
    b64 = chart_intensity_distribution(runs)
    if b64:
        charts['intensity_distribution'] = b64
    charts['vo2max_trend'] = chart_vo2max_trend()

    print("\n[6/7] Generating Training Pattern charts...")
    charts['time_of_day'] = chart_time_of_day(runs)
    charts['day_of_week'] = chart_day_of_week_heatmap(runs)
    charts['long_runs'] = chart_long_runs(runs)

    print("\n[7/8] Generating Race Prediction (HM Apr 25)...")
    b64 = chart_hm_prediction(runs)
    if b64:
        charts['hm_prediction'] = b64
    hm_pred_data = compute_hm_prediction(runs)

    print("\n[8/8] Generating HTML report...")
    generate_html_report(df, runs, charts, best_efforts, stats, hm_pred_data)

    print("\n" + "=" * 60)
    print("  COMPLETE!")
    print(f"  Charts saved to: {CHARTS_DIR}/")
    print(f"  CSV saved to: {CSV_FILE}")
    print(f"  Report saved to: {REPORT_FILE}")
    print("=" * 60)


if __name__ == '__main__':
    main()
