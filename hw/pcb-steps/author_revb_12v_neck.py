"""Authored heater-supply neck seed; apply only before the recorded final route.

The F crossover below the neck crosses the existing rear 3V3D route while
remaining outside the right front guard rail. Native final evidence is separate.
"""
import sys as _sys, pathlib as _pathlib  # hw/ root: this script moved to pcb-steps/
_sys.path.insert(1, str(_pathlib.Path(__file__).resolve().parent.parent))
import pcbnew as p

def apply(board):
    lookup={q.m_Uuid.AsString():q for q in board.GetTracks()}
    tail=lookup.get('dea7dc7d-4bb2-4065-afd0-0b31004f14ac')
    if tail is None or tail.GetNetname()!='/+12V_SW':
        raise ValueError('Missing pre-completion heater-supply anchor')
    if '1f373dc5-9473-45cb-aca9-f01226c9c1eb' in lookup:
        raise ValueError('Reviewed redundant guard feed removal not applied')
    pt=lambda xy:p.VECTOR2I(p.FromMM(xy[0]),p.FromMM(xy[1]))
    if tail.GetEnd()!=pt((111.85,120.7)):
        raise ValueError('Heater-supply source anchor changed')
    net=board.FindNet('/+12V_SW'); added=[]
    for layer,points in [
        (p.B_Cu,[(114.9,116.1),(112.9,116.0),(111.9,117.1),(111.9,118.9),(112.65,119.5)]),
        (p.F_Cu,[(112.65,119.5),(112.5,122.1)]),
        (p.B_Cu,[(112.5,122.1),(111.9,121.05)]),
    ]:
        for start,end in zip(points,points[1:]):
            track=p.PCB_TRACK(board);track.SetStart(pt(start));track.SetEnd(pt(end))
            track.SetWidth(p.FromMM(.18));track.SetLayer(layer);track.SetNet(net)
            board.Add(track);added.append(track.m_Uuid.AsString())
    for xy in [(114.9,116.1),(112.65,119.5),(112.5,122.1)]:
        via=p.PCB_VIA(board);via.SetPosition(pt(xy));via.SetWidth(p.FromMM(.4))
        via.SetDrill(p.FromMM(.2));via.SetViaType(p.VIATYPE_THROUGH)
        via.SetLayerPair(p.F_Cu,p.B_Cu);via.SetNet(net)
        board.Add(via);added.append(via.m_Uuid.AsString())
    return added
