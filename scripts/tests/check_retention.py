"""Check that the retention flags keep exactly the snapshots we expect, on ~110 fake nightly snapshots.

    python3 check_retention.py --keep-daily 7 --keep-weekly 4 --keep-monthly 6

Uses the restic repository in RESTIC_REPOSITORY (an empty local test repository). Fake snapshot times are made
with `restic backup --time`, so this takes a few seconds, not a year.
"""

import json
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta

flags = sys.argv[1:]
policy = {flags[i].removeprefix("--keep-"): int(flags[i + 1]) for i in range(0, len(flags), 2)}
BUCKETS = {
    "daily": lambda t: t.date(),
    "weekly": lambda t: t.isocalendar()[:2],
    "monthly": lambda t: (t.year, t.month),
}

# Every day for the last 6 weeks, every third day for the 7 months before: enough to exercise all three rules.
end = datetime(2025, 12, 31, 2, 30)
times = sorted({end - timedelta(days=day) for day in range(42)} | {end - timedelta(days=day) for day in range(42, 260, 3)})
with tempfile.TemporaryDirectory() as folder:
    for moment in times:
        subprocess.run(
            ["restic", "backup", "--quiet", "--host", "retention-test", "--time", moment.strftime("%Y-%m-%d %H:%M:%S"),
             folder],
            check=True,
        )

# What restic should keep: for each rule, the newest snapshot of each of the last N days / weeks / months.
expected = set()
for rule, count in policy.items():
    seen = []
    for moment in sorted(times, reverse=True):
        bucket = BUCKETS[rule](moment)
        if bucket not in seen and len(seen) < count:
            seen.append(bucket)
            expected.add(moment)

result = subprocess.run(
    ["restic", "forget", "--dry-run", "--json", "--host", "retention-test", *flags],
    check=True,
    capture_output=True,
    text=True,
)
groups = json.loads(result.stdout)
kept = {datetime.fromisoformat(s["time"]).replace(tzinfo=None) for g in groups for s in g["keep"]}
if kept != expected:
    print(f"FAIL  restic keeps {len(kept)} snapshots, expected {len(expected)}")
    print("      only restic:", sorted(kept - expected))
    print("      only expected:", sorted(expected - kept))
    sys.exit(1)
print(f"OK    retention keeps {len(kept)} of {len(times)} snapshots (newest {max(kept):%Y-%m-%d}, "
      f"oldest {min(kept):%Y-%m-%d})")
