import numpy as np
from PIL import Image, ImageDraw, ImageFont
SRC='cad/exports/head-end-exploded.png'
im=Image.open(SRC).convert('RGB'); A=np.array(im).astype(int)
H,W,_=A.shape
bright=A.sum(axis=2)
norm=A/np.maximum(bright[:,:,None],1)
def mask(rgb, tol=0.045, ylo=0, yhi=H, bmin=120, bmax=735):
    t=np.array(rgb); tn=t/t.sum()
    d=np.abs(norm-tn).sum(axis=2)
    m=(d<tol)&(bright>bmin)&(bright<bmax)
    m[:ylo]=False; m[yhi:]=False
    return m
# cap and O-ring are BOTH DimGray in the model, so split them by height;
# membrane is GhostWhite, which normalises identically to grey -- separate on
# absolute brightness instead.
parts=[
 ("cap",             mask((105,105,105), ylo=0,   yhi=380, bmax=560), 'r'),
 ("retainer screws (6 + 2 cap)", mask((150,150,155), tol=0.03, ylo=330, yhi=430, bmin=250, bmax=700), 'l'),
 ("retainer",        mask((176,196,222)),                            'r'),
 ("membrane (PMV15T)", ((A[:,:,2]-A[:,:,0])>4)&(bright>700)&(bright<770), 'l'),
 ("membrane gasket", mask((205,92,92)),                               'r'),
 ("carrier",         mask((240,230,140)),                            'l'),
 ("O-ring 24 x 1.5", mask((105,105,105), ylo=700, yhi=860, bmax=560), 'r'),
 ("head",            mask((210,180,140)),                            'l'),
]
im2=im.copy(); d=ImageDraw.Draw(im2)
try:
    f=ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 30)
except Exception:
    f=ImageFont.load_default()
for name,m,side in parts:
    ys,xs=np.nonzero(m)
    if len(ys)<40: print(f"  SKIP {name} ({m.sum()} px)"); continue
    cy=int(np.median(ys))
    row=xs[(ys>cy-6)&(ys<cy+6)]
    if len(row)<3: row=xs
    x_edge = int(row.max()) if side=='r' else int(row.min())
    tx = x_edge + 60 if side=='r' else x_edge - 60
    bb=d.textbbox((0,0),name,font=f); tw=bb[2]-bb[0]; th=bb[3]-bb[1]
    lx = tx if side=='r' else tx-tw
    d.line([(x_edge+ (8 if side=='r' else -8), cy), (tx - (8 if side=='r' else -8), cy)],
           fill=(70,70,70), width=3)
    d.ellipse([x_edge-4,cy-4,x_edge+4,cy+4], fill=(70,70,70))
    d.text((lx, cy-th/2-4), name, font=f, fill=(20,20,20))
    print(f"  {name:30} y={cy:5d} edge x={x_edge:5d} ({m.sum()} px)")
im2.save('cad/exports/head-end-exploded-labelled.png')
print("\nwrote cad/exports/head-end-exploded-labelled.png")
