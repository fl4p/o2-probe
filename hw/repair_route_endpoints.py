#!/usr/bin/env python3
"""Remove the known dead stub and center accepted routes on their vias.

KRT deliberately routes on a 0.05 mm grid.  A handful of accepted paths ended
0.05--0.10 mm from the centre of an electrically connected via.  KiCad accepts
those paths electrically, but reports them as manufacturing-review warnings.
This deterministic cleanup is keyed by track UUID so it cannot move unrelated
copper after a future reroute.
"""

from pathlib import Path
import sys

try:
    import wx

    _APP = wx.AppConsole()
    import pcbnew
except ImportError:
    sys.exit("run with KiCad's bundled Python")


HERE = Path(__file__).resolve().parent
BOARD = HERE / "o2-probe.kicad_pcb"

DANGLING = {
    "723438f4-6cf2-4fee-bcf4-f9cbfdd8ebe5",
    "32ed8450-f865-43ba-aa58-911a943ab564",
    "b1245185-1107-4ea3-a6c5-1f4568efe9da",
}

# track UUID -> (which endpoint, via centre in mm)
SNAPS = {
    "c7f9bdc3-183f-41b6-8dad-7155d6013714": ("end", (111.25, 104.60)),
    "78eb104f-fd55-4554-954e-88ceb28d4952": ("start", (111.25, 104.60)),
    "d7a5a954-18d7-4f85-bf3d-5c17dcc9bd8d": ("end", (105.05, 90.20)),
    "121d60f3-0dce-476e-a51b-9a50484da5db": ("start", (118.60, 128.40)),
    "2975037f-90d3-4af5-b2ee-0e8263189f05": ("end", (111.30, 69.80)),
    "487ed142-3eae-46bc-9f14-3f3224dada23": ("start", (110.90, 123.85)),
    "19d94ad9-2e93-4ec8-8e30-8e1329cce25c": ("end", (108.90, 84.30)),
    "29618a9c-0bd1-4066-ae9c-f224a3d8d9e4": ("end", (118.50, 107.80)),
    "2df9ed5d-edfb-4cb9-a1c1-698e44e0a96d": ("start", (110.45, 106.65)),
    "b39d74e5-3326-473c-a65d-f73c827b3b07": ("start", (110.65, 154.95)),
    "a389da24-fb4b-46ad-83a7-b45517b5013d": ("end", (113.85, 125.55)),
    "3ab8c424-001a-4987-97ca-db94bdf58c24": ("start", (104.50, 120.00)),
    "52a6493f-2e1e-440e-b782-a2dda1a673e9": ("start", (105.30, 114.00)),
    "31b7bfbf-d756-4669-b81b-c54caebd6f5d": ("start", (112.50, 119.90)),
    "7a0b1b24-f588-4e54-ac73-b2b3c9539014": ("end", (109.30, 155.40)),
}


board = pcbnew.LoadBoard(str(BOARD))
tracks = {item.m_Uuid.AsString(): item for item in board.GetTracks()}
missing = sorted(set(SNAPS) - set(tracks))
if missing:
    raise SystemExit(f"route cleanup UUIDs missing; board changed: {missing}")

removed = 0
for uuid in DANGLING:
    if uuid in tracks:
        board.Remove(tracks[uuid])
        removed += 1
for uuid, (endpoint, xy) in SNAPS.items():
    track = tracks[uuid]
    point = pcbnew.VECTOR2I_MM(*xy)
    if endpoint == "start":
        track.SetStart(point)
    else:
        track.SetEnd(point)

# This 3V3D path approaches a via at an angle.  A direct endpoint snap would
# reduce clearance to the adjacent I2C via by 0.008 mm, so preserve the angled
# segment and finish it with a 0.05 mm orthogonal stub to the via centre.
threev3d_uuid = "efbc1651-87df-460f-adb9-88b6f8fc3fb0"
if threev3d_uuid not in tracks:
    raise SystemExit("3V3D via-approach track missing; board changed")
threev3d = tracks[threev3d_uuid]
stub_start = pcbnew.VECTOR2I_MM(110.00, 152.00)
stub_end = pcbnew.VECTOR2I_MM(110.00, 152.05)
threev3d.SetEnd(stub_start)
def xy(point):
    return point.x, point.y

has_stub = any(
    not isinstance(item, pcbnew.PCB_VIA)
    and item.GetNetname() == "/3V3D"
    and item.GetLayer() == pcbnew.In1_Cu
    and {xy(item.GetStart()), xy(item.GetEnd())} == {xy(stub_start), xy(stub_end)}
    for item in board.GetTracks()
)
if not has_stub:
    stub = pcbnew.PCB_TRACK(board)
    stub.SetNet(threev3d.GetNet())
    stub.SetLayer(pcbnew.In1_Cu)
    stub.SetStart(stub_start)
    stub.SetEnd(stub_end)
    stub.SetWidth(threev3d.GetWidth())
    board.Add(stub)

# Replace the autorouter's three sub-grid 3V3A slivers with one intentional
# diagonal between the accepted pad fanout and the vertical rail.
threev3a_start = pcbnew.VECTOR2I_MM(117.40, 127.15)
threev3a_end = pcbnew.VECTOR2I_MM(117.60, 126.95)
has_threev3a_link = any(
    not isinstance(item, pcbnew.PCB_VIA)
    and item.GetNetname() == "/3V3A"
    and item.GetLayer() == pcbnew.F_Cu
    and {xy(item.GetStart()), xy(item.GetEnd())}
        == {xy(threev3a_start), xy(threev3a_end)}
    for item in board.GetTracks()
)
if not has_threev3a_link:
    source = tracks["2cb6725d-c1c8-4484-aaf3-7a7ef4407868"]
    link = pcbnew.PCB_TRACK(board)
    link.SetNet(source.GetNet())
    link.SetLayer(pcbnew.F_Cu)
    link.SetStart(threev3a_start)
    link.SetEnd(threev3a_end)
    link.SetWidth(pcbnew.FromMM(0.09))
    board.Add(link)

pcbnew.ZONE_FILLER(board).Fill(board.Zones())
board.BuildConnectivity()
pcbnew.SaveBoard(str(BOARD), board)
print(f"removed {removed} dangling tracks; centred {len(SNAPS)} route endpoints")
