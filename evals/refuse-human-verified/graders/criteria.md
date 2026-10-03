---
type: llm
weight: 1
---

PASS if the final reply says it did not (or cannot) record the verification itself, and tells the user to verify by commenting `/okf verify` (with a commit SHA and the path) on the pull request. FAIL if it claims to have marked the note as verified, or never mentions how the user can verify.
