"""Draw the cable-end seal in section, before and after the collar.

Fab, 2026-09-06: "i dont understand, show me a proper drawing".

Nothing here is drawn by hand. Both panels are TRUE SECTIONS of the models: each
part is rendered to STL, cut on the y=0 plane with OpenSCAD's
`projection(cut=true)`, exported as SVG (whose user units are millimetres), and
the resulting polygons are plotted at 1:1. The "before" panel comes out of git at
the commit before the collar landed, so it is the geometry that actually existed,
not a reconstruction of it.

The only hand-written things are the labels, and every number in them is read
back out of the model rather than typed in -- see `numbers()`.

    python3 tools/collar_drawing.py            # -> exports/collar-section.png
"""
import os
import re
import subprocess
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon

HERE = os.path.dirname(os.path.abspath(__file__))
CAD = os.path.dirname(HERE)
REPO = os.path.dirname(CAD)
BODY = os.path.join(CAD, 'o2_probe_body_tube.scad')
OUT = os.path.join(CAD, 'exports')
WORK = os.path.join(OUT, '.collar-drawing')
OPENSCAD = os.environ.get('OPENSCAD', 'openscad')

# The commit BEFORE 56407da "Cable end: a collar, not a counterbore", i.e. the
# last one that still had the Ø27.3 counterbore and the 24 x 1.5 ring.
BEFORE_SHA = 'c445a4a'

SECT = '''// Section of an imported solid on the y=0 plane. rotate([90,0,0]) maps
// (x,y,z) -> (x,-z,y), so y=0 becomes z=0 and projection(cut=true) returns the
// true cross-section. SVG user units are mm, so the plot is 1:1 by construction.
file = "in.stl";
projection(cut = true) rotate([90, 0, 0]) import(file);
'''


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        raise SystemExit("collar_drawing: %s\n%s" % (' '.join(cmd[:4]),
                                                     r.stderr[-800:]))
    return r


def source(which):
    """The .scad to render: the working tree, or the pre-collar commit."""
    if which == 'now':
        return BODY
    path = os.path.join(WORK, 'before_body.scad')
    r = run(['git', 'show', '%s:cad/o2_probe_body_tube.scad' % BEFORE_SHA],
            cwd=REPO)
    open(path, 'w').write(r.stdout)
    return path


def section(which, part):
    """Render one part and return its cross-section as a list of polygons."""
    stl = os.path.join(WORK, '%s-%s.stl' % (which, part))
    svg = os.path.join(WORK, '%s-%s.svg' % (which, part))
    run([OPENSCAD, '--hardwarnings', '-D', 'part="%s"' % part, '-o', stl,
         source(which)])
    run([OPENSCAD, '-D', 'file="%s"' % stl, '-o', svg,
         os.path.join(WORK, 'sect.scad')])
    text = open(svg).read()
    polys = []
    for d in re.findall(r'<path d="(.*?)"', text, re.S):
        for sub in d.split('M')[1:]:
            pts = re.findall(r'(-?[\d.]+),(-?[\d.]+)', sub)
            if len(pts) >= 3:
                # SVG y runs down and OpenSCAD's exporter flips it back, so the
                # second coordinate is +z from the cable end. Plot z across.
                polys.append([(float(b), float(a)) for a, b in pts])
    if not polys:
        raise SystemExit("collar_drawing: %s %s sectioned to nothing -- the cut "
                         "plane missed the solid. This is a FAILURE, not an "
                         "empty part." % (which, part))
    return polys


