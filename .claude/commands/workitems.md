---
description: Draft a new GitHub issue for julien-riel/palubicki and create it via gh after preview
---

# Create a new GitHub issue

You are drafting a new issue for the palubicki project (`julien-riel/palubicki` on github.com). Match the pragmatic, concrete voice of existing issues — no fluff, no marketing speak.

User idea: $ARGUMENTS

## Workflow

1. **List existing issues for context.** Run:
   ```
   gh issue list -R julien-riel/palubicki --limit 50
   ```
   Use these for cross-references and to recalibrate on the established voice. If the idea is closely related to one or two specific issues, also run `gh issue view <N>` on those to read their full body. (If the issue list is still empty or sparse, lean on this template's style rules instead.)

2. **Determine the type** (`bug` / `enhancement` / `task`). Use the prefix in the user's input if present (e.g., `bug: …`); otherwise ask once.

3. **Read the relevant repo state.** Identify files, modules, or features the idea touches. Read those files (with line ranges where appropriate) to ground the *Current state* section in reality, not guesses. Skim `README.md` and `CONTRIBUTING.md` if they exist at the repo root.

4. **Find related issues.** Skim the issue list for 1–3 issues that share scope, files, or concepts. Note their numbers for *Related* / *Dependencies* / *Blocked by*. Do not force connections that aren't there.

5. **Draft title + body** using the template for the chosen type (below). The title is short and action-oriented, often prefixed with the file or area (e.g., `birch.py: droop curve breaks at low gravity values`, `presets: monopodial preset uses wrong angle convention`).

6. **Show the user** the title, the label, and the full body in plain markdown. Then ask: "OK to create? (yes / no / change X)". Wait for the response. If they request edits, revise and re-show. Do not loop silently — every revision gets a fresh preview.

7. **On confirmation only,** create the issue. Pass the body via a HEREDOC so multi-line markdown survives the shell:
   ```bash
   gh issue create -R julien-riel/palubicki \
     --title "<title>" \
     --label "<type>" \
     --body "$(cat <<'EOF'
   <body>
   EOF
   )"
   ```
   Print the URL `gh` returns.

## Templates

Each template is a starting structure, not a rigid form. Drop sections that don't apply (e.g., a tiny bug doesn't need *Open questions*); add sections from a sibling template if the situation calls for it. The goal is to match the established voice, not to fill every heading.

### `bug`

```markdown
## Bug

<one paragraph: what happens vs what should happen, and where>

## Current state

<concrete file refs with line numbers; tables work well when several files share the same problem>

## Desired outcome

<what the fix should achieve. May list 2 reasonable conventions if the right one isn't obvious.>

## Acceptance criteria

- [ ] <verifiable condition>
- [ ] <verifiable condition>

## Related

- #N — <one-line why this is related>
```

### `enhancement`

```markdown
## Goal

<2–4 sentences: what we're adding and why it matters now. If carved out of another issue's out-of-scope list, say so.>

## Current state

<what exists today, with concrete file refs. Be specific about the gap.>

## Why this is harder than X (optional)

<only include if there's a non-obvious reason this isn't trivial>

## Feature scope

### Minimum viable

- <bullets: what v1 must include — small, shippable, useful>

### Nice to have

- <bullets: v2+ extensions, clearly labeled as not required>

## Dependencies

- **Blocked by #N** (why)
- **Related to #N** (how)

## Approach options (optional, only when there's a real choice)

1. **<approach name>.** <one paragraph: what it is, what it costs, what it gives you>
2. **<approach name>.** <…>

Recommendation: <which one and why>.

## Decisions to make

1. **<decision>.** <options + tradeoff>

## Out of scope

- <thing that's tempting but not in this issue, with a short reason or pointer to a follow-up>

## Acceptance criteria

- [ ] <verifiable condition>

## Open questions

- <question that needs an answer before / during implementation>
```

### `task`

```markdown
## Goal

<2–4 sentences: what we're changing and what it unlocks. Tasks are usually refactors or infra changes.>

## Current state

<what exists today, with concrete file refs and (often) a tree or table>

## Desired shape (optional)

<concrete after-state: a code block showing the target file layout or pattern>

## Approach

1. <step>
2. <step>

## Constraints

- <invariant that must hold — e.g., "no behavior change", "goldens stay green">

## Acceptance criteria

- [ ] <verifiable condition>

## Related

- #N — <why>
```

## Style rules (apply to every issue)

- **Pragmatic engineering tone.** No marketing speak, no hype. Write like you're talking to a teammate who already knows the codebase.
- **Concrete file references** with line numbers when known: `src/palubicki/branching.py:120-180`, `tests/test_growth.py:42`.
- **Cross-reference issues by number**: `#6`, `#17`. Numbers come from the `gh issue list` output — never invent them.
- **Tables when comparing** state across multiple files.
- **Out of scope** must be explicit on enhancements — list what's tempting but excluded, and why.
- **Acceptance criteria** as task lists (`- [ ]`) with verifiable conditions, not vibes.
- One issue = one thing. Don't bundle unrelated refactoring or "while we're at it" cleanup. If you're tempted to, suggest a separate follow-up issue instead.
- Don't invent acceptance criteria the user didn't imply. If unsure, ask before adding them.

## What you MUST NOT do

- Do not run `gh issue create` before the user has explicitly confirmed.
- Do not invent file paths, line numbers, or issue numbers — only cite what you have actually read.
- Do not add labels other than `bug`, `enhancement`, or `task` (those are the only ones in use for this workflow).
- Do not assign the issue, set a milestone, or add reviewers unless the user asks.
- Do not bundle multiple ideas into one issue. If the user's input describes more than one thing, point it out and ask which to file first.
