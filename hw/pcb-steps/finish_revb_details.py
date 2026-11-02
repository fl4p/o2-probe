"""Remove new assembly/silkscreen conflicts after current Rev B migration."""
import sys as _sys, pathlib as _pathlib  # hw/ root: this script moved to pcb-steps/
_sys.path.insert(1, str(_pathlib.Path(__file__).resolve().parent.parent))
import pcbnew as p

def apply(board):
 fps={f.GetReference():f for f in board.Footprints()}
 d=fps['D8']
 if d.GetLayer()!=p.B_Cu:raise ValueError('D8 source is not B.Cu')
 d.Flip(d.GetPosition(),False);d.SetOrientationDegrees(0)
 # Keep cathode at x113.45,y106.2 on the front; a separate via reaches the
 # divider on the back with a clear annular rim outside the SMD land.
 for a in d.Pads():
  if a.GetNumber()=='1':c=a
 assert c.GetNetname()=='/VIN_MON'
 def v(x,y):return p.VECTOR2I(p.FromMM(x),p.FromMM(y))
 matches=[]
 for t in board.GetTracks():
  if not isinstance(t,p.PCB_VIA) and t.GetNetname()=='/VIN_MON' and t.GetLayer()==p.B_Cu and t.GetEnd()==v(113.45,106.2):matches.append(t)
 if not matches:raise ValueError('VIN_MON local source differs')
 for old in matches:old.SetEnd(v(113.45,107.2))
 t=p.PCB_TRACK(board);t.SetStart(c.GetPosition());t.SetEnd(v(113.45,107.2));t.SetWidth(p.FromMM(.15));t.SetLayer(p.F_Cu);t.SetNet(c.GetNet());t.SetLocked(True);board.Add(t)
 via=p.PCB_VIA(board);via.SetPosition(v(113.45,107.2));via.SetWidth(p.FromMM(.4));via.SetDrill(p.FromMM(.2));via.SetViaType(p.VIATYPE_THROUGH);via.SetLayerPair(p.F_Cu,p.B_Cu);via.SetNet(c.GetNet());via.SetLocked(True);board.Add(via)
 for field in d.GetFields():field.SetVisible(False)
 d.Reference().SetLayer(p.F_Fab)
 for g in board.GetDrawings():
  if isinstance(g,p.PCB_TEXT) and g.GetText()=='CE':g.SetPosition(v(101.3,105.7))
 return {'D8':'front side, divider remains back','new_vias':1,'CE_legend':[101.3,105.7]}
