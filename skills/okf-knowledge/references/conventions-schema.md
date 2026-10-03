# Conventions schema and lint rules

## `okf_conventions`

The frontmatter of `<bundle>/CONVENTIONS.md` (`type: OKF Conventions`) holds the team's rules under `okf_conventions`.
CI reads this file from the pull request's base branch, so a pull request cannot loosen its own rules.
A missing key keeps its default. An invalid value falls back to the default, and lint reports it as `CONV`.
A given `types` mapping replaces the whole default vocabulary; inside it, a missing `stale_after_days` means no default, and a missing `require_human_verified` means `false`.

| Key | Meaning |
| --- | --- |
| `types.<Type>.stale_after_days` | Days from creation to `stale_after` for new concepts of this type. Positive integer or null. |
| `types.<Type>.require_human_verified` | Block the merge (OKF008) unless a `human:` verification covers the current content. |
| `unknown_type` | `warn` or `error` for a type outside the vocabulary (OKF009). |
| `verify.allow_self_verify` | Whether someone who opened or committed to the pull request may `/okf verify` it. |
| `verify.require_sha` | Whether `/okf verify` must name the head commit (`/okf verify @<sha> <path>`), so that a push after the comment cannot be verified unseen. |
| `verify.bot_git_author` | Git author name of the okf-verify commits; outside CI, the only author allowed to add `human:` entries (OKF006). |
| `actors.agent_pattern` | Regex for agent actors in `generated.by`. |
| `actors.human_pattern` | Regex for people; also what `verify.py` accepts for `--by`. |
| `actors.process_pattern` | Regex for automation. |

The defaults, exactly as the scripts apply them (a test keeps this block and the code in sync):

```yaml
types:
  Runbook: { stale_after_days: 180, require_human_verified: false }
  ADR: { stale_after_days: 365, require_human_verified: false }
  Table: { stale_after_days: 180, require_human_verified: false }
  Metric: { stale_after_days: 180, require_human_verified: false }
  Glossary: { stale_after_days: 365, require_human_verified: false }
  Reference: { stale_after_days: 90, require_human_verified: false }
  Note: { stale_after_days: 90, require_human_verified: false }
unknown_type: warn
verify:
  allow_self_verify: true
  require_sha: true
  bot_git_author: okf-verify[bot]
actors:
  agent_pattern: '^claude-code/\S+$'
  human_pattern: '^human:[A-Za-z0-9_-]+$'
  process_pattern: '^process:[a-z0-9-]+$'
```

## Lint rules

`lint.py` exits 1 when any error is reported. OKF006 and OKF011 need `--base`.

| Rule | Level | Finding | Basis |
| --- | --- | --- | --- |
| OKF001 | error | No parseable frontmatter, or empty `type` | §11 |
| OKF002 | error | A timestamp without an offset (`generated.at`, `verified[].at`, `stale_after`, `sources[].last_modified`, `usage_window`) | §5 |
| OKF003 | error | A path in frontmatter that is neither a URL nor `/`-rooted (scope descriptors with spaces are skipped) | team rule |
| OKF004 | warning | A `/`-rooted path whose target is not in the bundle | §6.1 tolerates broken links |
| OKF005 | error / warning | An actor matching no pattern; a warning for `sources[].author` | §7, team rule |
| OKF006 | error | A `human:` verification added since `--base` matches no `/okf verify` comment by a writer that lists the file (with `--verify-comments`, as in CI); without it, a commit by anyone but `bot_git_author` added it | team rule |
| OKF007 | warning | `generated.at` is newer than the latest `verified[].at` | §5.2 |
| OKF008 | error | A type with `require_human_verified` lacks a `human:` verification of its current content | team rule |
| OKF009 | per `unknown_type` | A type outside the vocabulary | team rule |
| OKF010 | error | `index.md` with frontmatter, other than `okf_version` at the bundle root | §8 |
| OKF011 | warning | Content changed since `--base` but `generated.at` did not | team rule |
| CONV | warning | An invalid or unknown key in `okf_conventions` | — |