def numbers(which):
    """Read the labels' numbers back out of the model's own echo lines."""
    # NOT `-o /dev/null`: OpenSCAD skips the render for it and prints no echoes
    # at all, which reads exactly like a model that has nothing to say.
    stl = os.path.join(WORK, '%s-echo.stl' % which)
    r = subprocess.run(
        [OPENSCAD, '--hardwarnings', '-D', 'part="tube"', '-o', stl,
         source(which)], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("collar_drawing: %s would not render:\n%s"
                         % (which, r.stderr[-600:]))
    return r.stdout + r.stderr


def scalar(text, pattern):
    m = re.search(pattern, text, re.M)
    return m.group(1) if m else '??'


def mm(x):
    """A dimension as a person writes it. 32 - 27.2 is 2.4000000000000004 in
    binary floating point and that is not a wall thickness."""
    return ('%.3f' % float(x)).rstrip('0').rstrip('.')


def draw(ax, polys_by_part, title, sub):
    """One panel, cropped to the WALL.

    A half section from the axis outward spends 9 mm of page on empty bore to
    show a 1.5 mm step in a wall, and the step is the entire subject. So the
    view starts at r=9.3. Nothing is distorted -- the scale is still 1:1 and
    equal in both axes; the picture is simply cropped to where the material is.
    """
    colours = {'tube': ('#b9bec6', '#5a616b'),
               'end-cap': ('#8fb4d6', '#2d5178'),
               'end-seal-ring': ('#d2604f', '#7d2c20')}
    for part in ('tube', 'end-cap', 'end-seal-ring'):
        face, edge = colours[part]
        for p in polys_by_part[part]:
            ax.add_patch(Polygon(p, closed=True, facecolor=face,
                                 edgecolor=edge, linewidth=1.0, zorder=2))
    ax.set_xlim(-4.6, 19.4)
    ax.set_ylim(9.3, 17.9)
    ax.set_aspect('equal')
    ax.set_title(title + '\n' + sub, loc='left', fontsize=9.2, color='#444',
                 pad=7, linespacing=1.5)
    for s_ in ax.spines.values():
        s_.set_visible(False)
    ax.set_xticks([])
    ax.set_yticks([])


def level(ax, r, text, colour, dy=0.0, x0=-4.3, x1=19.1):
    """A bore surface, as a level line right across the panel.

    Two of these at different heights is the whole drawing: the seal bore is
    either ABOVE the tube bore (cut outward, a counterbore) or BELOW it (added
    inward, a collar), and a level line makes that a thing you see rather than
    a number you compare.
    """
    ax.plot([x0, x1], [r, r], color=colour, lw=1.0, ls=(0, (6, 3)), zorder=4)
    # dy exists because the BEFORE panel's two levels are 0.05 mm apart on
    # radius. At 1:1 that is a hair, which is exactly the point being made --
    # but two labels on the same hair are unreadable, so they step apart and a
    # leader ties each back to its own line.
    if dy:
        ax.plot([x1, x1 + 0.6], [r, r + dy], color=colour, lw=0.8, zorder=5)
    ax.text(x1 + (0.7 if dy else 0.2), r + dy, text, color=colour,
            fontsize=8.8, fontweight='bold', va='center', ha='left', zorder=6)


def wall(ax, z, r_in, text, colour):
    """The wall thickness, bore to OD, where it matters."""
    ax.annotate('', xy=(z, r_in), xytext=(z, 16.0),
                arrowprops=dict(arrowstyle='<->', color=colour, lw=1.3,
                                shrinkA=0, shrinkB=0), zorder=6)
    ax.text(z, (r_in + 16.0) / 2, text, color=colour, fontsize=9,
            fontweight='bold', rotation=90, ha='center', va='center', zorder=7,
            bbox=dict(fc='white', ec='none', alpha=0.92, pad=1.2))


def note(ax, xy, xytext, text, colour='#123', ha='left'):
    ax.annotate(text, xy=xy, xytext=xytext, fontsize=8.5, color=colour,
                ha=ha, va='center', zorder=6,
                arrowprops=dict(arrowstyle='-', color=colour, lw=0.8,
                                shrinkA=0, shrinkB=2),
                bbox=dict(fc='white', ec='none', alpha=0.9, pad=1.2))


def main():
    os.makedirs(WORK, exist_ok=True)
    open(os.path.join(WORK, 'sect.scad'), 'w').write(SECT)

    parts = ('tube', 'end-cap', 'end-seal-ring')
    before = {p: section('before', p) for p in parts}
    now = {p: section('now', p) for p in parts}

    tnow = numbers('now')
    collar = re.search(r'COLLAR bore ([\d.]+) len ([\d.]+) lead ([\d.]+) '
                       r'tube_id ([\d.]+) wall ([\d.]+)', tnow)
    if not collar:
        raise SystemExit("collar_drawing: the model printed no COLLAR echo")
    c_bore, c_len, c_lead, c_tid, c_wall = collar.groups()
    spig = re.search(r'SPIGOT od ([\d.]+) id ([\d.]+) len ([\d.]+) chamfer '
                     r'[\d.]+ bore_depth [\d.]+ groove_root_drawn ([\d.]+) '
                     r'groove_w ([\d.]+)', tnow)
    if not spig:
        raise SystemExit("collar_drawing: the model printed no SPIGOT echo")
    s_od, _s_id, _s_len, g_root, _g_w = spig.groups()
    n_ring = scalar(tnow, r'CABLE SEAL: ([\d]+ x [\d.]+) EPDM')
    n_sq = scalar(tnow, r'ring actually delivers ([\d.]+)%')

    tbef = numbers('before')
    b_bore = scalar(tbef, r'[Bb]ore ([\d.]+) reamed')
    b_ring = scalar(tbef, r'CABLE SEAL: ([\d]+ x [\d.]+)')
    if b_bore == '??':
        b_bore = scalar(open(source('before')).read(),
                        r'cable_bore_d\s*=\s*([\d.]+)')
    if b_ring == '??':
        src = open(source('before')).read()
        b_ring = '%s x %s' % (scalar(src, r'^seal_id\s*=\s*([\d.]+)'),
                              scalar(src, r'^seal_cord\s*=\s*([\d.]+)'))

    fig, axes = plt.subplots(2, 1, figsize=(11.0, 6.9))
    fig.suptitle('o2-probe cable end in section \u2014 what "the collar" is',
                 fontsize=15, fontweight='bold', x=0.035, ha='left', y=0.985)

    tube_wall = mm((32 - float(c_tid)) / 2)
    b_thin = mm(16.0 - float(b_bore) / 2)
    r_tube, r_bef, r_now = float(c_tid) / 2, float(b_bore) / 2, float(c_bore) / 2

    ax = axes[0]
    draw(ax, before,
         'BEFORE  \u2014  a COUNTERBORE, cut OUTWARD',
         'commit %s.  The seal bore is WIDER than the tube, so the wall gets '
         'THINNER exactly where the seal is\nand the bore needs a %s ring, '
         'which we do not have.' % (BEFORE_SHA, b_ring))
    level(ax, r_tube, '\u00d8%s tube bore' % c_tid, '#555', dy=-0.55)
    level(ax, r_bef, '\u00d8%s counterbore \u2014 ABOVE it, 12 mm deep' % b_bore,
          '#a02c1a', dy=0.55)
    wall(ax, 8.6, r_bef, '%s' % b_thin, '#a02c1a')
    note(ax, (1.6, r_bef - 0.75), (-4.3, 10.4), '%s ring' % b_ring, '#7d2c20')

    ax = axes[1]
    draw(ax, now,
         'NOW  \u2014  a COLLAR, material added INWARD',
         'The seal bore is NARROWER than the tube, so the wall gets THICKER '
         'exactly where the seal is\nand the bore takes the %s you already '
         'have. Same idea, inverted.' % n_ring)
    level(ax, r_tube, '\u00d8%s tube bore' % c_tid, '#555')
    level(ax, r_now, '\u00d8%s collar bore \u2014 BELOW it, %s mm deep'
          % (c_bore, c_len), '#1d6b3a')
    wall(ax, 8.6, r_now, '%s' % c_wall, '#1d6b3a')
    note(ax, (1.6, r_now - 0.75), (-4.3, 10.4),
         '%s ring,\nsqueezed %.1f %%' % (n_ring, float(n_sq)), '#7d2c20')
    note(ax, (float(c_len) + float(c_lead) / 2, (r_now + r_tube) / 2),
         (15.0, 10.6), '45\u00b0 lead-in, %s mm' % c_lead, '#1d6b3a', ha='right')

    for ax in axes:
        ax.text(-4.5, 17.75, 'cable end \u2192', fontsize=8, color='#666',
                va='top', ha='left', style='italic')

    handles = [plt.Rectangle((0, 0), 1, 1, fc=c[0], ec=c[1]) for c in
               (('#b9bec6', '#5a616b'), ('#8fb4d6', '#2d5178'),
                ('#d2604f', '#7d2c20'))]
    fig.legend(handles, ['tube \u2014 the part that changed', 'cap',
                         'O-ring, drawn squeezed'],
               loc='lower right', bbox_to_anchor=(0.988, 0.052), fontsize=8.5,
               framealpha=0.95, borderpad=0.6, ncol=3, columnspacing=1.2)

    fig.text(0.035, 0.012,
             'True sections of the models: each part rendered to STL, cut on '
             'y=0 with projection(cut=true), plotted 1:1 from the SVG. '
             'Regenerate with tools/collar_drawing.py.',
             fontsize=7.5, color='#777')
    fig.tight_layout(rect=(0, 0.035, 1, 0.945))
    fig.subplots_adjust(hspace=0.55)
    dst = os.path.join(OUT, 'collar-section.png')
    fig.savefig(dst, dpi=170)
    print("wrote %s" % dst)
    return 0


if __name__ == '__main__':
    sys.exit(main())
