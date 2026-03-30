import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { z } from 'zod';
import type { StravaClient } from '../strava-client.js';
import type { StravaActivity, StravaStream } from '../types.js';
import { formatDuration, formatDistance, formatPace } from './format.js';

function formatActivityRow(a: StravaActivity): string {
  const date = new Date(a.start_date_local).toLocaleDateString();
  const dist = formatDistance(a.distance);
  const time = formatDuration(a.moving_time);
  const pace = formatPace(a.average_speed, a.type);
  const hr = a.average_heartrate ? `${Math.round(a.average_heartrate)} bpm` : '-';
  const elev = a.total_elevation_gain > 0 ? `${Math.round(a.total_elevation_gain)}m` : '-';
  return `| ${date} | ${a.name} | ${a.sport_type} | ${dist} | ${time} | ${pace} | ${hr} | ${elev} |`;
}

function summarizeStream(stream: StravaStream): string {
  const data = stream.data as number[];
  if (!data || data.length === 0) return `${stream.type}: no data`;

  const min = Math.min(...data);
  const max = Math.max(...data);
  const avg = data.reduce((a, b) => a + b, 0) / data.length;

  let summary = `${stream.type}: min=${min.toFixed(1)}, max=${max.toFixed(1)}, avg=${avg.toFixed(1)} (${data.length} points)`;

  if (data.length > 100) {
    const step = Math.floor(data.length / 100);
    const sampled = data.filter((_, i) => i % step === 0).slice(0, 100);
    summary += `\nSampled (every ${step}th): [${sampled.map(v => v.toFixed(1)).join(', ')}]`;
  } else {
    summary += `\nData: [${data.map(v => typeof v === 'number' ? v.toFixed(1) : String(v)).join(', ')}]`;
  }

  return summary;
}

function summarizeLatLngStream(stream: StravaStream): string {
  const data = stream.data as [number, number][];
  if (!data || data.length === 0) return 'latlng: no data';

  const lats = data.map(p => p[0]);
  const lngs = data.map(p => p[1]);

  return `latlng: ${data.length} GPS points, lat range [${Math.min(...lats).toFixed(4)}, ${Math.max(...lats).toFixed(4)}], lng range [${Math.min(...lngs).toFixed(4)}, ${Math.max(...lngs).toFixed(4)}]`;
}

