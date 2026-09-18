const base = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';
export async function api(path, options = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 10000);
    try {
        const response = await fetch(base + path, {
            ...options,
            headers: { 'Content-Type': 'application/json', 'X-Correlation-ID': 'ui-local', ...(options.headers || {}) },
            signal: controller.signal,
        });
        return await response.json();
    }
    finally {
        clearTimeout(timer);
    }
}
