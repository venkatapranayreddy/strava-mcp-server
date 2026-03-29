#!/usr/bin/env node

import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { loadConfig, loadTokens, saveTokens, isTokenExpired } from './config.js';
import { refreshAccessToken } from './auth.js';
import { StravaClient } from './strava-client.js';
import { registerAllTools } from './tools/index.js';

async function main() {
  const server = new McpServer({
    name: 'strava-mcp',
    version: '1.0.0',
  });

  // Create the access token provider that handles auto-refresh
  const getAccessToken = async (): Promise<string> => {
    const config = loadConfig();
    const tokens = loadTokens();

    if (!tokens) {
      throw new Error('Not authenticated. Please run the strava_auth tool first.');
    }

    if (isTokenExpired(tokens)) {
      const newTokens = await refreshAccessToken(config, tokens.refreshToken);
      if (!newTokens.athleteId && tokens.athleteId) {
        newTokens.athleteId = tokens.athleteId;
      }
      saveTokens(newTokens);
      return newTokens.accessToken;
    }

    return tokens.accessToken;
  };

  const client = new StravaClient(getAccessToken);
  registerAllTools(server, client);

  const transport = new StdioServerTransport();
  await server.connect(transport);
}

main().catch((error) => {
  console.error('Fatal error:', error);
  process.exit(1);
});
