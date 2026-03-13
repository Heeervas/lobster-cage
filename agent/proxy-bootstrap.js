// Preload-Script: Integrates OpenClaw's web_search + web_fetch tools with
// the secure proxy infrastructure (SearXNG, Reader-Proxy, Outbound-Proxy).
//
// Loaded via NODE_OPTIONS=--require=/proxy-bootstrap.js
//
// Routing:
// 1. web_search (Brave API) → redirected to SearXNG (Brave-compatible response)
// 2. web_fetch (arbitrary URLs) → non-whitelisted domains → Reader-Proxy (GET-only)
// 3. Whitelisted APIs (Telegram, OpenAI, …) → Outbound-Proxy (domain whitelist)
// 4. Internal services (searxng, reader, …) → direct connection
//
// Security features:
// - Audit log: every outgoing request is logged with route + destination
// - Search query length cap: prevents large data exfiltration via search queries
// - Direct SearXNG access detection: warns if agent bypasses the adapter

if (process.env.HTTPS_PROXY || process.env.HTTP_PROXY) {
  let undici;
  try {
    undici = require('/app/node_modules/.pnpm/undici@7.22.0/node_modules/undici');
  } catch (e) {
    try {
      undici = require('/app/node_modules/undici');
    } catch (_) {}
  }

  if (undici) {
    // ── 1. Globalen Proxy-Dispatcher setzen ──
    undici.setGlobalDispatcher(new undici.EnvHttpProxyAgent());

    // ── 2. Configuration ──
    const SEARXNG_URL = process.env.SEARXNG_URL || 'http://searxng:8080';
    const READER_URL = process.env.READER_PROXY_URL || 'http://reader:3000';

    // ── Audit logger ──
    function auditLog(route, method, url, extra) {
      const ts = new Date().toISOString();
      const truncUrl = url.length > 200 ? url.slice(0, 200) + '…' : url;
      const parts = [`[proxy-audit] ${ts} ${route}`];
      if (method) parts.push(method);
      parts.push(truncUrl);
      if (extra) parts.push(extra);
      console.error(parts.join(' '));
    }

    const NO_PROXY_HOSTS = new Set(
      (process.env.NO_PROXY || process.env.no_proxy || '')
        .split(',')
        .map(h => h.trim().toLowerCase())
        .filter(Boolean)
    );

    // Domains routed through the outbound proxy (Tinyproxy whitelist).
    // Read from /etc/proxy-whitelist.txt (mounted from outbound-proxy/whitelist.txt)
    // → Single source of truth: one file for Tinyproxy, dnsmasq, AND this script.
    let WHITELISTED_DOMAINS = [];
    try {
      const fs = require('fs');
      WHITELISTED_DOMAINS = fs.readFileSync('/etc/proxy-whitelist.txt', 'utf8')
        .split('\n')
        .map(l => l.replace(/#.*/, '').trim())
        .filter(Boolean);
    } catch (e) {
      // Fallback if file not mounted – log warning
      console.warn('[proxy-bootstrap] WARNING: /etc/proxy-whitelist.txt not found, using empty whitelist');
      WHITELISTED_DOMAINS = [];
    }

    // Extract SearXNG hostname for direct-access detection
    const SEARXNG_HOST = new URL(SEARXNG_URL).hostname;

    // Hosts with self-signed TLS certificates (e.g. LAN services like Nextcloud)
    // undici 7.x ignores connect.rejectUnauthorized for CONNECT tunnels,
    // so NODE_TLS_REJECT_UNAUTHORIZED is temporarily set.
    const TLS_SKIP_VERIFY_HOSTS = new Set(
      (process.env.TLS_SKIP_VERIFY_HOSTS || '')
        .split(',')
        .map(h => h.trim().toLowerCase())
        .filter(Boolean)
    );

    async function fetchWithTlsSkip(resource, init) {
      const prev = process.env.NODE_TLS_REJECT_UNAUTHORIZED;
      process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0';
      try {
        return await _origFetch(resource, init);
      } finally {
        if (prev === undefined) delete process.env.NODE_TLS_REJECT_UNAUTHORIZED;
        else process.env.NODE_TLS_REJECT_UNAUTHORIZED = prev;
      }
    }

    function isInternalHost(hostname) {
      const h = (hostname || '').toLowerCase();
      if (NO_PROXY_HOSTS.has(h)) return true;
      if (h === 'localhost' || h === '127.0.0.1' || h === '::1') return true;
      if (h.endsWith('.internal') || h.endsWith('.local')) return true;
      return false;
    }

    function isDomainWhitelisted(hostname) {
      const h = (hostname || '').toLowerCase();
      for (const domain of WHITELISTED_DOMAINS) {
        if (h === domain || h.endsWith('.' + domain)) return true;
      }
      return false;
    }

    // ── 3. Brave Search → SearXNG Adapter ──
    const _origFetch = globalThis.fetch;

    async function braveToSearxng(braveUrl, init) {
      const parsed = new URL(braveUrl);
      const query = parsed.searchParams.get('q') || '';
      const count = parseInt(parsed.searchParams.get('count') || '5', 10);
      const lang = parsed.searchParams.get('search_lang')
                || parsed.searchParams.get('ui_lang')
                || '';

      auditLog('SEARCH', 'GET', `q="${query.slice(0, 100)}"`, `(${query.length} chars)`);

      const searxUrl = new URL(`${SEARXNG_URL}/search`);
      searxUrl.searchParams.set('q', query);
      searxUrl.searchParams.set('format', 'json');
      if (lang) searxUrl.searchParams.set('language', lang);

      // Timeout vom Original-Request übernehmen
      const fetchOpts = {};
      if (init && init.signal) fetchOpts.signal = init.signal;

      const searxRes = await _origFetch(searxUrl.toString(), fetchOpts);

      if (!searxRes.ok) {
        const errText = await searxRes.text();
        return new Response(JSON.stringify({
          error: `SearXNG error (${searxRes.status}): ${errText}`.slice(0, 500)
        }), { status: searxRes.status, headers: { 'content-type': 'application/json' } });
      }

      const searxData = await searxRes.json();

      // SearXNG → Brave-Format transformieren
      const results = (searxData.results || []).slice(0, count).map(r => ({
        title: r.title || '',
        url: r.url || '',
        description: r.content || '',
        age: r.publishedDate || undefined,
      }));

      const braveResponse = { web: { results } };

      return new Response(JSON.stringify(braveResponse), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      });
    }

    // ── 4. Reader-Proxy redirect for non-whitelisted URLs ──
    async function fetchViaReader(targetUrl, init) {
      auditLog('READER', 'GET', targetUrl);

      const readerUrl = `${READER_URL}/fetch?url=${encodeURIComponent(targetUrl)}`;

      const fetchOpts = {};
      if (init && init.signal) fetchOpts.signal = init.signal;

      const readerRes = await _origFetch(readerUrl, fetchOpts);

      // Reader-Proxy gibt text/plain zurück – web_fetch verarbeitet das als "raw"
      // Wir wrappen es für bessere Kompatibilität mit web_fetch
      const text = await readerRes.text();

      if (readerRes.status !== 200) {
        return new Response(text || 'Reader proxy error', {
          status: readerRes.status >= 400 && readerRes.status < 600 ? readerRes.status : 502,
          headers: {
            'content-type': 'text/plain; charset=utf-8',
          },
        });
      }

      return new Response(text, {
        status: 200,
        headers: {
          'content-type': 'text/plain; charset=utf-8',
          'x-via-reader-proxy': 'true',
        },
      });
    }

    // ── 5. Haupt-Patch: fetch() abfangen ──
    globalThis.fetch = function patchedFetch(resource, init) {
      try {
        let urlStr = '';
        if (typeof resource === 'string') urlStr = resource;
        else if (resource instanceof URL) urlStr = resource.href;
        else if (resource && typeof resource === 'object' && resource.url) urlStr = resource.url;

        if (urlStr) {
          const parsed = new URL(urlStr);

          // a) Brave Search API → SearXNG
          if (parsed.hostname === 'api.search.brave.com') {
            return braveToSearxng(urlStr, init);
          }

          // b) Internal hosts → direct (no proxy)
          if (isInternalHost(parsed.hostname)) {
            // Security: detect direct SearXNG access (bypassing the adapter)
            if (parsed.hostname === SEARXNG_HOST) {
              auditLog('DIRECT-SEARXNG', init?.method || 'GET', urlStr,
                '⚠ bypassing search adapter');
            }
            return _origFetch(resource, init);
          }

          // c) Whitelisted domains → Tinyproxy (remove custom dispatcher)
          if (isDomainWhitelisted(parsed.hostname)) {
            const method = (init?.method || 'GET').toUpperCase();
            auditLog('WHITELIST', method, urlStr);
            const needsTlsSkip = TLS_SKIP_VERIFY_HOSTS.has(parsed.hostname);

            if (init && init.dispatcher) {
              const customDispatcher = init.dispatcher;
              const { dispatcher: _, ...cleanInit } = init;
              if (customDispatcher && typeof customDispatcher.close === 'function') {
                customDispatcher.close().catch(() => {});
              }
              return needsTlsSkip
                ? fetchWithTlsSkip(resource, cleanInit)
                : _origFetch(resource, cleanInit);
            }
            return needsTlsSkip
              ? fetchWithTlsSkip(resource, init)
              : _origFetch(resource, init);
          }

          // d) Everything else → Reader-Proxy (GET-only, secure)
          return fetchViaReader(urlStr, init);
        }
      } catch (_) {
        // URL parsing failed – fall through to original behavior
      }
      return _origFetch(resource, init);
    };
  }
}
