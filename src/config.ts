export interface ServerConfig {
  stravaClientId: string;
  stravaClientSecret: string;
  port: number;
  baseUrl: string;
}

export function loadConfig(): ServerConfig {
  const stravaClientId = process.env.STRAVA_CLIENT_ID;
  const stravaClientSecret = process.env.STRAVA_CLIENT_SECRET;

  if (!stravaClientId || !stravaClientSecret) {
    console.error('Missing required environment variables: STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET');
    process.exit(1);
  }

  const port = parseInt(process.env.PORT || '3000', 10);
  if (isNaN(port) || port < 1 || port > 65535) {
    console.error('PORT must be a valid port number (1-65535)');
    process.exit(1);
  }

  const baseUrl = (process.env.BASE_URL || `http://localhost:${port}`).replace(/\/+$/, '');

  return { stravaClientId, stravaClientSecret, port, baseUrl };
}
