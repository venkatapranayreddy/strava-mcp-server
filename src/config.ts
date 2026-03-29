import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import type { StravaConfig, StravaTokens } from './types.js';

const CONFIG_DIR = join(homedir(), '.config', 'strava-mcp');
const CONFIG_FILE = join(CONFIG_DIR, 'config.json');
const TOKENS_FILE = join(CONFIG_DIR, 'tokens.json');

function ensureConfigDir(): void {
  if (!existsSync(CONFIG_DIR)) {
    mkdirSync(CONFIG_DIR, { recursive: true });
  }
}

export function loadConfig(): StravaConfig {
  // Environment variables take precedence
  const envId = process.env.STRAVA_CLIENT_ID;
  const envSecret = process.env.STRAVA_CLIENT_SECRET;

  if (envId && envSecret) {
    return { clientId: envId, clientSecret: envSecret };
  }

  // Fall back to config file
  if (existsSync(CONFIG_FILE)) {
    const raw = JSON.parse(readFileSync(CONFIG_FILE, 'utf-8'));
    if (raw.clientId && raw.clientSecret) {
      return { clientId: raw.clientId, clientSecret: raw.clientSecret };
    }
  }

  throw new Error(
    'Strava not configured. Set STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET environment variables, ' +
    `or create ${CONFIG_FILE} with { "clientId": "...", "clientSecret": "..." }`
  );
}

export function loadTokens(): StravaTokens | null {
  if (!existsSync(TOKENS_FILE)) return null;
  try {
    const raw = JSON.parse(readFileSync(TOKENS_FILE, 'utf-8'));
    if (raw.accessToken && raw.refreshToken && raw.expiresAt) {
      return {
        accessToken: raw.accessToken,
        refreshToken: raw.refreshToken,
        expiresAt: raw.expiresAt,
        athleteId: raw.athleteId,
      };
    }
    return null;
  } catch {
    return null;
  }
}

export function saveTokens(tokens: StravaTokens): void {
  ensureConfigDir();
  writeFileSync(TOKENS_FILE, JSON.stringify(tokens, null, 2), 'utf-8');
}

export function isTokenExpired(tokens: StravaTokens): boolean {
  // 5-minute buffer before actual expiry
  return Date.now() / 1000 >= tokens.expiresAt - 300;
}

export function getConfigDir(): string {
  ensureConfigDir();
  return CONFIG_DIR;
}
