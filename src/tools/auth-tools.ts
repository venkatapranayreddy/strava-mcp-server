import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { loadConfig, loadTokens, isTokenExpired } from '../config.js';
import { runOAuthFlow } from '../auth.js';

export function registerAuthTools(server: McpServer) {
  server.tool(
    'strava_auth',
    'Authenticate with Strava via OAuth2. Opens a browser URL for authorization. Run this first before using any other Strava tools.',
    {},
    async () => {
      try {
        const config = loadConfig();
        const { athleteName } = await runOAuthFlow(config);
        return {
          content: [{
            type: 'text' as const,
            text: `Successfully authenticated with Strava as ${athleteName}! You can now use all Strava tools.`,
          }],
        };
      } catch (error) {
        return {
          content: [{
            type: 'text' as const,
            text: `Authentication failed: ${(error as Error).message}`,
          }],
          isError: true,
        };
      }
    }
  );

  server.tool(
    'strava_auth_status',
    'Check if you are currently authenticated with Strava and whether the token is valid.',
    {},
    async () => {
      try {
        const tokens = loadTokens();
        if (!tokens) {
          return {
            content: [{
              type: 'text' as const,
              text: 'Not authenticated. Run strava_auth to connect your Strava account.',
            }],
          };
        }

        const expired = isTokenExpired(tokens);
        const expiresAt = new Date(tokens.expiresAt * 1000);
        const now = new Date();
        const hoursLeft = ((tokens.expiresAt * 1000 - now.getTime()) / 3600000).toFixed(1);

        if (expired) {
          return {
            content: [{
              type: 'text' as const,
              text: `Authenticated (athlete ID: ${tokens.athleteId || 'unknown'}) but token expired at ${expiresAt.toLocaleString()}. It will be auto-refreshed on next API call.`,
            }],
          };
        }

        return {
          content: [{
            type: 'text' as const,
            text: `Authenticated (athlete ID: ${tokens.athleteId || 'unknown'}). Token valid for ${hoursLeft} more hours (expires ${expiresAt.toLocaleString()}).`,
          }],
        };
      } catch (error) {
        return {
          content: [{
            type: 'text' as const,
            text: `Error checking auth status: ${(error as Error).message}`,
          }],
          isError: true,
        };
      }
    }
  );
}
