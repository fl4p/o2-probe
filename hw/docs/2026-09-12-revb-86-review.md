# Independent Rev B 86 mm review — 2026-09-12

**Accepted as a bounded 3 mm cable-end reduction for new artifact generation.** The board is now 20 × 86 mm. No component, physical hole, track, via or thermal-slot location changes. This review does not supersede the archived 89 mm package or imply procurement/production qualification.

| Object | SHA-256 |
|---|---|
| Accepted 89 mm source | `3c24db8193af09d4d9ad07b2166c7f818885211b63b3e2af6e0c7cbec900c665` |
| Refilled 86 mm candidate | `9da60f0c3bbf4bc85fe11fb920bd16b3d50b55f7edb4ab5fc0db4f19af203794` |
| Full native DRC report | `75a67495607f25a6486aaab1dfdce69d8d8ca7e6a69de4aa9a95b72be1dbc505` |

## Exact geometry and copper preservation

The top straight edge moves from Y50 to Y53. Both existing rounded top corners move 3 mm in Y without changing their geometry; the two vertical sides meet them at Y55 instead of Y52. Bottom Y139, width 20 mm, all other outline geometry and all four thermal slots remain exact. Five outline objects change. The sole annotation change is `CABLE`, moved from (110,51.5), 0 degrees to (110,57), 90 degrees, retaining 0.8 mm text and 0.12 mm stroke.

Independent native comparison confirms **all 2543 track/via objects, including 195 vias, are exact** in UUID, net, geometry and lock state. All 83 native footprint/pad records are exact. Complete normalized footprint serialization—including pad mask/paste settings, graphics, values and population attributes—is also exact. Apart from the six named drawing objects and saved zone fills, remaining normalized board serialization is unchanged. Zone parameters remain exact.

Native saved-fill polygon comparison finds only 58.197 mm² of GND removed on each face by the new top and rounded-corner boundary. No copper is added by refill. These differences end above Y55.003; all filled copper below Y55.3 is identical, including the complete HEATER_LOW fill. Thus the previously reviewed lower guard/thermal geometry is preserved by direct equality, rather than assumed from unchanged track endpoints. The changed upper margin is the only lost copper area. Complete native connectivity remains closed.

## Cable edge and visible annotation

The four cable PTH copper lands remain centered at X103,107.7,112.3 and 117 mm, Y54.5, with 1.85 mm copper diameter and 0.85 mm drill. Their entire land width lies within the new straight top-edge span X102..118; the top corners therefore do not reduce the nominal **0.575mm copper-to-edge clearance**. Nominal hole-edge material to the top cut is 1.075 mm. The separate 2.2 mm NPTH cable holes remain at Y64.7. These are measurements of the existing CAD, not inferred dimensions of an external cable or housing.

The independent reviewer viewed the actual native front render `routing/revb-86/evidence/front.png`: the vertical CABLE label is legible between the inner wire lands, and the shortened corners/land margin are visually consistent with the native geometry. No new overlap or clipped annotation was found. Existing raised/dressed wire and temporary programming-head fit dispositions remain within the prior manual-assembly scope; the shrink is not a structural or assembled-interface qualification.

## Native outcome and remaining scope

Full native DRC reports **zero errors, zero unconnected items and zero schematic-parity findings**, with the same ten individually reviewed courtyard warnings and two intentional GUARD endpoint warnings. The latter remain exact UUIDs `7a4d4b0e-2f12-4bd4-b267-16bb450f841a` and `89269d21-c6ed-4b39-b0a9-b4b13dbc9d4f`; their driving connection and shielding geometry are unchanged. Rules, schematic and component selection are preserved. No DRC suppression or clearance relaxation was used for this shrink.

Measurement evidence is `checks/revb-86-independent/geometry.json`, produced by the fingerprinted native diagnostic `measure_shrink.py` in the same directory; successful measurement runtime was 1.117 s. The initial diagnostic filename shadowed Python's inspect module and failed before producing a result; renaming the diagnostic resolved that tooling issue. The final evidence uses only the successful native run. New 86 mm verifier/export code and actual exported artifacts require their separate review. The 89 mm review and artifact receipt remain historical and are not silently rebound to this board.
