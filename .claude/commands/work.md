---
description: Start work on a GitHub issue — runs a fixed-order ceremony (self-assign, branch, empty commit, push, draft PR) for julien-riel/palubicki. With no issue number, picks the next ticket from docs/roadmap.md. Aborts on any precondition failure; may suggest destructive recovery commands but never runs them without explicit user confirmation. Reminds, at ticket completion, to update docs/roadmap.md + docs/botany/simulator-gap-analysis.md.
---

# Start work on an issue

`/work <N>` — runs the issue-bootstrap ceremony for issue `#N` on `julien-riel/palubicki`, in a fixed order, with hard aborts. One issue, one branch, one draft PR — opened *before* the first real commit. After this skill exits cleanly the next step is to write code on the branch.

`/work` (no number) — consult the roadmap to pick the next ticket (see step 0), confirm with the user, then run the same ceremony.

## Step 0 — Identify the issue (only when `N` is omitted)

If the user gave an explicit `<N>`, skip this step and go straight to the preconditions.

If no number was given, **read `docs/roadmap.md`** and take the **first item in the "À faire (dans l'ordre)" list** — that is the canonical priority order, not GitHub's issue order. Skip any item already marked *en cours* whose branch is owned by someone else; an *en cours* item on a branch you can resume is a hint to resume, not to re-bootstrap (precondition 5 will catch a duplicate branch anyway).

Announce the pick in one line — *"roadmap → next is #<N> — <title>. Proceed? (y / n)"* — and wait for `y` before touching git. On `n`, stop. Once confirmed, `N` is fixed and the rest of the ceremony is identical.

## Preconditions (refuse-to-proceed gates)

Check all of these first. If any fail, stop and report — **do not** try to fix them on the user's behalf.

1. **Working tree clean.** `git status --porcelain` must be empty. Untracked files anywhere under the repo count: a stray `docs/...md` or an unstaged `src/` edit on `main` becomes a phantom diff on the new branch and confuses any later squash. Refuse with *"working tree not clean — commit, stash, or remove tracked changes (and untracked stragglers) before running /work"*.
2. **On a branch you're willing to leave.** If the current branch is not `main`, prompt: *"currently on `<branch>`. Switch to main? (y / n)"*. On `n`, exit. On `y`, continue with the checkout.
3. **`N` is an open issue.** `gh issue view <N> -R julien-riel/palubicki --json state,title,assignees`. If `state` ≠ `OPEN`, refuse with *"issue #<N> is `<state>` — won't start work on it"*.
4. **Assignee is empty or you.** Resolve the current user (`gh api user --jq .login`). If `.assignees[].login` contains *any user other than* the current user, refuse with: *"already assigned to @<other> — refusing to take it. Ask the current assignee to unassign, or coordinate before reassigning."* Do **not** silently replace another assignee.
5. **No branch named `issue-<N>-*` already exists** (local or remote). If a local branch matches `issue-<N>-*` (use `git branch --list 'issue-<N>-*'`) or a remote tracking ref matches (`git ls-remote --heads origin 'issue-<N>-*'`), refuse with *"branch `<name>` already exists — resume work on it manually, or delete it first"*. The repo's invariant is one branch per issue; `/work` does not adopt or reuse an existing one.

If all five pass, proceed.

## Workflow

1. **Read the issue title.** From the JSON fetched in precondition 3. Strip a leading `<area>:` or `<path>:` prefix if present (e.g. `sim: time / phenology axis` → `time / phenology axis`; `birch.py: droop curve breaks` → `droop curve breaks`). This matches the existing issue title style in the repo (e.g. `sim: determinate growth + flowers + inflorescences`, `geom: root flare at trunk base`).

2. **Derive a slug and announce the branch name.** From the stripped title:
   - lowercase
   - replace any run of non-alphanumeric characters with a single `-`
   - drop leading/trailing `-`
   - truncate at the last word boundary `≤ 40` characters (excluding the `issue-<N>-` prefix that follows). If the truncation lands mid-word, back up to the previous `-`.

   Print the resulting branch name (`issue-<N>-<slug>`) as a one-line announcement and continue. No prompt — the user can rename the branch after the fact if needed (`git branch -m`), and the slug is purely cosmetic for the PR URL. Don't burn an interaction on it.

3. **Self-assign if needed.** If the current user is *not* already in `assignees`:
   ```
   gh issue edit <N> -R julien-riel/palubicki --add-assignee "@me"
   ```
   Skip this call if already assigned (idempotent — no point re-writing).

4. **Refresh main.**
   ```
   git checkout main && git pull --ff-only
   ```
   If `--ff-only` refuses (local `main` has diverged), abort with *"local main has diverged from origin — resolve manually"*. May suggest a recovery (e.g. `git reset --hard origin/main` if local commits are known-disposable) but only execute on explicit `y`.

5. **Create the branch.**
   ```
   git checkout -b issue-<N>-<slug>
   ```

