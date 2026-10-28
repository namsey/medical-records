# CI/CD: from a merged pull request to the servers

Two workflows, both in `.github/workflows/`:

| Workflow | Runs on | Does |
| --- | --- | --- |
| **CI** (`ci.yml`) | every pull request to main, every push to main | backend, frontend and end-to-end tests, Terraform validate, script tests (backup and delivery), hadolint, a multi-arch image build with a Trivy scan, supply-chain checks. Never pushes anything. |
| **Deliver** (`deliver.yml`) | a successful CI run of a push to main; a `vX.Y.Z` tag; a manual run | builds and publishes the image, deploys staging, releases to prod, rolls back. Never runs for a pull request. |

Deliver **never connects to a server**. It only moves a tag in OCI Container Registry (OCIR): `staging` or
`prod`. The deploy agent on each VM (DEPLOY.md B9, `scripts/deploy-agent.sh`) notices within about 2 minutes,
deploys that image by digest (prod takes a backup first) and goes back to the previous one by itself if the app is
not healthy. No SSH key, server address or app secret is stored in GitHub.

```
merge to main ─► CI ─► build-push (sha-<commit>) ─► scan ─┬─► deploy-staging ─► prune (report only)
                                                          └─► mirror-dockerhub
git tag vX.Y.Z ─► verify ─► tag-release ─┬─► deploy-production (approval) ─► github-release
                                         └─► tag-release-dockerhub
Actions → Deliver → Run workflow ─► rollback (staging, or production with approval)
```

## Images and tags

One image per commit of main, built once for linux/arm64 and linux/amd64, with an SBOM and provenance attached.
The same digest goes everywhere: staging and prod run exactly the bytes CI built and Trivy scanned.

| Tag | Where | Moves? |
| --- | --- | --- |
| `sha-<full commit>` | OCIR and Docker Hub | never |
| `vX.Y.Z` | OCIR and Docker Hub | never (the workflow refuses to move an existing one) |
| `staging`, `prod` | OCIR only | yes: that is how a deploy happens |

OCIR (`medical-records/app`, private) is the source of truth; the VMs pull only from it. Docker Hub
(`DOCKERHUB_REPOSITORY`) is a backup copy made by digest, never rebuilt, and checked to have the same digest. A
Docker Hub failure shows as a failed job but never blocks a deploy.

## One-time setup in GitHub

Repository → Settings:

1. **Secrets and variables → Actions → Variables** (repository):
   - `OCIR_REGISTRY` = `bom.ocir.io` (`terraform output ocir_registry`)
   - `OCIR_REPOSITORY` = `bom.ocir.io/<namespace>/medical-records/app` (`terraform output ocir_repository`)
   - `DOCKERHUB_REPOSITORY` = `<docker hub user>/<repository>`
2. **Secrets** (repository):
   - `OCIR_USERNAME` = `<namespace>/ci-image-pusher`, `OCIR_AUTH_TOKEN` = its auth token (DEPLOY.md A12)
   - `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN` = a Docker Hub access token with *Read & Write* on that repository
     only (Docker Hub → Account settings → Personal access tokens), not the account password.
3. **Environments**:
   - `staging`: variable `APP_URL` = `https://staging-records.yourname.in`. Deployment branches and tags:
     *Selected*, `main`.
   - `production`: variable `APP_URL` = `https://records.yourname.in`. **Required reviewers: yourself.**
     Deployment branches and tags: *Selected*, tag pattern `v*.*.*`, and branch `main` (for rollbacks).
4. **Rules → Rulesets** (recommended): a tag ruleset for `v*` that blocks deletion and non-fast-forward updates, so
   a released tag cannot be moved to another commit.

Nothing above holds record data: the pipeline never sees the database, the files, `app.env` or the backups.

## Everyday use

**Ship to staging:** merge a pull request. When CI passes on main, Deliver builds `sha-<commit>`, scans it, moves
`staging`, waits until `APP_URL/api/version` reports the commit (up to 10 minutes) and runs
`scripts/smoke-test.sh`. If either fails, it moves `staging` back to the digest it pointed at before. Try the change
on staging with synthetic data.

**Release to prod:** from an up-to-date main, on a commit that staging has run successfully:

```bash
git switch main && git pull --ff-only
git tag -a v1.2.0 -m "v1.2.0" && git push origin v1.2.0
```

Deliver checks the tag is `vX.Y.Z` on a commit of main, that `sha-<commit>` exists in OCIR and that staging has a
successful deployment of that exact commit; then it tags the image `v1.2.0` and **waits for your approval**
(Actions → the run → *Review deployments*). After you approve it moves `prod` and waits up to 20 minutes (the prod
agent backs up first), runs the smoke test, moves `prod` back if anything fails, and finally creates the GitHub
release with generated notes.

**Roll back:** Actions → Deliver → *Run workflow*: version `v1.1.0` (or `sha-<full commit>`), environment. It moves
the tag to that image, waits for it and smoke-tests it. Production asks for approval. The database is **not**
rolled back: migrations only go forward and stay compatible with the previous release, so going back one release
is safe; further back across a destructive migration needs the restore runbook (DEPLOY.md C3/C4).

**Stop deploys** (maintenance, a breach): on the VM, `sudo touch /etc/medical-records/deploy-paused`. The tag can
still move, but the agent does nothing until the file is removed, so the pipeline's wait times out and it moves the
tag back.

## Old images

After every staging deploy the `prune` job lists the `sha-*` images that are not among the 10 newest commits of
main and are not also tagged `staging`, `prod` or `v*` (`scripts/prune-report.sh`). It **deletes nothing**:
deleting needs the OCI API with a signing key, and the pipeline only holds a registry auth token. Delete the listed
images by hand in the console now and then (Developer Services → Container Registry → `medical-records/app`),
where the repository's storage use is also shown.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| Deliver did not start after a merge | CI failed on main, or the workflow file is not on main yet (`workflow_run` uses main's copy). |
| `unauthorized` / `not authorized` on push | `OCIR_USERNAME` must be `<namespace>/ci-image-pusher`; the auth token was deleted or mistyped. |
| Timed out waiting for the commit | The agent on the VM is paused or failing: `journalctl -u medical-records-deploy -n 50` on the VM. The tag was moved back. |
| Smoke test failed | Read which check failed in the job log; the tag was moved back. Run `scripts/smoke-test.sh <url>` by hand. |
| Release refused: no successful staging deployment | Tag only commits that went through staging; wait for main's Deliver run to finish. |
| Trivy failed | A CRITICAL/HIGH vulnerability with a fix: update the base image digest or the package, then merge again. |

## Tests

`scripts/test-delivery.sh` (run by CI) tests `smoke-test.sh`, `move-env-tag.sh` and `prune-report.sh` against a
local stand-in for the site and the registry (`scripts/tests/fake_delivery.py`) with synthetic digests and commits.
The workflows themselves only run for real on GitHub.
