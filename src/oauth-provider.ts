import { randomUUID, randomBytes } from 'node:crypto';
import type { Response } from 'express';
import type { OAuthServerProvider, AuthorizationParams } from '@modelcontextprotocol/sdk/server/auth/provider.js';
import type { OAuthRegisteredClientsStore } from '@modelcontextprotocol/sdk/server/auth/clients.js';
import type { OAuthClientInformationFull, OAuthTokens, OAuthTokenRevocationRequest } from '@modelcontextprotocol/sdk/shared/auth.js';
import type { AuthInfo } from '@modelcontextprotocol/sdk/server/auth/types.js';

interface StravaTokenData {
  accessToken: string;
  refreshToken: string;
  expiresAt: number;
  athleteId?: number;
}

interface PendingAuth {
  clientId: string;
  codeChallenge: string;
  redirectUri: string;
  originalState?: string;
  scopes?: string[];
  createdAt: number;
}

interface ActiveToken {
  clientId: string;
  scopes: string[];
  expiresAt: number;
  strava: StravaTokenData;
}

interface PendingCode {
  clientId: string;
  codeChallenge: string;
  strava: StravaTokenData;
  redirectUri: string;
  createdAt: number;
}

// ── Clients Store ──────────────────────────────────────────────

class InMemoryClientsStore implements OAuthRegisteredClientsStore {
  private clients = new Map<string, OAuthClientInformationFull>();

  async getClient(clientId: string): Promise<OAuthClientInformationFull | undefined> {
    return this.clients.get(clientId);
  }

  async registerClient(metadata: OAuthClientInformationFull): Promise<OAuthClientInformationFull> {
    this.clients.set(metadata.client_id, metadata);
    return metadata;
  }
}

// ── Strava OAuth Provider ──────────────────────────────────────

export class StravaOAuthProvider implements OAuthServerProvider {
  readonly clientsStore: OAuthRegisteredClientsStore = new InMemoryClientsStore();

  private pendingAuths = new Map<string, PendingAuth>();
  private codes = new Map<string, PendingCode>();
  private tokens = new Map<string, ActiveToken>();
  private refreshTokens = new Map<string, string>();
  private cleanupInterval?: ReturnType<typeof setInterval>;

  constructor(
    private stravaClientId: string,
    private stravaClientSecret: string,
    private baseUrl: string,
  ) {}

  // ── Cleanup ─────────────────────────────────────────────────

  startCleanupInterval(): void {
    this.cleanupInterval = setInterval(() => this.cleanup(), 10 * 60 * 1000);
  }

  stopCleanupInterval(): void {
    if (this.cleanupInterval) clearInterval(this.cleanupInterval);
  }

  private cleanup(): void {
    const now = Date.now();
    const tenMinAgo = now - 10 * 60 * 1000;

    for (const [token, data] of this.tokens) {
      if (data.expiresAt < now) this.tokens.delete(token);
    }
    for (const [rt, at] of this.refreshTokens) {
      if (!this.tokens.has(at)) this.refreshTokens.delete(rt);
    }
    for (const [state, pending] of this.pendingAuths) {
      if (pending.createdAt < tenMinAgo) this.pendingAuths.delete(state);
    }
    for (const [code, data] of this.codes) {
      if (data.createdAt < tenMinAgo) this.codes.delete(code);
    }
  }

  // ── OAuthServerProvider interface ────────────────────────────

  async authorize(client: OAuthClientInformationFull, params: AuthorizationParams, res: Response): Promise<void> {
    const ourState = randomBytes(16).toString('hex');

    this.pendingAuths.set(ourState, {
      clientId: client.client_id,
      codeChallenge: params.codeChallenge,
      redirectUri: params.redirectUri,
      originalState: params.state,
      scopes: params.scopes,
      createdAt: Date.now(),
    });

    const stravaAuthUrl = new URL('https://www.strava.com/oauth/authorize');
    stravaAuthUrl.searchParams.set('client_id', this.stravaClientId);
    stravaAuthUrl.searchParams.set('response_type', 'code');
    stravaAuthUrl.searchParams.set('redirect_uri', `${this.baseUrl}/oauth/strava-callback`);
    stravaAuthUrl.searchParams.set('scope', 'read,read_all,profile:read_all,activity:read,activity:read_all');
    stravaAuthUrl.searchParams.set('state', ourState);
    stravaAuthUrl.searchParams.set('approval_prompt', 'auto');

    res.redirect(stravaAuthUrl.toString());
  }

  async challengeForAuthorizationCode(_client: OAuthClientInformationFull, authorizationCode: string): Promise<string> {
    const codeData = this.codes.get(authorizationCode);
    if (!codeData) throw new Error('Invalid authorization code');
    return codeData.codeChallenge;
  }

  async exchangeAuthorizationCode(
    client: OAuthClientInformationFull,
    authorizationCode: string,
  ): Promise<OAuthTokens> {
    const codeData = this.codes.get(authorizationCode);
    if (!codeData) throw new Error('Invalid authorization code');
    if (codeData.clientId !== client.client_id) throw new Error('Authorization code was not issued to this client');

    this.codes.delete(authorizationCode);

    const mcpAccessToken = randomUUID();
    const mcpRefreshToken = randomUUID();
    const expiresIn = 3600;

    this.tokens.set(mcpAccessToken, {
      clientId: client.client_id,
      scopes: ['strava:read'],
      expiresAt: Date.now() + expiresIn * 1000,
      strava: codeData.strava,
    });

    this.refreshTokens.set(mcpRefreshToken, mcpAccessToken);

    return {
      access_token: mcpAccessToken,
      token_type: 'bearer',
      expires_in: expiresIn,
      refresh_token: mcpRefreshToken,
      scope: 'strava:read',
    };
  }

