"""NRST J3.3 closure; additions only, no existing geometry edits.
Derived by one pinned KRT no-rip-up pass, then native endpoint correction.
Call on a disposable copy and validate all new geometry before promotion.
"""
import sys as _sys, pathlib as _pathlib  # hw/ root: this script moved to pcb-steps/
_sys.path.insert(1, str(_pathlib.Path(__file__).resolve().parent.parent))
import pcbnew as p
DATA = [{'type': 'track', 'net': '/NRST', 'start': [105.3, 98.435], 'end': [105.3, 99.35], 'width': 0.1, 'layer': 'F.Cu'}, {'type': 'track', 'net': '/NRST', 'start': [105.3, 99.35], 'end': [105.55, 99.6], 'width': 0.1, 'layer': 'F.Cu'}, {'type': 'track', 'net': '/NRST', 'start': [105.55, 99.6], 'end': [105.55, 100.25], 'width': 0.1, 'layer': 'F.Cu'}, {'type': 'track', 'net': '/NRST', 'start': [105.55, 100.25], 'end': [107.775, 102.475], 'width': 0.1, 'layer': 'B.Cu'}, {'type': 'track', 'net': '/NRST', 'start': [107.775, 102.475], 'end': [108.125, 102.475], 'width': 0.1, 'layer': 'B.Cu'}, {'type': 'track', 'net': '/NRST', 'start': [108.125, 102.475], 'end': [108.275, 102.325], 'width': 0.1, 'layer': 'B.Cu'}, {'type': 'track', 'net': '/NRST', 'start': [108.275, 102.325], 'end': [109.5, 101.1], 'width': 0.1, 'layer': 'F.Cu'}, {'type': 'track', 'net': '/NRST', 'start': [109.5, 101.1], 'end': [110.65, 102.275], 'width': 0.1, 'layer': 'B.Cu'}, {'type': 'track', 'net': '/NRST', 'start': [110.65, 102.275], 'end': [110.65, 103.975], 'width': 0.1, 'layer': 'F.Cu'}, {'type': 'track', 'net': '/NRST', 'start': [110.65, 103.975], 'end': [110.625, 104.0], 'width': 0.1, 'layer': 'F.Cu'}, {'type': 'track', 'net': '/NRST', 'start': [110.625, 104.0], 'end': [110.625, 104.2], 'width': 0.1, 'layer': 'F.Cu'}, {'type': 'track', 'net': '/NRST', 'start': [110.625, 104.2], 'end': [110.85, 104.425], 'width': 0.1, 'layer': 'F.Cu'}, {'type': 'track', 'net': '/NRST', 'start': [110.85, 104.425], 'end': [111.15, 104.425], 'width': 0.1, 'layer': 'F.Cu'}, {'type': 'track', 'net': '/NRST', 'start': [111.15, 104.425], 'end': [111.725, 103.85], 'width': 0.1, 'layer': 'F.Cu'}, {'type': 'track', 'net': '/NRST', 'start': [111.725, 103.85], 'end': [111.725, 102.925], 'width': 0.1, 'layer': 'F.Cu'}, {'type': 'track', 'net': '/NRST', 'start': [111.725, 102.925], 'end': [112.7, 101.95], 'width': 0.1, 'layer': 'F.Cu'}, {'type': 'track', 'net': '/NRST', 'start': [112.7, 101.95], 'end': [112.7, 101.275], 'width': 0.1, 'layer': 'F.Cu'}, {'type': 'track', 'net': '/NRST', 'start': [112.7, 101.275], 'end': [114.1, 99.85], 'width': 0.1, 'layer': 'F.Cu'}, {'type': 'via', 'net': '/NRST', 'xy': [105.55, 100.25], 'diameter': 0.4, 'drill': 0.2}, {'type': 'via', 'net': '/NRST', 'xy': [108.275, 102.325], 'diameter': 0.4, 'drill': 0.2}, {'type': 'via', 'net': '/NRST', 'xy': [109.5, 101.1], 'diameter': 0.4, 'drill': 0.2}, {'type': 'via', 'net': '/NRST', 'xy': [110.65, 102.275], 'diameter': 0.4, 'drill': 0.2}]
def apply(board):
    f=board.FindFootprintByReference('J3')
    if f is None:raise ValueError('J3 missing')
    q=next(x for x in f.Pads() if x.GetNumber()=='3')
    if q.GetNetname()!='/NRST' or (p.ToMM(q.GetPosition().x),p.ToMM(q.GetPosition().y))!=(105.3,98.435):raise ValueError('J3.3 endpoint changed')
    net=board.FindNet('/NRST')
    if net is None:raise ValueError('NRST net missing')
    out=[]
    def point(v):return p.VECTOR2I(p.FromMM(v[0]),p.FromMM(v[1]))
    for r in DATA:
        if r['type']=='via':
            t=p.PCB_VIA(board);t.SetPosition(point(r['xy']));t.SetWidth(p.FromMM(r['diameter']));t.SetDrill(p.FromMM(r['drill']));t.SetViaType(p.VIATYPE_THROUGH);t.SetLayerPair(p.F_Cu,p.B_Cu)
        else:
            t=p.PCB_TRACK(board);t.SetStart(point(r['start']));t.SetEnd(point(r['end']));t.SetWidth(p.FromMM(r['width']));t.SetLayer(p.F_Cu if r['layer']=='F.Cu' else p.B_Cu)
        t.SetNet(net);t.SetLocked(True);board.Add(t);out.append(t)
    board.BuildConnectivity()
    return [x.m_Uuid.AsString() for x in out]
