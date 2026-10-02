const base = import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_JARVIS_API_URL || '';
let ownerToken = '';

// Owner session token only. Never persist it or accept broker/model credentials.
export function setOwnerToken(value: string) {
  if (value && (value.length < 32 || /\s/.test(value))) throw new Error('Enter a valid owner access token.');
  ownerToken = value;
}

export async function api(path: string, options: RequestInit = {}) {
  if (!path.startsWith('/api/') && path !== '/health') throw new Error('Invalid API path.');
  const endpoint = new URL(base + path, window.location.origin);
  if (ownerToken && endpoint.protocol !== 'https:' && !['127.0.0.1', 'localhost', '[::1]'].includes(endpoint.hostname)) {
    throw new Error('Remote owner access requires HTTPS.');
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 10000);
  const headers = new Headers(options.headers);
  headers.set('Content-Type', 'application/json');
  headers.set('X-Correlation-ID', crypto.randomUUID());
  if (ownerToken) headers.set('Authorization', `Bearer ${ownerToken}`);
  try {
    const response = await fetch(endpoint.toString(), {...options, headers, signal: controller.signal, redirect: 'error'});
    const result = await response.json();
    if (!response.ok) throw new Error(response.status === 401 ? 'Owner access token required. Open Connection.' : result.message || result.code || `Request failed (${response.status}).`);
    return result;
  } finally { clearTimeout(timer); }
}
