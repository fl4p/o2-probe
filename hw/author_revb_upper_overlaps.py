"""Relocate U7 paste-window via and move C3 ground via off its solder land."""
import pcbnew as p
def apply(board):
 def xy(v):return (p.ToMM(v.x),p.ToMM(v.y))
 old=(116.4,73.525);new=(116.725,73.525)
 vv=[v for v in board.GetTracks() if isinstance(v,p.PCB_VIA) and xy(v.GetPosition())==old and v.GetNetname()=='GND']
 tt=[t for t in board.GetTracks() if not isinstance(t,p.PCB_VIA) and (xy(t.GetStart())==old or xy(t.GetEnd())==old)]
 ep=[v for v in board.GetTracks() if isinstance(v,p.PCB_VIA) and xy(v.GetPosition())==(109.1,113.15) and v.GetNetname()=='GND']
 ep_tracks=[t for t in board.GetTracks() if not isinstance(t,p.PCB_VIA) and (xy(t.GetStart())==(109.1,113.15) or xy(t.GetEnd())==(109.1,113.15))]
 # Mandatory pin-1 ground bridge must exist before removing the EP stitch.
 bridge=[t for t in board.GetTracks() if not isinstance(t,p.PCB_VIA) and t.GetNetname()=='GND' and t.GetLayer()==p.F_Cu and xy(t.GetStart())==(111.5,111.6) and xy(t.GetEnd())==(111.5,112.1)]
 if len(vv)!=1 or len(tt)!=2 or any(t.GetNetname()!='GND' for t in tt) or len(ep)!=1 or ep_tracks or len(bridge)!=1:raise ValueError('Unexpected C3/U7 ground topology')
 pos=p.VECTOR2I(p.FromMM(new[0]),p.FromMM(new[1]));vv[0].SetPosition(pos);vv[0].SetLocked(True)
 for t in tt:
  if xy(t.GetStart())==old:t.SetStart(pos)
  if xy(t.GetEnd())==old:t.SetEnd(pos)
  t.SetLocked(True)
 ep[0].SetPosition(p.VECTOR2I(p.FromMM(108.475),p.FromMM(114.1)));ep[0].SetLocked(True)
 t=p.PCB_TRACK(board);t.SetStart(ep[0].GetPosition());t.SetEnd(p.VECTOR2I(p.FromMM(108.9),p.FromMM(114.1)));t.SetLayer(p.F_Cu);t.SetWidth(p.FromMM(.15));t.SetNet(ep[0].GetNet());t.SetLocked(True);board.Add(t);board.BuildConnectivity()
 return dict(changed=[q.m_Uuid.AsString() for q in vv+tt+ep],added=[t.m_Uuid.AsString()])
