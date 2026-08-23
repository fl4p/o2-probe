# Accepted routing provenance

The accepted board was completed with bounded per-net passes from
KiCadRoutingTools at commit
`81a3c1930892cf9170fd15f8d9e61327d8420596`. Source:
<https://github.com/drandyhaas/KiCadRoutingTools>.

The release sequence used a 0.09 mm track floor, 0.15 mm clearance, and
0.25/0.15 mm advanced vias. The final targeted passes rerouted only the nets
affected by the moved LMP91000, SGX airflow slot, driven guard, and split plane;
the final scope included `/3V3D`, `/+12V_SW`, `/I2C_SCL`, `/VA_MON`, and
`/AFE_MENB`. Terminal escalation and via-rung fallback were disabled.

KRT output was never treated as acceptance evidence. Every promoted candidate
was reopened, zones were refilled, and KiCad 10.0.5 recomputed clearance,
connectivity, holes, outline, and schematic parity. The deterministic endpoint
cleanup is retained in `repair_route_endpoints.py`; the final manufacturing
gate is `audit_pcb.py --calibrate` plus KiCad DRC.
