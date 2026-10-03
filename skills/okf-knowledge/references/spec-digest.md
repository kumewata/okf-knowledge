# OKF v0.2 digest

What the [OKF v0.2 specification](https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md) requires, in the order you need it.
Section numbers (§) point into the specification.

## Conformance (§11)

A bundle conforms when every `.md` file other than `index.md` and `log.md` has a parseable YAML frontmatter block with a non-empty `type`.
Nothing else is required.
Consumers must not reject a bundle for unknown types, unknown keys, broken links, or missing `index.md` files.
Quality is judged on other axes, below.

## Three independent trust axes (§5.3–§5.5)

| Axis | Key | Values | When absent |
| --- | --- | --- | --- |
| Trust tier | `verified[].by` | human-reviewed if any `human:` entry; machine-confirmed if only others | unverified |
| Lifecycle | `status` | `draft` / `stable` / `deprecated` | `stable` |
| Freshness | `stale_after` | stale when `now >= stale_after` | never stale |

A concept can be human-reviewed and deprecated, or machine-confirmed and stale. Check all three.
A bare `verified` mapping counts as a one-element list (§5.2).

## Provenance (§5.1)

`sources` lists what a concept derives from. Each entry needs `resource`; `id` keys footnote citations.
`author`, `usage_count` and `last_modified` are signals, not a score.

## Verification versus attestation (§10.6)

`verified` records that the definition was checked; it lives in the bundle.
Attestation checks a single run of an Attested Computation and is not stored.
This plugin handles `verified` only. Attested Computations are out of scope: the specification leaves the receipt and verdict wire formats and the attester ABI to a future version (§12).

## Pitfalls the team rules exist for

- **Date-only timestamps.** Every timestamp must carry an offset (§5). A date-only `stale_after` is ignored by the reference implementation, so the concept never goes stale. Lint rule OKF002.
- **Relative paths.** §6.2 allows "a relative path", and its example resolves from the concept's directory, but the specification's own examples and the bundled sample also write root-relative paths without a leading `/`. A consumer cannot tell which is meant. The team writes `/`-rooted paths only. Lint rule OKF003.
- **Actors outside the three forms.** §7 names `<producer>/<version>`, `human:<id>` and `process:<id>`; examples elsewhere use `team:`. The team pins exact patterns in `CONVENTIONS.md`. Lint rule OKF005.
- **Self-declared verification.** Anyone, including an agent, can type `human:` into a file. The team accepts `human:` entries only from the okf-verify workflow. Lint rule OKF006.
