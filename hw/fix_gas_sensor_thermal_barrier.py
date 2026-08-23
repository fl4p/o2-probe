#!/usr/bin/env python3
"""Replace the ineffective gas-sensor slots with a transverse thermal barrier.

The released board placed two long slots parallel to the heater-to-U13 heat
flow.  This migration rotates them across that path, constrains all required
signals to the centre neck, and splits the In2 GND pour across the same barrier
so the plane cannot bypass the mechanical isolation as a copper heat strap.
"""

from pathlib import Path
import os
import sys

try:
    import wx

    _APP = wx.AppConsole()
    import pcbnew
except ImportError:
    sys.exit("run with KiCad's bundled Python")


HERE = Path(__file__).resolve().parent
SRC = Path(os.environ.get("O2_PCB_IN", HERE / "o2-probe.kicad_pcb"))
OUT = Path(os.environ.get("O2_PCB_OUT", HERE / "o2-probe.kicad_pcb"))
board = pcbnew.LoadBoard(str(SRC))
ORIGIN_X_MM = 100.0
ORIGIN_Y_MM = 50.0


def point(x: float, y: float):
    return pcbnew.VECTOR2I_MM(ORIGIN_X_MM + x, ORIGIN_Y_MM + y)


def local_xy(position):
    return (
        round(pcbnew.ToMM(position.x) - ORIGIN_X_MM, 3),
        round(pcbnew.ToMM(position.y) - ORIGIN_Y_MM, 3),
    )


def segment(net, layer, start, end, width):
    track = pcbnew.PCB_TRACK(board)
    track.SetNet(net)
    track.SetLayer(layer)
    track.SetStart(point(*start))
    track.SetEnd(point(*end))
    track.SetWidth(pcbnew.FromMM(width))
    board.Add(track)
    return track


def via(net, position, diameter=0.25, drill=0.15):
    item = pcbnew.PCB_VIA(board)
    item.SetNet(net)
    item.SetPosition(point(*position))
    item.SetWidth(pcbnew.FromMM(diameter))
    item.SetDrill(pcbnew.FromMM(drill))
    item.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    board.Add(item)
    return item


def edge_line(start, end):
    shape = pcbnew.PCB_SHAPE(board)
    shape.SetShape(pcbnew.SHAPE_T_SEGMENT)
    shape.SetStart(point(*start))
    shape.SetEnd(point(*end))
    shape.SetLayer(pcbnew.Edge_Cuts)
    shape.SetWidth(pcbnew.FromMM(0.05))
    board.Add(shape)


def edge_arc(start, midpoint, end):
    shape = pcbnew.PCB_SHAPE(board)
    shape.SetShape(pcbnew.SHAPE_T_ARC)
    shape.SetArcGeometry(point(*start), point(*midpoint), point(*end))
    shape.SetLayer(pcbnew.Edge_Cuts)
    shape.SetWidth(pcbnew.FromMM(0.05))
    board.Add(shape)


def slot(x, y, length, width):
    x0, x1 = x - length / 2, x + length / 2
    y0, y1 = y - width / 2, y + width / 2
    radius = width / 2
    edge_line((x0 + radius, y0), (x1 - radius, y0))
    edge_arc((x1 - radius, y0), (x1, y), (x1 - radius, y1))
    edge_line((x1 - radius, y1), (x0 + radius, y1))
    edge_arc((x0 + radius, y1), (x0, y), (x0 + radius, y0))


def replace_zone_outline(zone, corners):
    outline = pcbnew.VECTOR_VECTOR2I()
    for x, y in corners:
        outline.append(point(x, y))
    zone.Outline().RemoveAllContours()
    zone.AddPolygon(outline)


# Delete only the two old local-x 5/13, local-y 119.5 longitudinal slots.
old_slot_items = []
for drawing in board.Drawings():
    if drawing.GetLayer() != pcbnew.Edge_Cuts:
        continue
    bbox = drawing.GetBoundingBox()
    centre = local_xy(bbox.GetCenter())
    if 4.4 < centre[0] < 13.6 and 115.8 < centre[1] < 123.2:
        old_slot_items.append(drawing)
assert len(old_slot_items) == 8, f"expected eight old slot items, found {len(old_slot_items)}"
for drawing in old_slot_items:
    board.Remove(drawing)

gas_label = [
    drawing for drawing in board.Drawings()
    if isinstance(drawing, pcbnew.PCB_TEXT) and drawing.GetText() == "GAS / DO NOT POT"
]
assert len(gas_label) == 1, f"expected one gas-side label, found {len(gas_label)}"
gas_label[0].SetPosition(point(10.0, 109.5))

tp7 = next(footprint for footprint in board.Footprints() if footprint.GetReference() == "TP7")
assert local_xy(tp7.GetPosition()) == (10.0, 112.5), "TP7 no longer has the rejected heater-side placement"
tp7.SetPosition(point(10.0, 119.0))

