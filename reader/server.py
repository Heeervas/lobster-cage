"""
Reader-Proxy – Secure GET-only web page reader for OpenClaw Agent.

Fetches web pages and returns text content only.
Only GET requests allowed – POST, PUT, DELETE are rejected (405).

Security:
- GET-only: all other HTTP methods return 405
- SSRF protection: blocks private/internal IPs (RFC 1918, link-local, loopback)
- Response size cap: 2 MB download, 100k chars output
- Audit logging: every request logged with timestamp and URL
"""

import os
import re
import sys
import signal
import socket
import urllib.request
import urllib.error
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from html.parser import HTMLParser
from datetime import datetime, timezone

MAX_RESPONSE_SIZE = 2 * 1024 * 1024  # 2 MB max download
MAX_TEXT_LENGTH = 100_000              # 100k chars max response
LISTEN_PORT = int(os.environ.get("READER_PORT", "3000"))
REQUEST_TIMEOUT = int(os.environ.get("READER_TIMEOUT", "15"))

# Internal Docker service names (prevent SSRF to internal services)
BLOCKED_HOSTNAMES = {
    "hermes", "clawroute", "searxng", "browserless",
    "reader", "proxy", "caddy", "ollama", "dns",
    "openclaw",  # legacy agent name
}

# Blocked destinations (internal networks / metadata endpoints)
BLOCKED_PATTERNS = [
    r"^https?://169\.254\.",                    # AWS/cloud metadata
    r"^https?://10\.",                          # RFC 1918 private
    r"^https?://172\.(1[6-9]|2\d|3[01])\.",    # RFC 1918 private
    r"^https?://192\.168\.",                    # RFC 1918 private
    r"^https?://localhost",                     # Localhost
    r"^https?://127\.",                        # Loopback
    r"^https?://\[::1\]",                     # IPv6 loopback
    r"^https?://\[fd",                        # IPv6 ULA
    r"^https?://\[fe80:",                     # IPv6 link-local
    r"^https?://0\.",                         # Null routes
    r"^https?://metadata\.google\.internal",   # GCP metadata
]


# ── Audit logger ──
def audit_log(action: str, url: str = "", detail: str = ""):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    trunc_url = url[:200] + "…" if len(url) > 200 else url
    parts = [f"[reader-audit] {ts} {action}"]
    if trunc_url:
        parts.append(trunc_url)
    if detail:
        parts.append(f"({detail})")
    sys.stderr.write(" ".join(parts) + "\n")
    sys.stderr.flush()


class TextExtractor(HTMLParser):
    """Extracts readable text from HTML, ignoring scripts/styles."""

    def __init__(self):
        super().__init__()
        self._text = []
        self._skip = False
        self._skip_tags = {"script", "style", "noscript", "svg", "head"}

    def handle_starttag(self, tag, attrs):
        if tag in self._skip_tags:
            self._skip = True
        if tag in ("p", "br", "div", "h1", "h2", "h3", "h4", "h5", "h6",
                    "li", "tr", "blockquote", "article", "section"):
            self._text.append("\n")

    def handle_endtag(self, tag):
        if tag in self._skip_tags:
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            self._text.append(data)

    def get_text(self):
        text = " ".join(self._text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {2,}", " ", text)
        return text.strip()


def is_blocked(url: str) -> bool:
    """Check if URL points to internal/blocked networks."""
    for pattern in BLOCKED_PATTERNS:
        if re.match(pattern, url, re.IGNORECASE):
            return True

    # Block internal Docker service hostnames
    parsed = urllib.parse.urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if hostname in BLOCKED_HOSTNAMES:
        return True

    # Resolve hostname and check if it maps to a blocked IP
    if hostname:
        try:
            resolved_ip = socket.getaddrinfo(hostname, None)[0][4][0]
            resolved_url = f"http://{resolved_ip}/"
            for pattern in BLOCKED_PATTERNS:
                if re.match(pattern, resolved_url, re.IGNORECASE):
                    return True
        except socket.gaierror:
            pass

    return False


def fetch_url(url: str) -> tuple[str, str]:
    """Fetch URL content. Returns (content, content_type)."""
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; OpenClaw-Reader/1.0)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,text/plain;q=0.8",
            "Accept-Language": "en,de;q=0.5",
        },
    )

    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        content_type = resp.headers.get("Content-Type", "text/html")
        data = resp.read(MAX_RESPONSE_SIZE)
        charset = "utf-8"
        if "charset=" in content_type:
            charset = content_type.split("charset=")[-1].split(";")[0].strip()
        return data.decode(charset, errors="replace"), content_type


def extract_text(html_content: str) -> str:
    """Extract readable text from HTML."""
    parser = TextExtractor()
    parser.feed(html_content)
    text = parser.get_text()
    return text[:MAX_TEXT_LENGTH]


class ReaderHandler(BaseHTTPRequestHandler):
    """HTTP Handler – GET only."""

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/health":
            self._respond(200, "ok")
            return

        if parsed.path == "/fetch":
            params = urllib.parse.parse_qs(parsed.query)
            url = params.get("url", [None])[0]

            if not url:
                self._respond(400, "Missing 'url' parameter")
                return

            if not url.startswith(("http://", "https://")):
                self._respond(400, "URL must start with http:// or https://")
                return

            if is_blocked(url):
                audit_log("BLOCKED-PRIVATE", url)
                self._respond(403, "URL blocked: internal/private network")
                return

            audit_log("FETCH", url)

            try:
                content, content_type = fetch_url(url)

                if "html" in content_type.lower():
                    text = extract_text(content)
                else:
                    text = content[:MAX_TEXT_LENGTH]

                self._respond(200, text)

            except urllib.error.HTTPError as e:
                self._respond(502, f"Remote server returned {e.code}: {e.reason}")
            except urllib.error.URLError as e:
                self._respond(502, f"Could not reach URL: {e.reason}")
            except TimeoutError:
                self._respond(504, "Request timed out")
            except Exception as e:
                self._respond(500, f"Error: {str(e)}")
            return

        self._respond(404, "Not found. Use /fetch?url=... or /health")

    def do_POST(self):
        self._respond(405, "Method not allowed. Only GET requests are permitted.")

    def do_PUT(self):
        self._respond(405, "Method not allowed. Only GET requests are permitted.")

    def do_DELETE(self):
        self._respond(405, "Method not allowed. Only GET requests are permitted.")

    def do_PATCH(self):
        self._respond(405, "Method not allowed. Only GET requests are permitted.")

    def do_HEAD(self):
        self._respond(405, "Method not allowed. Only GET requests are permitted.")

    def do_OPTIONS(self):
        self._respond(405, "Method not allowed. Only GET requests are permitted.")

    def _respond(self, code: int, body: str):
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, format, *args):
        sys.stderr.write(f"[reader-proxy] {args[0]} {args[1]} {args[2]}\n")


def main():
    server = HTTPServer(("0.0.0.0", LISTEN_PORT), ReaderHandler)
    print(f"[reader-proxy] Listening on 0.0.0.0:{LISTEN_PORT} (GET-only)",
          flush=True)

    def shutdown(sig, frame):
        print("[reader-proxy] Shutting down...", flush=True)
        server.shutdown()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    server.serve_forever()


if __name__ == "__main__":
    main()
