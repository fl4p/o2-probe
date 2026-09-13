import pickle, uuid, pathlib, route
PCB='/Users/fab/dev/ee/hw/o2-probe/routing/revb-86-ring/o2-probe.kicad_pcb'
W=0.15; VIA_D=0.4; VIA_DR=0.2
routes=pickle.load(open('routes.pkl','rb'))
# Snap every run's endpoints onto the via centres, so a track always lands on
# the via it changes layer at.  The 0.05 mm grid can otherwise leave a one-cell
# offset, which KiCad reports as track_not_centered_on_via.
import board as _bd
_B=_bd.parse(PCB)
def _snap_to_existing(net, pt):
    """Land the route's last point exactly on the existing copper it joins, so the
    via is centred on that track rather than a grid cell away from it."""
    best=None
    for s in _B['segs']:
        if s['net']!=net: continue
        for q in (s['a'], s['b']):
            d=((q[0]-pt[1])**2+(q[1]-pt[2])**2)**0.5
            if d<0.35 and (best is None or d<best[0]): best=(d,q)
    for v in _B['vias']:
        if v['net']!=net: continue
        d=((v['at'][0]-pt[1])**2+(v['at'][1]-pt[2])**2)**0.5
        if d<0.35 and (best is None or d<best[0]): best=(d,v['at'])
    return (pt[0], best[1][0], best[1][1]) if best else pt
for _net,_pl in routes.items():
    if _pl is None: continue
    _pl[-1][-1]=_snap_to_existing(_net, _pl[-1][-1])
    if len(_pl[-1])==1 and len(_pl)>1:
        _pl[-2][-1]=(_pl[-2][-1][0], _pl[-1][0][1], _pl[-1][0][2])
for _net,_pl in routes.items():
    if _pl is None: continue
    for _k in range(len(_pl)-1):
        _j=_pl[_k][-1]
        _pl[_k+1][0]=(_pl[_k+1][0][0], _j[1], _j[2])
p=pathlib.Path(PCB); t=p.read_text()
def u(): return str(uuid.uuid4())
add=[]; nseg=nvia=0
for net,pl in routes.items():
    if pl is None: continue
    for run in pl:
        for k in range(len(run)-1):
            (li,x1,y1),(_,x2,y2)=run[k],run[k+1]
            if (x1,y1)==(x2,y2): continue
            add.append(f'\n\t(segment\n\t\t(start {x1:g} {y1:g})\n\t\t(end {x2:g} {y2:g})\n'
                       f'\t\t(width {W})\n\t\t(layer "{route.LAYERS[li]}")\n\t\t(net "{net}")\n'
                       f'\t\t(uuid "{u()}")\n\t)')
            nseg+=1
    for k in range(len(pl)-1):
        _,vx,vy=pl[k][-1]
        add.append(f'\n\t(via\n\t\t(at {vx:g} {vy:g})\n\t\t(size {VIA_D})\n\t\t(drill {VIA_DR})\n'
                   f'\t\t(layers "F.Cu" "B.Cu")\n\t\t(net "{net}")\n\t\t(uuid "{u()}")\n\t)')
        nvia+=1
k=t.rindex('\n\t(segment'); k=t.index('\n\t)',k)+3
p.write_text(t[:k]+"".join(add)+t[k:])
print(f"wrote {nseg} segments and {nvia} vias")
