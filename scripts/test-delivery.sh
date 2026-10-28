#!/usr/bin/env bash
# Tests for smoke-test.sh, move-env-tag.sh and prune-report.sh against a local stand-in for the site and OCIR
# (scripts/tests/fake_delivery.py) and a fake `docker` command: no registry, no VM, no cloud needed.
#
#   scripts/test-delivery.sh
#
# Needs python3, curl, jq and git.
set -euo pipefail
umask 077

SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/medical-records-delivery-test.XXXXXX")"
server=""
cleanup() {
  if [[ -n "$server" ]]; then kill "$server" 2>/dev/null || true; fi
  rm -rf "$WORK"
}
trap cleanup EXIT

pass() { echo "PASS  $*"; }
fail() {
  echo "FAIL  $*"
  exit 1
}

export STATE_DIR="$WORK/state"
mkdir -p "$STATE_DIR" "$WORK/bin"
cat >"$WORK/bin/docker" <<EOF
#!/usr/bin/env bash
exec "$PYTHON" "$SCRIPTS/tests/fake_delivery.py" docker "\$@"
EOF
chmod +x "$WORK/bin/docker"
export PATH="$WORK/bin:$PATH"

"$PYTHON" "$SCRIPTS/tests/fake_delivery.py" serve "$STATE_DIR" "$WORK/port" &
server=$!
for _ in $(seq 50); do [[ -s "$WORK/port" ]] && break; sleep 0.1; done
[[ -s "$WORK/port" ]] || fail "the fake site did not start"
SITE="http://127.0.0.1:$(cat "$WORK/port")"
REPO="127.0.0.1:$(cat "$WORK/port")/sample-namespace/medical-records/app"

# Synthetic commits and digests.
commit() { printf '%040d' "$1" | tr 0 "$2"; }
digest() { printf 'sha256:%064x' "$1"; }
C1=$(commit 1 a) C2=$(commit 2 b) C3=$(commit 3 c)
D1=$(digest 1) D2=$(digest 2) D3=$(digest 3)
site() { jq -n --arg tag "$REPO:staging" --argjson rest "$1" \
  --arg d1 "$D1" --arg d2 "$D2" --arg d3 "$D3" --arg c1 "$C1" --arg c2 "$C2" --arg c3 "$C3" \
  '{tag: $tag, commits: {($d1): $c1, ($d2): $c2, ($d3): $c3}, bad: [], break: []} + $rest' >"$STATE_DIR/site.json"; }
tag_of() { jq -r --arg ref "$REPO:$1" '.[$ref] // ""' "$STATE_DIR/tags.json"; }

# ---------------------------------------------------------------- smoke-test.sh
jq -n --arg ref "$REPO:staging" --arg d "$D1" '{($ref): $d}' >"$STATE_DIR/tags.json"
site '{}'
"$SCRIPTS/smoke-test.sh" "$SITE" >"$WORK/smoke.log" 2>&1 || { cat "$WORK/smoke.log"; fail "smoke test of a good site"; }
grep -q "PASS  /api/version answers (main-aaaaaaa $C1)" "$WORK/smoke.log" || fail "smoke test did not read /api/version"
pass "smoke-test.sh passes against a good site"

for check in health version records root nosniff frame csp h3; do
  site "{\"break\": [\"$check\"]}"
  if "$SCRIPTS/smoke-test.sh" "$SITE" >"$WORK/smoke.log" 2>&1; then
    cat "$WORK/smoke.log"
    fail "smoke test passed with '$check' broken"
  fi
  [[ "$(grep -c '^FAIL' "$WORK/smoke.log")" == 1 ]] || { cat "$WORK/smoke.log"; fail "'$check' broken: not exactly one FAIL"; }
done
pass "smoke-test.sh fails on each broken check, and only on that one"

status=0
"$SCRIPTS/smoke-test.sh" "$SITE/api" >/dev/null 2>&1 || status=$?
[[ "$status" == 2 ]] || fail "smoke test accepted a base URL with a path (exit $status)"
pass "smoke-test.sh refuses a base URL with a path"

# ---------------------------------------------------------------- move-env-tag.sh
move() { REPOSITORY="$REPO" APP_URL="$SITE" TIMEOUT=4 INTERVAL=1 GITHUB_STEP_SUMMARY="" "$SCRIPTS/move-env-tag.sh"; }

site '{}'
TAG=staging DIGEST="$D2" COMMIT="$C2" move >"$WORK/move.log" 2>&1 || { cat "$WORK/move.log"; fail "deploy of a good image"; }
[[ "$(tag_of staging)" == "$D2" ]] || fail "staging does not point at the new digest"
grep -q "Deployed: $SITE runs \`$C2\`" "$WORK/move.log" || fail "no success line"
pass "move-env-tag.sh moves the tag, waits for the new commit and runs the smoke test"

