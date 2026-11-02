"""Incremental C17 placement and local routing after apply_tip; no file I/O."""
import sys as _sys, pathlib as _pathlib  # hw/ root: this script moved to pcb-steps/
_sys.path.insert(1, str(_pathlib.Path(__file__).resolve().parent.parent))
import pcbnew

def pt(v): return (round(pcbnew.ToMM(v.x),6),round(pcbnew.ToMM(v.y),6))
def vec(p): return pcbnew.VECTOR2I(pcbnew.FromMM(p[0]),pcbnew.FromMM(p[1]))
def apply(board):
    fps={f.GetReference():f for f in board.GetFootprints()}
    sources=[('U7','9','/LMP_C2',(109.,115.4)),('U7','10','/LMP_C1',(109.5,115.4)),('C17','1','/LMP_C1',(107.3,115.675)),('C17','2','/LMP_C2',(107.3,114.125))]
    for ref,pin,net,xy in sources:
        pads=[p for p in fps[ref].Pads() if p.GetNumber()==pin]
        if len(pads)!=1 or pads[0].GetNetname()!=net or pt(pads[0].GetPosition())!=xy: raise ValueError('source changed '+ref+'.'+pin)
    old=[((109.4,116.1),(109.2,116.3)),((109.2,116.3),(109.2,117.15)),((109.2,117.15),(110.935,117.15)),((110.935,117.15),(110.935,117.4))]
    tracks=list(board.GetTracks()); deletes=[]
    for a,b in old:
        matches=[t for t in tracks if type(t).__name__=='PCB_TRACK' and t.GetNetname()=='/GUARD_REPLICA' and t.GetLayer()==pcbnew.B_Cu and {pt(t.GetStart()),pt(t.GetEnd())}=={a,b} and t.GetWidth()==pcbnew.FromMM(.25)]
        if len(matches)!=1: raise ValueError('guard source geometry missing/ambiguous '+str((a,b)))
        deletes.extend(matches)
    items={t.m_Uuid.AsString():t for t in tracks}
    guardvia=items['e3347344-82e2-475f-a3d9-53dbb9794be0']; guardtrack=items['c9e4b3bf-f171-4be5-9575-77e37421ea52']
    if guardvia.GetNetname()!='/GUARD_REPLICA' or pt(guardvia.GetPosition())!=(109.4,116.1) or guardtrack.GetNetname()!='/GUARD_REPLICA' or pt(guardtrack.GetEnd())!=(109.4,116.1): raise ValueError('guard endpoint changed')
    for t in tracks:
        if t.GetNetname() in ('/LMP_C1','/LMP_C2'): raise ValueError('C17 nets already routed')
    fps['C17'].SetOrientationDegrees(180); fps['C17'].SetPosition(vec((109.5,115.)))
    guardvia.SetPosition(vec((108.25,116.1))); guardtrack.SetEnd(vec((108.25,116.1)))
    for t in deletes: board.RemoveNative(t)
    routes=[('/GUARD_REPLICA',pcbnew.B_Cu,.25,[(108.25,116.1),(108.25,117.15),(110.935,117.15),(110.935,117.4)]),('/LMP_C1',pcbnew.F_Cu,.15,[(109.5,115.4),(109.4,116.1)]),('/LMP_C1',pcbnew.B_Cu,.15,[(109.4,116.1),(110.275,115.)]),('/LMP_C2',pcbnew.F_Cu,.15,[(109.,115.4),(108.85,116.15)]),('/LMP_C2',pcbnew.B_Cu,.15,[(108.85,116.15),(108.725,115.)])]
    added=[]
    for net,layer,width,points in routes:
        for a,b in zip(points,points[1:]):
            t=pcbnew.PCB_TRACK(board);t.SetNet(board.FindNet(net));t.SetLayer(layer);t.SetWidth(pcbnew.FromMM(width));t.SetStart(vec(a));t.SetEnd(vec(b));t.SetLocked(True);board.Add(t);added.append(t)
    for net,xy in [('/LMP_C1',(109.4,116.1)),('/LMP_C2',(108.85,116.15))]:
        t=pcbnew.PCB_VIA(board);t.SetNet(board.FindNet(net));t.SetPosition(vec(xy));t.SetViaType(pcbnew.VIATYPE_THROUGH);t.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);t.SetWidth(pcbnew.FromMM(.4));t.SetDrill(pcbnew.FromMM(.2));t.SetLocked(True);board.Add(t);added.append(t)
    return {'deleted':len(deletes),'added':len(added),'C17_pads':{p.GetNumber():pt(p.GetPosition()) for p in fps['C17'].Pads()}}
