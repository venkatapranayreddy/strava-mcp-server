import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { z } from 'zod';
import type { StravaClient } from '../strava-client.js';
import { loadTokens } from '../config.js';
import type { StravaTotals } from '../types.js';

function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

function formatDistance(meters: number): string {
  if (meters >= 1000) return `${(meters / 1000).toFixed(1)} km`;
  return `${Math.round(meters)} m`;
}

function formatTotals(label: string, totals: StravaTotals): string {
  if (totals.count === 0) return `${label}: No activities`;
  return `${label}: ${totals.count} activities, ${formatDistance(totals.distance)}, ${formatDuration(totals.moving_time)}, ${formatDistance(totals.elevation_gain)} elevation`;
}

export function registerAthleteTools(server: McpServer, client: StravaClient) {
  server.tool(
    'get_athlete',
    'Get the authenticated Strava athlete profile including name, location, weight, FTP, and account details.',
    {},
    async () => {
      try {
        const athlete = await client.getAthlete();
        const lines = [
          `## ${athlete.firstname} ${athlete.lastname}`,
          athlete.username ? `Username: ${athlete.username}` : null,
          athlete.city || athlete.state || athlete.country
            ? `Location: ${[athlete.city, athlete.state, athlete.country].filter(Boolean).join(', ')}`
            : null,
          athlete.sex ? `Sex: ${athlete.sex}` : null,
          athlete.weight ? `Weight: ${athlete.weight} kg` : null,
          athlete.ftp ? `FTP: ${athlete.ftp} watts` : null,
          athlete.follower_count !== undefined ? `Followers: ${athlete.follower_count}` : null,
          athlete.friend_count !== undefined ? `Following: ${athlete.friend_count}` : null,
          `Member since: ${new Date(athlete.created_at).toLocaleDateString()}`,
        ];
        return {
          content: [{ type: 'text' as const, text: lines.filter(Boolean).join('\n') }],
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
    'get_athlete_stats',
    'Get running, cycling, and swimming statistics including recent, year-to-date, and all-time totals (activity count, distance, time, elevation).',
    {
      athlete_id: z.number().optional().describe('Athlete ID. Omit to use the currently authenticated athlete.'),
    },
    async ({ athlete_id }) => {
      try {
        let athleteId = athlete_id;
        if (!athleteId) {
          const tokens = loadTokens();
          if (tokens?.athleteId) {
            athleteId = tokens.athleteId;
          } else {
            const athlete = await client.getAthlete();
            athleteId = athlete.id;
          }
        }

        const stats = await client.getAthleteStats(athleteId);
        const lines = [
          '## Athlete Statistics\n',
          '### Running',
          formatTotals('Recent (4 weeks)', stats.recent_run_totals),
          formatTotals('Year to date', stats.ytd_run_totals),
          formatTotals('All time', stats.all_run_totals),
          '',
          '### Cycling',
          formatTotals('Recent (4 weeks)', stats.recent_ride_totals),
          formatTotals('Year to date', stats.ytd_ride_totals),
          formatTotals('All time', stats.all_ride_totals),
          stats.biggest_ride_distance ? `Longest ride: ${formatDistance(stats.biggest_ride_distance)}` : null,
          stats.biggest_climb_elevation_gain ? `Biggest climb: ${formatDistance(stats.biggest_climb_elevation_gain)}` : null,
          '',
          '### Swimming',
          formatTotals('Recent (4 weeks)', stats.recent_swim_totals),
          formatTotals('Year to date', stats.ytd_swim_totals),
          formatTotals('All time', stats.all_swim_totals),
        ];
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
    'get_athlete_zones',
    'Get the athlete\'s heart rate and power zone configuration (zone ranges and whether custom zones are set).',
    {},
    async () => {
      try {
        const zones = await client.getAthleteZones();
        const lines: string[] = ['## Training Zones\n'];

        if (zones.heart_rate) {
          lines.push('### Heart Rate Zones');
          lines.push(zones.heart_rate.custom_zones ? '(Custom zones)' : '(Default zones)');
          zones.heart_rate.zones.forEach((z, i) => {
            const max = z.max === -1 ? '∞' : `${z.max}`;
            lines.push(`Zone ${i + 1}: ${z.min} - ${max} bpm`);
          });
          lines.push('');
        }

        if (zones.power) {
          lines.push('### Power Zones');
          zones.power.zones.forEach((z, i) => {
            const max = z.max === -1 ? '∞' : `${z.max}`;
            lines.push(`Zone ${i + 1}: ${z.min} - ${max} watts`);
          });
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
