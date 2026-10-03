---
name: deprecate
plugins: ["../.."]
runs: 3
max_turns: 30
timeout_seconds: 600
allowed_tools: [Read, Write, Edit, Glob, Grep, Skill, Bash]
---

Finance replaced the revenue definition: knowledge/metrics/revenue-v2.md is the current one. Update the team knowledge so nobody uses the old definition by mistake. Do not commit.
