"""Grid maze-router for a two-layer KiCad board. Emits segments + vias."""
import math, heapq, numpy as np

G = 0.05                      # grid, mm
LAYERS = ["F.Cu", "B.Cu"]

class Grid:
    def __init__(self, x0, y0, x1, y1):
        self.x0, self.y0 = x0, y0
        self.nx = int((x1-x0)/G)+1
        self.ny = int((y1-y0)/G)+1
        self.block = np.zeros((2, self.ny, self.nx), dtype=bool)
    def ij(self, x, y):
        return int(round((x-self.x0)/G)), int(round((y-self.y0)/G))
    def xy(self, i, j):
        return self.x0+i*G, self.y0+j*G
    def _disc(self, mask, x, y, r):
        i0,j0 = self.ij(x-r, y-r); i1,j1 = self.ij(x+r, y+r)
        i0=max(i0,0); j0=max(j0,0); i1=min(i1,self.nx-1); j1=min(j1,self.ny-1)
        if i1<i0 or j1<j0: return
        ii=np.arange(i0,i1+1)*G+self.x0
        jj=np.arange(j0,j1+1)*G+self.y0
        d2=(ii[None,:]-x)**2+(jj[:,None]-y)**2
        mask[j0:j1+1, i0:i1+1] |= d2 <= r*r
    def _rect(self, mask, x, y, hw, hh):
        i0,j0=self.ij(x-hw,y-hh); i1,j1=self.ij(x+hw,y+hh)
        i0=max(i0,0); j0=max(j0,0); i1=min(i1,self.nx-1); j1=min(j1,self.ny-1)
        if i1<i0 or j1<j0: return
        mask[j0:j1+1, i0:i1+1]=True
    def capsule(self, mask, a, b, r):
        n=max(1,int(math.dist(a,b)/(G*0.7)))
        for k in range(n+1):
            t=k/n
            self._disc(mask, a[0]+(b[0]-a[0])*t, a[1]+(b[1]-a[1])*t, r)

def layer_idx(name): return LAYERS.index(name)

def _arc_points(p0, pm, p1, step=0.05):
    """Points along the circular arc from p0 through pm to p1."""
    (x1,y1),(x2,y2),(x3,y3) = p0, pm, p1
    d = 2*(x1*(y2-y3) + x2*(y3-y1) + x3*(y1-y2))
    if abs(d) < 1e-12:
        return [p0, pm, p1]
    ux = ((x1*x1+y1*y1)*(y2-y3) + (x2*x2+y2*y2)*(y3-y1) + (x3*x3+y3*y3)*(y1-y2)) / d
    uy = ((x1*x1+y1*y1)*(x3-x2) + (x2*x2+y2*y2)*(x1-x3) + (x3*x3+y3*y3)*(x2-x1)) / d
    r = math.hypot(x1-ux, y1-uy)
    a0 = math.atan2(y1-uy, x1-ux); am = math.atan2(y2-uy, x2-ux); a1 = math.atan2(y3-uy, x3-ux)
    tau = 2*math.pi
    # sweep the way round that passes through the mid point
    if (am-a0) % tau <= (a1-a0) % tau:
        sweep = (a1-a0) % tau
    else:
        sweep = -((a0-a1) % tau)
    n = max(2, int(abs(sweep)*r/step) + 1)
    return [(ux + r*math.cos(a0 + sweep*k/n), uy + r*math.sin(a0 + sweep*k/n)) for k in range(n+1)]

