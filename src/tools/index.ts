import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import type { StravaClient } from '../strava-client.js';
import { registerAuthTools } from './auth-tools.js';
import { registerAthleteTools } from './athlete-tools.js';
import { registerActivityTools } from './activity-tools.js';
import { registerSegmentTools } from './segment-tools.js';
import { registerRouteTools } from './route-tools.js';

export function registerAllTools(server: McpServer, client: StravaClient) {
  registerAuthTools(server);
  registerAthleteTools(server, client);
  registerActivityTools(server, client);
  registerSegmentTools(server, client);
  registerRouteTools(server, client);
}
