let path = location.pathname;

if (path.endsWith("index.html")) {
  path = path.substring(0, path.length - 10);
}

if (!path.endsWith("/")) {
  path += "/";
}

const newUrl = location.origin + path + location.search + location.hash;

if (newUrl !== window.location.href) {
  window.history.pushState({}, "", newUrl);
}

const originalFetch = window.fetch.bind(window);

function isPageSession(session) {
  return session?.type === "page" && typeof session.webSocketDebuggerUrl === "string";
}

window.fetch = async function patchedFetch(input, init) {
  const response = await originalFetch(input, init);
  const requestUrl = typeof input === "string"
    ? input
    : input instanceof URL
      ? input.href
      : input?.url;

  if (!requestUrl) {
    return response;
  }

  const resolvedUrl = new URL(requestUrl, window.location.href);

  if (!resolvedUrl.pathname.endsWith("/sessions")) {
    return response;
  }

  const sessions = await response.clone().json().catch(() => null);

  if (!Array.isArray(sessions)) {
    return response;
  }

  const pageSessions = sessions
    .filter(isPageSession)
    .map((session) => ({
      ...session,
      browserWSEndpoint: session.webSocketDebuggerUrl,
    }));

  const headers = new Headers(response.headers);
  headers.delete("content-length");

  return new Response(JSON.stringify(pageSessions), {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
};