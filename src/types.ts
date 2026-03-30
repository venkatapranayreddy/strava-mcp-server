export interface StravaAthlete {
  id: number;
  username: string | null;
  firstname: string;
  lastname: string;
  city: string | null;
  state: string | null;
  country: string | null;
  sex: string | null;
  weight: number | null;
  ftp: number | null;
  profile: string;
  profile_medium: string;
  follower_count?: number;
  friend_count?: number;
  created_at: string;
  updated_at: string;
}

export interface StravaActivity {
  id: number;
  name: string;
  type: string;
  sport_type: string;
  distance: number;
  moving_time: number;
  elapsed_time: number;
  total_elevation_gain: number;
  start_date: string;
  start_date_local: string;
  timezone: string;
  average_speed: number;
  max_speed: number;
  average_heartrate?: number;
  max_heartrate?: number;
  average_watts?: number;
  max_watts?: number;
  weighted_average_watts?: number;
  kilojoules?: number;
  suffer_score?: number;
  calories?: number;
  achievement_count: number;
  kudos_count: number;
  comment_count: number;
  gear_id: string | null;
  has_heartrate: boolean;
  average_cadence?: number;
  map?: {
    id: string;
    summary_polyline: string | null;
    polyline?: string | null;
  };
}

export interface StravaActivityDetailed extends StravaActivity {
  description: string | null;
  device_name: string | null;
  embed_token: string;
  segment_efforts?: StravaSegmentEffort[];
  splits_metric?: StravaSplit[];
  splits_standard?: StravaSplit[];
  best_efforts?: StravaBestEffort[];
  laps?: StravaLap[];
  gear?: {
    id: string;
    name: string;
    distance: number;
  };
}

export interface StravaSegmentEffort {
  id: number;
  name: string;
  elapsed_time: number;
  moving_time: number;
  distance: number;
  start_date: string;
  average_heartrate?: number;
  max_heartrate?: number;
  average_watts?: number;
  segment: {
    id: number;
    name: string;
    distance: number;
    average_grade: number;
    maximum_grade: number;
    climb_category: number;
  };
  pr_rank: number | null;
}

export interface StravaSplit {
  distance: number;
  elapsed_time: number;
  elevation_difference: number;
  moving_time: number;
  split: number;
  average_speed: number;
  average_heartrate?: number;
  pace_zone: number;
}

export interface StravaBestEffort {
  id: number;
  name: string;
  elapsed_time: number;
  moving_time: number;
  distance: number;
  start_date: string;
  pr_rank: number | null;
}

export interface StravaLap {
  id: number;
  name: string;
  elapsed_time: number;
  moving_time: number;
  distance: number;
  start_index: number;
  end_index: number;
  average_speed: number;
  max_speed: number;
  average_heartrate?: number;
  max_heartrate?: number;
  average_cadence?: number;
  average_watts?: number;
  lap_index: number;
  split: number;
  pace_zone?: number;
}

export interface StravaStats {
  biggest_ride_distance: number | null;
  biggest_climb_elevation_gain: number | null;
  recent_ride_totals: StravaTotals;
  recent_run_totals: StravaTotals;
  recent_swim_totals: StravaTotals;
  ytd_ride_totals: StravaTotals;
  ytd_run_totals: StravaTotals;
  ytd_swim_totals: StravaTotals;
  all_ride_totals: StravaTotals;
  all_run_totals: StravaTotals;
  all_swim_totals: StravaTotals;
}

export interface StravaTotals {
  count: number;
  distance: number;
  moving_time: number;
  elapsed_time: number;
  elevation_gain: number;
  achievement_count?: number;
}

export interface StravaStream {
  type: string;
  data: number[] | [number, number][];
  series_type: string;
  original_size: number;
  resolution: string;
}

export interface StravaZones {
  heart_rate?: {
    custom_zones: boolean;
    zones: StravaZoneRange[];
  };
  power?: {
    zones: StravaZoneRange[];
  };
}

export interface StravaZoneRange {
  min: number;
  max: number;
}

export interface StravaSegment {
  id: number;
  name: string;
  activity_type: string;
  distance: number;
  average_grade: number;
  maximum_grade: number;
  elevation_high: number;
  elevation_low: number;
  climb_category: number;
  city: string | null;
  state: string | null;
  country: string | null;
  total_elevation_gain: number;
  effort_count: number;
  athlete_count: number;
  star_count: number;
  athlete_segment_stats?: {
    pr_elapsed_time: number | null;
    pr_date: string | null;
    effort_count: number;
  };
}

export interface StravaRoute {
  id: number;
  name: string;
  description: string | null;
  distance: number;
  elevation_gain: number;
  type: number;
  sub_type: number;
  starred: boolean;
  timestamp: number;
  map: {
    summary_polyline: string | null;
  };
}
