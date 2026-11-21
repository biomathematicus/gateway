# Frozen copies of the registered files

Created 2026-11-20, after the REV5 review asked that the frozen versions be preserved beside their hashes. Each file below was copied while its SHA-256 still matched the registration record, so the copy is the registered file.

| File | SHA-256 | Registered in |
|---|---|---|
| `class_size_addendum_v1.0.md` | `3dcc7f82cb30bb0199058c79c1720f03f7123034ff61aaf3bfd68a4cc147171f` | `class_size_registration.md` |
| `cs_data.py` | `f07af34068bc32023dc90c9c50b72322bf0b0a97a9d88e2f012f04a3984151ea` | `class_size_registration.md` |
| `run_class_size.py` | `df7cf44653111d1699d0eba68c743657d6b5892a91cd21434219a74c95957b7a` | `class_size_registration.md` |
| `mc_data.py` (state after deviation D1) | `6ed4fa72be70c41fc59276167f982641be0ea4a75abcc391a0eea7b151269ea5` | `class_size_registration.md`; plan Section 17, D1 |
| `mc_models.py` | `ee149bff5cdf064b0db2cb84f9604d38d9bf75f00a41edd0e3202bd6448faa62` | both registration records |
| `run_module_c.py` (state after deviation D1) | `dde5a0bfd5e327e3d82578b4814a06ce366b7efde9d021bd99da524a11275136` | `class_size_registration.md`; plan Section 17, D1 |
| `stage0_maps.md` | `074de6c5643ebe5dfef728890e766c65f717007a5521c99172f701bcddd7f835` | `registration_event.md` |
| `stage0_subjects.csv` | `74018701f70a86a81bd351119123772d7b8902affcd2aebb5ff66c6d21588a98` | `class_size_registration.md` |

## To restore from the Dropbox version history

Three registered files no longer exist in their frozen state in the working tree, because deviations were written into them after the freeze. Their registered hashes are in `registration_event.md`; a restored copy is the frozen file when its SHA-256 matches.

| File | Registered SHA-256 | State to restore |
|---|---|---|
| `analysis_plan.md` | `333fb7f8a7f44a66ed0c395e3d5b79c4238b573fb9be7eb7cbf93cbed640b468` | version 1.0 as frozen on 2026-11-18, before Section 17 received D1, A1, and D2 |
| `mc_data.py` | `44a3ec0cdd0b18e4df36c683ea2abc4cc3dc68098439303d5e43a94376e20494` | before the cohort option of D1 |
| `run_module_c.py` | `98611809d466f23f31a68e4c58ae240c333f5f55a38fad259d7f5e0f26d75572` | before the cohort option of D1 |

`code/ingest/crdc_courses.py` also differs from its registered hash (`f330c81d...`; current `6c0a49e1...`). The project notes record that the loader was extended on 2026-11-19 with the grades 7-8 enrollment estimate, after the registration. The subject coefficients and standard errors of the performance models reproduce to four decimals on the current tables (checked by `rev5_module_c.py` on 2026-11-20), so the school measures the models read are unchanged in effect. The change is recorded in Section 17 of the plan (record A2, 2026-11-20).
