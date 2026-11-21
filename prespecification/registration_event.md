# Typed event: registration of the Module C analysis plan (P0-D06)

Status: ACCEPTED by the PI on 2026-11-18. The event follows the
§0.4 template of `VER9_Architecture.md` and is ready for entry into
`VER9_Log.md`. It was written before any registered estimation.

```yaml
event_id: EVT-P0-D06-REGISTRATION-2026-11-18
event_type: DECISION
object_type: DELIVERABLE
object_id: P0-D06
claim_id: null
document: VER9_paper0_math_gateway.md
source_path: Economics/Paper0/module_c/analysis_plan.md
source_locator: "# Module C analysis plan"
source_sha256: 333fb7f8a7f44a66ed0c395e3d5b79c4238b573fb9be7eb7cbf93cbed640b468
decision: ACCEPTED
decision_owner: PI
effective_at: 2026-11-18
text_exact: >
  The Module C analysis plan, version 1.0, is frozen. Outcome
  estimation proceeds under this text. Any later change is recorded
  in Section 17 of the plan with date and reason, and results from a
  deviating analysis are labeled exploratory.
reason_exact: >
  PI answers of 2026-11-18: all cohorts; CAP retained with a flag;
  demographics block included; thresholds accepted; IRB coverage
  confirmed by the PI; the two amendments of version 0.2 accepted.
```

## Frozen inputs

| Object | SHA-256 |
|---|---|
| `Economics/Paper0/module_c/analysis_plan.md` | `333fb7f8a7f44a66ed0c395e3d5b79c4238b573fb9be7eb7cbf93cbed640b468` |
| `Economics/Paper0/module_c/stage0_maps.md` | `074de6c5643ebe5dfef728890e766c65f717007a5521c99172f701bcddd7f835` |
| `code/module_c/mc_data.py` | `44a3ec0cdd0b18e4df36c683ea2abc4cc3dc68098439303d5e43a94376e20494` |
| `code/module_c/mc_models.py` | `ee149bff5cdf064b0db2cb84f9604d38d9bf75f00a41edd0e3202bd6448faa62` |
| `code/module_c/run_module_c.py` | `98611809d466f23f31a68e4c58ae240c333f5f55a38fad259d7f5e0f26d75572` |
| `code/ingest/crdc_courses.py` | `f330c81df01c3f62d83eedf52fe7c4058c0948ef44c79dfd251972fd352562e5` |
| `core.hs_crosswalk` (GATEWAY, 1,663 rows, ordered name-city-zip, fields joined by a bar) | `bf71809ee9a121c86881f3b10aa8fc1a90eec6bdbad176cf1b2ec46ba502e000` |

A whole-file hash cannot sit inside the file it describes, so the plan's hash lives here.
