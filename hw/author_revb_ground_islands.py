"""Two local ground stitches for the TP2 and R25 islands. No file I/O."""
import pcbnew
POSES=((103.15,94.1),(112.3,103.2))
def apply(board):
 net=board.FindNet('GND')
 if net is None:raise ValueError('GND net missing')
 added=[]
 for x,y in POSES:
  v=pcbnew.PCB_VIA(board);v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x),pcbnew.FromMM(y)));v.SetWidth(pcbnew.FromMM(.4));v.SetDrill(pcbnew.FromMM(.2));v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetNet(net);v.SetLocked(True);board.Add(v);added.append(v.m_Uuid.AsString())
 return added
