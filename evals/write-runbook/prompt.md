---
name: write-runbook
plugins: ["../.."]
runs: 3
max_turns: 30
timeout_seconds: 600
allowed_tools: [Read, Write, Edit, Glob, Grep, Skill, Bash]
---

Add a runbook at knowledge/runbooks/restart-api.md to the team knowledge for restarting the API server: run `sudo systemctl restart api`, then check that `curl -fsS http://localhost:8080/healthz` succeeds. If it fails, page #oncall. Do not commit.
