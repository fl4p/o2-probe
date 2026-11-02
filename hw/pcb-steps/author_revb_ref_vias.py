"""Repair measured REF3425 via-to-SMD gaps; caller owns fill and DRC."""
import sys as _sys, pathlib as _pathlib  # hw/ root: this script moved to pcb-steps/
_sys.path.insert(1, str(_pathlib.Path(__file__).resolve().parent.parent))
import pcbnew as p
MOVES = [((116.45,108.6),(116.9,108.6),2),
         ((117.2,112.5125),(117.15,112.9),2),
         ((113.375,112.175),(113.175,112.1),2)]
def apply(board):
 def xy(v):return (p.ToMM(v.x),p.ToMM(v.y))
 plan=[]
 for old,new,count in MOVES:
  vv=[v for v in board.GetTracks() if isinstance(v,p.PCB_VIA) and xy(v.GetPosition())==old and v.GetNetname()=='GND']
  tt=[t for t in board.GetTracks() if not isinstance(t,p.PCB_VIA) and (xy(t.GetStart())==old or xy(t.GetEnd())==old)]
  if len(vv)!=1 or len(tt)!=count or any(t.GetNetname()!='GND' for t in tt):raise ValueError(('Unexpected REF via topology',old,len(vv),len(tt)))
  plan.append((vv[0],tt,old,new))
 changed=[]
 for v,tracks,old,new in plan:
  position=p.VECTOR2I(p.FromMM(new[0]),p.FromMM(new[1]));v.SetPosition(position);v.SetLocked(True);changed.append(v.m_Uuid.AsString())
  for t in tracks:
   if xy(t.GetStart())==old:t.SetStart(position)
   if xy(t.GetEnd())==old:t.SetEnd(position)
   t.SetLocked(True);changed.append(t.m_Uuid.AsString())
 board.BuildConnectivity();return changed
