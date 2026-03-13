#!/usr/bin/env python3
"""Tiny HTTP server to catch the OpenAI OAuth callback redirect."""
import http.server
import urllib.parse
import sys

class CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/auth/callback"):
            full_url = f"http://localhost:1455{self.path}"
            print("\n" + "=" * 60)
            print("CALLBACK RECEIVED! Copy this URL:")
            print(full_url)
            print("=" * 60 + "\n")
            sys.stdout.flush()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            html = f"""<!DOCTYPE html><html><body style="background:#1a1a1a;color:#fff;font-family:sans-serif;padding:40px;text-align:center">
<h1>✅ OAuth Callback empfangen!</h1>
<p>Kopiere diese URL und füge sie im Terminal ein:</p>
<textarea id="url" rows="4" cols="80" style="background:#333;color:#0f0;padding:10px;font-size:14px;width:90%">{full_url}</textarea>
<br><br>
<button onclick="navigator.clipboard.writeText(document.getElementById('url').value)" style="padding:12px 24px;font-size:16px;cursor:pointer">📋 URL kopieren</button>
<p style="color:#888;margin-top:20px">Du kannst diesen Tab jetzt schließen.</p>
</body></html>"""
            self.wfile.write(html.encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        print(f"[oauth-catcher] {args[0]}")

if __name__ == "__main__":
    server = http.server.HTTPServer(("0.0.0.0", 1455), CallbackHandler)
    print("OAuth callback catcher listening on http://0.0.0.0:1455 ...")
    print("Waiting for OpenAI redirect...")
    sys.stdout.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
