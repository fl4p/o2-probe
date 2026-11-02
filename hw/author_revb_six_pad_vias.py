"""Seven actual via/paste-land overlap repairs, preserving bus copper. No file I/O."""
import pcbnew
PLAN = {'vias': [{'uuid': '4dd93650-b219-402c-a99d-104fcb731501', 'net': 'GND', 'old': [106.5, 135.1], 'new': [106.55, 135.1], 'diameter': 0.4, 'drill': 0.2}, {'uuid': 'aa71ddb9-3135-4090-9153-8899a3fb1d2a', 'net': 'GND', 'old': [112.5, 136.2], 'new': [111.85, 136.2], 'diameter': 0.45, 'drill': 0.2}, {'uuid': 'bb5b5b37-cff2-411b-ad94-04edb50d6597', 'net': 'GND', 'old': [114.1, 134.8], 'new': [114.1, 134.45], 'diameter': 0.4, 'drill': 0.2}, {'uuid': 'cf7278fc-2c16-4f55-959b-ab6d55df4a63', 'net': 'GND', 'old': [111.35, 134.825], 'new': [111.55, 134.825], 'diameter': 0.4, 'drill': 0.2}, {'uuid': '214117fa-bc15-481e-8b24-4c706dc09cab', 'net': '/HEATER_GATE', 'old': [113.7, 137.35], 'new': [113.7, 137.42], 'diameter': 0.45, 'drill': 0.2}, {'uuid': '300de5df-1632-4639-978a-c3c173968921', 'net': '/HEATER_GATE', 'old': [109.05, 134.3], 'new': [108.5, 133.8], 'diameter': 0.4, 'drill': 0.2}], 'ends': [{'uuid': '5427d36e-3384-46f9-9243-1e3cb9fc6e71', 'net': 'GND', 'endpoint': 'end', 'old': [106.5, 135.1], 'new': [106.55, 135.1]}, {'uuid': 'a6d03cdd-8cef-4981-8c1f-814855dca883', 'net': 'GND', 'endpoint': 'end', 'old': [106.5, 135.1], 'new': [106.55, 135.1]}, {'uuid': 'cf703a01-a776-453e-9d56-37e4f9347461', 'net': 'GND', 'endpoint': 'start', 'old': [106.5, 135.1], 'new': [106.55, 135.1]}, {'uuid': '01555252-27c3-4b02-9896-377a79193f90', 'net': 'GND', 'endpoint': 'start', 'old': [112.5, 136.2], 'new': [111.85, 136.2]}, {'uuid': 'a21f6365-923a-4364-ba5b-dc8a10e339d2', 'net': 'GND', 'endpoint': 'end', 'old': [112.5, 136.2], 'new': [111.85, 136.2]}, {'uuid': '5d77eb3a-c1b8-4dba-af49-6be21fb52bda', 'net': '/HEATER_GATE', 'endpoint': 'end', 'old': [113.7, 137.35], 'new': [113.7, 137.42]}, {'uuid': '38c4fc93-5b9d-4242-bbcd-1bff7293cc4a', 'net': '/HEATER_GATE', 'endpoint': 'end', 'old': [113.7, 137.35], 'new': [113.7, 137.42]}, {'uuid': 'c2a7d0c1-6d43-4ee1-9418-0f5778fa8e93', 'net': '/HEATER_GATE', 'endpoint': 'end', 'old': [109.05, 134.3], 'new': [108.5, 133.8]}, {'uuid': 'db4be12f-4221-46de-b184-0326af652d91', 'net': '/HEATER_GATE', 'endpoint': 'start', 'old': [109.05, 134.3], 'new': [108.5, 133.8]}], 'add': [{'net': '/HEATER_GATE', 'layer': 'B.Cu', 'width': 0.18, 'start': [108.5, 133.8], 'end': [109.05, 134.3125]}, {'net': 'GND', 'layer': 'B.Cu', 'width': 0.15, 'start': [111.55, 134.825], 'end': [111.35, 134.825]}, {'net': 'GND', 'layer': 'B.Cu', 'width': 0.15, 'start': [114.1, 134.45], 'end': [114.1, 134.8]}], 'delete': []}
def pt(v):return [round(pcbnew.ToMM(v.x),6),round(pcbnew.ToMM(v.y),6)]
def vec(v):return pcbnew.VECTOR2I(pcbnew.FromMM(v[0]),pcbnew.FromMM(v[1]))
def apply(board):
 items={t.m_Uuid.AsString():t for t in board.GetTracks()}
 for s in PLAN['vias']:
  if s['uuid'] not in items or items[s['uuid']].GetNetname()!=s['net'] or pt(items[s['uuid']].GetPosition())!=s['old']:raise ValueError('via source changed '+s['uuid'])
 for s in PLAN['ends']:
  if s['uuid'] not in items:raise ValueError('track source absent '+s['uuid'])
  t=items[s['uuid']];xy=t.GetStart() if s['endpoint']=='start' else t.GetEnd()
  if t.GetNetname()!=s['net'] or pt(xy)!=s['old']:raise ValueError('track source changed '+s['uuid'])
 for s in PLAN['delete']:
  if s['uuid'] not in items or items[s['uuid']].GetNetname()!=s['net'] or pt(items[s['uuid']].GetStart())!=s['start'] or pt(items[s['uuid']].GetEnd())!=s['end']:raise ValueError('deleted source changed '+s['uuid'])
 for s in PLAN['delete']:board.RemoveNative(items[s['uuid']])
 for s in PLAN['vias']:
  v=items[s['uuid']];v.SetPosition(vec(s['new']));v.SetWidth(pcbnew.FromMM(s['diameter']));v.SetDrill(pcbnew.FromMM(s['drill']))
 for s in PLAN['ends']:
  t=items[s['uuid']]
  if s['endpoint']=='start':t.SetStart(vec(s['new']))
  else:t.SetEnd(vec(s['new']))
 for s in PLAN['add']:
  t=pcbnew.PCB_TRACK(board);t.SetStart(vec(s['start']));t.SetEnd(vec(s['end']));t.SetLayer(board.GetLayerID(s['layer']));t.SetWidth(pcbnew.FromMM(s['width']));t.SetNet(board.FindNet(s['net']));t.SetLocked(True);board.Add(t)
 return {'vias':len(PLAN['vias']),'ends':len(PLAN['ends']),'add':len(PLAN['add'])}
