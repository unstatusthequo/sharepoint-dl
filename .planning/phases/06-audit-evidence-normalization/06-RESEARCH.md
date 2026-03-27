# Phase 06 Research: Audit Evidence Normalization

**Date:** 2026-03-27
**Question:** What do we need to know to plan Phase 06 well?

## Recommended Approach

- Keep this phase docs-only. The code gaps are already closed by Phases 4 and 5.
- Normalize the verification docs for Phases 1-3 so they reflect the current truth after gap-closure work:
  - completed human checks should be recorded as completed evidence, not pending human gates
  - "verified by design" claims should stay clearly labeled and should not be rewritten as live human verification
  - reopened requirements now owned by Phases 4 and 5 should no longer be claimed as fully satisfied by Phases 1-3
- Update `ROADMAP.md` so the phase-detail plan counts and progress table match the plans actually on disk, including Phases 4-6.
- Leave `.planning/v1.0-MILESTONE-AUDIT.md` alone in this phase. It is the pre-closure audit artifact; the refreshed audit should come from the next `$gsd-audit-milestone` run.

## Exact Contradictions To Fix

- `01-VERIFICATION.md`
  - frontmatter still says `status: human_needed` even though `01-03-SUMMARY.md` records completed manual verification
  - requirement coverage still claims `ENUM-03` in Phase 1, but traceability now assigns that integrated download-flow requirement to Phase 4
- `02-VERIFICATION.md`
  - human verification section says resume was verified, but `02-03-SUMMARY.md` says resume was only "verified by design"
  - requirement coverage still claims `DWNL-02` and `CLI-03` in Phase 2, but those reopened gaps are now closed by Phase 4
- `03-VERIFICATION.md`
  - includes a "Human Verification Required" section while also saying "No gaps"
  - requirement coverage still claims `VRFY-02` in Phase 3, but the manifest-path gap was reopened and closed by Phase 5
- `ROADMAP.md`
  - progress table still shows stale counts for Phases 1-3
  - phase-detail sections still show stale plan counts for Phase 4 and an unplanned placeholder for Phase 6

## Recommended Split

One plan is enough:
1. normalize Phase 1-3 verification docs
2. normalize roadmap accounting and Phase 6 handoff

## Files Phase 06 Should Modify

- `.planning/phases/01-foundation/01-VERIFICATION.md`
- `.planning/phases/02-download-engine/02-VERIFICATION.md`
- `.planning/phases/03-forensic-deliverables/03-VERIFICATION.md`
- `.planning/ROADMAP.md`

## Verification Strategy

- Verify Phase 1-3 verification docs no longer contradict their own summaries or current requirement ownership.
- Verify `ROADMAP.md` plan counts match the actual planned/completed plans:
  - Phase 1 = `3/3`
  - Phase 2 = `3/3`
  - Phase 3 = `2/2`
  - Phase 4 = `2/2`
  - Phase 5 = `1/1`
  - Phase 6 = `0/1` after planning
- Run `uv run pytest -p no:playwright -q` as a green-workspace sanity check before re-audit.

## Traps To Avoid

- Do not invent new human verification that never happened.
- Do not rewrite execution summaries; treat them as historical evidence.
- Do not leave Phase 1-3 requirement tables claiming ownership of requirements now closed by Phases 4 and 5.
- Do not refresh the milestone audit report inside this phase; the next audit command should do that explicitly.
