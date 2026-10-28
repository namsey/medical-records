#!/usr/bin/env bash
# Deploys an image by moving an environment's OCIR tag (docs/CICD.md). The deliver workflow runs it for staging,
# prod and rollbacks; it never touches a VM. The VM's agent (scripts/deploy-agent.sh) sees the tag move within
# about 2 minutes, deploys the digest and goes back by itself if the app is not healthy.
#
#   REPOSITORY=bom.ocir.io/<namespace>/medical-records/app TAG=staging DIGEST=sha256:... \
#     APP_URL=https://staging-records.example.com COMMIT=<full sha> TIMEOUT=600 scripts/move-env-tag.sh
#
# Remembers the digest the tag points at now, moves the tag, then waits until APP_URL/api/version reports COMMIT
# and runs scripts/smoke-test.sh. If either fails, it moves the tag back to the remembered digest and exits 1.
# Needs `docker login` to the registry, docker buildx, curl and jq.
set -euo pipefail

: "${REPOSITORY:?}" "${TAG:?}" "${DIGEST:?}" "${APP_URL:?}" "${COMMIT:?}"
TIMEOUT="${TIMEOUT:-600}"
INTERVAL="${INTERVAL:-15}"
[[ "$DIGEST" =~ ^sha256:[0-9a-f]{64}$ ]] || { echo "DIGEST must be sha256:<64 hex>" >&2; exit 2; }
[[ "$COMMIT" =~ ^[0-9a-f]{40}$ ]] || { echo "COMMIT must be a full commit sha" >&2; exit 2; }
APP_URL="${APP_URL%/}"

summary() {
  if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then printf '%s\n' "$*" >>"$GITHUB_STEP_SUMMARY"; fi
  printf '%s\n' "$*"
}

previous=""
if previous=$(docker buildx imagetools inspect "$REPOSITORY:$TAG" --format '{{.Manifest.Digest}}' 2>/dev/null); then
  echo "'$TAG' points at $previous now"
else
  previous=""
  echo "'$TAG' does not exist yet: there is nothing to move back to if this deploy fails"
fi

docker buildx imagetools create -t "$REPOSITORY:$TAG" "$REPOSITORY@$DIGEST"
summary "Moved \`$TAG\` to \`$DIGEST\` (commit \`$COMMIT\`)${previous:+, was \`$previous\`}"

verify() {
  local deadline=$((SECONDS + TIMEOUT)) seen=""
  echo "Waiting up to ${TIMEOUT}s for $APP_URL/api/version to report $COMMIT"
  while ((SECONDS < deadline)); do
    seen=$(curl -sS --max-time 10 "$APP_URL/api/version" 2>/dev/null | jq -r '.commit // empty' 2>/dev/null || true)
    if [[ "$seen" == "$COMMIT" ]]; then
      echo "$APP_URL runs $COMMIT"
      "$(dirname "${BASH_SOURCE[0]}")/smoke-test.sh" "$APP_URL"
      return
    fi
    sleep "$INTERVAL"
  done
  echo "Timed out: $APP_URL still reports '${seen:-nothing}' (see 'journalctl -u medical-records-deploy' on the VM)"
  return 1
}

if verify; then
  summary "Deployed: $APP_URL runs \`$COMMIT\` and the smoke test passed."
  exit 0
fi

if [[ -n "$previous" && "$previous" != "$DIGEST" ]]; then
  docker buildx imagetools create -t "$REPOSITORY:$TAG" "$REPOSITORY@$previous"
  summary "FAILED: moved \`$TAG\` back to \`$previous\`. The agent keeps or restores that image."
else
  summary "FAILED: \`$TAG\` was left at \`$DIGEST\` (no earlier digest to move back to)."
fi
exit 1
