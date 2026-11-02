"""Parse a .kicad_pcb into the geometry a router needs. Read-only."""
import re, math

def _blocks(t, kw):
    out=[]
    for m in re.finditer(r'\n\t\(%s\b'%kw, t):
        s=m.start()+1; d=0; j=s
        while j<len(t):
            if t[j]=='(': d+=1
            elif t[j]==')':
                d-=1
                if d==0: break
            j+=1
        out.append(t[s:j+1])
    return out

def _f(pat, blk, n=1, default=None):
    m=re.search(pat, blk)
    if not m: return default
    return tuple(float(x) for x in m.groups() if x is not None)

def parse(path):
    t=open(path).read()
    segs=[]; vias=[]; pads=[]; holes=[]; edges=[]
    for b in _blocks(t,'segment'):
        sx,sy=_f(r'\(start ([-\d.]+) ([-\d.]+)\)',b)
        ex,ey=_f(r'\(end ([-\d.]+) ([-\d.]+)\)',b)
        w=_f(r'\(width ([-\d.]+)\)',b)[0]
        lay=re.search(r'\(layer "([^"]+)"\)',b).group(1)
        net=re.search(r'\(net "([^"]+)"\)',b)
        segs.append(dict(a=(sx,sy),b=(ex,ey),w=w,layer=lay,net=net.group(1) if net else None))
    for b in _blocks(t,'via'):
        x,y=_f(r'\(at ([-\d.]+) ([-\d.]+)\)',b)
        size=_f(r'\(size ([-\d.]+)\)',b)[0]
        drill=_f(r'\(drill ([-\d.]+)\)',b)[0]
        net=re.search(r'\(net "([^"]+)"\)',b)
        vias.append(dict(at=(x,y),size=size,drill=drill,net=net.group(1) if net else None))
    for b in _blocks(t,'gr_line')+_blocks(t,'gr_arc'):
        if '"Edge.Cuts"' not in b: continue
        pts=[(float(a),float(c)) for a,c in re.findall(r'\((?:start|mid|end) ([-\d.]+) ([-\d.]+)\)',b)]
        edges.append(pts)
    for b in _blocks(t,'footprint'):
        fat=_f(r'\n\t\t\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)',b)
        if fat is None: continue
        fx,fy=fat[0],fat[1]
        frot=re.search(r'\n\t\t\(at [-\d.]+ [-\d.]+ ([-\d.]+)\)',b)
        frot=float(frot.group(1)) if frot else 0.0
        th=math.radians(frot); cs,sn=math.cos(th),math.sin(th)
        ref=re.search(r'\(property "Reference" "([^"]+)"',b)
        ref=ref.group(1) if ref else '?'
        pbs=[]
        for pm0 in re.finditer(r'\(pad "', b):
            s0=pm0.start(); d0=0; j0=s0
            while j0<len(b):
                if b[j0]=='(': d0+=1
                elif b[j0]==')':
                    d0-=1
                    if d0==0: break
                j0+=1
            pbs.append(b[s0:j0+1])
        for pb in pbs:
            pm=re.match(r'\(pad "([^"]*)" (\S+) (\S+)', pb)
            if not pm: continue
            num,ptype,shape=pm.groups()
            o=_f(r'\(at ([-\d.]+) ([-\d.]+)',pb)
            if o is None: continue
            ox,oy=o
            prot=re.search(r'\(at [-\d.]+ [-\d.]+ ([-\d.]+)\)',pb)
            prot=float(prot.group(1)) if prot else frot
            sz=_f(r'\(size ([-\d.]+) ([-\d.]+)\)',pb) or (0.5,0.5)
            x=fx + ox*cs + oy*sn
            y=fy - ox*sn + oy*cs
            layers=re.search(r'\(layers ([^)]*)\)',pb)
            layers=layers.group(1) if layers else ''
            net=re.search(r'\(net "([^"]+)"\)',pb)
            dr=_f(r'\(drill (?:oval )?([-\d.]+)(?: ([-\d.]+))?\)',pb)
            w,h=sz
            if abs((prot%180)-90)<1: w,h=h,w
            pads.append(dict(ref=ref,num=num,at=(x,y),w=w,h=h,layers=layers,
                             net=net.group(1) if net else None,ptype=ptype,drill=dr))
            if ptype in ('thru_hole','np_thru_hole') and dr:
                holes.append(dict(at=(x,y),d=max(dr[0], dr[1] if len(dr)>1 and dr[1] else dr[0])))
    return dict(segs=segs,vias=vias,pads=pads,holes=holes,edges=edges,text=t)
