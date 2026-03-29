#!/usr/bin/env python3
"""
Strava Complete Data Extractor
Fetches ALL activity data from the Strava API and saves as JSON + CSV.

Rate limits: 100 requests per 15 min, 1000 per day.
Strategy: Fetch summaries first (4 calls), then details in batches.
"""

import json
import csv
import os
import time
import sys
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import urlencode

# ─── Config ───────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, 'data', 'raw')
os.makedirs(OUTPUT_DIR, exist_ok=True)

TOKEN_FILE = os.path.expanduser('~/.config/strava-mcp/tokens.json')
CLIENT_ID = '134002'
CLIENT_SECRET = '535c986253ca43a24ac64980c54f6faf15d43b7c'
API_BASE = 'https://www.strava.com/api/v3'

# Rate limiting
REQUEST_COUNT = 0
BATCH_START = time.time()
MAX_PER_15MIN = 90  # leave 10 buffer
CONSECUTIVE_429 = 0


def load_tokens():
    with open(TOKEN_FILE) as f:
        return json.load(f)


def save_tokens(tokens):
    with open(TOKEN_FILE, 'w') as f:
        json.dump(tokens, f, indent=2)


def refresh_token(tokens):
    """Refresh the Strava access token."""
    print("  Refreshing access token...")
    data = urlencode({
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'refresh_token',
        'refresh_token': tokens['refreshToken'],
    }).encode()
    req = Request('https://www.strava.com/oauth/token', data=data, method='POST')
    with urlopen(req) as resp:
        result = json.loads(resp.read())
    tokens['accessToken'] = result['access_token']
    tokens['refreshToken'] = result['refresh_token']
    tokens['expiresAt'] = result['expires_at']
    save_tokens(tokens)
    print(f"  Token refreshed, expires at {datetime.fromtimestamp(result['expires_at'])}")
    return tokens


def get_access_token():
    tokens = load_tokens()
    if tokens['expiresAt'] < time.time() + 300:
        tokens = refresh_token(tokens)
    return tokens['accessToken']