  async exchangeRefreshToken(
    client: OAuthClientInformationFull,
    refreshToken: string,
  ): Promise<OAuthTokens> {
    const oldAccessToken = this.refreshTokens.get(refreshToken);
    if (!oldAccessToken) throw new Error('Invalid refresh token');

    const oldData = this.tokens.get(oldAccessToken);
    if (!oldData) throw new Error('Token data not found');
    if (oldData.clientId !== client.client_id) throw new Error('Refresh token was not issued to this client');

    const freshStrava = await this.refreshStravaToken(oldData.strava);

    this.tokens.delete(oldAccessToken);
    this.refreshTokens.delete(refreshToken);

    const newAccessToken = randomUUID();
    const newRefreshToken = randomUUID();
    const expiresIn = 3600;

    this.tokens.set(newAccessToken, {
      clientId: client.client_id,
      scopes: oldData.scopes,
      expiresAt: Date.now() + expiresIn * 1000,
      strava: freshStrava,
    });

    this.refreshTokens.set(newRefreshToken, newAccessToken);

    return {
      access_token: newAccessToken,
      token_type: 'bearer',
      expires_in: expiresIn,
      refresh_token: newRefreshToken,
      scope: oldData.scopes.join(' '),
    };
  }

  async verifyAccessToken(token: string): Promise<AuthInfo> {
    const data = this.tokens.get(token);
    if (!data) throw new Error('Invalid access token');
    if (data.expiresAt < Date.now()) throw new Error('Access token expired');
    return {
      token,
      clientId: data.clientId,
      scopes: data.scopes,
      expiresAt: Math.floor(data.expiresAt / 1000),
    };
  }

  async revokeToken(_client: OAuthClientInformationFull, request: OAuthTokenRevocationRequest): Promise<void> {
    const { token } = request;
    if (this.tokens.has(token)) {
      this.tokens.delete(token);
    }
    if (this.refreshTokens.has(token)) {
      const accessToken = this.refreshTokens.get(token)!;
      this.tokens.delete(accessToken);
      this.refreshTokens.delete(token);
    }
  }

  // ── Strava callback handler ──────────────────────────────────

  async handleStravaCallback(code: string, state: string): Promise<{ redirectUri: string }> {
    const pending = this.pendingAuths.get(state);
    if (!pending) throw new Error('Invalid or expired OAuth state');
    this.pendingAuths.delete(state);

    const stravaTokens = await this.exchangeStravaCode(code);

    const mcpCode = randomUUID();
    this.codes.set(mcpCode, {
      clientId: pending.clientId,
      codeChallenge: pending.codeChallenge,
      strava: stravaTokens,
      redirectUri: pending.redirectUri,
      createdAt: Date.now(),
    });

    const redirectUrl = new URL(pending.redirectUri);
    redirectUrl.searchParams.set('code', mcpCode);
    if (pending.originalState) {
      redirectUrl.searchParams.set('state', pending.originalState);
    }

    return { redirectUri: redirectUrl.toString() };
  }

  // ── Get Strava access token for API calls ────────────────────

  async getStravaAccessToken(mcpToken: string): Promise<string> {
    const data = this.tokens.get(mcpToken);
    if (!data) throw new Error('Invalid MCP token');

    if (Date.now() / 1000 >= data.strava.expiresAt - 300) {
      const fresh = await this.refreshStravaToken(data.strava);
      data.strava = fresh;
    }

    return data.strava.accessToken;
  }

  // ── Private Strava OAuth helpers ─────────────────────────────

  private async exchangeStravaCode(code: string): Promise<StravaTokenData> {
    const response = await fetch('https://www.strava.com/oauth/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        client_id: this.stravaClientId,
        client_secret: this.stravaClientSecret,
        code,
        grant_type: 'authorization_code',
      }),
    });

    if (!response.ok) {
      const body = await response.text();
      console.error(`Strava token exchange failed (${response.status}): ${body}`);
      throw new Error('Strava token exchange failed');
    }

    const data = await response.json() as {
      access_token: string;
      refresh_token: string;
      expires_at: number;
      athlete: { id: number };
    };

    return {
      accessToken: data.access_token,
      refreshToken: data.refresh_token,
      expiresAt: data.expires_at,
      athleteId: data.athlete.id,
    };
  }

  private async refreshStravaToken(strava: StravaTokenData): Promise<StravaTokenData> {
    const response = await fetch('https://www.strava.com/oauth/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        client_id: this.stravaClientId,
        client_secret: this.stravaClientSecret,
        refresh_token: strava.refreshToken,
        grant_type: 'refresh_token',
      }),
    });

    if (!response.ok) {
      const body = await response.text();
      console.error(`Strava token refresh failed (${response.status}): ${body}`);
      throw new Error('Strava token refresh failed');
    }

    const data = await response.json() as {
      access_token: string;
      refresh_token: string;
      expires_at: number;
      athlete?: { id: number };
    };

    return {
      accessToken: data.access_token,
      refreshToken: data.refresh_token,
      expiresAt: data.expires_at,
      athleteId: data.athlete?.id ?? strava.athleteId,
    };
  }
}
