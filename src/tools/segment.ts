import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { z } from 'zod';
import type { StravaClient } from '../strava-client.js';
import { formatDistance, formatDuration } from './format.js';

export function registerSegmentTools(server: McpServer, client: StravaClient) {
  server.tool(
    'list_starred_segments',
    'List the authenticated athlete\'s starred/saved segments with distance, grade, and climb category.',
    {
      page: z.number().optional().default(1).describe('Page number (default 1)'),
      per_page: z.number().optional().default(30).describe('Segments per page (default 30)'),
    },
    async ({ page, per_page }) => {
      try {
        const segments = await client.listStarredSegments({ page: page ?? 1, per_page: per_page ?? 30 });

        if (segments.length === 0) {
          return { content: [{ type: 'text' as const, text: 'No starred segments found.' }] };
        }

        const lines = [
          `## Starred Segments (${segments.length})\n`,
          '| Name | Type | Distance | Avg Grade | Max Grade | Climb Cat | City |',
          '|------|------|----------|-----------|-----------|-----------|------|',
        ];

        for (const s of segments) {
          const climbCat = s.climb_category > 0 ? `Cat ${s.climb_category}` : '-';
          const city = s.city || '-';
          lines.push(`| ${s.name} | ${s.activity_type} | ${formatDistance(s.distance)} | ${s.average_grade}% | ${s.maximum_grade}% | ${climbCat} | ${city} |`);
        }

        return { content: [{ type: 'text' as const, text: lines.join('\n') }] };
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
    'Get detailed information about a specific Strava segment including elevation, grades, effort counts, and your personal records.',
    {
      segment_id: z.number().describe('The Strava segment ID'),
    },
    async ({ segment_id }) => {
      try {
        const s = await client.getSegment(segment_id);
        const climbCat = s.climb_category > 0 ? `Category ${s.climb_category}` : 'Not categorized';

        const lines = [
          `## ${s.name}`,
          `**${s.activity_type}** segment`,
          '',
          `Distance: ${formatDistance(s.distance)}`,
          `Elevation: ${Math.round(s.elevation_low)}m - ${Math.round(s.elevation_high)}m (+${Math.round(s.total_elevation_gain)}m)`,
          `Average grade: ${s.average_grade}%`,
          `Maximum grade: ${s.maximum_grade}%`,
          `Climb category: ${climbCat}`,
          s.city || s.state || s.country
            ? `Location: ${[s.city, s.state, s.country].filter(Boolean).join(', ')}`
            : null,
          '',
          `Total efforts: ${s.effort_count.toLocaleString()}`,
          `Unique athletes: ${s.athlete_count.toLocaleString()}`,
          `Stars: ${s.star_count.toLocaleString()}`,
        ];

        if (s.athlete_segment_stats) {
          lines.push('');
          lines.push('### Your Stats');
          lines.push(`Efforts: ${s.athlete_segment_stats.effort_count}`);
          if (s.athlete_segment_stats.pr_elapsed_time) {
            lines.push(`PR: ${formatDuration(s.athlete_segment_stats.pr_elapsed_time)}`);
          }
          if (s.athlete_segment_stats.pr_date) {
            lines.push(`PR date: ${new Date(s.athlete_segment_stats.pr_date).toLocaleDateString()}`);
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
}