def rate_limit_wait():
    """Respect Strava rate limits."""
    global REQUEST_COUNT, BATCH_START
    REQUEST_COUNT += 1
    if REQUEST_COUNT >= MAX_PER_15MIN:
        elapsed = time.time() - BATCH_START
        wait = max(0, 910 - elapsed)  # 15 min + 10s buffer
        if wait > 0:
            mins = int(wait // 60)
            secs = int(wait % 60)
            print(f"\n  Rate limit: {REQUEST_COUNT} requests. Waiting {mins}m {secs}s for window reset...")
            time.sleep(wait)
        REQUEST_COUNT = 0
        BATCH_START = time.time()


def api_get(endpoint, params=None, _retry=0):
    """Make authenticated GET request to Strava API."""
    global REQUEST_COUNT, BATCH_START, CONSECUTIVE_429
    rate_limit_wait()
    token = get_access_token()
    url = f"{API_BASE}{endpoint}"
    if params:
        url += '?' + urlencode(params)
    req = Request(url, headers={'Authorization': f'Bearer {token}'})
    try:
        with urlopen(req) as resp:
            CONSECUTIVE_429 = 0
            return json.loads(resp.read())
    except HTTPError as e:
        if e.code == 429:
            CONSECUTIVE_429 += 1
            # Read Retry-After header or use escalating wait
            wait = min(60 * CONSECUTIVE_429, 920)  # escalate: 60s, 120s, ... up to 15min
            mins = int(wait // 60)
            secs = int(wait % 60)
            print(f"  429 rate limited (attempt {CONSECUTIVE_429}) — waiting {mins}m {secs}s...")
            time.sleep(wait)
            # Reset counter after long wait
            if wait >= 900:
                REQUEST_COUNT = 0
                BATCH_START = time.time()
                CONSECUTIVE_429 = 0
            if _retry < 5:
                return api_get(endpoint, params, _retry + 1)
            else:
                print(f"  Failed after 5 retries for {endpoint}")
                return None
        else:
            print(f"  HTTP {e.code}: {e.reason} for {endpoint}")
            return None


def fetch_all_activity_summaries():
    """Fetch ALL activity summaries (paginated). Returns list of raw JSON objects."""
    cache_file = os.path.join(OUTPUT_DIR, 'all_activities_summary.json')

    # Use cached data if available
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            all_activities = json.load(f)
        print(f"\n[1/3] Loaded {len(all_activities)} cached activity summaries from {cache_file}")
        return all_activities

    print("\n[1/3] Fetching all activity summaries...")
    all_activities = []
    page = 1
    while True:
        print(f"  Page {page} (200 per page)...")
        activities = api_get('/athlete/activities', {'page': page, 'per_page': 200})
        if not activities:
            break
        all_activities.extend(activities)
        print(f"    Got {len(activities)} activities (total: {len(all_activities)})")
        if len(activities) < 200:
            break
        page += 1

    # Save raw JSON
    with open(cache_file, 'w') as f:
        json.dump(all_activities, f, indent=2)
    print(f"  Saved {len(all_activities)} activities to {cache_file}")

    # Save CSV
    csv_file = os.path.join(OUTPUT_DIR, 'all_activities_summary.csv')
    if all_activities:
        fields = [
            'id', 'name', 'type', 'sport_type', 'start_date_local', 'distance',
            'moving_time', 'elapsed_time', 'average_speed', 'max_speed',
            'average_heartrate', 'max_heartrate', 'has_heartrate',
            'total_elevation_gain', 'elev_high', 'elev_low',
            'average_cadence', 'average_watts', 'kilojoules',
            'suffer_score', 'calories', 'achievement_count',
            'kudos_count', 'comment_count', 'athlete_count',
            'gear_id', 'device_name', 'start_latlng', 'end_latlng',
            'timezone', 'workout_type', 'pr_count',
        ]
        with open(csv_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
            writer.writeheader()
            for a in all_activities:
                row = {k: a.get(k, '') for k in fields}
                if a.get('start_latlng'):
                    row['start_latlng'] = f"{a['start_latlng'][0]},{a['start_latlng'][1]}"
                if a.get('end_latlng'):
                    row['end_latlng'] = f"{a['end_latlng'][0]},{a['end_latlng'][1]}"
                writer.writerow(row)
        print(f"  Saved CSV to {csv_file}")

    return all_activities


def fetch_activity_details(activity_id):
    """Fetch full activity details including splits and best efforts."""
    return api_get(f'/activities/{activity_id}', {'include_all_efforts': 'false'})


def fetch_all_details(activities):
    """Fetch detailed data for all running activities."""
    runs = [a for a in activities if a.get('type') in ('Run', 'TrailRun')]
    print(f"\n[2/3] Fetching detailed data for {len(runs)} running activities...")
    print(f"  (Estimated time: ~{len(runs) * 1.0 / 95 * 15:.0f} minutes with rate limiting)")

    details_dir = os.path.join(OUTPUT_DIR, 'activity_details')
    os.makedirs(details_dir, exist_ok=True)

    # Check for already-fetched activities (resume support)
    existing = set()
    for f in os.listdir(details_dir):
        if f.endswith('.json'):
            existing.add(f.replace('.json', ''))

    all_details = []
    all_splits = []
    all_best_efforts = []

    for i, run in enumerate(runs):
        aid = str(run['id'])
        if aid in existing:
            # Load from cache
            with open(os.path.join(details_dir, f'{aid}.json')) as f:
                detail = json.load(f)
        else:
            detail = fetch_activity_details(run['id'])
            if detail:
                with open(os.path.join(details_dir, f'{aid}.json'), 'w') as f:
                    json.dump(detail, f, indent=2)

        if not detail:
            continue

        all_details.append(detail)

        # Extract splits
        if detail.get('splits_metric'):
            for s in detail['splits_metric']:
                all_splits.append({
                    'activity_id': run['id'],
                    'activity_name': run['name'],
                    'activity_date': run['start_date_local'],
                    'split_km': s.get('split'),
                    'distance_m': s.get('distance'),
                    'moving_time_sec': s.get('moving_time'),
                    'elapsed_time_sec': s.get('elapsed_time'),
                    'elevation_diff_m': s.get('elevation_difference'),
                    'average_speed_mps': s.get('average_speed'),
                    'average_hr': s.get('average_heartrate'),
                    'pace_min_per_km': round(1000 / s['average_speed'] / 60, 2) if s.get('average_speed', 0) > 0 else None,
                })

        # Extract best efforts
        if detail.get('best_efforts'):
            for e in detail['best_efforts']:
                all_best_efforts.append({
                    'activity_id': run['id'],
                    'activity_name': run['name'],
                    'activity_date': run['start_date_local'],
                    'effort_name': e.get('name'),
                    'distance_m': e.get('distance'),
                    'moving_time_sec': e.get('moving_time'),
                    'elapsed_time_sec': e.get('elapsed_time'),
                    'pr_rank': e.get('pr_rank'),
                    'start_index': e.get('start_index'),
                    'end_index': e.get('end_index'),
                })

        if (i + 1) % 20 == 0 or i == len(runs) - 1:
            print(f"  [{i+1}/{len(runs)}] {run['start_date_local'][:10]} — {run['name']}")

    # Save splits CSV
    if all_splits:
        splits_file = os.path.join(OUTPUT_DIR, 'all_splits.csv')
        with open(splits_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=all_splits[0].keys())
            writer.writeheader()
            writer.writerows(all_splits)
        print(f"  Saved {len(all_splits)} splits to {splits_file}")

    # Save best efforts CSV
    if all_best_efforts:
        efforts_file = os.path.join(OUTPUT_DIR, 'all_best_efforts.csv')
        with open(efforts_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=all_best_efforts[0].keys())
            writer.writeheader()
            writer.writerows(all_best_efforts)
        print(f"  Saved {len(all_best_efforts)} best efforts to {efforts_file}")

    return all_details


def generate_comprehensive_csv(activities, details):
    """Generate one master CSV with all data merged."""
    print("\n[3/3] Generating master CSV...")

    detail_map = {}
    for d in details:
        detail_map[d['id']] = d

    rows = []
    for a in activities:
        d = detail_map.get(a['id'], {})
        row = {
            # Core
            'strava_id': a['id'],
            'name': a.get('name', ''),
            'type': a.get('type', ''),
            'sport_type': a.get('sport_type', ''),
            'date': a.get('start_date_local', ''),
            'timezone': a.get('timezone', ''),

            # Distance & Time
            'distance_m': a.get('distance', 0),
            'distance_km': round(a.get('distance', 0) / 1000, 3),
            'distance_mi': round(a.get('distance', 0) / 1609.34, 3),
            'moving_time_sec': a.get('moving_time', 0),
            'elapsed_time_sec': a.get('elapsed_time', 0),

            # Speed & Pace
            'avg_speed_mps': a.get('average_speed', 0),
            'max_speed_mps': a.get('max_speed', 0),
            'avg_pace_min_per_km': round(1000 / a['average_speed'] / 60, 2) if a.get('average_speed', 0) > 0 else None,
            'avg_pace_min_per_mi': round(1609.34 / a['average_speed'] / 60, 2) if a.get('average_speed', 0) > 0 else None,

            # Heart Rate
            'has_heartrate': a.get('has_heartrate', False),
            'avg_hr': a.get('average_heartrate'),
            'max_hr': a.get('max_heartrate'),

            # Elevation
            'elevation_gain_m': a.get('total_elevation_gain', 0),
            'elev_high_m': a.get('elev_high'),
            'elev_low_m': a.get('elev_low'),

            # Cadence & Power
            'avg_cadence': a.get('average_cadence'),
            'avg_watts': a.get('average_watts'),
            'max_watts': d.get('max_watts'),
            'weighted_avg_watts': d.get('weighted_average_watts'),
            'kilojoules': a.get('kilojoules'),

            # Scores
            'suffer_score': a.get('suffer_score'),
            'calories': d.get('calories') or a.get('calories'),
            'achievement_count': a.get('achievement_count', 0),
            'pr_count': a.get('pr_count', 0),
            'kudos_count': a.get('kudos_count', 0),

            # Gear & Device
            'gear_id': a.get('gear_id', ''),
            'gear_name': d.get('gear', {}).get('name', '') if d.get('gear') else '',
            'device_name': d.get('device_name', a.get('device_name', '')),

            # Location
            'start_lat': a['start_latlng'][0] if a.get('start_latlng') else None,
            'start_lng': a['start_latlng'][1] if a.get('start_latlng') else None,
            'end_lat': a['end_latlng'][0] if a.get('end_latlng') else None,
            'end_lng': a['end_latlng'][1] if a.get('end_latlng') else None,

            # Meta
            'workout_type': a.get('workout_type'),
            'description': d.get('description', ''),
            'athlete_count': a.get('athlete_count', 1),

            # Best efforts summary
            'best_400m': None, 'best_1km': None, 'best_1mi': None,
            'best_5km': None, 'best_10km': None, 'best_hm': None,
        }

        # Fill best efforts from detail
        if d.get('best_efforts'):
            for e in d['best_efforts']:
                t = e['moving_time']
                mins = t // 60
                secs = t % 60
                time_str = f"{mins}:{secs:02d}"
                name_map = {
                    '400m': 'best_400m', '1k': 'best_1km', '1 mile': 'best_1mi',
                    '5k': 'best_5km', '10k': 'best_10km',
                    'Half-Marathon': 'best_hm',
                }
                if e['name'] in name_map:
                    row[name_map[e['name']]] = time_str

        rows.append(row)

    # Save
    master_file = os.path.join(OUTPUT_DIR, 'master_activities.csv')
    if rows:
        with open(master_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        print(f"  Saved {len(rows)} activities to {master_file}")

    return rows


def main():
    print("=" * 60)
    print("  STRAVA COMPLETE DATA EXTRACTOR")
    print("=" * 60)

    # Step 1: All summaries
    activities = fetch_all_activity_summaries()
    print(f"\n  Total activities: {len(activities)}")
    types = {}
    for a in activities:
        t = a.get('sport_type', a.get('type', 'Unknown'))
        types[t] = types.get(t, 0) + 1
    for t, c in sorted(types.items(), key=lambda x: -x[1]):
        print(f"    {t}: {c}")

    # Step 2: Detailed data for runs
    details = fetch_all_details(activities)

    # Step 3: Master CSV
    generate_comprehensive_csv(activities, details)

    print("\n" + "=" * 60)
    print("  OUTPUT FILES:")
    print(f"  {OUTPUT_DIR}/")
    print(f"    all_activities_summary.json  — raw Strava JSON (all {len(activities)} activities)")
    print(f"    all_activities_summary.csv   — summary CSV")
    print(f"    all_splits.csv               — per-km splits for all runs")
    print(f"    all_best_efforts.csv         — best efforts (400m, 1K, 1mi, 5K, 10K, HM)")
    print(f"    master_activities.csv        — comprehensive merged CSV")
    print(f"    activity_details/            — individual JSON per run")
    print("=" * 60)


if __name__ == '__main__':
    main()