6. **Empty starter commit.**
   ```
   git commit --allow-empty -m "Start work on #<N>"
   ```

7. **Push and set upstream.**
   ```
   git push -u origin issue-<N>-<slug>
   ```

8. **Open the draft PR.** Pass the title verbatim from the issue.
   ```
   gh pr create -R julien-riel/palubicki --draft --assignee "@me" \
     --base main \
     --title "<issue title>" \
     --body "Closes #<N>"
   ```
   - **Never** put `Draft:` in `--title` — `--draft` adds the prefix on its own.
   - Body is exactly `Closes #<N>` (one line). Real body comes later, written by hand on the PR before marking ready.
   - `gh pr create` has no equivalent of GitLab's `--squash-before-merge` or `--remove-source-branch`; squash-vs-merge and branch deletion are decided at merge time (e.g. `gh pr merge --squash --delete-branch`) or via repo settings, not at create.

9. **Print the PR URL** that `gh` returned. Done.

## When the ticket is finished (reminder for later, not part of the bootstrap)

This belongs to the *end* of the work, not `/work` itself — but record it here so it isn't forgotten. Before marking the PR ready / merging, **update both docs in the same PR** so they never drift from the code:

- **`docs/roadmap.md`** — move the finished issue out of "À faire (dans l'ordre)" into the "Fait" table (with its PR number), and re-check the ordering of what remains (a finished ticket often unblocks or reprioritizes the next ones).
- **`docs/botany/simulator-gap-analysis.md`** — flip the relevant row(s) from ❌/🟡 to ✅ / the right Δ, update the section verdict, and refresh the "Last reviewed" line + the "Top remaining recommendations" list if the change affects them.

If the ticket was purely software/tooling (no botanical concept touched), the gap-analysis may not need an edit — say so explicitly rather than skipping silently.

## Abort rules

- Stop the moment any step fails. Print the failing command, the error, and what state the working tree / remote are in.
- **Suggesting a fix is fine — running it autonomously is not.** When a recovery would be destructive or hard-to-reverse (`git reset --hard`, `git push --force`, `git push --force-with-lease`, `git checkout --`, `git restore --staged`, `git clean -fd`, `git branch -D`, deleting an existing `issue-<N>-*` branch, dropping a stash), the skill may *propose* the exact command with a one-line rationale and ask: *"Run this? (y / n / show alternatives)"*. Default `n`. **Never** execute a destructive command without that explicit `y`. Show the alternative path when one exists (e.g. `git stash` before `git reset --hard`).
- If `gh pr create` fails (network, auth, GitHub outage), leave the branch and the starter commit in place. Suggest the retry command (`gh pr create …` with the same flags) but don't loop on it; the user decides whether to retry, edit flags, or give up.

## What you MUST NOT do

- Do not start writing code. The whole point of opening the PR *before* the first real commit is to make the work visible from keystroke one. If you find yourself editing files after step 9, you've drifted out of `/work` and into the implementation — that's a separate, deliberate decision.
- Do not skip the empty starter commit. GitHub needs a commit to attach the PR to; the empty commit is also the "Start work on #N" milestone that surfaces in `git log` later.
- Do not omit `Closes #<N>` from the PR body. It's what auto-closes the issue on merge.
- Do not run on a repo other than `julien-riel/palubicki`. Hard-coded.
- Do not silently replace an existing assignee. Precondition 4 covers this.
- Do not adopt an existing `issue-<N>-*` branch. Precondition 5 covers this.

## Design rationale

This command encodes a deterministic, abort-on-mismatch issue-bootstrap ceremony for `julien-riel/palubicki`. The order *"branch → empty commit → push → PR"* (not *"branch → code → PR"*) is the bit that needs scaffolding — opening the draft PR *before* the first real commit makes the work visible from keystroke one and gives an obvious place to track scope discussion as it accumulates.

The "abort, then propose" stance: the skill protects state, the user owns reconciliation. The skill *may* suggest a destructive recovery command (often the user knows it's safe — e.g. an untracked file from a prior aborted run that can be `rm`'d, or a stale local `issue-<N>-*` branch left over after the remote was deleted), but executing it requires an explicit `y`. The asymmetry matters: a missing suggestion costs the user a Google search; an auto-executed `git reset --hard` costs them their work.

Slug derivation runs without confirmation because the branch name is cosmetic — it surfaces in the PR URL but doesn't affect any of the merge / close-issue machinery, and `git branch -m` is a one-liner if the user wants to rename it later. Burning a prompt on every invocation to confirm a name that's almost always right is the wrong trade.

GitHub-specific notes: `gh pr create` has no equivalent of GitLab's `--squash-before-merge` or `--remove-source-branch` flags — squash-vs-merge is chosen at merge time (`gh pr merge --squash --delete-branch`) or via repo settings. The repo currently has `delete_branch_on_merge: false`, so source branches stick around until manually deleted; flip that setting if you'd rather have automatic cleanup. Issue state in GitHub's JSON is `OPEN` (uppercase), not GitLab's `opened`.
