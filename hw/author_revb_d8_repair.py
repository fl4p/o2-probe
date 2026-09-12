"""Repair only the attempted D8 F.Cu transfer; retain divider pad copper."""
import pcbnew as p
def apply(board):
 def xy(v):return (p.ToMM(v.x),p.ToMM(v.y))
 def pt(v):return p.VECTOR2I(p.FromMM(v[0]),p.FromMM(v[1]))
 f=board.FindFootprintByReference('D8')
 if f is None or f.GetLayer()!=p.F_Cu:raise ValueError('Expected current front-side D8')
 cath=next(q for q in f.Pads() if q.GetNumber()=='1')
 if cath.GetNetname()!='/VIN_MON' or xy(cath.GetPosition())!=(113.45,106.2):raise ValueError('D8 cathode changed')
 targets=[];bad=[]
 for t in board.GetTracks():
  if t.GetNetname()!='/VIN_MON':continue
  if isinstance(t,p.PCB_VIA):
   if xy(t.GetPosition())==(113.45,107.2):bad.append(t)
  elif t.GetLayer()==p.B_Cu and xy(t.GetEnd())==(113.45,107.2):targets.append(t)
  elif t.GetLayer()==p.F_Cu and xy(t.GetStart())==(113.45,106.2) and xy(t.GetEnd())==(113.45,107.2):bad.append(t)
 if len(targets)!=2 or len(bad)!=2:raise ValueError(('D8 attempted transfer differs',len(targets),len(bad)))
 for t in targets:t.SetEnd(pt((113.45,106.2)))
 for t in bad:board.RemoveNative(t)
 made=[]
 def tr(layer,points):
  for a,b in zip(points,points[1:]):
   t=p.PCB_TRACK(board);t.SetStart(pt(a));t.SetEnd(pt(b));t.SetWidth(p.FromMM(.15));t.SetLayer(layer);t.SetNet(cath.GetNet());t.SetLocked(True);board.Add(t);made.append(t)
 vxy=(112.475,105.4)
 tr(p.F_Cu,[xy(cath.GetPosition()),vxy])
 tr(p.B_Cu,[vxy,(112.3,105.575),(112.3,106.2)])
 v=p.PCB_VIA(board);v.SetPosition(pt(vxy));v.SetWidth(p.FromMM(.4));v.SetDrill(p.FromMM(.2));v.SetViaType(p.VIATYPE_THROUGH);v.SetLayerPair(p.F_Cu,p.B_Cu);v.SetNet(cath.GetNet());v.SetLocked(True);board.Add(v);made.append(v)
 board.BuildConnectivity()
 return [t.m_Uuid.AsString() for t in made]
