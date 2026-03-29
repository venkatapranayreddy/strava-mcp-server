import { loadConfig } from './src/config.js';
import { runOAuthFlow } from './src/auth.js';

async function main() {
  const config = loadConfig();
  console.error('Starting OAuth flow...');
  const result = await runOAuthFlow(config);
  console.log('SUCCESS: Authenticated as ' + result.athleteName);
}

main().catch(e => { console.error(e); process.exit(1); });
