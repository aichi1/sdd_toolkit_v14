# SDD Core Workflow

## Command Sequence (MUST follow this order)
```
/init-task → /run-phase N → [/re-init-task → /run-phase N] → /finalize → /retrospective
```

Note: `/re-init-task → /run-phase N` のループは任意回数繰り返し可能。

## /init-task
- Creates: docs/ (What), skills/ (How), CLAUDE.md, metadata.json
- Requires: empty or new project directory
- Completion: all docs/ have content (not template stubs), all SKILL.md exist

## /run-phase
- Input: phase number (`1`), range (`1-3`), or `all`
- Flags: `--review-only`, `--no-validation`, `--checkpoint`, `--batch`
- Flow per phase:
  1. Builder generates deliverables → `outputs/phase-{N}/`
  2. Pre-check via `scripts/validate-outputs.py --phase {N}`
  3. Fast-path (if pre-check PASS + ≤5 criteria + ≤3 files) or full Validator
  4. PASS → next phase | NEEDS_REVISION → fix cycle (max 2 auto) | FAIL → escalate
- Default multi-phase: Smart mode (auto-advance on PASS, pause on issues)

## /re-init-task
- Requires: all phases in current iteration completed or completed_with_issues
- Flow:
  1. Check prerequisites (all phases completed)
  2. Show current status summary
  3. Delta intake (max 5 questions — goal, features, constraints, phase count, docs)
  4. Update docs/ with changes (append, not overwrite)
  5. Create new phase skills/ (continuing phase numbers)
  6. Update metadata.json (add iterations[] entry, increment phase_count)
  7. Update iteration_history.md (add new section)
  8. Update CLAUDE.md Deliverables section (add iteration subsection)
- Backward compatibility: first re-init auto-creates iterations[0] for existing phases
- Phase numbering: continuous (Iter1: 01-04, Iter2: 05-08)

## /finalize
- Archives to `~/.sdd-knowledge/docs-archive/`
- Extracts/updates starters
- Generates finalization-report.md
- Warns if Critical Issues remain

## /retrospective
- Structured Q&A + metrics
- Saves: ./retrospective.md + ~/.sdd-knowledge/retrospectives/*.json
- Updates summary.json

## Phase Dependencies
- Phase N requires Phase N-1 completed (unless explicitly independent)
- Skip allowed only with user approval → status: `completed_with_issues`

## Error Handling
- Missing prerequisite phase → prompt to run it first
- 3x NEEDS_REVISION → stop auto-fix, escalate to user
- Builder timeout (>10min) → save partial, ask user
- Validator timeout → mark `not_validated`

## Ad-hoc Feature Addition (independent of phase workflow)

```
/add-feature [機能名]
```

- Creates: `.steering/YYYYMMDD-機能名/` (requirements.md, design.md, tasklist.md)
- Autonomous implementation until all tasks in tasklist.md are completed
- Uses SDD knowledge base (`scripts/generate_context.py`, `scripts/search_knowledge.py`) for context
- Independent of `/run-phase` workflow — no Builder/Validator pattern
- Deliverables stay in `.steering/` (not `outputs/`)
- See: `.claude/commands/add-feature.md`, `.claude/skills/add-feature/SKILL.md`

## Detail Reference
Full workflow details, execution patterns, and troubleshooting: `docs/rules-reference/sdd-workflow-detail.md`
