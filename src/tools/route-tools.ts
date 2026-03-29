import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { z } from 'zod';
import type { StravaClient } from '../strava-client.js';
import { loadTokens } from '../config.js';

function formatDistance(meters: number): string {
  if (meters >= 1000) return `${(meters / 1000).toFixed(2)} km`;
  return `${Math.round(meters)} m`;
}

const ROUTE_TYPES: Record<number, string> = { 1: 'Ride', 2: 'Run', 3: 'Walk' };
const SUB_TYPES: Record<number, string> = { 1: 'Road', 2: 'MTB', 3: 'CX', 4: 'Trail', 5: 'Mixed' };

export function registerRouteTools(server: McpServer, client: StravaClient) {
  server.tool(
    'list_routes',
    'List your saved Strava routes with name, distance, elevation, and type.',
    {
      page: z.number().optional().default(1).describe('Page number (default 1)'),
      per_page: z.number().optional().default(30).describe('Results per page (default 30)'),
    },
    async ({ page, per_page }) => {
      try {
        const tokens = loadTokens();
        let athleteId: number;
        if (tokens?.athleteId) {
          athleteId = tokens.athleteId;
        } else {
          const athlete = await client.getAthlete();
          athleteId = athlete.id;
        }

        const routes = await client.listRoutes(athleteId, {
          page: page ?? 1,
          per_page: per_page ?? 30,
        });

        if (routes.length === 0) {
          return { content: [{ type: 'text' as const, text: 'No routes found.' }] };
        }

        const lines = [
          `## Routes (${routes.length})\n`,
          '| Name | Distance | Elevation | Type | Starred |',
          '|------|----------|-----------|------|---------|',
        ];

        for (const r of routes) {
          const type = ROUTE_TYPES[r.type] || 'Other';
          const subType = SUB_TYPES[r.sub_type] || '';
          const typeStr = subType ? `${type} (${subType})` : type;
          lines.push(`| ${r.name} | ${formatDistance(r.distance)} | +${Math.round(r.elevation_gain)}m | ${typeStr} | ${r.starred ? 'Yes' : 'No'} |`);
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
    'export_route_gpx',
    'Export a Strava route as GPX XML data. Useful for analyzing route waypoints or saving to a file.',
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
