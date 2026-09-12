"""Move existing VIN_MON transition clear of the repaired SDA corridor."""
import pcbnew as p
def apply(board):
 def xy(v):return (p.ToMM(v.x),p.ToMM(v.y))
 old=(112.475,105.4);new=(112.6,105.7)
 vias=[v for v in board.GetTracks() if isinstance(v,p.PCB_VIA) and xy(v.GetPosition())==old and v.GetNetname()=='/VIN_MON']
 tracks=[t for t in board.GetTracks() if not isinstance(t,p.PCB_VIA) and (xy(t.GetStart())==old or xy(t.GetEnd())==old)]
 elbow=(112.3,105.575);elbow_new=(112.3,105.65)
 elbow_tracks=[t for t in board.GetTracks() if not isinstance(t,p.PCB_VIA) and (xy(t.GetStart())==elbow or xy(t.GetEnd())==elbow)]
 if len(elbow_tracks)!=2 or any(t.GetNetname()!='/VIN_MON' for t in elbow_tracks):raise ValueError('Unexpected VIN_MON elbow')
 if len(vias)!=1 or len(tracks)!=2 or any(t.GetNetname()!='/VIN_MON' for t in tracks):raise ValueError('Unexpected VIN_MON transition topology')
 pos=p.VECTOR2I(p.FromMM(new[0]),p.FromMM(new[1]));vias[0].SetPosition(pos);vias[0].SetLocked(True)
 for t in tracks:
  if xy(t.GetStart())==old:t.SetStart(pos)
  if xy(t.GetEnd())==old:t.SetEnd(pos)
  t.SetLocked(True)
 for t in elbow_tracks:
  ep=p.VECTOR2I(p.FromMM(elbow_new[0]),p.FromMM(elbow_new[1]))
  if xy(t.GetStart())==elbow:t.SetStart(ep)
  if xy(t.GetEnd())==elbow:t.SetEnd(ep)
  t.SetLocked(True)
 board.BuildConnectivity();return [t.m_Uuid.AsString() for t in vias+tracks+elbow_tracks]
