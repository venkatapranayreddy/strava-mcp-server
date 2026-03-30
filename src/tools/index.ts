import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import type { StravaClient } from '../strava-client.js';
import { registerAthleteTools } from './athlete.js';
import { registerActivityTools } from './activity.js';
import { registerSegmentTools } from './segment.js';
import { registerRouteTools } from './route.js';

export function registerAllTools(server: McpServer, client: StravaClient): void {
  registerAthleteTools(server, client);
  registerActivityTools(server, client);
  registerSegmentTools(server, client);
  registerRouteTools(server, client);
}
