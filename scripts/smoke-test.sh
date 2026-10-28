#!/usr/bin/env bash
# Smoke test of a running site, from the outside and without signing in (docs/CICD.md). The deliver workflow runs
# it after every staging and prod deploy; safe to run by hand against any environment:
#
#   scripts/smoke-test.sh https://staging-records.example.com
#
# Only anonymous GET requests: it never signs in, never sends or reads record data. Exits non-zero if any check
# fails. An http:// base URL (a laptop) skips the HTTPS redirect check.
set -uo pipefail

base="${1:-}"
if [[ ! "$base" =~ ^https?://[^/]+$ ]]; then
  echo "Usage: $0 <base-url>   (scheme and host only, e.g. https://records.example.com)" >&2
  exit 2
fi
command -v jq >/dev/null || { echo "jq is needed" >&2; exit 2; }

CURL=(curl -sS --max-time 20 --proto '=http,https')
failures=0
pass() { printf 'PASS  %s\n' "$1"; }
fail() { printf 'FAIL  %s: %s\n' "$1" "$2"; failures=$((failures + 1)); }

# fetch PATH: sets $status, $headers and $body, without following redirects.
fetch() {
  local out
  out=$("${CURL[@]}" -D - -w '\n%{http_code}' "$base$1" 2>&1) || { status=000; headers=""; body="$out"; return; }
  status="${out##*$'\n'}"
  out="${out%$'\n'*}"
  headers="$(printf '%s' "${out%%$'\r\n\r\n'*}" | tr -d '\r')"
  body="${out#*$'\r\n\r\n'}"
}
header() { printf '%s\n' "$headers" | grep -i "^$1:" | head -1 | sed 's/^[^:]*: *//'; }

if [[ "$base" == https://* ]]; then
  host="${base#https://}"
  if out=$("${CURL[@]}" -o /dev/null -w '%{http_code} %{redirect_url}' "http://$host/"); then
    read -r code location <<<"$out"
    if [[ "$code" =~ ^30[178]$ && "$location" == "https://$host/"* ]]; then
      pass "http:// redirects to https:// ($code)"
    else
      fail "http:// redirects to https://" "got $code ${location:-no Location}"
    fi
  else
    fail "http:// redirects to https://" "$out"
  fi
fi

fetch /api/health
if [[ "$status" == 200 && "$(jq -r .status <<<"$body" 2>/dev/null)" == ok ]]; then
  pass "/api/health is ok"
else
  fail "/api/health is ok" "HTTP $status"
fi

fetch /api/version
if [[ "$status" == 200 ]] && jq -e '(.commit | type == "string") and (.version | type == "string")' <<<"$body" >/dev/null 2>&1; then
  pass "/api/version answers ($(jq -r '.version + " " + .commit' <<<"$body"))"
else
  fail "/api/version answers" "HTTP $status"
fi

fetch /api/auth/privacy
if [[ "$status" == 200 ]]; then pass "/api/auth/privacy is public (200)"; else fail "/api/auth/privacy is public" "HTTP $status"; fi

fetch /api/records
if [[ "$status" == 401 ]]; then pass "/api/records needs a session (401)"; else fail "/api/records needs a session" "HTTP $status"; fi

fetch /
if [[ "$status" == 200 && "$body" == *'<div id="root">'* ]]; then pass "/ serves the app"; else fail "/ serves the app" "HTTP $status"; fi
# The app's own headers (backend/app/middleware.py), checked on the page itself.
value="$(header x-content-type-options)"
if [[ "$value" == nosniff ]]; then pass "X-Content-Type-Options: nosniff"; else fail "X-Content-Type-Options" "'$value'"; fi
value="$(header x-frame-options)"
if [[ "$value" == SAMEORIGIN ]]; then pass "X-Frame-Options: SAMEORIGIN"; else fail "X-Frame-Options" "'$value'"; fi
value="$(header content-security-policy)"
if [[ "$value" == *"frame-ancestors 'self'"* ]]; then
  pass "Content-Security-Policy with frame-ancestors 'self'"
else
  fail "Content-Security-Policy with frame-ancestors 'self'" "'$value'"
fi
# HTTP/3 stays off (deploy/compose/Caddyfile): phones that tried QUIC first could not upload.
value="$(header alt-svc)"
if [[ "$value" != *h3* ]]; then pass "no HTTP/3 advertised"; else fail "no HTTP/3 advertised" "Alt-Svc: $value"; fi

if ((failures)); then
  echo "Smoke test FAILED: $failures check(s) against $base"
  exit 1
fi
echo "Smoke test passed against $base"
