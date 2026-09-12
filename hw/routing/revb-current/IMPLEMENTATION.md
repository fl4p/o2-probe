# Current Rev B implementation

The saved `o2-probe.kicad_pcb` is the authoritative routed artifact. The neighboring project, rules and schematic belong with it. Use `verify_revb_current.py` and `make_fab_revb_current.py` for verification/export of that artifact.

`migrate_revb_current.py` and the `author_revb_*.py` files record the geometry migration and local repairs. They are ordered implementation steps with source-state assertions, not an idempotent rebuild of the completed route. Do not run the migration over the finished PCB. `route_revb_current.py`, `route_revb_power_repair.py`, `route_revb_neck_completion.py` and `route_revb_12v_completion.py` pin the recorded router attempts; the failed neck attempt is retained as provenance and is not accepted output. Native full-error DRC and explicit final review determine acceptance.

The main routing seed and run receipts are under `provenance/`. Repairs retain their exact deltas and independent evidence under `evidence/`. The source used the existing 89 mm outline and retained cell interface and thermal slot locations.

Process minima are user-authorized 0.10 mm trace, 0.10 mm ordinary copper clearance and 0.20 mm via drill, with 0.40 mm minimum via diameter. Other project rules remain in the native project/DRU. This is a user-overridden engineering profile, not a claim of standard Aisler process compliance.

Unpopulated C4 (22 uF) and C8 (1 uF) retain their population values and native DNP flags. R4/R39 also remain DNP. J5/F3 and the optional external heated ring remain deferred to Rev C.
