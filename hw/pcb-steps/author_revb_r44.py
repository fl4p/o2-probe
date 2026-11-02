"""Local R44 ground stitch repair; preserve divider and bus topology."""
import sys as _sys, pathlib as _pathlib  # hw/ root: this script moved to pcb-steps/
_sys.path.insert(1, str(_pathlib.Path(__file__).resolve().parent.parent))
import pcbnew as p
def apply(b):
 xy=lambda v:(p.ToMM(v.x),p.ToMM(v.y))
 pt=lambda z:p.VECTOR2I(p.FromMM(z[0]),p.FromMM(z[1]))
 f=b.FindFootprintByReference('R44');lookup={t.m_Uuid.AsString():t for t in b.GetTracks()}
 ids=['d7d4220d-39fc-4415-85fe-ceb7fb122c47','4548393c-d814-4cb4-b5ac-158f4128548a','92a1e269-72e5-4db6-8a77-b7dfeefb216a','05a82528-842a-4ba1-a598-cf410a2365ba','aac350b1-b634-40c7-90e9-a61525f04205','8da329af-7126-4f6b-a909-80ceecbe6bc2']
 if f is None or xy(f.GetPosition())!=(108.35,111.5) or any(i not in lookup for i in ids):raise ValueError('Unexpected R44 local source')
 expected={
  ids[0]:('GND',(108.5,110.7),(108.5,110.7)),
  ids[1]:('GND',(108.5,111.6),(108.5,110.7)),
  ids[2]:('/CE_MON',(108.35,112.3),(108.35,112.325)),
  ids[3]:('/I2C_SDA',(107.9,111.9),(107.9,110.9)),
  ids[4]:('/I2C_SDA',(107.9,110.9),(107.5,110.5)),
  '657e5e8b-90f4-4082-b8ba-eaae7eb14716':('/I2C_SDA',(107.5,110.5),(107.5,110.5)),
  '71692441-6d1d-475e-ba2d-3da092a13026':('/I2C_SDA',(107.5,110.5),(107.9,110.1)),
 }
 if f.GetLayer()!=p.B_Cu or f.GetOrientationDegrees()!=90:raise ValueError('R44 side/orientation changed')
 if {q.GetNumber():q.GetNetname() for q in f.Pads()}!={'1':'/CE_MON','2':'GND'}:raise ValueError('R44 net mapping changed')
 for ident,(net,a,c) in expected.items():
  t=lookup.get(ident)
  if t is None or t.GetNetname()!=net or xy(t.GetStart())!=a or xy(t.GetEnd())!=c:raise ValueError('R44 source copper changed: '+ident)
 f.SetPosition(pt((108.4,111.5)))
 sv=lookup['657e5e8b-90f4-4082-b8ba-eaae7eb14716'];sv.SetPosition(pt((107.4,110.3)));sv.SetLocked(True)
 st=lookup['71692441-6d1d-475e-ba2d-3da092a13026'];st.SetStart(sv.GetPosition());st.SetLocked(True)
 v=lookup[ids[0]];v.SetPosition(pt((107.7,110.875)));v.SetLocked(True)
 b.RemoveNative(lookup[ids[1]])
 t=lookup[ids[2]];t.SetEnd(pt((108.4,112.325)));t.SetLocked(True)
 # SDA emerges above the relocated stitch, then runs down its right side.
 for ident,a,c in [(ids[3],(108.2,111.6),(108.2,110.5)),(ids[4],(108.2,110.5),(107.4,110.3))]:
  t=lookup[ident];t.SetStart(pt(a));t.SetEnd(pt(c));t.SetLocked(True)
 t=p.PCB_TRACK(b);t.SetNet(b.FindNet('/I2C_SDA'));t.SetLayer(p.F_Cu);t.SetWidth(p.FromMM(.1));t.SetStart(pt((108.2,111.6)));t.SetEnd(pt((107.9,111.9)));t.SetLocked(True);b.Add(t)
 made=[t.m_Uuid.AsString()]
 for layer,a,c in [(p.B_Cu,(107.7,110.875),(108.4,110.675)),(p.F_Cu,(108.5,111.6),(108.5,112.15)),(p.F_Cu,(108.5,112.15),(108.8,112.45))]:
  t=p.PCB_TRACK(b);t.SetNet(v.GetNet());t.SetLayer(layer);t.SetWidth(p.FromMM(.15));t.SetStart(pt(a));t.SetEnd(pt(c));t.SetLocked(True);b.Add(t);made.append(t.m_Uuid.AsString())
 nv=p.PCB_VIA(b);nv.SetNet(v.GetNet());nv.SetPosition(pt((107.5,111.8)));nv.SetWidth(p.FromMM(.4));nv.SetDrill(p.FromMM(.2));nv.SetViaType(p.VIATYPE_THROUGH);nv.SetLayerPair(p.F_Cu,p.B_Cu);nv.SetLocked(True);b.Add(nv);made.append(nv.m_Uuid.AsString())
 b.BuildConnectivity();return dict(modified=[i for i in expected if i!=ids[1]],removed=[ids[1]],added=made,placement=['R44',108.4,111.5,90,'B.Cu'])
