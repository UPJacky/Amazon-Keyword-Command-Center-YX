import { createGateway } from './gateway.mjs';

// Public deployment settings only; no service key is read by this function.
const handler = createGateway({
  supabaseUrl: Deno.env.get('SUPABASE_URL'),
  allowedOrigin: Deno.env.get('KWCC_ALLOWED_ORIGIN') || 'https://upjacky.github.io',
});
Deno.serve(handler);
