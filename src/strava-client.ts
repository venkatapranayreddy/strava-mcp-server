import type {
  StravaAthlete,
  StravaActivity,
  StravaActivityDetailed,
  StravaStats,
  StravaStream,
  StravaLap,
  StravaZones,
  StravaSegment,
  StravaRoute,
} from './types.js';

export class StravaClient {
  private baseUrl = 'https://www.strava.com/api/v3';
  private cachedAthleteId?: number;

  constructor(private getAccessToken: () => Promise<string>) {}

  async getAthleteId(): Promise<number> {
    if (!this.cachedAthleteId) {
      const athlete = await this.getAthlete();
      this.cachedAthleteId = athlete.id;
    }
    return this.cachedAthleteId;
  }

  private async request<T>(path: string, params?: Record<string, string | number | boolean | undefined>): Promise<T> {
    const token = await this.getAccessToken();
    const url = new URL(`${this.baseUrl}${path}`);

    if (params) {
      for (const [key, value] of Object.entries(params)) {
        if (value !== undefined && value !== null) {
          url.searchParams.set(key, String(value));
        }
      }
    }

    const response = await fetch(url.toString(), {
      headers: { Authorization: `Bearer ${token}` },
    });

    if (response.status === 429) {
      const retryAfter = response.headers.get('Retry-After');
      throw new Error(`Strava rate limit exceeded. Try again after ${retryAfter || '15'} minutes.`);
    }

    if (!response.ok) {
      const body = await response.text();
      throw new Error(`Strava API error ${response.status}: ${body}`);
    }

    return response.json() as Promise<T>;
  }

  private async requestRaw(path: string): Promise<string> {
    const token = await this.getAccessToken();
    const url = `${this.baseUrl}${path}`;

    const response = await fetch(url, {
      headers: { Authorization: `Bearer ${token}` },
    });

    if (!response.ok) {
      const body = await response.text();
      throw new Error(`Strava API error ${response.status}: ${body}`);
    }

    return response.text();
  }

  async getAthlete(): Promise<StravaAthlete> {
    return this.request<StravaAthlete>('/athlete');
  }

  async getAthleteStats(athleteId: number): Promise<StravaStats> {
    return this.request<StravaStats>(`/athletes/${athleteId}/stats`);
  }

  async getAthleteZones(): Promise<StravaZones> {
    return this.request<StravaZones>('/athlete/zones');
  }

  async listActivities(params: {
    page?: number;
    per_page?: number;
    before?: number;
    after?: number;
  }): Promise<StravaActivity[]> {
    return this.request<StravaActivity[]>('/athlete/activities', params as Record<string, number>);
  }

  async getActivity(id: number, includeAllEfforts?: boolean): Promise<StravaActivityDetailed> {
    return this.request<StravaActivityDetailed>(`/activities/${id}`, {
      include_all_efforts: includeAllEfforts,
    });
  }

  async getActivityStreams(id: number, keys: string[], resolution?: string): Promise<StravaStream[]> {
    return this.request<StravaStream[]>(`/activities/${id}/streams`, {
      keys: keys.join(','),
      key_by_type: true,
      ...(resolution ? { resolution } : {}),
    });
  }

  async getActivityLaps(id: number): Promise<StravaLap[]> {
    return this.request<StravaLap[]>(`/activities/${id}/laps`);
  }

  async getSegment(id: number): Promise<StravaSegment> {
    return this.request<StravaSegment>(`/segments/${id}`);
  }

  async listStarredSegments(params?: { page?: number; per_page?: number }): Promise<StravaSegment[]> {
    return this.request<StravaSegment[]>('/segments/starred', params as Record<string, number>);
  }

  async listRoutes(athleteId: number, params?: { page?: number; per_page?: number }): Promise<StravaRoute[]> {
    return this.request<StravaRoute[]>(`/athletes/${athleteId}/routes`, params as Record<string, number>);
  }

  async exportRouteGpx(id: number): Promise<string> {
    return this.requestRaw(`/routes/${id}/export_gpx`);
  }
}
