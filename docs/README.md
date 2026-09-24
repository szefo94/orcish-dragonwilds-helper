# Documentation map

This directory contains several kinds of documentation. They do not all have the same authority.

For repository-wide coding rules and the source-of-truth hierarchy, start with [../AGENTS.md](../AGENTS.md).

| Document | Status | Use it for |
| --- | --- | --- |
| [FISHING.md](FISHING.md) | **Active feature specification** | Fishing state semantics, cue priority, calibration, fail-safe behavior, known limitations |
| [../roadmap.md](../roadmap.md) | **Active roadmap** | Planned work, priorities, validation gates, intentionally deferred features |
| [CHANGELOG.md](CHANGELOG.md) | **Historical record** | Release history, past behavior changes, verification notes |
| [FRAMEWORK.md](FRAMEWORK.md) | **Architecture reference / partially historical** | Reusable architectural patterns and design rationale; verify concrete layout/version claims against current code |
| [AIM_RESEARCH.md](AIM_RESEARCH.md) | **Research** | Aim/target-tracking experiments, evidence and candidate approaches |
| [SCOUT_RESEARCH.md](SCOUT_RESEARCH.md) | **Research** | Scout visual/process-telemetry investigation and design |
| [SCOUT_CANDIDATES.md](SCOUT_CANDIDATES.md) | **Research evidence** | Semantic memory candidates and promotion/validation criteria |
| [INTERNAL_TELEMETRY.md](INTERNAL_TELEMETRY.md) | **Experimental research** | UE4SS/Frida/internal telemetry setup, observations and recovery experiments |
| [PUBLICATION_REVIEW.md](PUBLICATION_REVIEW.md) | **Project/release review** | Public-repository publication checks |
| [THIRD_PARTY.md](THIRD_PARTY.md) | **Reference** | Third-party components and related notes |

## Interpretation rules

- **Code and tests describe current implemented behavior.**
- **AGENTS.md defines repository-wide engineering constraints.**
- **Feature specifications explain intended semantics and rationale.**
- **Roadmap items are not implemented merely because they are documented.**
- **Research documents may contain hypotheses, failed approaches, provisional thresholds, or observations tied to a particular game build. Treat them as evidence to validate, not instructions to wire directly into live control.**
- **Historical documentation can explain why code exists, but concrete version/layout statements may become stale. Verify them against the current tree before making structural changes.**

When changing behavior, update the smallest relevant active document in the same PR when practical. Avoid copying the same behavioral rule into many files; prefer one authoritative explanation and links from other docs.
