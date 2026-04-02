import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { z } from 'zod';
import type { StravaClient } from './strava-client.js';

function json(data: unknown) {
  return { content: [{ type: 'text' as const, text: JSON.stringify(data, null, 2) }] };
}

function error(err: unknown) {
  return { content: [{ type: 'text' as const, text: `Error: ${(err as Error).message}` }], isError: true as const };
}

export function registerAllTools(server: McpServer, client: StravaClient): void {
  server.tool(
    'get_athlete',
    'Get the authenticated athlete\'s Strava profile.',
    {},
    async () => {
      try { return json(await client.getAthlete()); }
      catch (e) { return error(e); }
    }
  );

  server.tool(
    'get_athlete_stats',
    'Get running, cycling, and swimming statistics (recent, YTD, all-time totals).',
    {
      athlete_id: z.number().optional().describe('Athlete ID. Omit to use the authenticated athlete.'),
    },
    async ({ athlete_id }) => {
      try {
        const id = athlete_id ?? await client.getAthleteId();
        return json(await client.getAthleteStats(id));
      } catch (e) { return error(e); }
    }
  );

  server.tool(
    'get_athlete_zones',
    'Get the athlete\'s heart rate and power training zones.',
    {},
    async () => {
      try { return json(await client.getAthleteZones()); }
      catch (e) { return error(e); }
    }
  );

  server.tool(
    'list_activities',
    'List recent Strava activities with pagination and optional date filters.',
    {
      page: z.number().optional().describe('Page number (default 1)'),
      per_page: z.number().optional().describe('Activities per page (default 30, max 200)'),
      before: z.string().optional().describe('Only activities before this date (ISO format)'),
      after: z.string().optional().describe('Only activities after this date (ISO format)'),
    },
    async ({ page, per_page, before, after }) => {
      try {
        const params: Record<string, number> = { page: page ?? 1, per_page: per_page ?? 30 };
        if (before) params.before = Math.floor(new Date(before).getTime() / 1000);
        if (after) params.after = Math.floor(new Date(after).getTime() / 1000);
        return json(await client.listActivities(params));
      } catch (e) { return error(e); }
    }
  );

  server.tool(
    'get_activity',
    'Get full details of a Strava activity including splits, segment efforts, best efforts, and gear.',
    {
      activity_id: z.number().describe('The Strava activity ID'),
      include_all_efforts: z.boolean().optional().describe('Include all segment efforts (default false)'),
    },
    async ({ activity_id, include_all_efforts }) => {
      try { return json(await client.getActivity(activity_id, include_all_efforts)); }
      catch (e) { return error(e); }
    }
  );

  server.tool(
    'get_activity_streams',
    'Get time-series data for an activity (heart rate, power, cadence, GPS, altitude, speed, etc.).',
    {
      activity_id: z.number().describe('The Strava activity ID'),
      stream_types: z.array(z.enum([
        'time', 'distance', 'latlng', 'altitude', 'heartrate',
        'cadence', 'watts', 'temp', 'moving', 'grade_smooth', 'velocity_smooth',
      ])).describe('Stream types to fetch'),
      resolution: z.enum(['low', 'medium', 'high']).optional().describe('Data resolution: low (~100 points), medium (~1000), high (~10000)'),
    },
    async ({ activity_id, stream_types, resolution }) => {
      try { return json(await client.getActivityStreams(activity_id, stream_types, resolution)); }
      catch (e) { return error(e); }
    }
  );

  server.tool(
    'get_activity_laps',
    'Get lap data for a Strava activity.',
    {
      activity_id: z.number().describe('The Strava activity ID'),
    },
    async ({ activity_id }) => {
      try { return json(await client.getActivityLaps(activity_id)); }
      catch (e) { return error(e); }
    }
  );

  server.tool(
    'list_starred_segments',
    'List the authenticated athlete\'s starred segments.',
    {
      page: z.number().optional().describe('Page number (default 1)'),
      per_page: z.number().optional().describe('Segments per page (default 30)'),
    },
    async ({ page, per_page }) => {
      try { return json(await client.listStarredSegments({ page: page ?? 1, per_page: per_page ?? 30 })); }
      catch (e) { return error(e); }
    }
  );

  server.tool(
    'get_segment',
    'Get detailed information about a Strava segment.',
    {
      segment_id: z.number().describe('The Strava segment ID'),
    },
    async ({ segment_id }) => {
      try { return json(await client.getSegment(segment_id)); }
      catch (e) { return error(e); }
    }
  );

  server.tool(
    'list_routes',
    'List the authenticated athlete\'s saved routes.',
    {
      page: z.number().optional().describe('Page number (default 1)'),
      per_page: z.number().optional().describe('Routes per page (default 30)'),
    },
    async ({ page, per_page }) => {
      try {
        const id = await client.getAthleteId();
        return json(await client.listRoutes(id, { page: page ?? 1, per_page: per_page ?? 30 }));
      } catch (e) { return error(e); }
    }
  );

  server.tool(
    'export_route_gpx',
    'Export a Strava route as GPX XML.',
    {
      route_id: z.number().describe('The Strava route ID'),
    },
    async ({ route_id }) => {
      try {
        return { content: [{ type: 'text' as const, text: await client.exportRouteGpx(route_id) }] };
      } catch (e) { return error(e); }
    }
  );
}
