"""Write drive_tip_i2c.py's routes into a board.

Usage: emit_tip.py <routes.pkl> <board.kicad_pcb>

Grid routes start and end one 0.05 mm cell off the copper they join. Each run's
first point is moved onto the source pad centre, and its last point onto the
nearest point of existing same-net copper (segment, via or pad), so KiCad sees
a real connection rather than a dangling track a cell short.
"""
import os
import pickle
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board
import route

W, VIA_D, VIA_DR = 0.15, 0.4, 0.2
SOURCES = {"/I2C_SCL": ("U12", "2"), "/I2C_SDA": ("U10", "6"), "GND": ("C20", "2")}

routes = pickle.load(open(sys.argv[1], "rb"))
pcb = sys.argv[2]
B = board.parse(pcb)


def nearest_on_net(net, x, y):
    best = None

    def take(d, q):
        nonlocal best
        if best is None or d < best[0]:
            best = (d, q)

    for s in B["segs"]:
        if s["net"] != net:
            continue
        (ax, ay), (bx, by) = s["a"], s["b"]
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / L2))
        q = (ax + t * dx, ay + t * dy)
        take(((q[0] - x) ** 2 + (q[1] - y) ** 2) ** 0.5, q)
    for v in B["vias"]:
        if v["net"] == net:
            take(((v["at"][0] - x) ** 2 + (v["at"][1] - y) ** 2) ** 0.5, v["at"])
    for p in B["pads"]:
        if p["net"] == net:
            take(((p["at"][0] - x) ** 2 + (p["at"][1] - y) ** 2) ** 0.5, p["at"])
    return best


add = []
nseg = nvia = 0
for net, pl in routes.items():
    ref, num = SOURCES[net]
    pad = [p for p in B["pads"] if p["ref"] == ref and p["num"] == num][0]
    # Clamp the first point INTO the pad (0.05 mm inside its edge) rather than
    # moving it to the centre: a stub from U12 pad 2's centre crosses the
    # footprint's no-track keepout, whose cutout covers only the pad's inner end.
    li0, fx, fy = pl[0][0]
    m = 0.05
    cx = min(max(fx, pad["at"][0] - pad["w"] / 2 + m), pad["at"][0] + pad["w"] / 2 - m)
    cy = min(max(fy, pad["at"][1] - pad["h"] / 2 + m), pad["at"][1] + pad["h"] / 2 - m)
    pl[0][0] = (li0, round(cx, 4), round(cy, 4))
    lx = pl[-1][-1]
    d, q = nearest_on_net(net, lx[1], lx[2])
    if d > 0.35:
        sys.exit("%s: route ends %.3f mm from its net - refusing to snap" % (net, d))
    pl[-1][-1] = (lx[0], round(q[0], 4), round(q[1], 4))
    print("%s: start -> %s.%s centre, end snapped %.3f mm onto existing copper"
          % (net, ref, num, d))
    for run in pl:
        for k in range(len(run) - 1):
            (li, x1, y1), (_, x2, y2) = run[k], run[k + 1]
            if (x1, y1) == (x2, y2):
                continue
            add.append('\n\t(segment\n\t\t(start %g %g)\n\t\t(end %g %g)\n'
                       '\t\t(width %s)\n\t\t(layer "%s")\n\t\t(net "%s")\n'
                       '\t\t(uuid "%s")\n\t)'
                       % (x1, y1, x2, y2, W, route.LAYERS[li], net, uuid.uuid4()))
            nseg += 1
    for k in range(len(pl) - 1):
        _, vx, vy = pl[k][-1]
        add.append('\n\t(via\n\t\t(at %g %g)\n\t\t(size %s)\n\t\t(drill %s)\n'
                   '\t\t(layers "F.Cu" "B.Cu")\n\t\t(net "%s")\n\t\t(uuid "%s")\n\t)'
                   % (vx, vy, VIA_D, VIA_DR, net, uuid.uuid4()))
        nvia += 1

t = open(pcb).read()
k = t.rindex("\n\t(segment")
k = t.index("\n\t)", k) + 3
open(pcb, "w").write(t[:k] + "".join(add) + t[k:])
print("wrote %d segments and %d vias" % (nseg, nvia))
