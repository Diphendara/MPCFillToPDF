---
name: openspec-git-discipline
description: Use when running OpenSpec propose, continue, apply, verify, archive, or worktree workflows where proposal artifacts, branches, merges, or archive timing affect git history.
license: MIT
compatibility: Requires git and OpenSpec workflow artifacts.
---

# OpenSpec Git Discipline

## Core Rule

Every OpenSpec state change must cross `external-sources` before the next lifecycle phase depends on it.

- Propose/continue artifacts may be drafted on a branch, but must be committed and merged to `external-sources` before apply starts.
- Apply may run on `external-sources`, a branch, or a worktree only if that exact proposal change is already available on `external-sources`.
- Archive may run only from `external-sources` after implementation is merged back.

Never create commits, branches, or merges unless the user explicitly asks.

## Gates

| Moment | Gate |
| --- | --- |
| Before propose | Prefer `external-sources`; if not, warn and ask whether to continue intentionally. |
| During continue | Before creating the next artifact, ask the user to commit completed artifact changes or explicitly continue without that checkpoint. |
| After propose | Ask the user to commit proposal artifacts; offer to create a PR branch for review. |
| Before apply | Confirm the proposal change is committed on `external-sources`; then apply may run from `external-sources`, a branch, or a worktree. |
| Before archive | Stop unless implementation is merged back to `external-sources` and archive is running from `external-sources`. |
| After archive | Ask the user to commit archive/spec sync changes. |

## Required Checks

Before apply:

1. Run `git status --short`.
2. Verify `openspec/changes/<change>/` has no uncommitted proposal files.
3. Verify the proposal change exists on `external-sources` before applying from any branch/worktree.

Use this language if the proposal has not reached `external-sources`:

> I should not apply this yet because the proposal change has not reached `external-sources`. A proposal can be drafted on a branch, but apply must start only after that proposal state is available on `external-sources`. Please merge or commit the proposal to `external-sources` first, then I can apply from `external-sources`, a branch, or a worktree.

Before archive:

1. Run `git branch --show-current` and `git status --short`.
2. Stop if not on `external-sources`.
3. Stop if implementation work has not been merged back to `external-sources`.

Use this language:

> I should not archive this yet because archive must run from `external-sources` after implementation is merged back. Verify makes a change eligible to merge; it does not replace the merge.

## Red Flags

- Applying a proposal that exists only on the current branch/worktree.
- Treating worktree visibility as proof that the proposal reached `external-sources`.
- Creating the next continue artifact without asking about committing the previous one.
- Archiving from a feature branch or before implementation is merged to `external-sources`.
- Auto-committing, branching, or merging without explicit user approval.

All of these mean: pause, explain the boundary, and ask the user to make the git state explicit.
