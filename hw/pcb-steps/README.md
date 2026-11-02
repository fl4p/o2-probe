# pcb-steps

One-shot board-surgery scripts: each made one recorded change to a board
(`adopt_*`, `author_revb_*`, `route_*`, `repair_*`, `restore_*`, `trim`/`close`/`finish`).
They are kept because the dated docs and the routing evidence cite them, not
because they are rerun. Many no longer apply to the current board. For example,
`clear_cell_drill_envelope.py` asserts Rev A geometry.

They moved here from `hw/` on 2026-11-02. Each one resolves paths from `hw/`
(its `HERE`/`ROOT` is the parent directory) and puts `hw/` on `sys.path`, so
they import `thermal_design`, `gen_pcb`, `critical_routes` and so on as before.
Run them from anywhere, with KiCad's Python where they import `pcbnew`. Dated
documents that write `python3 author_revb_bus.py` mean `python3 pcb-steps/author_revb_bus.py`.

The live toolchain stays in `hw/`: `gen_sch.py`, `gen_pcb.py`, the `audit_*`
scripts, `make_fab*` and the `verify_*`/`inspect_*` checks that the fab scripts call.
