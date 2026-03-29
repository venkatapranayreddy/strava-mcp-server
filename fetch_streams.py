#!/usr/bin/env python3
"""
Fetch second-by-second stream data for all activities in the last 3 months.
Streams: time, distance, heartrate, cadence, altitude, velocity, GPS, grade
"""

import json
import os
import time
import sys
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import urlencode

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, 'data', 'raw', 'streams')
os.makedirs(OUTPUT_DIR, exist_ok=True)

TOKEN_FILE = os.path.expanduser('~/.config/strava-mcp/tokens.json')
CLIENT_ID = '134002'
CLIENT_SECRET = '535c986253ca43a24ac64980c54f6faf15d43b7c'
API_BASE = 'https://www.strava.com/api/v3'

REQUEST_COUNT = 0
BATCH_START = time.time()
MAX_PER_15MIN = 90
CONSECUTIVE_429 = 0


def load_tokens():
    with open(TOKEN_FILE) as f:
        return json.load(f)

def save_tokens(tokens):
    with open(TOKEN_FILE, 'w') as f:
        json.dump(tokens, f, indent=2)

def refresh_token(tokens):
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
    return tokens

def get_access_token():
    tokens = load_tokens()
    if tokens['expiresAt'] < time.time() + 300:
        tokens = refresh_token(tokens)
    return tokens['accessToken']

def rate_limit_wait():
    global REQUEST_COUNT, BATCH_START
    REQUEST_COUNT += 1
    if REQUEST_COUNT >= MAX_PER_15MIN:
        elapsed = time.time() - BATCH_START
        wait = max(0, 910 - elapsed)
        if wait > 0:
            mins = int(wait // 60)
            secs = int(wait % 60)
            print(f"\n  Rate limit pause: waiting {mins}m {secs}s...", flush=True)
            time.sleep(wait)
        REQUEST_COUNT = 0
        BATCH_START = time.time()

def api_get(endpoint, params=None, _retry=0):
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
            wait = min(60 * CONSECUTIVE_429, 920)
            print(f"  429 rate limited (attempt {CONSECUTIVE_429}) — waiting {int(wait//60)}m {int(wait%60)}s...", flush=True)
            time.sleep(wait)
            if wait >= 900:
                REQUEST_COUNT = 0
                BATCH_START = time.time()
                CONSECUTIVE_429 = 0
            if _retry < 5:
                return api_get(endpoint, params, _retry + 1)
            return None
        else:
            print(f"  HTTP {e.code}: {e.reason} for {endpoint}")
            return None


def main():
    print("=" * 60)
    print("  FETCHING SECOND-BY-SECOND STREAM DATA (Last 3 months)")
    print("=" * 60, flush=True)

    # Load all activities
    with open(os.path.join(BASE_DIR, 'data', 'raw', 'all_activities_summary.json')) as f:
        all_activities = json.load(f)

    # Filter to last 3 months
    recent = [a for a in all_activities if a['start_date_local'] >= '2026-01-01']
    print(f"\nActivities since Jan 1, 2026: {len(recent)}", flush=True)

    # Stream types to fetch
    stream_types = ['time', 'distance', 'heartrate', 'cadence', 'altitude', 'velocity_smooth', 'latlng', 'grade_smooth']

    fetched = 0
    skipped = 0
    failed = 0

    for i, a in enumerate(recent):
        aid = a['id']
        name = a['name']
        date = a['start_date_local'][:10]
        sport = a['sport_type']
        cache_file = os.path.join(OUTPUT_DIR, f'{aid}.json')

        # Skip if already cached
        if os.path.exists(cache_file):
            skipped += 1
            continue

        # Fetch streams
        streams = api_get(f'/activities/{aid}/streams', {
            'keys': ','.join(stream_types),
            'key_type': 'time',
        })

        if streams:
            # Save raw stream data with metadata
            output = {
                'activity_id': aid,
                'name': name,
                'date': date,
                'sport_type': sport,
                'distance_m': a.get('distance', 0),
                'moving_time_sec': a.get('moving_time', 0),
                'streams': {}
            }
            for s in streams:
                output['streams'][s['type']] = {
                    'data': s['data'],
                    'series_type': s.get('series_type', ''),
                    'original_size': s.get('original_size', len(s['data'])),
                    'resolution': s.get('resolution', 'high'),
                }

            with open(cache_file, 'w') as f:
                json.dump(output, f)

            total_points = sum(len(s['data']) for s in streams)
            fetched += 1
            print(f"  [{i+1}/{len(recent)}] {date} {sport:15s} {name:30s} — {total_points:,} data points", flush=True)
        else:
            failed += 1
            print(f"  [{i+1}/{len(recent)}] {date} {sport:15s} {name:30s} — NO STREAM DATA", flush=True)

    # Summary
    print(f"\n{'=' * 60}")
    print(f"  COMPLETE!")
    print(f"  Fetched: {fetched} | Cached (skipped): {skipped} | Failed: {failed}")
    print(f"  Total files: {len(os.listdir(OUTPUT_DIR))}")
    total_size = sum(os.path.getsize(os.path.join(OUTPUT_DIR, f)) for f in os.listdir(OUTPUT_DIR) if f.endswith('.json'))
    print(f"  Total size: {total_size / 1024 / 1024:.1f} MB")
    print(f"  Location: {OUTPUT_DIR}/")
    print(f"{'=' * 60}", flush=True)


if __name__ == '__main__':
    main()
