"""Connect the final R27/C7/C36/R39 ground island to the front main plane."""
import sys as _sys, pathlib as _pathlib  # hw/ root: this script moved to pcb-steps/
_sys.path.insert(1, str(_pathlib.Path(__file__).resolve().parent.parent))
import pcbnew as p
def apply(b):
 f=b.FindFootprintByReference('R27')
 if f is None:raise ValueError('Missing R27')
 pads=[q for q in f.Pads() if q.GetNumber()=='2'];xy=lambda v:(p.ToMM(v.x),p.ToMM(v.y))
 if len(pads)!=1 or pads[0].GetNetname()!='GND' or xy(pads[0].GetPosition())!=(115.1,103.175) or not pads[0].IsOnLayer(p.B_Cu):raise ValueError('R27 ground pad changed')
 pad=pads[0];pos=p.VECTOR2I(p.FromMM(115.4),p.FromMM(103.9))
 v=p.PCB_VIA(b);v.SetPosition(pos);v.SetNet(pad.GetNet());v.SetViaType(p.VIATYPE_THROUGH);v.SetLayerPair(p.F_Cu,p.B_Cu);v.SetWidth(p.FromMM(.4));v.SetDrill(p.FromMM(.2));v.SetLocked(True);b.Add(v)
 t=p.PCB_TRACK(b);t.SetStart(pad.GetPosition());t.SetEnd(pos);t.SetNet(pad.GetNet());t.SetLayer(p.B_Cu);t.SetWidth(p.FromMM(.15));t.SetLocked(True);b.Add(t);b.BuildConnectivity();return [v.m_Uuid.AsString(),t.m_Uuid.AsString()]
