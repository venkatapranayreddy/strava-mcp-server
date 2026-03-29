import { createServer, type IncomingMessage, type ServerResponse } from 'node:http';
import { exec } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import { loadConfig, loadTokens, saveTokens, isTokenExpired } from './config.js';
import type { StravaConfig, StravaTokens } from './types.js';

const SCOPES = 'read,read_all,profile:read_all,activity:read,activity:read_all';
const AUTH_TIMEOUT_MS = 120_000; // 2 minutes

interface TokenResponse {
  token_type: string;
  expires_at: number;
  expires_in: number;
  refresh_token: string;
  access_token: string;
  athlete: {
    id: number;
    firstname: string;
    lastname: string;
  };
}

async function findAvailablePort(startPort: number): Promise<number> {
  for (let port = startPort; port < startPort + 6; port++) {
    try {
      await new Promise<void>((resolve, reject) => {
        const server = createServer();
        server.once('error', reject);
        server.listen(port, () => {
          server.close(() => resolve());
        });
      });
      return port;
    } catch {
      continue;
    }
  }
  throw new Error('Could not find an available port for OAuth callback (tried 8847-8852)');
}

function waitForAuthCode(port: number, expectedState: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const server = createServer((req: IncomingMessage, res: ServerResponse) => {
      const url = new URL(req.url!, `http://localhost:${port}`);

      if (url.pathname === '/callback') {
        const code = url.searchParams.get('code');
        const state = url.searchParams.get('state');
        const error = url.searchParams.get('error');

        if (error) {
          res.writeHead(400, { 'Content-Type': 'text/html' });
          res.end(`<html><body><h1>Authorization Failed</h1><p>${error}</p><p>You can close this tab.</p></body></html>`);
          server.close();
          reject(new Error(`Strava authorization denied: ${error}`));
          return;
        }

        if (state !== expectedState) {
          res.writeHead(400, { 'Content-Type': 'text/html' });
          res.end('<html><body><h1>Security Error</h1><p>State mismatch. Please try again.</p></body></html>');
          server.close();
          reject(new Error('OAuth state mismatch — possible CSRF attack'));
          return;
        }

        if (!code) {
          res.writeHead(400, { 'Content-Type': 'text/html' });
          res.end('<html><body><h1>Error</h1><p>No authorization code received.</p></body></html>');
          server.close();
          reject(new Error('No authorization code in callback'));
          return;
        }

        res.writeHead(200, { 'Content-Type': 'text/html' });
        res.end('<html><body><h1>Authorization Successful!</h1><p>You can close this tab and return to Claude Code.</p></body></html>');
        server.close();
        resolve(code);
      } else {
        res.writeHead(404);
        res.end();
      }
    });

    server.listen(port);

    const timeout = setTimeout(() => {
      server.close();
      reject(new Error('OAuth callback timed out after 2 minutes. Please try again.'));
    }, AUTH_TIMEOUT_MS);

    server.on('close', () => clearTimeout(timeout));
  });
}

async function exchangeCodeForTokens(code: string, redirectUri: string, config: StravaConfig): Promise<StravaTokens> {
  const response = await fetch('https://www.strava.com/oauth/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      client_id: config.clientId,
      client_secret: config.clientSecret,
      code,
      grant_type: 'authorization_code',
    }),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Token exchange failed (${response.status}): ${body}`);
  }

  const data = (await response.json()) as TokenResponse;
  return {
    accessToken: data.access_token,
    refreshToken: data.refresh_token,
    expiresAt: data.expires_at,
    athleteId: data.athlete.id,
  };
}

export async function refreshAccessToken(config: StravaConfig, refreshToken: string): Promise<StravaTokens> {
  const response = await fetch('https://www.strava.com/oauth/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      client_id: config.clientId,
      client_secret: config.clientSecret,
      refresh_token: refreshToken,
      grant_type: 'refresh_token',
    }),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Token refresh failed (${response.status}): ${body}`);
  }

  const data = (await response.json()) as TokenResponse;
  return {
    accessToken: data.access_token,
    refreshToken: data.refresh_token,
    expiresAt: data.expires_at,
    athleteId: data.athlete?.id,
  };
}

export async function runOAuthFlow(config: StravaConfig): Promise<{ tokens: StravaTokens; athleteName: string }> {
  const port = await findAvailablePort(8847);
  const state = randomBytes(16).toString('hex');
  const redirectUri = `http://localhost:${port}/callback`;

  const authUrl = new URL('https://www.strava.com/oauth/authorize');
  authUrl.searchParams.set('client_id', config.clientId);
  authUrl.searchParams.set('response_type', 'code');
  authUrl.searchParams.set('redirect_uri', redirectUri);
  authUrl.searchParams.set('scope', SCOPES);
  authUrl.searchParams.set('state', state);
  authUrl.searchParams.set('approval_prompt', 'auto');

  // Log to stderr so it doesn't interfere with stdio MCP transport
  console.error(`\n🔗 Opening browser for Strava authorization...\n${authUrl.toString()}\n`);

  // Auto-open the browser on macOS
  exec(`open "${authUrl.toString()}"`);

  const code = await waitForAuthCode(port, state);
  const tokens = await exchangeCodeForTokens(code, redirectUri, config);
  saveTokens(tokens);

  // Fetch athlete name for confirmation
  const athleteResponse = await fetch('https://www.strava.com/api/v3/athlete', {
    headers: { Authorization: `Bearer ${tokens.accessToken}` },
  });

  let athleteName = 'Unknown';
  if (athleteResponse.ok) {
    const athlete = (await athleteResponse.json()) as { firstname: string; lastname: string };
    athleteName = `${athlete.firstname} ${athlete.lastname}`;
  }

  return { tokens, athleteName };
}

export async function ensureAuthenticated(): Promise<string> {
  const config = loadConfig();
  const tokens = loadTokens();

  if (!tokens) {
    throw new Error('Not authenticated. Please run the strava_auth tool first.');
  }

  if (isTokenExpired(tokens)) {
    const newTokens = await refreshAccessToken(config, tokens.refreshToken);
    // Preserve athleteId from old tokens if refresh doesn't return it
    if (!newTokens.athleteId && tokens.athleteId) {
      newTokens.athleteId = tokens.athleteId;
    }
    saveTokens(newTokens);
    return newTokens.accessToken;
  }

  return tokens.accessToken;
}
