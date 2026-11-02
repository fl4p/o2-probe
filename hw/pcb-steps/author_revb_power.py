"""Local placement/routing recipe; caller owns migration, old-copper retirement and DRC.
No file I/O and no implicit changes to unrelated parts, nets, zones or copper.
"""
import sys as _sys, pathlib as _pathlib  # hw/ root: this script moved to pcb-steps/
_sys.path.insert(1, str(_pathlib.Path(__file__).resolve().parent.parent))
import pcbnew
PLACEMENT = {
 'U1': (104.5,77.5,0,'F.Cu'), 'C1': (104.3,80.8,0,'F.Cu'),
 'C2': (105.8,75.,0,'F.Cu'), 'D3': (111.5,69.5,90,'F.Cu'),
 'U15': (115.5,111.,180,'F.Cu'), 'C10': (115.5,113.65,0,'F.Cu'),
 'C36': (115.5,108.6,0,'F.Cu'),
}
# All endpoints use actual loaded pad positions and require matching nets.
# Intermediate points are intentional local geometry, not a collision verdict.
ROUTES = [
 ('/+12V_SW',.4,'F.Cu',['U1.3',(102.825,78.9875),'C1.1']),
 ('GND',.4,'F.Cu',['U1.4',(105.775,78.5875),'C1.2']),
 ('/BUCK_BST',.18,'F.Cu',['U1.6',(105.32,76.2325),'C2.1']),
 ('/BUCK_SW',.18,'F.Cu',['C2.2',(106.7,75.42),(106.7,77.5),'U1.5']),
 ('/BUCK_SW',.3,'F.Cu',['U1.5','L1.1']),
 ('/3V3D',.2,'F.Cu',['C36.1',(114.3625,109.2575),'U15.4']),
 ('/VREF_TRIM',.25,'F.Cu',['U15.6',(114.3625,113.2875),'C10.1']),
 ('/VREF_TRIM',.15,'F.Cu',['U15.5','U15.6']),
 ('GND',.25,'F.Cu',['U15.1',(116.6375,113.2875),'C10.2']),
 ('GND',.15,'F.Cu',['U15.2','U15.1']),
 ('GND',.2,'F.Cu',['C36.2',(116.45,108.6)]),
 ('GND',.25,'F.Cu',['U15.1',(117.2,112.5125)]),
]
VIAS=[('GND',116.45,108.6),('GND',117.2,112.5125)]

def place(board):
 fps={f.GetReference():f for f in board.GetFootprints()}
 for ref in PLACEMENT:
  if ref not in fps:raise ValueError('missing migrated footprint '+ref)
 for ref,(x,y,a,layer) in PLACEMENT.items():
  f=fps[ref];p=pcbnew.VECTOR2I(pcbnew.FromMM(x),pcbnew.FromMM(y))
  if board.GetLayerName(f.GetLayer())!=layer:f.Flip(f.GetPosition(),True)
  f.SetPosition(p);f.SetOrientationDegrees(a)

def author(board):
 """Validate every endpoint first, then add only the declared tracks/vias."""
 fps={f.GetReference():f for f in board.GetFootprints()}
 plan=[];vp=[]
 for net,width,layer,points in ROUTES:
  ni=board.FindNet(net)
  if ni is None or ni.GetNetCode()<=0:raise ValueError('missing net '+net)
  coords=[]
  for point in points:
   if isinstance(point,str):
    ref,pin=point.split('.')
    pp=[p for p in fps[ref].Pads() if p.GetNumber()==pin]
    if len(pp)!=1:raise ValueError('ambiguous/missing pad '+point)
    pad=pp[0]
    if pad.GetNetname()!=net:raise ValueError('net mismatch '+point+' '+pad.GetNetname()+' != '+net)
    coords.append(pad.GetPosition())
   else:coords.append(pcbnew.VECTOR2I(pcbnew.FromMM(point[0]),pcbnew.FromMM(point[1])))
  plan.append((ni,width,board.GetLayerID(layer),coords))
 for net,x,y in VIAS:
  ni=board.FindNet(net)
  if ni is None or ni.GetNetCode()<=0:raise ValueError('missing via net '+net)
  vp.append((ni,x,y))
 added=[]
 for ni,width,layer,coords in plan:
  for start,end in zip(coords,coords[1:]):
   if start==end:continue
   t=pcbnew.PCB_TRACK(board);t.SetNet(ni);t.SetLayer(layer);t.SetWidth(pcbnew.FromMM(width));t.SetStart(start);t.SetEnd(end);t.SetLocked(True);board.Add(t);added.append(t)
 for ni,x,y in vp:
  v=pcbnew.PCB_VIA(board);v.SetNet(ni);v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x),pcbnew.FromMM(y)));v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetWidth(pcbnew.FromMM(.4));v.SetDrill(pcbnew.FromMM(.2));v.SetLocked(True);board.Add(v);added.append(v)
 return added
