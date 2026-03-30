import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { z } from 'zod';
import type { StravaClient } from '../strava-client.js';
import { formatDistance } from './format.js';

export function registerRouteTools(server: McpServer, client: StravaClient) {
  server.tool(
    'list_routes',
    'List the authenticated athlete\'s saved routes with distance, elevation, and type.',
    {
      page: z.number().optional().default(1).describe('Page number (default 1)'),
      per_page: z.number().optional().default(30).describe('Routes per page (default 30)'),
    },
    async ({ page, per_page }) => {
      try {
        const athlete = await client.getAthlete();
        const routes = await client.listRoutes(athlete.id, { page: page ?? 1, per_page: per_page ?? 30 });

        if (routes.length === 0) {
          return { content: [{ type: 'text' as const, text: 'No routes found.' }] };
        }

        const typeMap: Record<number, string> = { 1: 'Ride', 2: 'Run', 3: 'Walk' };
        const subTypeMap: Record<number, string> = { 1: 'Road', 2: 'MTB', 3: 'CX', 4: 'Trail', 5: 'Mixed' };

        const lines = [
          `## Routes (${routes.length})\n`,
          '| Name | Type | Distance | Elevation | Starred |',
          '|------|------|----------|-----------|---------|',
        ];

        for (const r of routes) {
          const type = typeMap[r.type] || `Type ${r.type}`;
          const subType = subTypeMap[r.sub_type] || '';
          const fullType = subType ? `${type} (${subType})` : type;
          lines.push(`| ${r.name} | ${fullType} | ${formatDistance(r.distance)} | +${Math.round(r.elevation_gain)}m | ${r.starred ? 'Yes' : '-'} |`);
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
    'export_route_gpx',
    'Export a Strava route as GPX XML data for use in GPS devices or mapping tools.',
    {
      route_id: z.number().describe('The Strava route ID'),
    },
    async ({ route_id }) => {
      try {
        const gpx = await client.exportRouteGpx(route_id);
        return {
          content: [{ type: 'text' as const, text: gpx }],
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
