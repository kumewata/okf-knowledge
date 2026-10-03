#!/bin/bash
# The shared bundle plus a newer revenue definition that replaces the old one.
set -euo pipefail
git init -q -b main
git config user.name "Eval"
git config user.email "eval@example.com"
mkdir -p knowledge/runbooks knowledge/metrics
cat > knowledge/CONVENTIONS.md <<'MD'
---
type: OKF Conventions
title: Knowledge bundle conventions
okf_conventions:
  types:
    Runbook: { stale_after_days: 180 }
    Metric: { stale_after_days: 180 }
    Note: { stale_after_days: 90 }
---

# Conventions

Paths are `/`-rooted. Only the okf-verify workflow adds `human:` verifications.
MD
cat > knowledge/index.md <<'MD'
---
okf_version: "0.2"
---
MD
cat > knowledge/metrics/revenue.md <<'MD'
---
type: Metric
title: Revenue
description: Recognized revenue for a period.
generated: { by: claude-code/claude-opus-5-5, at: 2026-01-10T00:00:00Z }
verified:
  - { by: human:alice, at: 2026-01-12T00:00:00Z }
stale_after: 2026-03-01T00:00:00Z
---

# Definition

Revenue is the sum of `net_amount` over delivered orders, recognized 14 days after delivery.
MD
cat > knowledge/metrics/revenue-v2.md <<'MD'
---
type: Metric
title: Revenue (FY2026)
description: Recognized revenue for a period, per the FY2026 policy.
generated: { by: claude-code/claude-opus-5-5, at: 2026-09-01T00:00:00Z }
stale_after: 2027-03-01T00:00:00Z
---

# Definition

Revenue is the sum of `net_amount` over delivered orders, recognized 30 days after delivery.
MD
