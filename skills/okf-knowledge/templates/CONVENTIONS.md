---
type: OKF Conventions
title: Knowledge bundle conventions
description: Team rules for this OKF v0.2 bundle, read by the okf-knowledge scripts.
okf_conventions:
  # A given `types` mapping replaces the default vocabulary.
  types:
    Runbook: { stale_after_days: 180, require_human_verified: false }
    ADR: { stale_after_days: 365, require_human_verified: false }
    Table: { stale_after_days: 180, require_human_verified: false }
    Metric: { stale_after_days: 180, require_human_verified: false }
    Glossary: { stale_after_days: 365, require_human_verified: false }
    Reference: { stale_after_days: 90, require_human_verified: false }
    Note: { stale_after_days: 90, require_human_verified: false }
  unknown_type: warn            # warn | error
  verify:
    allow_self_verify: true     # may someone who committed to the PR verify it?
    require_sha: true           # must /okf verify name the commit, as in /okf verify @<sha> <path>?
    bot_git_author: okf-verify[bot]
  actors:
    agent_pattern: '^claude-code/\S+$'
    human_pattern: '^human:[A-Za-z0-9_-]+$'
    process_pattern: '^process:[a-z0-9-]+$'
---

# Conventions

- Paths in frontmatter are URLs or bundle paths starting with `/`.
- Timestamps are ISO 8601 datetimes with an offset, such as `2026-10-03T14:00:00+09:00`.
- People are `human:<GitHub ID>`. Agents are `claude-code/<model ID>`. Automation is `process:<name>`.
- Only the okf-verify workflow adds `human:` entries to `verified`. Ask for a verification by commenting `/okf verify @<sha> <path>` on the pull request.
