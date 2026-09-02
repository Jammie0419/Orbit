- **Whole-file rewrites** of existing files when a targeted edit would do —
  they destroy blame history and reviewability.
- **Fixing a failing build with force operations** (`vcs_rollback` /
  `vcs_revert` / skipping review) instead of fixing the actual cause.
- **Committing without verifying** — no build, no targeted tests, and no
  `vcs_diff` review: the diff IS the deliverable, read it before you commit.
- **Guessing platform behavior in code** — Windows vs POSIX paths, line
  endings, shell quoting; verify with a tiny run instead of assuming.
- **Sprawling edits in one commit** — unrelated changes mixed into a single
  commit make review and rollback impossible.