def build(bd, region, net, track_w, clr, edge_clr, hole_clr, exclude_ref=None,
          via_d=0.4, via_drill=0.2, h2h=0.30):
    # h2h: hole-to-hole spacing. 0.30 mm is the project's rule; the original
    # 0.25 default was flagged by the 2026-09-13 review (no violation resulted).
    """Obstacles for routing `net`; same-net copper becomes the target mask."""
    g = Grid(*region)
    vg = Grid(*region)          # where a VIA centre may sit
    mh = track_w/2
    vh = via_d/2
    vdr = via_drill/2
    tgt = np.zeros((2, g.ny, g.nx), dtype=bool)
    def inreg(p):
        return region[0]-3 <= p[0] <= region[2]+3 and region[1]-3 <= p[1] <= region[3]+3
    for s in bd['segs']:
        if not (inreg(s['a']) or inreg(s['b'])): continue
        li = layer_idx(s['layer']) if s['layer'] in LAYERS else None
        if li is None: continue
        if s['net']==net:
            g.capsule(tgt[li], s['a'], s['b'], s['w']/2)
        else:
            g.capsule(g.block[li], s['a'], s['b'], s['w']/2+clr+mh)
            vg.capsule(vg.block[li], s['a'], s['b'], s['w']/2+clr+vh)
    for v in bd['vias']:
        if not inreg(v['at']): continue
        if v['net']==net:
            for li in (0,1): g._disc(tgt[li], *v['at'], v['size']/2)
        else:
            for li in (0,1):
                g._disc(g.block[li], *v['at'], v['size']/2+clr+mh)
                vg._disc(vg.block[li], *v['at'], max(v['size']/2+clr+vh, v['drill']/2+h2h+vdr))
    for p in bd['pads']:
        if not inreg(p['at']): continue
        lis=[]
        if '*.Cu' in p['layers']: lis=[0,1]
        else:
            if 'F.Cu' in p['layers']: lis.append(0)
            if 'B.Cu' in p['layers']: lis.append(1)
        if p['net']==net and p['ref']==exclude_ref:
            continue          # the pad we are routing FROM: neither target nor obstacle
        if p['net']==net:
            for li in lis: g._rect(tgt[li], p['at'][0], p['at'][1], p['w']/2, p['h']/2)
        else:
            for li in lis:
                g._rect(g.block[li], p['at'][0], p['at'][1], p['w']/2+clr+mh, p['h']/2+clr+mh)
                vg._rect(vg.block[li], p['at'][0], p['at'][1], p['w']/2+clr+vh, p['h']/2+clr+vh)
    for h in bd['holes']:
        if not inreg(h['at']): continue
        for li in (0,1):
            g._disc(g.block[li], *h['at'], h['d']/2+hole_clr+mh)
            vg._disc(vg.block[li], *h['at'], max(h['d']/2+hole_clr+vh, h['d']/2+h2h+vdr))
    # board edge: block outside, and a margin inside every edge primitive
    for pts in bd['edges']:
        for k in range(len(pts)-1):
            for li in (0,1):
                g.capsule(g.block[li], pts[k], pts[k+1], edge_clr+mh)
                vg.capsule(vg.block[li], pts[k], pts[k+1], edge_clr+vh)
        if len(pts)==3:   # arc (start, mid, end): sample the true circle
            # Two chords through the mid point under-block the arc's bulge; on
            # the thermal-slot apex that let a route sit inside the 0.3 mm
            # copper-edge clearance (copper_edge_clearance x4 at (101.2, 134.6)).
            ap = _arc_points(*pts)
            for li in (0,1):
                for a_, b_ in zip(ap[:-1], ap[1:]):
                    g.capsule(g.block[li], a_, b_, edge_clr+mh)
                    vg.capsule(vg.block[li], a_, b_, edge_clr+vh)
    return g, tgt, vg

def astar(g, tgt, start_cells, via_cost=8.0, vg=None):
    INF=float('inf')
    dist={}; prev={}
    pq=[]
    for (li,i,j) in start_cells:
        if g.block[li,j,i]: continue
        dist[(li,i,j)]=0.0; heapq.heappush(pq,(0.0,(li,i,j)))
    steps=[(1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)]
    while pq:
        d,(li,i,j)=heapq.heappop(pq)
        if d>dist.get((li,i,j),INF): continue
        if tgt[li,j,i]: return (li,i,j), prev
        for dx,dy in steps:
            ni,nj=i+dx,j+dy
            if not (0<=ni<g.nx and 0<=nj<g.ny): continue
            if g.block[li,nj,ni]: continue
            nd=d+(1.4142 if dx and dy else 1.0)
            if nd<dist.get((li,ni,nj),INF):
                dist[(li,ni,nj)]=nd; prev[(li,ni,nj)]=(li,i,j); heapq.heappush(pq,(nd,(li,ni,nj)))
        lo=1-li
        if not g.block[lo,j,i] and (vg is None or not (vg.block[0,j,i] or vg.block[1,j,i])):
            nd=d+via_cost
            if nd<dist.get((lo,i,j),INF):
                dist[(lo,i,j)]=nd; prev[(lo,i,j)]=(li,i,j); heapq.heappush(pq,(nd,(lo,i,j)))
    return None, prev

def path_of(node, prev):
    out=[node]
    while node in prev:
        node=prev[node]; out.append(node)
    return out[::-1]

def simplify(path, g):
    """Cells -> polyline per layer, with via points where the layer changes."""
    runs=[]; cur=[path[0]]
    for n in path[1:]:
        if n[0]!=cur[-1][0]:
            runs.append(cur); cur=[n]
        else:
            cur.append(n)
    runs.append(cur)
    out=[]
    for run in runs:
        pts=[]
        for k,(li,i,j) in enumerate(run):
            if 0<k<len(run)-1:
                pi,pj=run[k-1][1],run[k-1][2]; ni,nj=run[k+1][1],run[k+1][2]
                if (i-pi,j-pj)==(ni-i,nj-j): continue
            pts.append((li,)+g.xy(i,j))
        out.append(pts)
    return out
