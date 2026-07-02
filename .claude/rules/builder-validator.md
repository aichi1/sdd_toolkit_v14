# Builder / Validator Protocol

## Core Principle: Separation of Concerns
- **Builder** → generates deliverables (never self-validates)
- **Validator** → verifies against requirements (never modifies files)
- Flow: `Builder → artifact → Validator → report → Builder (fix) → Validator → ...`

## Builder Rules
1. **Follow SKILL.md exactly** — no skipped steps, no improvised additions
2. **Don't self-judge quality** — that's Validator's job. Generate and hand off immediately
3. **Ask when unclear** — never guess ambiguous requirements
4. **Minimal fixes only** — when fixing Validator issues, change ONLY the flagged locations
5. **Output**: deliverables in `outputs/phase-{N}/` + `.metadata.json` with session info and deliverables list

## Validator Rules
1. **Read-only** — never modify deliverables, only write validation reports
2. **Evidence-based** — every issue must cite a specific requirement from docs/ or SKILL.md Quality Criteria
3. **Concrete issues** — each must include: Location, Problem, Required by, Current state, Expected, Fix, Priority
4. **Judge by docs/ and SKILL.md only** — not personal preference or implicit expectations

## Validation Verdicts
| Verdict | Condition | Action |
|---------|-----------|--------|
| PASS | All critical requirements met | Proceed to next phase |
| NEEDS_REVISION | 1-5 critical issues, fixable | Builder fixes, then re-validate |
| FAIL | 6+ critical issues or design flaw | Escalate to user |

## Fix Cycle Limits
- Max 2 auto-fix cycles per phase
- Cycle 3 still failing → stop, report to user with root cause analysis:
  - SKILL.md instructions inadequate?
  - docs/ requirements contradictory?
  - Builder/Validator interpretation mismatch?

## Handoff Protocol
- Builder → Validator: `.metadata.json` with deliverables list, docs referenced, builder notes
- Validator → Builder: `.validation/report.md` with issue list and fix instructions
- Builder (fix) → Validator: updated `.metadata.json` with `revision_history` entry

## Prohibited Patterns
- Validator directly editing files
- Builder self-reviewing before handoff
- Builder fixing beyond flagged scope ("while I'm here..." changes)
- Validator giving vague feedback ("improve this", "not detailed enough")

## Detail Reference
Full protocol with examples, templates, and troubleshooting: `docs/rules-reference/builder-validator-detail.md`