# Each 7.5 mm slot leaves 0.75 mm edge webs and a 3.5 mm centre neck.  The
# combined direct FR-4 path is therefore 5.0 mm rather than the full 20 mm.
slot(4.5, 114.0, 7.5, 0.8)
slot(15.5, 114.0, 7.5, 0.8)


# Split the existing gas-side In2 plane across the slot line.  Both regions
# remain solid GND pours and rejoin through one explicit 0.25 mm centre bridge.
gas_zones = []
for zone in board.Zones():
    if zone.GetNetname() != "/GND" or not zone.IsOnLayer(pcbnew.In2_Cu):
        continue
    ys = [local_xy(zone.GetCornerPosition(i))[1] for i in range(zone.GetNumCorners())]
    if min(ys) == 85.25 and max(ys) == 124.75:
        gas_zones.append(zone)
assert len(gas_zones) == 1, f"expected one unsplit gas-side GND zone, found {len(gas_zones)}"
heater_zone = gas_zones[0]
tip_zone = heater_zone.Clone(pcbnew.In2_Cu)
replace_zone_outline(heater_zone, ((0.25, 85.25), (19.75, 85.25),
                                   (19.75, 113.25), (0.25, 113.25)))
replace_zone_outline(tip_zone, ((0.25, 114.75), (19.75, 114.75),
                                (19.75, 124.75), (0.25, 124.75)))
board.Add(tip_zone)
gnd = board.FindNet("/GND")
segment(gnd, pcbnew.In2_Cu, (10.0, 113.25), (10.0, 114.75), 0.25)


tracks = {item.m_Uuid.AsString(): item for item in board.GetTracks()}


def remove_uuids(uuids):
    missing = set(uuids) - set(tracks)
    assert not missing, f"route migration UUIDs missing: {sorted(missing)}"
    for uuid in uuids:
        board.Remove(tracks[uuid])


# Keep U13's exposed-pad test land on the gasward side.  The rejected route
# crossed the barrier directly into the sensor's thermal pad.
remove_uuids({"f09860d4-13c9-4964-85d4-b06872e7ffab"})
gas_ep = board.FindNet("/TMP_GAS_EP")
segment(gas_ep, pcbnew.B_Cu, (10.0, 116.0), (10.6, 116.6), 0.18)
segment(gas_ep, pcbnew.B_Cu, (10.6, 116.6), (10.6, 118.4), 0.18)
segment(gas_ep, pcbnew.B_Cu, (10.6, 118.4), (10.0, 119.0), 0.18)


# 3V3D: move the one heater-to-tip crossing into the centre neck.
remove_uuids({
    "7a9b61c3-0971-4ea6-a267-779b339cb334",
    "0413e170-b0ad-490d-b678-7fc43a41de4d",
    "2d934ae7-0226-47bd-86ed-bf70383d4ef7",
    "e59ad97c-253b-45c5-83f8-2788ec1046f4",
    "955af30f-a48c-43d9-80ee-a6b67cf662dc",
})
rail = board.FindNet("/3V3D")
segment(rail, pcbnew.F_Cu, (8.0, 112.5), (8.6, 113.1), 0.15)
segment(rail, pcbnew.F_Cu, (8.6, 113.1), (8.6, 114.8), 0.15)
segment(rail, pcbnew.F_Cu, (8.6, 114.8), (8.65, 115.0), 0.15)
segment(rail, pcbnew.F_Cu, (8.65, 115.0), (8.0, 115.2), 0.15)
segment(rail, pcbnew.F_Cu, (8.65, 115.0), (8.5, 115.5), 0.09)
via(rail, (8.5, 115.5))
segment(rail, pcbnew.In1_Cu, (8.5, 115.5), (10.65, 115.35), 0.15)


# SCL: the old top trace crossed the left slot.  Continue from its existing
# upstream via on B.Cu, cross at x=9.1, and return to F.Cu beside U13.
remove_uuids({
    "d4782efa-2496-4204-97d6-502b2a359dd5",
    "7c53ac3d-38ba-4bfd-9e6e-70b18a3a2035",
    "4cf3a1dd-d34a-41bb-83d2-0c6e717beeff",
    "7a4e356c-100e-4098-a082-7e2f4ed58e3d",
    "65b9d6d1-ec16-4fd1-9d8b-4a5c9fb3cd8c",
    "b177647d-b5ad-401a-ac7b-443caf79fc5f",
})
scl = board.FindNet("/I2C_SCL")
segment(scl, pcbnew.B_Cu, (5.05, 112.4), (8.7, 112.4), 0.09)
segment(scl, pcbnew.B_Cu, (8.7, 112.4), (9.1, 112.8), 0.09)
segment(scl, pcbnew.B_Cu, (9.1, 112.8), (9.1, 115.0), 0.09)
segment(scl, pcbnew.B_Cu, (9.1, 115.0), (6.8, 115.0), 0.09)
via(scl, (6.8, 115.0))
segment(scl, pcbnew.F_Cu, (6.8, 115.0), (6.8, 118.2), 0.09)
segment(scl, pcbnew.F_Cu, (6.8, 118.2), (9.35, 118.2), 0.09)


