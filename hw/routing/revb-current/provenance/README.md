# Route provenance

`main-seed.kicad_pcb` is the authored input to the main routine-routing pass;
its same-stem project and rules are retained. `main-route-run.json` fingerprints
the exact router revision, flags, input and output. `main-route-drc.json`
records that intermediate result, including six opens; it is not final acceptance.
`main-route.log` and `main-route-summary.json` are the router's own reports.
Native KiCad reports, not router completion messages, govern acceptance.

C17 was connected locally after that pass. Its copper displaced unlocked
routing on three named nets, recorded by exactUUID in
`c17-disturbed-net-withdrawal.json`. Those nets require a separate bounded
completion pass around the final locked critical repairs. The current accepted
PCB is the saved board one directory above; use its final review artifacts.

The board adapters record authored placement and copper decisions. The
main-route seed and committed accepted board remain explicit geometry inputs;
regenerating the schematic alone does not recreate the routed PCB.
