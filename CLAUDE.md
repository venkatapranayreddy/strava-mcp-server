# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

An HTTP-only MCP server wrapping the Strava API v3, designed to be deployed as a remote connector for the Claude mobile app. Uses OAuth2 to authenticate users via Strava.

## Commands

```bash
npm run build          # TypeScript -> dist/
npm run dev            # Run server with tsx (hot reload)
npm start              # Run compiled server (requires build first)
```

Docker:
```bash
docker build -t strava-mcp .    # Multi-stage build (node:22-alpine)
docker run -p 3000:3000 -e STRAVA_CLIENT_ID=... -e STRAVA_CLIENT_SECRET=... -e BASE_URL=... strava-mcp
```

No test framework or linter is configured.

## Environment Variables

- `STRAVA_CLIENT_ID` / `STRAVA_CLIENT_SECRET` — required. Get from https://www.strava.com/settings/api
- `PORT` — server port (default 3000)
- `BASE_URL` — public URL (default `http://localhost:$PORT`). Must match your deployment URL exactly. Trailing slashes are stripped automatically.

## Architecture

Single entrypoint (`src/index.ts`) running an Express 5 server with the MCP SDK's auth and transport framework.

### OAuth Flow (Double Dance)
Claude client → MCP server OAuth (`/authorize`, `/token`) → Strava OAuth → `/oauth/strava-callback` → redirect back to Claude with MCP token. The `StravaOAuthProvider` manages this, mapping MCP tokens to Strava tokens in memory.

### Per-Session Isolation
Each MCP client session gets its own `StreamableHTTPServerTransport`, `McpServer`, and `StravaClient` instance. Session-to-auth-token mapping tracked in `sessionAuthTokens` (in-memory maps in `index.ts`).

### Key Modules
- `config.ts` — `loadConfig()` validates env vars and exits on failure. Returns `ServerConfig`.
- `types.ts` — TypeScript interfaces for all Strava API response shapes.
- `oauth-provider.ts` — `StravaOAuthProvider` implementing MCP SDK's `OAuthServerProvider`. All state (tokens, pending auths, codes) in-memory Maps with periodic cleanup (10 min interval).
- `strava-client.ts` — Thin HTTP client over Strava API v3. Transport-agnostic via `getAccessToken` function injection. Handles rate limiting (429s) with retry-after messaging.
- `tools/` — MCP tools grouped by domain (`athlete.ts`, `activity.ts`, `segment.ts`, `route.ts`). `tools/index.ts` registers all via `registerAllTools()`. `tools/format.ts` has shared formatters for duration/distance/pace.

### Adding a New Tool
1. Create or extend a file in `tools/` following the existing pattern (Zod schema for params, handler returns `{ content: [{ type: 'text', text }] }`).
2. Add the corresponding method to `StravaClient` if it needs a new Strava API call.
3. Add the type interfaces to `types.ts`.
4. Wire it up in `tools/index.ts` via the domain's register function.

### MCP Tools
`get_athlete`, `get_athlete_stats`, `get_athlete_zones`, `list_activities`, `get_activity`, `get_activity_streams`, `get_activity_laps`, `get_segment`, `list_starred_segments`, `list_routes`, `export_route_gpx`

## Key Conventions

- ESM throughout (`"type": "module"`). All local imports use `.js` extension.
- Zod schemas for MCP tool parameter validation.
- Tool handlers return `{ content: [{ type: 'text', text }] }` with formatted markdown tables.
- Token refresh uses a 5-minute buffer before actual expiry.
- Errors are logged to stderr with full details, but sanitized messages are returned to clients.
