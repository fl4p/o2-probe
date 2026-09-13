import sys, numpy as np, board, route
from route import Grid, build, astar, path_of, simplify, layer_idx

PCB='/Users/fab/dev/ee/hw/o2-probe/routing/revb-86-ring/o2-probe.kicad_pcb'
REGION=(99.5,53.0,120.5,139.5)
W=0.15; CLR=0.1; EDGE=0.3; HOLE=0.25
VIA_D=0.4; VIA_DR=0.2
import os; VIA_COST=float(os.environ.get('VIA_COST','8'))

bd=board.parse(PCB)
ORDER=[('/I2C_SDA','3'),('/I2C_SCL','4'),('/UART2_RX','6'),('/UART2_TX','5'),('/3V3D','1')]
extra_segs=[]; extra_vias=[]
results={}
for net,padnum in ORDER:
    b2=dict(bd); b2['segs']=bd['segs']+extra_segs; b2['vias']=bd['vias']+extra_vias
    g,tgt,vg=build(b2, REGION, net, W, CLR, EDGE, HOLE, exclude_ref='J107',
                   via_d=VIA_D, via_drill=VIA_DR)
    src=[p for p in bd['pads'] if p['ref']=='J107' and p['num']==padnum][0]
    li=1  # J107 is on B.Cu
    i,j=g.ij(*src['at'])
    starts=[]
    r=int(0.4/route.G)
    for di in range(-r,r+1):
        for dj in range(-r,r+1):
            if 0<=i+di<g.nx and 0<=j+dj<g.ny and not g.block[li,j+dj,i+di]:
                starts.append((li,i+di,j+dj))
    if not starts:
        print(f"{net}: SOURCE PAD FULLY BLOCKED"); results[net]=None; continue
    end,prev=astar(g,tgt,starts,via_cost=VIA_COST,vg=vg)
    if end is None:
        print(f"{net}: NO PATH"); results[net]=None; continue
    pl=simplify(path_of(end,prev),g)
    npts=sum(len(r_) for r_ in pl); nvia=len(pl)-1
    length=0.0
    for run in pl:
        for k in range(len(run)-1):
            length+=((run[k+1][1]-run[k][1])**2+(run[k+1][2]-run[k][2])**2)**0.5
    print(f"{net}: path found, {length:.1f} mm, {nvia} via(s), {npts} vertices")
    results[net]=pl
    for run in pl:
        for k in range(len(run)-1):
            extra_segs.append(dict(a=(run[k][1],run[k][2]),b=(run[k+1][1],run[k+1][2]),
                                   w=W,layer=route.LAYERS[run[k][0]],net=net))
    for k in range(len(pl)-1):
        lp=pl[k][-1]
        extra_vias.append(dict(at=(lp[1],lp[2]),size=VIA_D,drill=VIA_DR,net=net))
import pickle; pickle.dump(results, open('routes.pkl','wb'))
print("saved routes.pkl")