export function registerActivityTools(server: McpServer, client: StravaClient) {
  server.tool(
    'list_activities',
    'List recent Strava activities with pagination and optional date/sport filters. Returns a formatted table with date, name, type, distance, time, pace, HR, and elevation.',
    {
      page: z.number().optional().default(1).describe('Page number (default 1)'),
      per_page: z.number().optional().default(30).describe('Activities per page (default 30, max 200)'),
      before: z.string().optional().describe('Only activities before this date (ISO format, e.g. 2026-03-01)'),
      after: z.string().optional().describe('Only activities after this date (ISO format, e.g. 2026-01-01)'),
      sport_type: z.string().optional().describe('Filter by sport type (e.g. Run, Ride, Swim, Walk, Hike, WeightTraining)'),
    },
    async ({ page, per_page, before, after, sport_type }) => {
      try {
        const params: Record<string, number> = { page: page ?? 1, per_page: per_page ?? 30 };
        if (before) params.before = Math.floor(new Date(before).getTime() / 1000);
        if (after) params.after = Math.floor(new Date(after).getTime() / 1000);

        let activities = await client.listActivities(params);

        if (sport_type) {
          activities = activities.filter(a =>
            a.sport_type.toLowerCase() === sport_type.toLowerCase() ||
            a.type.toLowerCase() === sport_type.toLowerCase()
          );
        }

        if (activities.length === 0) {
          return { content: [{ type: 'text' as const, text: 'No activities found matching the criteria.' }] };
        }

        const header = '| Date | Name | Type | Distance | Time | Pace/Speed | Avg HR | Elevation |';
        const divider = '|------|------|------|----------|------|------------|--------|-----------|';
        const rows = activities.map(formatActivityRow);

        const text = `Found ${activities.length} activities (page ${page ?? 1}):\n\n${header}\n${divider}\n${rows.join('\n')}`;
        return { content: [{ type: 'text' as const, text }] };
      } catch (error) {
        return {
          content: [{ type: 'text' as const, text: `Error: ${(error as Error).message}` }],
          isError: true,
        };
      }
    }
  );

  server.tool(
    'get_activity',
    'Get full details of a single Strava activity including description, splits, segment efforts, best efforts, and gear.',
    {
      activity_id: z.number().describe('The Strava activity ID'),
      include_all_efforts: z.boolean().optional().default(false).describe('Include all segment efforts (default false)'),
    },
    async ({ activity_id, include_all_efforts }) => {
      try {
        const a = await client.getActivity(activity_id, include_all_efforts ?? false);
        const lines = [
          `## ${a.name}`,
          `**${a.sport_type}** on ${new Date(a.start_date_local).toLocaleString()}`,
          a.description ? `\n${a.description}` : null,
          '',
          `Distance: ${formatDistance(a.distance)}`,
          `Moving time: ${formatDuration(a.moving_time)}`,
          `Elapsed time: ${formatDuration(a.elapsed_time)}`,
          `Pace/Speed: ${formatPace(a.average_speed, a.type)} (max: ${formatPace(a.max_speed, a.type)})`,
          `Elevation: +${Math.round(a.total_elevation_gain)}m`,
          a.has_heartrate ? `Heart rate: avg ${Math.round(a.average_heartrate!)} / max ${Math.round(a.max_heartrate!)} bpm` : null,
          a.average_watts ? `Power: avg ${Math.round(a.average_watts)}w` + (a.max_watts ? ` / max ${a.max_watts}w` : '') + (a.weighted_average_watts ? ` (NP: ${a.weighted_average_watts}w)` : '') : null,
          a.average_cadence ? `Cadence: avg ${Math.round(a.average_cadence)}` : null,
          a.calories ? `Calories: ${Math.round(a.calories)}` : null,
          a.kilojoules ? `Energy: ${Math.round(a.kilojoules)} kJ` : null,
          a.suffer_score ? `Suffer score: ${a.suffer_score}` : null,
          a.device_name ? `Device: ${a.device_name}` : null,
          a.gear ? `Gear: ${a.gear.name}` : null,
          `Kudos: ${a.kudos_count} | Comments: ${a.comment_count} | Achievements: ${a.achievement_count}`,
        ];

        if (a.best_efforts && a.best_efforts.length > 0) {
          lines.push('\n### Best Efforts');
          for (const e of a.best_efforts) {
            const pr = e.pr_rank ? ` (PR #${e.pr_rank})` : '';
            lines.push(`${e.name}: ${formatDuration(e.moving_time)}${pr}`);
          }
        }

        if (a.splits_metric && a.splits_metric.length > 0) {
          lines.push('\n### Splits (per km)');
          lines.push('| KM | Time | Pace | HR | Elev |');
          lines.push('|----|------|------|----|------|');
          for (const s of a.splits_metric) {
            const pace = formatPace(s.average_speed, a.type);
            const hr = s.average_heartrate ? `${Math.round(s.average_heartrate)}` : '-';
            lines.push(`| ${s.split} | ${formatDuration(s.moving_time)} | ${pace} | ${hr} | ${s.elevation_difference > 0 ? '+' : ''}${Math.round(s.elevation_difference)}m |`);
          }
        }

        if (a.segment_efforts && a.segment_efforts.length > 0) {
          lines.push(`\n### Segment Efforts (${a.segment_efforts.length} total)`);
          const top = a.segment_efforts.slice(0, 10);
          for (const e of top) {
            const pr = e.pr_rank ? ` PR #${e.pr_rank}` : '';
            lines.push(`- ${e.name}: ${formatDuration(e.elapsed_time)}, ${formatDistance(e.distance)}, ${e.segment.average_grade}% avg grade${pr}`);
          }
          if (a.segment_efforts.length > 10) {
            lines.push(`... and ${a.segment_efforts.length - 10} more segments`);
          }
        }

        return {
          content: [{ type: 'text' as const, text: lines.filter(x => x !== null).join('\n') }],
        };
      } catch (error) {
        return {
          content: [{ type: 'text' as const, text: `Error: ${(error as Error).message}` }],
          isError: true,
        };
      }
    }
  );

  server.tool(
    'get_activity_streams',
    'Get detailed stream/time-series data for an activity (heart rate, power, cadence, GPS, altitude, speed, etc.). Returns summary statistics and sampled data by default. Set raw=true for complete data arrays.',
    {
      activity_id: z.number().describe('The Strava activity ID'),
      stream_types: z.array(z.enum([
        'time', 'distance', 'latlng', 'altitude', 'heartrate',
        'cadence', 'watts', 'temp', 'moving', 'grade_smooth', 'velocity_smooth',
      ])).describe('Stream types to fetch (e.g. ["heartrate", "watts", "cadence"])'),
      resolution: z.enum(['low', 'medium', 'high']).optional().describe('Data resolution: low (~100 points), medium (~1000), high (~10000). Default is full resolution.'),
      raw: z.boolean().optional().default(false).describe('If true, return complete raw data arrays instead of summaries.'),
    },
    async ({ activity_id, stream_types, resolution, raw }) => {
      try {
        const streams = await client.getActivityStreams(activity_id, stream_types, resolution);

        if (!streams || streams.length === 0) {
          return { content: [{ type: 'text' as const, text: 'No stream data available for this activity with the requested types.' }] };
        }

        const lines = [`## Activity ${activity_id} — Stream Data\n`];

        for (const stream of streams) {
          if (raw) {
            lines.push(`### ${stream.type} (${(stream.data as number[]).length} points)`);
            lines.push(JSON.stringify(stream.data));
            lines.push('');
          } else {
            if (stream.type === 'latlng') {
              lines.push(summarizeLatLngStream(stream));
            } else {
              lines.push(summarizeStream(stream));
            }
            lines.push('');
          }
        }

        return {
          content: [{ type: 'text' as const, text: lines.join('\n') }],
        };
      } catch (error) {
        return {
          content: [{ type: 'text' as const, text: `Error: ${(error as Error).message}` }],
          isError: true,
        };
      }
    }
  );

  server.tool(
    'get_activity_laps',
    'Get lap data for a Strava activity. Returns a table with lap number, distance, time, pace, heart rate, and cadence.',
    {
      activity_id: z.number().describe('The Strava activity ID'),
    },
    async ({ activity_id }) => {
      try {
        const laps = await client.getActivityLaps(activity_id);

        if (!laps || laps.length === 0) {
          return { content: [{ type: 'text' as const, text: 'No lap data available for this activity.' }] };
        }

        const lines = [
          `## Laps for Activity ${activity_id} (${laps.length} laps)\n`,
          '| Lap | Distance | Moving Time | Pace/Speed | Avg HR | Max HR | Cadence |',
          '|-----|----------|-------------|------------|--------|--------|---------|',
        ];

        for (const lap of laps) {
          const dist = formatDistance(lap.distance);
          const time = formatDuration(lap.moving_time);
          const pace = `${(lap.average_speed * 3.6).toFixed(1)} km/h`;
          const avgHr = lap.average_heartrate ? `${Math.round(lap.average_heartrate)}` : '-';
          const maxHr = lap.max_heartrate ? `${Math.round(lap.max_heartrate)}` : '-';
          const cadence = lap.average_cadence ? `${Math.round(lap.average_cadence)}` : '-';
          lines.push(`| ${lap.lap_index} | ${dist} | ${time} | ${pace} | ${avgHr} | ${maxHr} | ${cadence} |`);
        }

        return {
          content: [{ type: 'text' as const, text: lines.join('\n') }],
        };
      } catch (error) {
        return {
          content: [{ type: 'text' as const, text: `Error: ${(error as Error).message}` }],
          isError: true,
        };
      }
    }
  );
}
