import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import type { StravaClient } from '../strava-client.js';
import { registerAthleteTools } from './athlete-tools.js';
import { registerActivityTools } from './activity-tools.js';
import { registerSegmentTools } from './segment-tools.js';
import { registerRouteTools } from './route-tools.js';

/**
 * Registers all tools except auth tools.
 * In remote/HTTP mode, OAuth is handled by the connector framework
 * so strava_auth and strava_auth_status are not needed.
 */
export function registerRemoteTools(server: McpServer, client: StravaClient) {
  registerAthleteTools(server, client);
  registerActivityTools(server, client);
  registerSegmentTools(server, client);
  registerRouteTools(server, client);
}
