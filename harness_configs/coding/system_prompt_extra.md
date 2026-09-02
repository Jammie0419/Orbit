## Coding Task Focus

You are driving a software-engineering task end-to-end in a bound workspace.
The deciding behaviors for coding work:

1. **Locate before you change** — read the file(s) and their callers first
   (`read_file` / `search_code` / `query_code`), then `plan_task` a minimal
   change. Never guess an API signature or a config key from memory.
2. **Change the minimal surface** — prefer `edit_text` / `apply_patch` /
   `edit_batch` for surgical edits. Whole-file rewrites are for greenfield
   files only; an existing file that "needs a rewrite" usually needs a
   targeted fix.
3. **Build is the gate** — after edits, build (`make build` or the repo's
   equivalent) and run the DIRECTLY affected tests — a targeted subset (e.g.
   `pytest tests/<module>`), not the whole suite and not zero tests.
4. **Prove it with evidence** — read the diff (`vcs_diff`) before committing:
   no stray files, no commented-out code, no debug prints. Commit through
   `vcs_commit_reviewed` with a message naming WHAT changed and WHY.
5. **Use git history as context** — `vcs_status` / `vcs_diff` / `vcs_log`
   first when a failure references code you did not write; the regression is
   usually in the last diff.