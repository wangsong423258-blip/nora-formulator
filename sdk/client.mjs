import { operations } from './operations.mjs';

export class NoraClientError extends Error {
  constructor(code, status) {
    super(status ? `${code} (HTTP ${status})` : code);
    this.name = 'NoraClientError';
    this.code = code;
    if (status !== undefined) this.status = status;
  }
}

/** HTTP transport only. Domain results are returned without calculation or rounding. */
export class NoraClient {
  #base;
  #token;
  #fetch;
  #timeout;
  constructor({ baseUrl = 'http://127.0.0.1:8765', token, fetchImpl = globalThis.fetch, timeoutMs = 30000 }) {
    let url;
    try { url = new URL(baseUrl); } catch { throw new NoraClientError('INVALID_BASE_URL'); }
    const local = url.protocol === 'http:' && url.hostname === '127.0.0.1';
    if ((!local && url.protocol !== 'https:') || url.username || url.password || url.search || url.hash) {
      throw new NoraClientError('INVALID_BASE_URL');
    }
    if (typeof token !== 'string' || !token.trim() || /[\s\x00-\x1f\x7f]/.test(token)) {
      throw new NoraClientError('INVALID_CREDENTIAL');
    }
    if (typeof fetchImpl !== 'function' || !Number.isSafeInteger(timeoutMs) || timeoutMs < 1) {
      throw new NoraClientError('INVALID_CLIENT_OPTIONS');
    }
    this.#base = url.href.replace(/\/+$/, '');
    this.#token = token;
    this.#fetch = fetchImpl;
    this.#timeout = timeoutMs;
  }
  async call(operationId, { body, path = {}, query = {}, signal } = {}) {
    if (!Object.hasOwn(operations, operationId)) throw new NoraClientError('UNKNOWN_OPERATION');
    const op = operations[operationId];
    let route = op.path;
    const pathKeys = op.parameters.filter(p => p.in === 'path').map(p => p.name);
    const queryKeys = op.parameters.filter(p => p.in === 'query').map(p => p.name);
    if (Object.keys(path).some(k => !pathKeys.includes(k)) || Object.keys(query).some(k => !queryKeys.includes(k))) {
      throw new NoraClientError('UNKNOWN_PARAMETER');
    }
    for (const key of pathKeys) {
      const value = path[key];
      if (typeof value !== 'string' || !/^[A-Za-z0-9_-]+$/.test(value)) throw new NoraClientError('INVALID_PATH_PARAMETER');
      route = route.replace(`{${key}}`, encodeURIComponent(value));
    }
    const url = new URL(this.#base + route);
    for (const [key, value] of Object.entries(query)) {
      if (!['string', 'number', 'boolean'].includes(typeof value) || (typeof value === 'number' && !Number.isFinite(value))) {
        throw new NoraClientError('INVALID_QUERY_PARAMETER');
      }
      url.searchParams.set(key, String(value));
    }
    if (op.method === 'GET' && body !== undefined) throw new NoraClientError('UNEXPECTED_BODY');
    if (op.method === 'POST' && (!body || typeof body !== 'object' || Array.isArray(body))) {
      throw new NoraClientError('OBJECT_BODY_REQUIRED');
    }
    let encoded;
    try {
      if (body !== undefined) encoded = JSON.stringify(body, (_key, value) => {
        if (typeof value === 'number' && !Number.isFinite(value)) throw new Error();
        return value;
      });
    } catch { throw new NoraClientError('INVALID_JSON_BODY'); }
    const timeout = AbortSignal.timeout(this.#timeout);
    let response;
    try {
      response = await this.#fetch(url, {
        method: op.method, redirect: 'error',
        headers: { Accept: 'application/json', Authorization: `Bearer ${this.#token}`,
          ...(encoded === undefined ? {} : { 'Content-Type': 'application/json' }) },
        body: encoded, signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
      });
    } catch { throw new NoraClientError('TRANSPORT_UNAVAILABLE'); }
    if (!response.ok) throw new NoraClientError('HTTP_ERROR', response.status);
    try {
      const result = await response.json();
      if (!result || typeof result !== 'object' || Array.isArray(result)) throw new Error();
      return result;
    } catch { throw new NoraClientError('INVALID_JSON_RESPONSE'); }
  }
  async runtimeStatus() {
    let response;
    try {
      response = await this.#fetch(this.#base + '/runtime/v1/status', {
        method: 'GET', redirect: 'error', headers: { Accept: 'application/json', Authorization: `Bearer ${this.#token}` },
        signal: AbortSignal.timeout(this.#timeout),
      });
    } catch { throw new NoraClientError('TRANSPORT_UNAVAILABLE'); }
    if (!response.ok) throw new NoraClientError('HTTP_ERROR', response.status);
    try {
      const value = await response.json();
      if (!value || value.api_version !== 'v1' || typeof value.attribution_required !== 'boolean') throw new Error();
      return value;
    } catch { throw new NoraClientError('INVALID_JSON_RESPONSE'); }
  }
  version(options) { return this.call('version', options); }
}
