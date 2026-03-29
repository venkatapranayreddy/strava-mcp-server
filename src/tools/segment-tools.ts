import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { z } from 'zod';
import type { StravaClient } from '../strava-client.js';

function formatDistance(meters: number): string {
  if (meters >= 1000) return `${(meters / 1000).toFixed(2)} km`;
  return `${Math.round(meters)} m`;
}

function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}h ${m}m ${s}s`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

export function registerSegmentTools(server: McpServer, client: StravaClient) {
  server.tool(
    'list_starred_segments',
    'List your starred/saved Strava segments with name, distance, grade, and location.',
    {
      page: z.number().optional().default(1).describe('Page number (default 1)'),
      per_page: z.number().optional().default(30).describe('Results per page (default 30)'),
    },
    async ({ page, per_page }) => {
      try {
        const segments = await client.listStarredSegments({
          page: page ?? 1,
          per_page: per_page ?? 30,
        });

        if (segments.length === 0) {
          return { content: [{ type: 'text' as const, text: 'No starred segments found.' }] };
        }

        const lines = [
          `## Starred Segments (${segments.length})\n`,
          '| Name | Distance | Avg Grade | Max Grade | Category | Location |',
          '|------|----------|-----------|-----------|----------|----------|',
        ];

        const catNames = ['NC', '4', '3', '2', '1', 'HC'];
        for (const s of segments) {
          const cat = s.climb_category > 0 ? `Cat ${catNames[s.climb_category] || s.climb_category}` : 'Flat';
          const location = [s.city, s.state].filter(Boolean).join(', ') || '-';
          lines.push(`| ${s.name} | ${formatDistance(s.distance)} | ${s.average_grade.toFixed(1)}% | ${s.maximum_grade.toFixed(1)}% | ${cat} | ${location} |`);
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
    'get_segment',
    'Get detailed information about a Strava segment including elevation profile, grade, athlete stats, and effort counts.',
    {
      segment_id: z.number().describe('The Strava segment ID'),
    },
    async ({ segment_id }) => {
      try {
        const s = await client.getSegment(segment_id);
        const catNames = ['NC', '4', '3', '2', '1', 'HC'];
        const cat = s.climb_category > 0 ? `Cat ${catNames[s.climb_category] || s.climb_category}` : 'Flat';
        const location = [s.city, s.state, s.country].filter(Boolean).join(', ') || 'Unknown';

        const lines = [
          `## ${s.name}`,
          `Type: ${s.activity_type} | Category: ${cat}`,
          `Location: ${location}`,
          '',
          `Distance: ${formatDistance(s.distance)}`,
          `Average grade: ${s.average_grade.toFixed(1)}%`,
          `Maximum grade: ${s.maximum_grade.toFixed(1)}%`,
          `Elevation: ${Math.round(s.elevation_low)}m → ${Math.round(s.elevation_high)}m (+${Math.round(s.total_elevation_gain)}m)`,
          '',
          `Total efforts: ${s.effort_count.toLocaleString()}`,
          `Unique athletes: ${s.athlete_count.toLocaleString()}`,
          `Stars: ${s.star_count.toLocaleString()}`,
        ];

        if (s.athlete_segment_stats) {
          lines.push('');
          lines.push('### Your Stats');
          if (s.athlete_segment_stats.pr_elapsed_time) {
            lines.push(`PR: ${formatDuration(s.athlete_segment_stats.pr_elapsed_time)} (${s.athlete_segment_stats.pr_date || 'unknown date'})`);
          }
          lines.push(`Your efforts: ${s.athlete_segment_stats.effort_count}`);
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
