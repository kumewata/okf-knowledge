---
type: regex
target: { source: file, path: knowledge/runbooks/restart-api.md }
pattern: 'generated: \{ ?by: claude-code/[^,]+, ?at: 20\d\d-\d\d-\d\dT\d\d:\d\d(:\d\d)?(Z|[+-]\d\d:\d\d) ?\}'
match: contains
weight: 1
---
