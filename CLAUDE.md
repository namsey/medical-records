===== FILE: CLAUDE.md =====
# Working rules for this repo

This is a personal medical records app (private health journal). The feature plan lives in ROADMAP.md.

## How to implement a roadmap item
1. Read ROADMAP.md and the item asked for. Check its "Depends on" items are done (checked). If not, stop and tell me.
2. Explore the relevant code first. For items in Level 3 or above, present a short plan (data model changes, files to touch, UI changes, migration needs) and WAIT for my approval before coding.
3. Keep changes scoped to the item. No unrelated refactors. Reuse existing components, tokens and patterns.
4. Never lose or corrupt existing user records. Any data model change needs a migration with default values for existing records.
5. Run the app and check the change at 360px and 430px widths. Run existing tests/lint/build if they exist, and add tests for new logic.
6. Commit with the message "feat(#N): <title>" (or "fix(#N)"). One item per commit or small series of commits.
7. In ROADMAP.md, tick the item's checkbox and add a one-line "Notes:" entry under it (what was built and anything deferred).
8. Finish with a short summary: what changed, how to test it, any follow-ups.

## Privacy rules (health data)
- Never send record data, attachments or personal info to any third-party service unless the roadmap item explicitly requires it and I approved it.
- Never log record contents to the console in production code.