site '{"bad": ["'"$D3"'"]}'
if TAG=staging DIGEST="$D3" COMMIT="$C3" move >"$WORK/move.log" 2>&1; then fail "a deploy that never went live passed"; fi
[[ "$(tag_of staging)" == "$D2" ]] || fail "staging was not moved back after a failed deploy"
grep -q "Timed out: $SITE still reports '$C2'" "$WORK/move.log" || { cat "$WORK/move.log"; fail "no time-out message"; }
pass "move-env-tag.sh moves the tag back when the VM never runs the new commit"

site '{"break": ["csp"]}'
if TAG=staging DIGEST="$D3" COMMIT="$C3" move >"$WORK/move.log" 2>&1; then fail "a deploy failing the smoke test passed"; fi
[[ "$(tag_of staging)" == "$D2" ]] || fail "staging was not moved back after a failed smoke test"
pass "move-env-tag.sh moves the tag back when the smoke test fails"

site '{"tag": "'"$REPO:prod"'", "bad": ["'"$D1"'"]}'
if TAG=prod DIGEST="$D1" COMMIT="$C1" move >"$WORK/move.log" 2>&1; then fail "a failed first deploy passed"; fi
[[ "$(tag_of prod)" == "$D1" ]] || fail "a first deploy without an earlier digest changed the tag again"
grep -q "no earlier digest to move back to" "$WORK/move.log" || fail "no message about the missing earlier digest"
pass "move-env-tag.sh fails a first deploy without inventing a digest to go back to"

before="$(cat "$STATE_DIR/tags.json")"
for bad in "sha256:short $C1" "$D1 abc123"; do
  status=0
  DIGEST="${bad% *}" COMMIT="${bad#* }" TAG=staging REPOSITORY="$REPO" APP_URL="$SITE" "$SCRIPTS/move-env-tag.sh" >/dev/null 2>&1 || status=$?
  [[ "$status" == 2 ]] || fail "move-env-tag.sh accepted $bad (exit $status)"
done
[[ "$(cat "$STATE_DIR/tags.json")" == "$before" ]] || fail "a refused input still moved a tag"
pass "move-env-tag.sh refuses a short digest or commit and moves nothing"

# ---------------------------------------------------------------- prune-report.sh
git init -q "$WORK/git"
git -C "$WORK/git" -c user.name="Test Runner" -c user.email=runner@example.com commit -q --allow-empty -m "start"
for i in $(seq 1 13); do
  git -C "$WORK/git" -c user.name="Test Runner" -c user.email=runner@example.com commit -q --allow-empty -m "change $i"
done
git -C "$WORK/git" update-ref refs/remotes/origin/main HEAD
mapfile -t main < <(git -C "$WORK/git" rev-list origin/main) # newest first: 14 commits
side=$(commit 9 e)
tags=$(jq -n '{}')
add() { tags=$(jq --arg ref "$REPO:$1" --arg d "$2" '. + {($ref): $d}' <<<"$tags"); }
for i in "${!main[@]}"; do add "sha-${main[$i]}" "$(digest $((i + 10)))"; done
add staging "$(digest 10)"             # the newest commit
add prod "$(digest 21)"                # main[11], older than the 10 kept
add v1.0.0 "$(digest 22)"              # main[12]
add "sha-$side" "$(digest 99)"         # a commit not on main
echo "$tags" >"$STATE_DIR/tags.json"

(cd "$WORK/git" && REPOSITORY="$REPO" REGISTRY_USERNAME=pusher REGISTRY_PASSWORD=secret KEEP=10 \
  "$SCRIPTS/prune-report.sh") >"$WORK/prune.log" 2>&1 || { cat "$WORK/prune.log"; fail "prune report"; }
grep -q "Kept the 10 newest sha-\* images" "$WORK/prune.log" || fail "did not keep 10"
grep -q "keep   sha-${main[11]} (also prod)" "$WORK/prune.log" || fail "the image tagged prod was not kept"
grep -q "keep   sha-${main[12]} (also v1.0.0)" "$WORK/prune.log" || fail "the image tagged v1.0.0 was not kept"
grep -q "keep   sha-$side (commit not on origin/main" "$WORK/prune.log" || fail "the image of a side commit was not kept"
grep -q "Would delete 2 image(s):" "$WORK/prune.log" || { cat "$WORK/prune.log"; fail "wrong number to delete"; }
for i in 10 13; do
  grep -q "  sha-${main[$i]} " "$WORK/prune.log" || fail "sha-${main[$i]} is not listed for deletion"
done
[[ "$(cat "$STATE_DIR/tags.json")" == "$tags" ]] || fail "the report changed the registry"
pass "prune-report.sh keeps the 10 newest, staging/prod/v* and side commits, lists the rest, deletes nothing"

status=0
(cd "$WORK/git" && REPOSITORY="$REPO" REGISTRY_USERNAME=pusher REGISTRY_PASSWORD=wrong "$SCRIPTS/prune-report.sh") \
  >/dev/null 2>&1 || status=$?
[[ "$status" != 0 ]] || fail "prune-report.sh did not fail with a wrong password"
pass "prune-report.sh fails when the registry refuses the sign-in"

echo "All delivery script tests passed."
