#!/usr/bin/env node

import { randomUUID } from 'node:crypto';
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import { mcpAuthRouter } from '@modelcontextprotocol/sdk/server/auth/router.js';
import { requireBearerAuth } from '@modelcontextprotocol/sdk/server/auth/middleware/bearerAuth.js';
import { createMcpExpressApp } from '@modelcontextprotocol/sdk/server/express.js';
import { isInitializeRequest } from '@modelcontextprotocol/sdk/types.js';
import { StravaOAuthProvider } from './oauth-provider.js';
import { StravaClient } from './strava-client.js';
import { registerRemoteTools } from './tools/remote-tools.js';

import type { Request, Response } from 'express';

// ── Configuration ──────────────────────────────────────────────

const PORT = parseInt(process.env.PORT || '3000', 10);
const BASE_URL = (process.env.BASE_URL || `http://localhost:${PORT}`).replace(/\/+$/, '');
const STRAVA_CLIENT_ID = process.env.STRAVA_CLIENT_ID;
const STRAVA_CLIENT_SECRET = process.env.STRAVA_CLIENT_SECRET;

if (!STRAVA_CLIENT_ID || !STRAVA_CLIENT_SECRET) {
  console.error('STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET environment variables are required');
  process.exit(1);
}

// ── OAuth Provider ─────────────────────────────────────────────

const provider = new StravaOAuthProvider(STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, BASE_URL);

// ── Express App ────────────────────────────────────────────────

const app = createMcpExpressApp({ host: '0.0.0.0' });

// Mount OAuth endpoints: /authorize, /token, /register, /revoke, /.well-known/*
const issuerUrl = new URL(BASE_URL);
const resourceServerUrl = new URL(`${BASE_URL}/mcp`);
app.use(mcpAuthRouter({
  provider,
  issuerUrl,
  resourceServerUrl,
  scopesSupported: ['strava:read'],
  resourceName: 'Strava MCP Server',
}));

// Strava OAuth callback — intermediate redirect from Strava back to us
app.get('/oauth/strava-callback', async (req: Request, res: Response) => {
  try {
    const { code, state, error } = req.query as Record<string, string>;

    if (error) {
      res.status(400).send(`Strava authorization failed: ${error}`);
      return;
    }
    if (!code || !state) {
      res.status(400).send('Missing code or state from Strava callback');
      return;
    }

    const result = await provider.handleStravaCallback(code, state);
    res.redirect(result.redirectUri);
  } catch (err) {
    console.error('Strava callback error:', err);
    res.status(500).send(`OAuth error: ${(err as Error).message}`);
  }
});

// ── Bearer Auth Middleware for /mcp ────────────────────────────

const authMiddleware = requireBearerAuth({ verifier: provider, requiredScopes: [] });

// ── Session Management ─────────────────────────────────────────

const transports: Record<string, StreamableHTTPServerTransport> = {};

// Store the auth token per session so the StravaClient can resolve it
const sessionAuthTokens: Record<string, string> = {};

// ── MCP Endpoint Handlers ──────────────────────────────────────

app.post('/mcp', authMiddleware, async (req: Request, res: Response) => {
  const sessionId = req.headers['mcp-session-id'] as string | undefined;
  const authToken = (req as any).auth?.token as string | undefined;

  try {
    let transport: StreamableHTTPServerTransport;

    if (sessionId && transports[sessionId]) {
      transport = transports[sessionId];
    } else if (!sessionId && isInitializeRequest(req.body)) {
      // New session — create transport, server, and client
      transport = new StreamableHTTPServerTransport({
        sessionIdGenerator: () => randomUUID(),
        onsessioninitialized: (sid: string) => {
          transports[sid] = transport;
          if (authToken) {
            sessionAuthTokens[sid] = authToken;
          }
        },
      });

      transport.onclose = () => {
        const sid = transport.sessionId;
        if (sid) {
          delete transports[sid];
          delete sessionAuthTokens[sid];
        }
      };

      // Create a StravaClient whose token resolution goes through our OAuth provider
      const getAccessToken = async (): Promise<string> => {
        const sid = transport.sessionId;
        const mcpToken = sid ? sessionAuthTokens[sid] : authToken;
        if (!mcpToken) {
          throw new Error('No auth token available for this session');
        }
        return provider.getStravaAccessToken(mcpToken);
      };

      const server = new McpServer({
        name: 'strava-mcp',
        version: '1.0.0',
      });

      const client = new StravaClient(getAccessToken);
      registerRemoteTools(server, client);

      await server.connect(transport);
      await transport.handleRequest(req, res, req.body);
      return;
    } else {
      res.status(400).json({
        jsonrpc: '2.0',
        error: { code: -32000, message: 'Bad Request: No valid session ID provided' },
        id: null,
      });
      return;
    }

    await transport.handleRequest(req, res, req.body);
  } catch (error) {
    console.error('Error handling MCP request:', error);
    if (!res.headersSent) {
      res.status(500).json({
        jsonrpc: '2.0',
        error: { code: -32603, message: 'Internal server error' },
        id: null,
      });
    }
  }
});

app.get('/mcp', authMiddleware, async (req: Request, res: Response) => {
  const sessionId = req.headers['mcp-session-id'] as string | undefined;
  if (!sessionId || !transports[sessionId]) {
    res.status(400).send('Invalid or missing session ID');
    return;
  }
  await transports[sessionId].handleRequest(req, res);
});

app.delete('/mcp', authMiddleware, async (req: Request, res: Response) => {
  const sessionId = req.headers['mcp-session-id'] as string | undefined;
  if (!sessionId || !transports[sessionId]) {
    res.status(400).send('Invalid or missing session ID');
    return;
  }
  try {
    await transports[sessionId].handleRequest(req, res);
  } catch (error) {
    console.error('Error handling session termination:', error);
    if (!res.headersSent) {
      res.status(500).send('Error processing session termination');
    }
  }
});

// ── Health check ───────────────────────────────────────────────

app.get('/health', (_req: Request, res: Response) => {
  res.json({ status: 'ok', server: 'strava-mcp', version: '1.0.0' });
});

// ── Start ──────────────────────────────────────────────────────

app.listen(PORT, '0.0.0.0', () => {
  console.log(`Strava MCP HTTP Server listening on 0.0.0.0:${PORT}`);
  console.log(`Base URL: ${BASE_URL}`);
  console.log(`MCP endpoint: ${BASE_URL}/mcp`);
  console.log(`OAuth callback: ${BASE_URL}/oauth/strava-callback`);
});

// Graceful shutdown
process.on('SIGINT', async () => {
  console.log('Shutting down...');
  for (const sid in transports) {
    try {
      await transports[sid].close();
      delete transports[sid];
      delete sessionAuthTokens[sid];
    } catch (error) {
      console.error(`Error closing session ${sid}:`, error);
    }
  }
  process.exit(0);
});
