import { createGateway } from './gateway.mjs';

// Public deployment settings only; no service key is read by this function.
// Pin the upstream to the same project as the public bundle so a stale
// dashboard value cannot route authentication to another Supabase project.
const handler = createGateway({
  supabaseUrl: 'https://fcowaovsbxxtxljjhllp.supabase.co',
  allowedOrigin: Deno.env.get('KWCC_ALLOWED_ORIGIN') || 'https://upjacky.github.io',
});
Deno.serve(handler);
