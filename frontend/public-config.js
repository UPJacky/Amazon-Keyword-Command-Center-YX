// Public deployment configuration only. Live requires BOTH explicit switches.
// Never place a privileged key, password, or user session in this file.
globalThis.KWCC_PUBLIC_CONFIG = Object.freeze({
  mode: 'demo',
  liveEnabled: false,
  supabaseUrl: '',
  publicKey: '',
});
