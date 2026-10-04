---
name: okf-knowledge
description: Use when writing, updating, reading, or maintaining team knowledge kept as an Open Knowledge Format (OKF) v0.2 bundle in a repository: a directory (`knowledge/` by default) whose `CONVENTIONS.md` has `type: OKF Conventions`. Covers runbooks, ADRs, table and metric definitions, glossary entries, references and notes; asking a person to verify knowledge; finding stale or unverified knowledge; regenerating `index.md`; fixing lint findings named OKF001–OKF012; and setting up a new bundle. Do NOT use for documentation that lives outside the bundle.
---

# okf-knowledge

The team keeps knowledge as an OKF v0.2 bundle: markdown files with YAML frontmatter, reviewed in pull requests.
Your job is to write knowledge that a reader can trust for the right reasons, and never to fake the reasons.

`<skill-dir>` below is the base directory shown when this skill loads.
Scripts run with `uv run <skill-dir>/scripts/<name>.py`; they declare their own dependencies.

## Find the bundle

A bundle is a directory whose root holds a `CONVENTIONS.md` with `type: OKF Conventions`.
`knowledge/` is the default name, but any directory works, and a repository may hold several bundles (not nested).
Work in the bundle that contains the file at hand: the nearest ancestor directory with such a `CONVENTIONS.md`.
Below, `<bundle>` is that directory; pass it to every script, and write `/`-rooted paths (rule 5) relative to it.
Read its `okf_conventions` before writing: it holds the type vocabulary, each type's `stale_after_days`, and which types need a human verification.
If there is no bundle and the user wants one, see "Set up a bundle".

## Rules

1. **Never add anything to `verified`.** Only the okf-verify workflow writes there, recording a person's `/okf verify` comment as `human:<id>`, and CI rejects any `human:` entry that does not match such a comment and any other entry added by hand, such as `process:` (OKF006). You may not verify on a person's behalf, even if asked; tell them how to do it instead.
2. When you create or change a concept's content, set `generated: { by: claude-code/<your model ID>, at: <now> }`. Leave `generated` alone when you change nothing but `verified`.
3. Every timestamp is an ISO 8601 datetime with an offset. Get the current time with `date -u +%Y-%m-%dT%H:%M:%SZ`.
4. Set `stale_after` on every new concept: now plus the type's `stale_after_days`. Compute it with the command below before writing the file; do not type the date by hand.
   `python3 -c "from datetime import *; print((datetime.now(timezone.utc)+timedelta(days=180)).strftime('%Y-%m-%dT%H:%M:%SZ'))"`
5. Paths in frontmatter (`resource`, `sources[].resource`) are URLs or bundle paths starting with `/`. Never `policies/x.md` or `../x.md`.
6. Record where a claim came from: add a `sources` entry with an `id`, and cite it with a footnote whose label is that id (`[^id]`).
7. Use only types in the vocabulary. If none fits, say so to the user rather than inventing one.

## Write or update a concept

1. Pick the type and copy its template from `<skill-dir>/templates/` (`runbook.md`, `adr.md`, `table.md`, `metric.md`, `glossary.md`, `reference.md`, `note.md`).
2. Replace every `<PLACEHOLDER>`. Delete body sections that do not apply rather than leaving them empty.
3. Link related concepts with bundle paths: `[orders](/tables/orders.md)`.
4. Regenerate the indexes: `uv run <skill-dir>/scripts/index.py <bundle>`.
5. Lint until there are no errors: `uv run <skill-dir>/scripts/lint.py <bundle> --base origin/main`. The rules are in `references/conventions-schema.md`.
6. In the pull request description, list the concepts that need a person to check them, and ask for verification (next section).

## Ask for a verification

Verification means a person compared the content with its sources or the system it describes.
Ask the person who can do that to check the pull request's latest commit, and then comment on the pull request, naming that commit:

```
/okf verify @<head commit SHA> knowledge/runbooks/restart-api.md
```

Several paths may follow; each must be a file the pull request changed, and all of them in one bundle (use one comment per bundle).
The workflow adds `{ by: human:<their GitHub ID>, at: <comment time> }` and pushes a commit.
It refuses commenters without write access, a SHA that is not the head, and (when the conventions say so) people who opened or committed to the pull request.
If the content changes afterwards, the verification no longer covers it (OKF007), and types that require one block the merge (OKF008).

## Read knowledge before relying on it

Before you use a concept to answer a question or make a change, check its frontmatter:

- `status: deprecated`: do not rely on it; follow the link to its replacement.
- `stale_after` in the past: treat it as possibly outdated, and say so.
- No `human:` entry in `verified`: it has not been checked by a person; say so when it matters.
- `generated.at` newer than the latest `verified[].at`: the latest change is unverified.

## Take stock

`uv run <skill-dir>/scripts/status.py <bundle>` lists stale, deprecated, unverified, changed-since-verification and unreadable concepts.
For each one, propose one of:

- **Re-verify**: still true; ask a person for `/okf verify`.
- **Update**: no longer true; edit it (rules 2–4 apply).
- **Deprecate**: superseded; set `status: deprecated` and link the replacement in the body.

## Set up a bundle

1. Ask the user where the bundle should live; suggest `knowledge/`. Call the answer `<bundle>`.
2. Copy `<skill-dir>/templates/CONVENTIONS.md` to `<bundle>/CONVENTIONS.md` and adjust it with the team.
3. Create `<bundle>/index.md` with `okf_version: "0.2"` in its frontmatter, then run `index.py <bundle>`.
4. Copy the workflows in `<skill-dir>/templates/github/` to `.github/workflows/`, and set `bundle: <bundle>` in each, plus `paths: ["<bundle>/**"]` in okf-lint. Leave the `uses:` lines as they are.
   If the repository already has okf workflows for another bundle, add a job per bundle to them instead: add `"<bundle>/**"` to okf-lint's `paths` list (it filters the whole workflow), and give the new okf-status job its own `label`.
5. Add a line to the repository's `CLAUDE.md`: knowledge lives in `<bundle>/`; start from `<bundle>/index.md`.
6. Tell the user what to set in GitHub, which you cannot do from here: protect the default branch (pull requests required; the okf-lint job `<job> / lint` as a required check; Code Owners review), add `/<bundle>/CONVENTIONS.md` to `CODEOWNERS`, and optionally a GitHub App for okf-verify. The README's "Protect the default branch" section has the details.

## References

- `references/spec-digest.md`: what OKF v0.2 requires, and the pitfalls these rules exist for.
- `references/conventions-schema.md`: every `okf_conventions` key with its default, and every lint rule.
