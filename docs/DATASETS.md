# Dataset policy

The November-December 2025 NQ dataset is frozen and must not be regenerated or
silently merged with later files.

Rules:

1. Raw `.csv.gz`, normalized CSV, and `.Last.txt` files stay outside Git.
2. Select the active outright NQ contract by session volume while preserving
   the observed rollover (`NQZ5` to `NQH6`).
3. Reject snapshots, EOD files, invalid schemas, conflicting duplicate bars,
   and incomplete sessions.
4. Preserve genuine provider and scheduled-holiday gaps; never synthesize bars.
5. Record source range, row count, timezone, validation result, and SHA-256 in a
   separate controlled manifest before a backtest.

