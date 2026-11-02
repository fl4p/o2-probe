"""Rev B MCU-side ADC RC placement and critical routes; native pcbnew 10.
Call after authoritative schematic nets and C26 0402 replacement are applied.
The caller owns removal of obsolete affected-net copper before invoking this.
"""
import sys as _sys, pathlib as _pathlib  # hw/ root: this script moved to pcb-steps/
_sys.path.insert(1, str(_pathlib.Path(__file__).resolve().parent.parent))
import pcbnew as p
POSES = {
 'R33': (112.1,86.1,0), 'C28': (112.8,88.3,180),
 'R37': (115.8,88.4,0), 'C30': (116.625,90.1,-90),
 'R38': (115.4,86.6,0), 'C31': (117.9,86.6,0),
 'C26': (117.6,92.2,180), 'C13': (118.3,89.6,90),
}
EXPECTED = {'20':'/ADC_AFE_VOUT','11':'/ADC_WE_BUF','12':'/ADC_RE_BUF','5':'/VREF_TRIM','7':'GND','4':'/3V3D','6':'/3V3D'}
def vec(xy): return p.VECTOR2I(p.FromMM(xy[0]),p.FromMM(xy[1]))
def xy(item): return (p.ToMM(item.GetPosition().x),p.ToMM(item.GetPosition().y))
def apply(board):
 fps={f.GetReference():f for f in board.GetFootprints()}
 if xy(fps['U6'])!=(114.5,90.5) or abs(fps['U6'].GetOrientationDegrees()-180)>1e-6: raise ValueError('U6 pose changed; adapter requires re-evaluation')
 pads=lambda ref,pin: next(q for q in fps[ref].Pads() if q.GetNumber()==str(pin))
 for pin,net in EXPECTED.items():
  if pads('U6',pin).GetNetname()!=net: raise ValueError(('Wrong MCU net',pin,pads('U6',pin).GetNetname(),net))
 if '0402' not in str(fps['C26'].GetFPID().GetLibItemName()): raise ValueError('C26 must already be the authoritative 0402 footprint')
 for ref,(x,y,a) in POSES.items():
  f=fps[ref]
  if f.GetLayer()!=p.B_Cu: f.Flip(f.GetPosition(),False)
  f.SetPosition(vec((x,y))); f.SetOrientationDegrees(a)
 generated=[]
 def route(net,layer,points,width=.15):
  n=board.FindNet(net)
  if n is None: raise ValueError(('Missing net',net))
  for a,b in zip(points,points[1:]):
   if a==b: continue
   t=p.PCB_TRACK(board);t.SetStart(vec(a));t.SetEnd(vec(b));t.SetWidth(p.FromMM(width));t.SetLayer(layer);t.SetNet(n);t.SetLocked(True);board.Add(t);generated.append(t)
 def via(net,point):
  v=p.PCB_VIA(board);v.SetPosition(vec(point));v.SetWidth(p.FromMM(.4));v.SetDrill(p.FromMM(.2));v.SetViaType(p.VIATYPE_THROUGH);v.SetLayerPair(p.F_Cu,p.B_Cu);v.SetNet(board.FindNet(net));v.SetLocked(True);board.Add(v);generated.append(v)
 escapes={'20':(113.75,87.55),'11':(117.5,88.25),'12':(117.5,87.65),'5':(117.5,91.35),'7':(117.5,89.9)}
 for pin,pos in escapes.items():
  net=EXPECTED[pin]
  escape_path=[xy(pads('U6',pin)),pos] if pin!='7' else [xy(pads('U6',pin)),(117.65,90.25),pos]
  route(net,p.F_Cu,escape_path);via(net,pos)
 route('/ADC_AFE_VOUT',p.B_Cu,[xy(pads('R33',2)),(112.925,86.725),escapes['20'],xy(pads('C28',1))])
 route('/ADC_WE_BUF',p.B_Cu,[xy(pads('R37',2)),escapes['11']])
 route('/ADC_WE_BUF',p.B_Cu,[xy(pads('R37',2)),xy(pads('C30',1))])
 route('/ADC_RE_BUF',p.B_Cu,[xy(pads('R38',2)),xy(pads('C31',1)),escapes['12']])
 route('/VREF_TRIM',p.B_Cu,[escapes['5'],(118.08,91.93),xy(pads('C26',1))])
 route('GND',p.B_Cu,[xy(pads('C26',2)),(116.4,92.52),(116.4,92.85)],.2)
 via('GND',(116.4,92.85))
 route('GND',p.F_Cu,[(116.4,92.85),(116.4,90.25),escapes['7']],.2)
 route('GND',p.B_Cu,[xy(pads('C30',2)),escapes['7']],.2)
 for ref,pos in [('C28',(111.5,88.3)),('C31',(119.2,86.6))]:
  route('GND',p.B_Cu,[xy(pads(ref,2)),pos],.2);via('GND',pos)
 # C13 is the closest VDD/VDDA ceramic; C14 remains the nearby bulk.
 via('/3V3D',(117.5,90.75))
 route('/3V3D',p.F_Cu,[xy(pads('U6',6)),(117.5,90.75)],.2)
 route('/3V3D',p.B_Cu,[(117.5,90.75),(118.3,90.75),xy(pads('C13',1))],.2)
 route('GND',p.B_Cu,[xy(pads('C13',2)),(117.5,89.12),escapes['7']],.2)
 route('/3V3D',p.B_Cu,[(117.5,90.75),(116.95,91.1),(116.1,91.1),(115.375,91.825),xy(pads('C14',1))],.2)
 # VBAT (U6.4) has a narrow lead escape but joins the same local supply mesh.
 via('/3V3D',(117.5,92.95))
 route('/3V3D',p.F_Cu,[xy(pads('U6',4)),(117.65,91.75),(117.5,91.9),(117.5,92.95)],.1)
 route('/3V3D',p.B_Cu,[(117.5,92.95),(117.9,93.35),(115.375,93.35),xy(pads('C14',1))],.2)
 # Supplemental bypass/monitor reservoirs get explicit local plane returns.
 for ref,pos in [('C12',(108.52,92.9)),('C14',(113.825,92.9)),('C32',(113.2,90.4)),('C33',(113.25,93.2))]:
  route('GND',p.B_Cu,[xy(pads(ref,2)),pos],.2);via('GND',pos)
 board.BuildConnectivity()
 return {'poses':POSES,'items':[x.m_Uuid.AsString() for x in generated],'escape_vias':escapes}
