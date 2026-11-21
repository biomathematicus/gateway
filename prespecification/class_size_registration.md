# Typed event: registration of the class-size addendum to Module C (P0-D06)

Status: the design decisions listed in the addendum header were accepted by the PI on 2026-11-19. The specification beyond them (the model ladder, hypotheses H3 and H4, the support thresholds, and the 45-student cap) was fixed by the analyst before the freeze; a PI amendment to any of it enters Section 14 of the addendum as a deviation. The event follows the §0.4 template of `VER9_Architecture.md` and is ready for entry into `VER9_Log.md`. It was written before any within-course model was fitted to unshuffled grades; Section 12 of the addendum lists what was seen before the freeze.

```yaml
event_id: EVT-P0-D06-CLASS-SIZE-ADDENDUM-2026-11-19
event_type: DECISION
object_type: DELIVERABLE
object_id: P0-D06
claim_id: null
document: VER9_paper0_math_gateway.md
source_path: Economics/Paper0/module_c/class_size_addendum.md
source_locator: "# Module C addendum: section size and first-year performance"
source_sha256: 3dcc7f82cb30bb0199058c79c1720f03f7123034ff61aaf3bfd68a4cc147171f
decision: ACCEPTED
decision_owner: PI
effective_at: 2026-11-19
text_exact: >
  The class-size addendum to the Module C analysis plan, version
  1.0, is frozen. Outcome estimation for this question proceeds
  under its text. Any later change is recorded in Section 14 of the
  addendum with date and reason, and results from a deviating
  analysis are labeled exploratory.
reason_exact: >
  PI decisions of 2026-11-19: the class-size curves are to be
  examined as evidence for an intervention with a model of smaller
  sections; all 25 subjects with mathematics first; next-course
  grade as the leniency check; registration before estimation on
  real grades; section size within a course varies for logistical
  reasons.
```

## Frozen inputs

| Object | SHA-256 |
|---|---|
| `Economics/Paper0/module_c/class_size_addendum.md` | `3dcc7f82cb30bb0199058c79c1720f03f7123034ff61aaf3bfd68a4cc147171f` |
| `code/module_c/cs_data.py` | `f07af34068bc32023dc90c9c50b72322bf0b0a97a9d88e2f012f04a3984151ea` |
| `code/module_c/run_class_size.py` | `df7cf44653111d1699d0eba68c743657d6b5892a91cd21434219a74c95957b7a` |
| `code/module_c/mc_data.py` | `6ed4fa72be70c41fc59276167f982641be0ea4a75abcc391a0eea7b151269ea5` |
| `code/module_c/mc_models.py` | `ee149bff5cdf064b0db2cb84f9604d38d9bf75f00a41edd0e3202bd6448faa62` |
| `code/module_c/run_module_c.py` | `dde5a0bfd5e327e3d82578b4814a06ce366b7efde9d021bd99da524a11275136` |
| `code/figures/module_c/cohorts_2014_2019/stage0_subjects.csv` | `74018701f70a86a81bd351119123772d7b8902affcd2aebb5ff66c6d21588a98` |

The three `mc_*` and `run_module_c` files are the Module C pipeline as it stands after deviation D1; the addendum imports them unchanged. A whole-file hash cannot sit inside the file it describes, so the addendum's hash lives here.
