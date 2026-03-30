# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

An HTTP-only MCP server wrapping the Strava API v3, designed to be deployed as a remote connector for the Claude mobile app. Uses OAuth2 to authenticate users via Strava.

## Commands

```bash
npm run build          # TypeScript -> dist/
npm run dev            # Run server with tsx (hot reload)
npm start              # Run compiled server
```

No test framework is configured.

## Environment Variables

- `STRAVA_CLIENT_ID` / `STRAVA_CLIENT_SECRET` — required. Get from https://www.strava.com/settings/api
- `PORT` — server port (default 3000)
- `BASE_URL` — public URL (default `http://localhost:$PORT`). Must match your deployment URL exactly.

## Architecture

Single entrypoint (`src/index.ts`) running an Express server with the MCP SDK's auth and transport framework.

### OAuth Flow (Double Dance)
Claude client → MCP server OAuth (`/authorize`, `/token`) → Strava OAuth → `/oauth/strava-callback` → redirect back to Claude with MCP token. The `StravaOAuthProvider` manages this, mapping MCP tokens to Strava tokens in memory.

### Per-Session Isolation
Each MCP client session gets its own `StreamableHTTPServerTransport`, `McpServer`, and `StravaClient` instance. Session-to-auth-token mapping tracked in `sessionAuthTokens`.

### Key Modules
- `config.ts` — Environment variable validation
- `oauth-provider.ts` — `StravaOAuthProvider` implementing MCP SDK's `OAuthServerProvider`. In-memory token maps with periodic cleanup (10 min interval).
- `strava-client.ts` — Thin HTTP client over Strava API v3. Transport-agnostic via `getAccessToken` function injection.
- `tools/` — MCP tools grouped by domain. `tools/index.ts` registers all. `tools/format.ts` has shared formatters.

### MCP Tools
`get_athlete`, `get_athlete_stats`, `get_athlete_zones`, `list_activities`, `get_activity`, `get_activity_streams`, `get_activity_laps`, `get_segment`, `list_starred_segments`, `list_routes`, `export_route_gpx`

## Key Conventions

- ESM throughout (`"type": "module"`). All local imports use `.js` extension.
- Zod schemas for MCP tool parameter validation.
- Tool handlers return `{ content: [{ type: 'text', text }] }` with formatted markdown tables.
- Token refresh uses a 5-minute buffer before actual expiry.
- Errors are logged to stderr with full details, but sanitized messages are returned to clients.
