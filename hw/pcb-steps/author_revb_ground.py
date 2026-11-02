"""U7.1 ground-to-exposed-pad closure and VREF legend; no added vias."""
import sys as _sys, pathlib as _pathlib  # hw/ root: this script moved to pcb-steps/
_sys.path.insert(1, str(_pathlib.Path(__file__).resolve().parent.parent))
import pcbnew as p
def apply(board):
 f=board.FindFootprintByReference('U7')
 if f is None or f.GetLayer()!=p.F_Cu:raise ValueError('Expected front U7')
 pads={q.GetNumber():q for q in f.Pads() if q.GetNumber()}
 if pads['1'].GetNetname()!='GND' or pads['15'].GetNetname()!='GND':raise ValueError('U7 ground pin map changed')
 labels=[x for x in board.GetDrawings() if isinstance(x,p.PCB_TEXT) and x.GetText()=='VREF']
 if len(labels)!=1:raise ValueError('Expected unique VREF legend')
 def vec(x,y):return p.VECTOR2I(p.FromMM(x),p.FromMM(y))
 if pads['1'].GetPosition()!=vec(111.5,111.6):raise ValueError('U7 pose changed')
 made=[]
 for a,b in [(pads['1'].GetPosition(),vec(111.5,112.1)),(vec(111.5,112.1),vec(111.2,112.4))]:
  t=p.PCB_TRACK(board);t.SetStart(a);t.SetEnd(b);t.SetWidth(p.FromMM(.15));t.SetLayer(p.F_Cu);t.SetNet(pads['1'].GetNet());t.SetLocked(True);board.Add(t);made.append(t)
 labels[0].SetPosition(vec(118,109.4));board.BuildConnectivity()
 return [x.m_Uuid.AsString() for x in made]
