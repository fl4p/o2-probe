"""Close 3V3D through the neck; remove redundant B guard feed, retain F rails."""
import pcbnew as p
def apply(b):
 xy=lambda v:(p.ToMM(v.x),p.ToMM(v.y))
 pt=lambda z:p.VECTOR2I(p.FromMM(z[0]),p.FromMM(z[1]))
 net=b.FindNet('/3V3D');items={t.m_Uuid.AsString():t for t in b.GetTracks()}
 anchors=[(p.F_Cu,(115.35,110.55)),(p.B_Cu,(111.5,119.3))]
 for layer,point in anchors:
  if not any(t.GetNetname()=='/3V3D' and t.IsOnLayer(layer) and point in [xy(t.GetStart()),xy(t.GetEnd())] for t in b.GetTracks()):raise ValueError('Missing 3V3D neck anchor '+str(point))
 remove={'1ed5e83e-bc47-4eac-ab25-4dd23013a437':(p.B_Cu,(110.935,117.4),(112.15,117.1)), '1f373dc5-9473-45cb-aca9-f01226c9c1eb':(p.F_Cu,(112.15,117.1),(112.15,117.1))}
 for ident,(layer,a,c) in remove.items():
  t=items.get(ident)
  if t is None or t.GetNetname()!='/GUARD_REPLICA' or t.GetLayer()!=layer or xy(t.GetStart())!=a or xy(t.GetEnd())!=c:raise ValueError('Unexpected top guard feed '+ident)
 bridge=items.get('90bdd9e8-a471-4727-922b-b1b8083d1deb')
 if bridge is None or bridge.GetNetname()!='/GUARD_REPLICA' or xy(bridge.GetStart())!=(110.95,123.6) or xy(bridge.GetEnd())!=(112.15,123.68):raise ValueError('Missing retained bottom guard bridge')
 for ident in remove:b.RemoveNative(items[ident])
 made=[]
 for layer,points in [(p.F_Cu,[(115.35,110.55),(115.5,110.7),(115.5,114.4)]),(p.B_Cu,[(115.5,114.4),(115.5,115.7),(112.8,115.7),(111.4,117.1),(111.4,119.3),(111.5,119.3)])]:
  for a,c in zip(points,points[1:]):
   t=p.PCB_TRACK(b);t.SetStart(pt(a));t.SetEnd(pt(c));t.SetWidth(p.FromMM(.15));t.SetLayer(layer);t.SetNet(net);t.SetLocked(True);b.Add(t);made.append(t.m_Uuid.AsString())
 v=p.PCB_VIA(b);v.SetPosition(pt((115.5,114.4)));v.SetNet(net);v.SetViaType(p.VIATYPE_THROUGH);v.SetLayerPair(p.F_Cu,p.B_Cu);v.SetWidth(p.FromMM(.4));v.SetDrill(p.FromMM(.2));v.SetLocked(True);b.Add(v);made.append(v.m_Uuid.AsString());b.BuildConnectivity();return dict(added=made,removed=list(remove))
