"""One-board native geometry evidence; not a generic fabrication-release gate."""
import pcbnew as p
import wx,json,hashlib,time
from pathlib import Path
from collections import Counter
start=time.perf_counter();app=wx.AppConsole();root=Path(__file__).resolve().parents[1]
boardfile=root/'routing/revb-current/o2-probe.kicad_pcb';expected='3c24db8193af09d4d9ad07b2166c7f818885211b63b3e2af6e0c7cbec900c665'
sha=lambda f:hashlib.sha256(Path(f).read_bytes()).hexdigest()
if sha(boardfile)!=expected:raise RuntimeError('Final board fingerprint differs')
b=p.LoadBoard(str(boardfile));vias=[t for t in b.GetTracks() if isinstance(t,p.PCB_VIA)];pads=[(f,q) for f in b.GetFootprints() for q in f.Pads()]
if len(vias)!=195 or len(list(b.GetFootprints()))!=83:raise RuntimeError('Unexpected board inventory')
xy=lambda v:[p.ToMM(v.x),p.ToMM(v.y)]
copper=[];mask=[];paste=[];margin_summary=Counter()
for f,q in pads:
 for cu,ma,pa in [(p.F_Cu,p.F_Mask,p.F_Paste),(p.B_Cu,p.B_Mask,p.B_Paste)]:
  if q.GetAttribute()==p.PAD_ATTRIB_SMD and q.IsOnLayer(cu):copper.append((f,q,cu,q.GetEffectiveShape(cu)))
  if q.IsOnLayer(ma):
   margin=q.GetSolderMaskExpansion(cu)
   if margin!=0:raise RuntimeError('Nonzero mask margin requires explicit expanded-shape implementation')
   mask.append((f,q,cu,q.GetEffectiveShape(ma)));margin_summary['mask_apertures_at_zero_expansion']+=1
  if q.IsOnLayer(pa):
   m=q.GetSolderPasteMargin(cu)
   if m.x!=0 or m.y!=0:raise RuntimeError('Nonzero paste margin requires explicit expanded-shape implementation')
   paste.append((f,q,cu,q.GetEffectiveShape(pa)));margin_summary['paste_apertures_at_zero_margin']+=1
hits=dict(via_copper_to_smd_copper=[],via_drill_to_pad_mask_opening=[],via_drill_to_paste_aperture=[])
for v in vias:
 hole=p.PCB_VIA(b);hole.SetPosition(v.GetPosition());hole.SetWidth(v.GetDrillValue());hole.SetDrill(v.GetDrillValue());hole.SetLayerPair(p.F_Cu,p.B_Cu)
 for key,rows,item in [('via_copper_to_smd_copper',copper,v),('via_drill_to_pad_mask_opening',mask,hole),('via_drill_to_paste_aperture',paste,hole)]:
  for f,q,layer,shape in rows:
   if item.GetEffectiveShape(layer).Collide(shape,0):hits[key].append(dict(via_uuid=v.m_Uuid.AsString(),via_xy=xy(v.GetPosition()),via_net=v.GetNetname(),pad=f.GetReference()+'.'+q.GetNumber(),pad_uuid=q.m_Uuid.AsString(),layer=b.GetLayerName(layer)))
# Known-bad calibration: deliberately place a temporary native via disc at a
# solder land and at an anonymous paste-only EP window; neither is saved.
probe=p.PCB_VIA(b);probe.SetWidth(p.FromMM(.4));probe.SetDrill(p.FromMM(.2));probe.SetLayerPair(p.F_Cu,p.B_Cu)
f,q,layer,shape=copper[0];probe.SetPosition(q.GetPosition());bad_copper=probe.GetEffectiveShape(layer).Collide(shape,0)
paste_only=next(r for r in paste if not r[1].IsOnLayer(p.F_Cu) and not r[1].IsOnLayer(p.B_Cu));f,q,layer,shape=paste_only;probe.SetPosition(q.GetPosition());bad_paste=probe.GetEffectiveShape(layer).Collide(shape,0)
if not bad_copper or not bad_paste:raise RuntimeError('Native known-bad contact calibration failed')
if sha(boardfile)!=expected:raise RuntimeError('Board changed during review')
result=dict(scope='Final board native copper, mask and paste geometry; no physical solder-process qualification',board_path=str(boardfile.relative_to(root)),board_sha256=expected,code_path=str(Path(__file__).relative_to(root)),code_sha256=sha(__file__),native_binding_sha256=sha(p.__file__),kicad_version=p.GetBuildVersion(),project_sha256=sha(boardfile.with_suffix('.kicad_pro')),rules_sha256=sha(boardfile.with_suffix('.kicad_dru')),footprints=83,via_count=len(vias),via_drills_mm=dict(Counter(str(p.ToMM(v.GetDrillValue())) for v in vias)),smd_copper_layer_shapes=len(copper),pad_apertures=dict(margin_summary),resolved_front_tented=sum(v.IsTented(p.F_Cu) for v in vias),resolved_back_tented=sum(v.IsTented(p.B_Cu) for v in vias),includes_anonymous_paste_only_pads=True,contact_margin_mm=0,hits=hits,known_bad_calibration=dict(copper_overlap_detected=bad_copper,paste_only_window_overlap_detected=bad_paste),status='NO_NATIVE_OVERLAPS' if not any(hits.values()) else 'OVERLAPS_FOUND',limits=['No universal 0.20 mm via-to-land rule is assumed.','Tenting is a resolved design setting, not proof that the fabricator will reliably cover every hole.','Zero drawn overlap does not establish a qualified solder-mask web, stencil process, registration tolerance, or filled/capped-via process.'],runtime_seconds=round(time.perf_counter()-start,3))
out=root/'routing/revb-current/evidence/final/no-via-in-pad.json';out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