# Join U12's SDA branch to the main trunk on the heater side. U13 pad 6 is
# already joined to pad 4 gasward of the barrier, so a second SDA crossing
# would be a redundant electrical loop and an avoidable copper heat path.
remove_uuids({
    "6ba75dba-db29-46f8-808f-b1b208356097",
    "222d88fc-a030-4376-afc3-460e06f1223f",
    "bc9904c9-99b2-45b1-8f4c-7306f2bfa13a",
})
sda = board.FindNet("/I2C_SDA")
via(sda, (4.65, 112.95))
segment(sda, pcbnew.B_Cu, (4.65, 112.95), (4.0, 112.3), 0.09)
segment(sda, pcbnew.B_Cu, (4.0, 112.3), (4.0, 110.5), 0.09)
segment(sda, pcbnew.B_Cu, (4.0, 110.5), (10.2, 110.5), 0.09)
via(sda, (10.2, 110.5))
segment(sda, pcbnew.F_Cu, (10.2, 110.5), (10.65, 110.5), 0.09)


# ALERT: replace the right-slot crossing, then simplify the R30 branch so it
# stays entirely gasward of the barrier instead of weaving through it twice.
remove_uuids({
    "a5dc5f91-f18a-4fc2-b616-6c05cd171bac",
    "cf7f5c1e-6661-4a79-92d5-4f21debf12e1",
    "6688b7bd-fd01-444f-8bdc-949d40af46d5",
    "544b3384-f03f-4d0e-b2c5-a48a48e29110",
    "eda52d4e-cb5f-4325-9171-d0da2ec7176d",
    "c44d73ab-8592-44f5-b475-35fb762f451f",
    "96bff1dc-b3f5-4d64-b6c6-917c85b405a5",
    "0e5fb356-a184-4fce-b67c-ba0917063fb8",
    "2b9b3d7b-21b5-410b-836b-dffb22053da0",
    "8459cd7b-88b5-4d60-a7ca-08636be3acb3",
    "23ac7cd8-7871-4132-bd3c-71e85600da39",
})
alert = board.FindNet("/TGAS_ALERT")
segment(alert, pcbnew.F_Cu, (14.2, 112.4), (11.2, 112.4), 0.18)
segment(alert, pcbnew.F_Cu, (11.2, 112.4), (11.2, 114.8), 0.18)
segment(alert, pcbnew.F_Cu, (11.2, 114.8), (11.4, 114.8), 0.18)
segment(alert, pcbnew.F_Cu, (11.4, 114.8), (11.4, 115.2), 0.18)
segment(alert, pcbnew.F_Cu, (11.4, 116.4), (11.4, 117.5), 0.18)
via(alert, (11.4, 117.5), 0.45, 0.20)
segment(alert, pcbnew.In1_Cu, (11.4, 117.5), (8.0, 117.5), 0.18)
segment(alert, pcbnew.In1_Cu, (8.0, 117.5), (8.0, 116.3), 0.18)


# Move C21's GND via clear of the right-hand slot and the adjacent 3V3D via.
remove_uuids({
    "60967c84-b311-4bbd-9fae-341fe61533d5",
    "0f1ceb66-3f34-4082-8d1b-8588e3b7c741",
    "45b54da1-f217-469b-9cc2-55baf226f111",
    "0d0f624d-f58c-42b2-b434-62647cb3ee8d",
    "2a8e276c-cc35-4b03-87b5-4336f0cf475e",
    "b9e2ae22-c0b5-4b17-a96c-d8de98f53d09",
    "487f986c-28dd-4677-8a11-dca5bee50e49",
    "23635cb7-0203-4211-a5e1-0101bc09ce5e",
    "aec4e401-9785-436b-9df8-643d5a014eae",
    "b2f2d67f-9557-41cb-8100-38332514e668",
    "0e08f9d0-5f1c-4d37-aedf-94b2fc68228b",
    "70710d60-11fd-4c5f-bb28-2f47df2c4ec7",
    "044e66e0-c13d-4a25-bbba-97d42b5a7122",
    "35389e08-3e1e-464c-b11a-d8ea664b453e",
    "a16be3f2-facd-4148-817b-1e3c79f95351",
    "da254e0c-6328-4ee8-8491-894d2cfcde66",
    "0921162e-a057-4fce-afa0-290e145731e3",
})
segment(gnd, pcbnew.F_Cu, (12.0, 115.52), (12.0, 115.25), 0.20)
segment(gnd, pcbnew.F_Cu, (12.0, 115.25), (12.45, 114.8), 0.20)
segment(gnd, pcbnew.F_Cu, (12.45, 114.8), (14.0, 114.8), 0.20)
segment(gnd, pcbnew.F_Cu, (14.0, 114.8), (14.0, 114.95), 0.20)
via(gnd, (14.0, 114.95), 0.45, 0.20)


pcbnew.ZONE_FILLER(board).Fill(board.Zones())
board.BuildConnectivity()
pcbnew.SaveBoard(str(OUT), board)
print(f"wrote {OUT}; transverse U13 thermal barrier and split In2 GND plane")
