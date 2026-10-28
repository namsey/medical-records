#!/usr/bin/env bash
# Report-only clean-up of old images in OCIR (docs/CICD.md). Run by the deliver workflow after each build of main.
#
#   REPOSITORY=bom.ocir.io/<namespace>/medical-records/app REGISTRY_USERNAME=... REGISTRY_PASSWORD=... \
#     KEEP=10 scripts/prune-report.sh
#
# Lists the sha-* tags that are not among the KEEP newest commits of origin/main and whose digest is not also
# tagged staging, prod or v*. It deletes nothing: deleting needs the OCI API (an API signing key), and
# ci-image-pusher only has a registry auth token. Run from a checkout with the history of origin/main.
set -euo pipefail

: "${REPOSITORY:?}"
KEEP="${KEEP:-10}"
registry="${REPOSITORY%%/*}"
name="${REPOSITORY#*/}"
CURL=(curl -sS --fail --max-time 20)
scheme=https
if [[ "$registry" == localhost:* || "$registry" == 127.0.0.1:* ]]; then scheme=http; fi # tests only

# Registry token (Docker registry v2 auth): the realm and service come from the 401 answer.
auth=()
challenge=$(curl -sS -o /dev/null -D - --max-time 20 "$scheme://$registry/v2/$name/tags/list" | tr -d '\r' |
  grep -i '^www-authenticate: bearer' || true)
if [[ -n "$challenge" ]]; then
  realm=$(sed -n 's/.*realm="\([^"]*\)".*/\1/p' <<<"$challenge")
  service=$(sed -n 's/.*service="\([^"]*\)".*/\1/p' <<<"$challenge")
  : "${REGISTRY_USERNAME:?}" "${REGISTRY_PASSWORD:?}"
  token=$("${CURL[@]}" -u "$REGISTRY_USERNAME:$REGISTRY_PASSWORD" -G "$realm" \
    --data-urlencode "service=$service" --data-urlencode "scope=repository:$name:pull" | jq -r '.token // .access_token')
  auth=(-H "Authorization: Bearer $token")
fi

tags=$("${CURL[@]}" "${auth[@]}" "$scheme://$registry/v2/$name/tags/list" | jq -r '.tags[]?')
digest_of() {
  "${CURL[@]}" "${auth[@]}" -o /dev/null -D - -I \
    -H 'Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json' \
    "$scheme://$registry/v2/$name/manifests/$1" | tr -d '\r' | sed -n 's/^[Dd]ocker-[Cc]ontent-[Dd]igest: //p'
}

declare -A protected=()
while read -r tag; do
  if [[ "$tag" == staging || "$tag" == prod || "$tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    d=$(digest_of "$tag")
    protected[$d]+="$tag "
  fi
done <<<"$tags"

declare -A sha_tags=()
while read -r tag; do
  if [[ "$tag" =~ ^sha-([0-9a-f]{40})$ ]]; then sha_tags[${BASH_REMATCH[1]}]=1; fi
done <<<"$tags"

kept=0 would_delete=()
for commit in $(git rev-list origin/main); do # newest first
  [[ -n "${sha_tags[$commit]:-}" ]] || continue
  unset "sha_tags[$commit]"
  if ((kept < KEEP)); then
    kept=$((kept + 1))
    continue
  fi
  d=$(digest_of "sha-$commit")
  if [[ -n "${protected[$d]:-}" ]]; then
    echo "keep   sha-$commit (also ${protected[$d]% })"
  else
    would_delete+=("sha-$commit $d")
  fi
done

echo "Kept the $kept newest sha-* images of main, and everything tagged staging, prod or v*."
for commit in "${!sha_tags[@]}"; do
  echo "keep   sha-$commit (commit not on origin/main: check it by hand)"
done
if ((${#would_delete[@]})); then
  echo "Would delete ${#would_delete[@]} image(s):"
  printf '  %s\n' "${would_delete[@]}"
else
  echo "Nothing to delete."
fi
cat <<'EOF'
Nothing was deleted (report only). Untagged images (the per-architecture parts and attestations of deleted
indexes) are not listed by the registry API; see them in the OCI console under Container Registry.
To delete automatically, the pipeline would need an OCI API signing key for a user allowed to "manage repos"
(ci-image-pusher's policy already allows it since PR #37) as new secrets, and `oci artifacts container image
delete`. Until then, delete by hand in the console: Developer Services -> Container Registry -> medical-records/app.
EOF
