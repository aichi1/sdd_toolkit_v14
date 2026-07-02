# Quality Standards

## docs/ vs skills/ Relationship
- **docs/** = What (requirements, scope, constraints, audience, format)
- **skills/** = How (procedures, tools, quality criteria, output specs)
- docs/ is authoritative: if docs/ changes, update affected skills/
- skills/ references docs/ (never duplicates content from docs/)
- Consistency check: before run-phase, verify docs/ ↔ skills/ alignment

## Quality Gates (all phases)

### Gate 0: Basic Completeness (mandatory, never exempt)
- All SKILL.md-specified deliverables exist and are non-empty
- `.metadata.json` exists with required fields
- Markdown renders correctly

### Gate 1: docs/ Requirements (mandatory)
- All "must-have" requirements from docs/ are addressed
- Scope boundaries respected (no out-of-scope content)
- Target audience level appropriate (per docs/audience.md)

### Gate 2: SKILL.md Quality Criteria (mandatory)
- Every step in SKILL.md procedure was executed
- All Quality Criteria items checked (Met/Partial/Missing)
- Output matches specified format and structure

### Gate 3: Consistency (recommended)
- No contradictions with previous phase outputs
- Terminology consistent across deliverables
- Claims supported by evidence; tables match narrative

## Phase-Specific Additions
| Phase Type | Additional Checks |
|---|---|
| Research/Analysis | Data sources cited, survey targets fully covered |
| Comparison/Evaluation | Same criteria applied to all subjects, scoring justified, recommendation consistent with scores |
| Report/Document | Follows docs/format.md structure, self-contained (readable without prior phases), minimal typos |

## Exemptions
- Gate 0 + mandatory requirements: **never exempt**
- Other gates: exempt only with explicit user approval → record as `completed_with_issues`
- Time pressure: fix Critical only, defer Suggestions, note in retrospective

## Quality Score
- Phase Quality Score (PQS) = passed gates / total gates × 100
- Project Quality Score = average of all PQS

## Detail Reference
Full gate definitions, scoring templates, and custom gate examples: `docs/rules-reference/quality-gates-detail.md`
