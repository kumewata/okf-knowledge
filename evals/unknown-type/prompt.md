---
name: unknown-type
plugins: ["../.."]
runs: 3
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Write, Edit, Glob, Grep, Skill, Bash]
---

Add a postmortem of yesterday's checkout outage to the team knowledge, as a Postmortem document: root cause was an expired TLS certificate; it lasted 42 minutes. Do not commit.
