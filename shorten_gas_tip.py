#!/usr/bin/env python3
"""Shorten the gas tip and move optional pressure sensing off the cold tip.

This one-way migration starts from the accepted transverse-barrier board.  It
keeps all six routed slots byte-for-byte, moves TP7 laterally beside U13, moves
the DNP BMP390 and its two DNP capacitors heaterward of the barrier, shortens
the rounded outline from 125 mm to 119 mm, and replaces only the affected
copper.  Assertions make the script fail closed on any other input revision.
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
NEW_LENGTH_MM = 119.0
TRACKS_BY_UUID = {item.m_Uuid.AsString(): item for item in board.GetTracks()}
REMOVED_ITEMS = []


def point(x: float, y: float):
    return pcbnew.VECTOR2I_MM(ORIGIN_X_MM + x, ORIGIN_Y_MM + y)


def absolute_xy(position):
    return pcbnew.ToMM(position.x), pcbnew.ToMM(position.y)


def local_xy(position):
    x, y = absolute_xy(position)
    return round(x - ORIGIN_X_MM, 4), round(y - ORIGIN_Y_MM, 4)


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


def add_outline():
    width, radius, length = 20.0, 2.0, NEW_LENGTH_MM
    edge_line((radius, 0), (width - radius, 0))
    edge_arc((width - radius, 0), (width - 0.586, 0.586), (width, radius))
    edge_line((width, radius), (width, length - radius))
    edge_arc((width, length - radius),
             (width - 0.586, length - 0.586), (width - radius, length))
    edge_line((width - radius, length), (radius, length))
    edge_arc((radius, length), (0.586, length - 0.586), (0, length - radius))
    edge_line((0, length - radius), (0, radius))
    edge_arc((0, radius), (0.586, 0.586), (radius, 0))


def replace_zone_outline(zone, corners):
    outline = pcbnew.VECTOR_VECTOR2I()
    for x, y in corners:
        outline.append(point(x, y))
    zone.Outline().RemoveAllContours()
    zone.AddPolygon(outline)


def remove_uuids(uuids):
    missing = set(uuids) - set(TRACKS_BY_UUID)
    assert not missing, f"route migration UUIDs missing: {sorted(missing)}"
    for uuid in uuids:
        item = TRACKS_BY_UUID[uuid]
        board.Remove(item)
        REMOVED_ITEMS.append(item)


def remove_via_at(netname, position):
    matches = [
        item for item in board.GetTracks()
        if isinstance(item, pcbnew.PCB_VIA)
        and item.GetNetname() == netname
        and all(abs(actual - wanted) < 0.001
                for actual, wanted in zip(absolute_xy(item.GetPosition()), position))
    ]
    assert len(matches) == 1, f"expected one {netname} via at {position}, found {len(matches)}"
    board.Remove(matches[0])
    REMOVED_ITEMS.append(matches[0])


# Replace only the eight-item outer contour.  Every routed-slot item is saved
# before the operation and compared by UUID and serialized geometry afterward.
edge_items = [item for item in board.Drawings() if item.GetLayer() == pcbnew.Edge_Cuts]
assert len(edge_items) == 32, f"expected 32 Edge.Cuts items, found {len(edge_items)}"


def is_outer(item):
    points = [absolute_xy(item.GetStart()), absolute_xy(item.GetEnd())]
    if item.GetShapeStr() == "Arc":
        points.append(absolute_xy(item.GetArcMid()))
    return any(abs(x - 100.0) < 0.001 or abs(x - 120.0) < 0.001
               or abs(y - 50.0) < 0.001 or abs(y - 175.0) < 0.001
               for x, y in points)


outer = [item for item in edge_items if is_outer(item)]
slots_before = {
    item.m_Uuid.AsString(): (
        item.GetShapeStr(), local_xy(item.GetStart()), local_xy(item.GetEnd()),
        local_xy(item.GetArcMid()) if item.GetShapeStr() == "Arc" else None,
        round(pcbnew.ToMM(item.GetWidth()), 4),
    )
    for item in edge_items if item not in outer
}
assert len(outer) == 8 and len(slots_before) == 24, (
    f"expected 8 outline and 24 slot items, found {len(outer)} and {len(slots_before)}"
)
for item in outer:
    board.Remove(item)
    REMOVED_ITEMS.append(item)
add_outline()


# Move only the requested footprints.  C22 remains beside U13 because it is
# U13's fitted decoupler, not part of the optional pressure-sensor cluster.
placements = {
    "TP7": ((10.0, 119.0), (15.0, 116.0)),
    "U14": ((16.0, 120.0), (16.0, 110.0)),
    "C23": ((15.0, 116.0), (15.0, 107.5)),
    "C24": ((18.0, 122.0), (18.0, 110.0)),
}
for reference, (old_position, new_position) in placements.items():
    footprint = board.FindFootprintByReference(reference)
    assert footprint is not None, f"missing {reference}"
    assert local_xy(footprint.GetPosition()) == old_position, (
        f"{reference} is at {local_xy(footprint.GetPosition())}, want {old_position}"
    )
    footprint.SetPosition(point(*new_position))


# Shorten only the isolated tip-side In2 GND region.  The 1.5 mm no-pour gap
# around the transverse barrier and both upstream regions remain unchanged.
tip_zones = []
for zone in board.Zones():
    if zone.GetNetname() != "/GND" or not zone.IsOnLayer(pcbnew.In2_Cu):
        continue
    ys = [local_xy(zone.GetCornerPosition(i))[1] for i in range(zone.GetNumCorners())]
    if min(ys) == 114.75 and max(ys) == 124.75:
        tip_zones.append(zone)
assert len(tip_zones) == 1, f"expected one old tip GND zone, found {len(tip_zones)}"
replace_zone_outline(tip_zones[0], ((0.25, 114.75), (19.75, 114.75),
                                    (19.75, 118.75), (0.25, 118.75)))


# Delete the old U14-only I2C branches, shorten U13's SCL stub back to its
# existing trunk, and replace TP7's dogleg with one lateral B.Cu connection.
remove_uuids({
    # TMP_GAS_EP old tipward dogleg.
    "2ada8fc4-d031-4da8-9435-b2bb824b0304",
    "a016f4d0-6ac5-472e-bcec-7063eabc79e0",
    "a86112a0-61ba-4b9b-844e-76731d53db36",
    # SCL old U14 branch, including only the surplus part beyond U13.
    "d21be58a-4ef0-4cab-bc9c-67f384eb7ecb",
    "6b85acce-ff72-4af8-997a-66dd35c556cf",
    "f85bdb6c-1f92-4900-9ae7-29a29ebf24bd",
    "7cabcafe-510f-49a4-b1d5-7dd51af01541",
    "33db45f1-59dd-4727-baba-07fa36326b9f",
    "bd7b14ae-d483-4fcb-b610-0fe5acdbcef7",
    "5dedda88-6d32-4e5c-99b8-a4b6e62dbfbe",
    "96a11d1a-54b7-4a7a-aeb5-8118dc2c2998",
    "9f0d4cc2-715a-4bf9-a61f-63086fd329b4",
    # SDA old U14 branch.
    "06c51def-861b-458a-854e-4fcc35adb627",
    "2b57853e-a4d6-483a-b39c-58c810b19b5a",
    "9130b59a-d6e3-4280-abff-50e86448ba26",
    "cf4ab922-e3e1-4e5c-993d-0ab84642ca1d",
    "4e0a5e14-088d-4e6d-a6ec-f900d173a243",
})
gas_ep = board.FindNet("/TMP_GAS_EP")
scl = board.FindNet("/I2C_SCL")
sda = board.FindNet("/I2C_SDA")
segment(gas_ep, pcbnew.B_Cu, (10.0, 116.0), (15.0, 116.0), 0.18)
segment(scl, pcbnew.F_Cu, (9.35, 117.0), (9.35, 118.2), 0.09)


# Remove the old U14/C23/C24 supply fanout, but keep U13/C21/C22 and the
# gas-side 3V3D feed.  C22 is rejoined with a short straight branch.
remove_uuids({
    "045341c2-0b27-4196-a590-cd025f78c874",
    "18ad2334-1cca-4deb-82cc-00c7c3c4386f",
    "2cb17919-daef-4597-8e50-6fed86c3ad09",
    "373412af-211d-41b6-917a-cf79ba5dd52e",
    "3fa1daa9-83be-47db-ab85-84e685ffcbae",
    "47d95f1f-191f-400a-a25b-c354c95cb115",
    "507190f1-90ba-45d3-8fc0-28124388f28e",
    "54baa497-711b-4ea6-a354-0cdc4e9d45ed",
    "5ba8ac26-3c9e-4d96-a51b-41837cec6580",
    "5c6a27b3-a63a-4b38-bf67-91a697d21027",
    "6425e8b9-1506-4c7f-a8b1-6ba2c715bd55",
    "6842f27d-9b32-4f25-bcbf-3a7f95e5e7d5",
    "71d5510b-958d-4034-b1f3-29f04402f065",
    "8dc853d5-821a-47a1-9df1-c3f6ed20f5f3",
    "9526b160-6601-4c51-bcc5-1c871168236d",
    "9e6fd8e7-14f7-4dd9-94c2-662caa236503",
    "b75bc0e9-7904-4eef-bd8c-9ce98728d534",
    "bcdc7be2-606d-43fa-8364-73fe84fcbcaa",
    "dfcfcad6-a56e-44bf-be0a-fe0b1747cb90",
    "e37c58af-5504-4259-8f87-d33fe1cc23d2",
    "ede29f72-3bbd-4a8e-9eb4-420bd38e69dc",
})
rail = board.FindNet("/3V3D")
segment(rail, pcbnew.F_Cu, (15.0, 116.5), (18.0, 116.5), 0.15)


# Remove KRT's dense old U14 ground escape plus the old C23/C24 GND vias.
old_u14_gnd = []
for item in board.GetTracks():
    if isinstance(item, pcbnew.PCB_VIA) or item.GetNetname() != "/GND":
        continue
    x1, y1 = absolute_xy(item.GetStart())
    x2, y2 = absolute_xy(item.GetEnd())
    if min(x1, x2) >= 115.2 and min(y1, y2) >= 169.49:
        old_u14_gnd.append(item)
assert len(old_u14_gnd) == 44, f"expected 44 old U14 GND tracks, found {len(old_u14_gnd)}"
for item in old_u14_gnd:
    board.Remove(item)
    REMOVED_ITEMS.append(item)
for position in ((117.15, 170.5), (115.25, 170.4),
                 (115.0, 165.52), (118.0, 171.52)):
    remove_via_at("/GND", position)


# New heater-side BMP390 cluster.  I2C reaches existing heater-side vias on
# In2; 3V3D reaches the existing U12 rail on In1.  No new copper crosses the
# U13 barrier.  The DNP sensor's four ground pads and both DNP capacitors have
# explicit vias into the controlled In2 ground region.
gnd = board.FindNet("/GND")

# 3V3D: U14 pins 1/10 and C23, then U14 pin 6 and C24.
segment(rail, pcbnew.F_Cu, (15.2375, 109.5), (15.5, 109.2375), 0.15)
segment(rail, pcbnew.F_Cu, (15.5, 109.2375), (15.75, 109.2375), 0.15)
segment(rail, pcbnew.F_Cu, (15.0, 107.98), (15.0, 108.5), 0.15)
segment(rail, pcbnew.F_Cu, (15.0, 108.5), (15.44, 109.2375), 0.15)
segment(rail, pcbnew.F_Cu, (14.7, 108.0), (15.0, 107.98), 0.15)
via(rail, (14.7, 108.0))
segment(rail, pcbnew.F_Cu, (16.25, 110.7625), (16.25, 111.0), 0.15)
segment(rail, pcbnew.F_Cu, (16.25, 111.0), (17.7, 111.0), 0.15)
segment(rail, pcbnew.F_Cu, (17.7, 111.0), (18.0, 110.48), 0.15)
segment(rail, pcbnew.F_Cu, (18.0, 110.48), (18.0, 110.8), 0.15)
via(rail, (18.0, 110.8))
segment(rail, pcbnew.In1_Cu, (14.7, 108.0), (14.0, 112.5), 0.15)
segment(rail, pcbnew.In1_Cu, (14.0, 112.5), (18.8, 112.5), 0.15)
segment(rail, pcbnew.In1_Cu, (18.8, 112.5), (18.0, 110.8), 0.15)
segment(rail, pcbnew.In1_Cu, (14.7, 108.0), (11.8, 111.1), 0.15)
segment(rail, pcbnew.In1_Cu, (11.8, 111.1), (8.6, 113.1), 0.15)
via(rail, (8.6, 113.1))

# I2C heater-side branches.
segment(scl, pcbnew.F_Cu, (16.25, 109.2375), (16.5, 108.85), 0.09)
via(scl, (16.5, 108.85))
segment(scl, pcbnew.In2_Cu, (16.5, 108.85), (12.5, 108.85), 0.09)
segment(scl, pcbnew.In2_Cu, (12.5, 108.85), (7.5, 110.5), 0.09)
segment(scl, pcbnew.In2_Cu, (7.5, 110.5), (5.05, 112.4), 0.09)
segment(sda, pcbnew.F_Cu, (16.7625, 110.0), (17.4, 110.0), 0.09)
via(sda, (17.4, 110.0))
segment(sda, pcbnew.B_Cu, (17.4, 110.0), (16.0, 110.0), 0.09)
segment(sda, pcbnew.B_Cu, (16.0, 110.0), (16.0, 111.2), 0.09)
segment(sda, pcbnew.B_Cu, (16.0, 111.2), (14.5, 111.2), 0.09)
segment(sda, pcbnew.B_Cu, (14.5, 111.2), (10.2, 110.5), 0.09)

# Ground escape for U14 and both DNP capacitors.
segment(gnd, pcbnew.F_Cu, (16.7625, 109.5), (17.15, 109.5), 0.20)
segment(gnd, pcbnew.F_Cu, (17.15, 109.5), (17.15, 109.15), 0.20)
via(gnd, (17.15, 109.15), 0.45, 0.20)
segment(gnd, pcbnew.F_Cu, (16.7625, 110.5), (17.15, 110.5), 0.20)
via(gnd, (17.15, 110.5), 0.45, 0.20)
segment(gnd, pcbnew.F_Cu, (15.2375, 110.0), (15.25, 110.0), 0.20)
segment(gnd, pcbnew.F_Cu, (15.25, 110.0), (15.25, 110.4), 0.20)
segment(gnd, pcbnew.F_Cu, (15.2375, 110.5), (15.25, 110.4), 0.20)
via(gnd, (15.25, 110.4), 0.45, 0.20)
via(gnd, (15.0, 107.02), 0.45, 0.20)
via(gnd, (18.0, 109.52), 0.45, 0.20)


pcbnew.ZONE_FILLER(board).Fill(board.Zones())
board.BuildConnectivity()

edge_after = [item for item in board.Drawings() if item.GetLayer() == pcbnew.Edge_Cuts]
slots_after = {
    item.m_Uuid.AsString(): (
        item.GetShapeStr(), local_xy(item.GetStart()), local_xy(item.GetEnd()),
        local_xy(item.GetArcMid()) if item.GetShapeStr() == "Arc" else None,
        round(pcbnew.ToMM(item.GetWidth()), 4),
    )
    for item in edge_after if item.m_Uuid.AsString() in slots_before
}
assert len(edge_after) == 32 and slots_after == slots_before, "routed-slot geometry changed"

pcbnew.SaveBoard(str(OUT), board)
print(f"wrote {OUT}; 20 x 119 mm tip, lateral TP7, heater-side U14 cluster")
