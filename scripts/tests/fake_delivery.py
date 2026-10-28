"""Test helper for test-delivery.sh: a stand-in for a deployed site and for OCIR, and a fake `docker` command.

    python fake_delivery.py serve <state dir> <port file>     the site and the registry API on one free port
    python fake_delivery.py docker buildx imagetools ...       what move-env-tag.sh and the workflow call

State, all in <state dir> (STATE_DIR for the docker command), re-read on every request:
    tags.json      {"<repository>:<tag>": "sha256:..."}: the registry; the fake docker moves tags in it
    site.json      {"tag": "<repository>:staging", "commits": {digest: commit}, "bad": [digest], "break": [check]}
                   The site acts as the VM's agent: it runs the commit of the digest its tag points at, unless that
                   digest is bad (then it keeps the last good one). "break" names smoke-test checks to fail.

The registry asks for a bearer token (user "pusher", password "secret") like OCIR does. Nothing here is real data.
"""

import base64
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TOKEN = "test-token"


def load(state: Path, name: str, default):
    path = state / name
    return json.loads(path.read_text()) if path.exists() else default


def save(state: Path, name: str, value) -> None:
    tmp = state / f".{name}.tmp"
    tmp.write_text(json.dumps(value, indent=1))
    tmp.replace(state / name)


def serve(state: Path, port_file: Path) -> None:
    running = {"commit": ""}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, body=b"", headers=None, content_type="application/json"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            if self.path.startswith("/v2/") or self.path.startswith("/token"):
                self.registry()
            else:
                self.site()

        # ---- registry (Docker registry v2 API, only what prune-report.sh reads)
        def registry(self):
            host = self.headers["Host"]
            if self.path.startswith("/token"):
                expected = "Basic " + base64.b64encode(b"pusher:secret").decode()
                if self.headers.get("Authorization") != expected:
                    return self.reply(401)
                return self.reply(200, json.dumps({"token": TOKEN}).encode())
            if self.headers.get("Authorization") != f"Bearer {TOKEN}":
                challenge = f'Bearer realm="http://{host}/token",service="test-registry"'
                return self.reply(401, b"{}", {"WWW-Authenticate": challenge})
            tags = load(state, "tags.json", {})
            path = self.path[len("/v2/"):]
            if path.endswith("/tags/list"):
                name = path[: -len("/tags/list")]
                found = [ref.rsplit(":", 1)[1] for ref in tags if ref.rsplit(":", 1)[0] == f"{host}/{name}"]
                return self.reply(200, json.dumps({"name": name, "tags": found}).encode())
            name, _, tag = path.partition("/manifests/")
            digest = tags.get(f"{host}/{name}:{tag}")
            if not digest:
                return self.reply(404)
            return self.reply(200, b"{}", {"Docker-Content-Digest": digest}, "application/vnd.oci.image.index.v1+json")

        # ---- site (what smoke-test.sh and move-env-tag.sh read)
        def site(self):
            site = load(state, "site.json", {})
            digest = load(state, "tags.json", {}).get(site.get("tag", ""), "")
            if digest and digest not in site.get("bad", []):
                running["commit"] = site.get("commits", {}).get(digest, "")
            broken = set(site.get("break", []))
            security = {
                "X-Content-Type-Options": "sniff" if "nosniff" in broken else "nosniff",
                "X-Frame-Options": "DENY" if "frame" in broken else "SAMEORIGIN",
                "Content-Security-Policy": "default-src 'self'"
                + ("" if "csp" in broken else "; frame-ancestors 'self'"),
            }
            if "h3" in broken:
                security["Alt-Svc"] = 'h3=":443"; ma=2592000'
            if self.path == "/api/health":
                status = "degraded" if "health" in broken else "ok"
                return self.reply(200, json.dumps({"status": status}).encode())
            if self.path == "/api/version":
                body = {"commit": running["commit"], "version": "main-" + running["commit"][:7]}
                return self.reply(500 if "version" in broken else 200, json.dumps(body).encode())
            if self.path == "/api/auth/privacy":
                return self.reply(200, b'{"text": "Sample privacy notice"}')
            if self.path == "/api/records":
                return self.reply(200 if "records" in broken else 401, b'{"detail": "Not signed in"}')
            if self.path == "/":
                page = b"<!doctype html><title>Sample</title>" + (b"" if "root" in broken else b'<div id="root"></div>')
                return self.reply(200, page, security, "text/html")
            return self.reply(404, b"{}")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port_file.write_text(str(server.server_address[1]))
    server.serve_forever()


def docker(args: list) -> int:
    """`docker buildx imagetools inspect REF --format '{{.Manifest.Digest}}'` and `... create -t REF SOURCE`."""
    state = Path(os.environ["STATE_DIR"])
    tags = load(state, "tags.json", {})
    if args[:3] == ["buildx", "imagetools", "inspect"]:
        ref = args[3]
        digest = ref.split("@", 1)[1] if "@" in ref else tags.get(ref)
        if not digest:
            print(f"ERROR: {ref}: not found", file=sys.stderr)
            return 1
        print(digest)
        return 0
    if args[:4] == ["buildx", "imagetools", "create", "-t"]:
        target, source = args[4], args[5]
        digest = source.split("@", 1)[1] if "@" in source else tags.get(source)
        if not digest:
            print(f"ERROR: {source}: not found", file=sys.stderr)
            return 1
        tags[target] = digest
        save(state, "tags.json", tags)
        with open(state / "docker.log", "a") as log:
            log.write(f"{target} -> {digest}\n")
        return 0
    print(f"fake docker: unsupported {args}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    if sys.argv[1] == "serve":
        serve(Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        sys.exit(docker(sys.argv[2:]))
