#!/usr/bin/env node

import { randomUUID } from 'node:crypto';
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import { mcpAuthRouter } from '@modelcontextprotocol/sdk/server/auth/router.js';
import { requireBearerAuth } from '@modelcontextprotocol/sdk/server/auth/middleware/bearerAuth.js';
import { createMcpExpressApp } from '@modelcontextprotocol/sdk/server/express.js';
import { isInitializeRequest } from '@modelcontextprotocol/sdk/types.js';
import { loadConfig } from './config.js';
import { StravaOAuthProvider } from './oauth-provider.js';
import { StravaClient } from './strava-client.js';
import { registerAllTools } from './tools.js';

import type { Request, Response } from 'express';

const VERSION = '2.0.0';

// ── Configuration ──────────────────────────────────────────────

const config = loadConfig();
const { stravaClientId, stravaClientSecret, port, baseUrl } = config;

// ── OAuth Provider ─────────────────────────────────────────────

const provider = new StravaOAuthProvider(stravaClientId, stravaClientSecret, baseUrl);
provider.startCleanupInterval();

// ── Express App ────────────────────────────────────────────────

const app = createMcpExpressApp({ host: '0.0.0.0' });
app.set('trust proxy', 1);

// Mount OAuth endpoints: /authorize, /token, /register, /revoke, /.well-known/*
const issuerUrl = new URL(baseUrl);
const resourceServerUrl = new URL(`${baseUrl}/mcp`);
app.use(mcpAuthRouter({
  provider,
  issuerUrl,
  resourceServerUrl,
  scopesSupported: ['strava:read'],
  resourceName: 'Strava MCP Server',
}));

// Strava OAuth callback
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
    res.status(500).send('Authorization failed. Please try again.');
  }
});

// ── Bearer Auth Middleware for /mcp ────────────────────────────

const authMiddleware = requireBearerAuth({ verifier: provider, requiredScopes: [] });

// ── Session Management ─────────────────────────────────────────

const transports: Record<string, StreamableHTTPServerTransport> = {};
const sessionAuthTokens: Record<string, string> = {};

// ── Request Logging ────────────────────────────────────────────

app.use('/mcp', (req: Request, _res: Response, next) => {
  const sessionId = req.headers['mcp-session-id'] as string | undefined;
  console.log(`[${new Date().toISOString()}] ${req.method} /mcp session=${sessionId ?? 'none'}`);
  next();
});

// ── MCP Endpoint Handlers ──────────────────────────────────────

app.post('/mcp', authMiddleware, async (req: Request, res: Response) => {
  const sessionId = req.headers['mcp-session-id'] as string | undefined;
  const authToken = (req as any).auth?.token as string | undefined;

  try {
    let transport: StreamableHTTPServerTransport;

    if (sessionId && transports[sessionId]) {
      transport = transports[sessionId];
    } else if (!sessionId && isInitializeRequest(req.body)) {
      transport = new StreamableHTTPServerTransport({
        sessionIdGenerator: () => randomUUID(),
        onsessioninitialized: (sid: string) => {
          transports[sid] = transport;
          if (authToken) sessionAuthTokens[sid] = authToken;
        },
      });

      transport.onclose = () => {
        const sid = transport.sessionId;
        if (sid) {
          delete transports[sid];
          delete sessionAuthTokens[sid];
        }
      };

      const getAccessToken = async (): Promise<string> => {
        const sid = transport.sessionId;
        const mcpToken = sid ? sessionAuthTokens[sid] : authToken;
        if (!mcpToken) throw new Error('No auth token available for this session');
        return provider.getStravaAccessToken(mcpToken);
      };

      const server = new McpServer({ name: 'strava-mcp', version: VERSION });
      const client = new StravaClient(getAccessToken);
      registerAllTools(server, client);

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
  res.json({ status: 'ok', server: 'strava-mcp', version: VERSION });
});

// ── Start ──────────────────────────────────────────────────────

app.listen(port, '0.0.0.0', () => {
  console.log(`Strava MCP HTTP Server listening on 0.0.0.0:${port}`);
  console.log(`Base URL: ${baseUrl}`);
  console.log(`MCP endpoint: ${baseUrl}/mcp`);
  console.log(`OAuth callback: ${baseUrl}/oauth/strava-callback`);
});

// ── Graceful shutdown ──────────────────────────────────────────

async function shutdown(signal: string): Promise<void> {
  console.log(`Received ${signal}, shutting down...`);
  provider.stopCleanupInterval();
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
}

process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));
