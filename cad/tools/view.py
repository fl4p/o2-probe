#!/usr/bin/env python3
"""Look at any part of any model in the three.js viewer, in one command.

    tools/view.py o2_probe_head_end.scad:carrier
    tools/view.py exports/asa-*.stl
    tools/view.py --scene bed
    tools/view.py --list

WHAT THIS REPLACES. The viewer worked, but reaching it did not: each scene
needed its own Makefile target, its own generator script writing its own
parts.json, and a server pinned to port 8777 rooted at exactly the right
directory. Adding a part to a picture meant editing three files, and getting the
port or the root wrong produced a page that loaded perfectly and showed nothing.

The rules that survive from those generators, because they were the right rules:

  - NO DIMENSION IS WRITTEN HERE. Parts come out of the model at their assembly
    coordinate and are loaded with an identity matrix. A viewer that does its own
    arithmetic can place a part by a stale copy of a constant and still look
    entirely plausible -- that already happened once, 11 mm out.
  - A STALE MESH LOOKS EXACTLY LIKE A CURRENT ONE. So every mesh older than the
    SCAD it came from is rebuilt before serving, and anything that cannot be
    rebuilt (a KiCad export, a hand-made STL) is reported on screen instead of
    being drawn silently.
  - The -D flags come from the MAKEFILE, via `make print-<VAR>`, not from a copy
    kept here. `HEAD_END_PROV` supplies measured-input placeholders the model
    refuses to default; a scene rendered without them does not build at all, and
    one rendered with the wrong ones builds the wrong part.

SPEC forms:
    path/to/mesh.stl              an existing mesh, loaded as-is
    model.scad:part               render `-D part="part"` from that model
    model.scad:part=Label         ... with a name for the panel
Anything ending .scad without a part renders its default top-level object.
"""
import argparse
import concurrent.futures as futures
import glob
import hashlib
import http.server
import json
import os
import re
import shlex
import struct
import socket
import socketserver
import subprocess
import sys
import time
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
CAD = os.path.dirname(HERE)
OUT = os.path.join(CAD, 'exports')
VIEWER = os.path.join(CAD, 'viewer')
SCENES = os.path.join(HERE, 'scenes.json')

# Per-model default flags, named as MAKEFILE VARIABLES rather than spelled out.
# A model not listed here renders with no flags, which is right for the ones that
# have no measured inputs to refuse.
FLAG_VAR = {
    'o2_probe_head_end.scad': 'ASA',
    'o2_probe_head.scad': 'HEAD_PROV',
}

# Enough distinct hues that a five-part scene never repeats one. Deliberately
# not the OpenSCAD palette: this is a viewer, not a render.
PALETTE = ['#d6c36a', '#8fa9c9', '#c62828', '#a0522d', '#4f9d69',
           '#b07fc7', '#e08b3a', '#5aa9b8', '#c9c9c9', '#7a8b99']

_flag_cache = {}


def make_var(name):
    """Read a variable out of the Makefile, so the flags have ONE definition."""
    if name in _flag_cache:
        return _flag_cache[name]
    try:
        out = subprocess.run(['make', '-s', 'print-' + name], cwd=CAD,
                             capture_output=True, text=True, timeout=30)
        val = out.stdout.strip() if out.returncode == 0 else ''
    except Exception:
        val = ''
    if not val:
        # HARD, not a warning. A model listed in FLAG_VAR is one that refuses to
        # default its measured inputs; rendering it without them either fails an
        # assert or -- worse -- builds a different part. Continuing with no flags
        # once produced five silent render failures that the page reported as a
        # successful rebuild, which is the exact shape of bug this file's
        # docstring is about.
        raise SystemExit(
            "view: cannot read Makefile variable %s (tried `make -s print-%s`).\n"
            "The print-%% rule is what exports it -- check it still exists in "
            "cad/Makefile." % (name, name))
    _flag_cache[name] = shlex.split(val)
    return _flag_cache[name]


def parse_spec(spec, flags=()):
    """SPEC -> dict(kind, ...). Meshes pass through; .scad specs get rendered."""
    label = None
    if spec.endswith('.stl') or spec.endswith('.off') or spec.endswith('.3mf'):
        path = spec if os.path.isabs(spec) else os.path.join(os.getcwd(), spec)
        return dict(mesh=os.path.relpath(path, CAD),
                    name=os.path.splitext(os.path.basename(spec))[0],
                    scad=None, part=None)
    body = spec
    if '=' in spec:
        body, label = spec.split('=', 1)
    scad, part = (body.split(':', 1) + [None])[:2] if ':' in body else (body, None)
    if not scad.endswith('.scad'):
        scad += '.scad'
    if not os.path.exists(os.path.join(CAD, scad)):
        sys.exit("view: no such model: %s" % scad)
    stem = os.path.splitext(os.path.basename(scad))[0]
    tag = re.sub(r'[^a-z0-9]+', '-', (part or 'default').lower())
    # A scene's extra -D flags go into the CACHE NAME. Without that, two scenes
    # of the same part under different parameters share one file and the second
    # one silently shows the first one's geometry -- the whole point of the
    # substitution being invisible.
    if flags:
        tag += '-' + hashlib.sha1(' '.join(flags).encode()).hexdigest()[:6]
    return dict(mesh=os.path.join('exports', 'view-%s-%s.stl' % (stem[:18], tag)),
                name=label or part or stem, scad=scad, part=part, flags=list(flags))


def newest_source(scad):
    """The SCAD plus anything it includes -- an included file changing is
    exactly the case where a mesh goes stale without its own model moving."""
    path = os.path.join(CAD, scad)
    files = [path]
    try:
        src = open(path).read()
        for inc in re.findall(r'(?:include|use)\s*<([^>]+)>', src):
            p = os.path.join(CAD, inc)
            if os.path.exists(p):
                files.append(p)
    except OSError:
        pass
    return max(os.path.getmtime(f) for f in files)


def render(item, force=False):
    """Build one mesh if it is missing or older than its model. Returns a note."""
    if not item['scad']:
        return rebuild_mesh(item, force)
    dst = os.path.join(CAD, item['mesh'])
    src_t = newest_source(item['scad'])
    if not force and os.path.exists(dst) and os.path.getmtime(dst) >= src_t:
        return None
    cmd = [os.environ.get('OPENSCAD', 'openscad'), '--hardwarnings']
    try:
        cmd += make_var(FLAG_VAR[item['scad']]) if item['scad'] in FLAG_VAR else []
    except SystemExit as e:
        return str(e)
    cmd += item.get('flags') or []
    if item['part']:
        cmd += ['-D', 'part="%s"' % item['part']]
    cmd += ['-o', dst, item['scad']]
    t0 = time.time()
    r = subprocess.run(cmd, cwd=CAD, capture_output=True, text=True)
    if r.returncode != 0:
        print("  FAILED %s" % item['mesh'])
    if r.returncode != 0 or not os.path.exists(dst):
        # OpenSCAD says why on stdout as often as on stderr -- an empty top
        # level object and a failed assert come out on different streams -- so
        # read both and keep the lines that carry the reason.
        blob = ((r.stderr or '') + '\n' + (r.stdout or '')).splitlines()
        why = [l.strip() for l in blob
               if re.search(r'ERROR|WARNING|Assert|empty|No such', l, re.I)]
        return 'FAILED to render:\n' + '\n'.join((why or blob)[-6:])
    print("  built %-34s %5.1fs" % (item['mesh'], time.time() - t0))
    return None


def rebuild_mesh(item, force=False):
    """A mesh this file does not render, but that a scene can teach it to rebuild.

    Without this, an unmanaged mesh was simply reported present-or-missing -- and
    "present" is not "current". The head-end scene's PCB tip is produced by
    tools/board_tip.py, which places it at the model's own board_tip_z; when that
    datum moved 18.7 -> 16.0 on 2026-09-05 the tracked mesh stayed at 18.7 and
    `make view SCENE=head-end` would have served the old placement indefinitely,
    looking perfectly plausible. (Found by the 2026-09-05 Codex review, and it is
    the SAME failure -- a stale board placement in this viewer -- that
    board_tip.py's own docstring is about.)

    A scene part may therefore carry:
        "rebuild": ["python3", "tools/board_tip.py", "<src>", "<dst>"]
        "deps":    ["o2_probe_head_end.scad", "exports/o2-probe-board-bin.stl"]
    Missing deps are a hard failure, never a silent skip: a dep that cannot be
    stat-ed is exactly the case where "it looked current" is worthless.
    """
    dst = os.path.join(CAD, item['mesh'])
    cmd = item.get('rebuild')
    if not cmd:
        return None if os.path.exists(dst) else 'missing (not built from a model here)'
    deps = item.get('deps') or []
    try:
        dep_t = max(os.path.getmtime(os.path.join(CAD, d)) for d in deps) if deps else 0
    except OSError as e:
        return 'cannot stat a rebuild dependency: %s' % e
    if not force and os.path.exists(dst) and os.path.getmtime(dst) >= dep_t:
        return None
    t0 = time.time()
    r = subprocess.run(cmd, cwd=CAD, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(dst):
        return 'FAILED to rebuild:\n' + ((r.stderr or r.stdout).strip()[-600:])
    print("  rebuilt %-33s %5.1fs" % (item['mesh'], time.time() - t0))
    return None


def mesh_top_z(path):
    """Highest Z in an STL, or None if it cannot be read.

    None is NOT a height. It sorts to the BOTTOM of the panel and is reported,
    because a mesh we failed to measure must never be silently presented as the
    topmost part of the assembly.
    """
    try:
        with open(path, 'rb') as f:
            if f.read(5) == b'solid':
                f.seek(0)
                top = None
                for line in f:
                    if line.lstrip()[:6] == b'vertex':
                        z = float(line.split()[3])
                        top = z if top is None else max(top, z)
                return top
            f.seek(80)
            n = struct.unpack('<I', f.read(4))[0]
            top = None
            for _ in range(n):
                d = struct.unpack('<12fH', f.read(50))
                z = max(d[5], d[8], d[11])
                top = z if top is None else max(top, z)
            return top
    except Exception:
        return None


def build_scene(items, force=False):
    ident = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    with futures.ThreadPoolExecutor(max_workers=4) as ex:
        notes = list(ex.map(lambda it: render(it, force), items))

    # ORDER THE PANEL THE WAY THE PICTURE READS. Parts load at their assembly
    # coordinate with an identity matrix, so Z is the real stacking order: sort
    # by the top of each part, highest first, and the list beside the model
    # matches the model. Anything unmeasurable keeps scene order at the end
    # rather than being placed by a guess.
    ranked = [(mesh_top_z(it['mesh']) if it.get('mesh') else None, i, it, note)
              for i, (it, note) in enumerate(zip(items, notes))]
    known = sorted((r for r in ranked if r[0] is not None), key=lambda r: (-r[0], r[1]))
    unknown = [r for r in ranked if r[0] is None]
    for _, _, it, _ in unknown:
        print("  ! %s: could not measure its height, listed last" % it['name'])
    pairs = [(it, note) for _, _, it, note in list(known) + unknown]

    parts = []
    for i, (it, note) in enumerate(pairs):
        parts.append(dict(name=it['name'], kind='stl',
                          file='../' + it['mesh'].replace(os.sep, '/'),
                          matrix=ident,
                          color=it.get('color') or PALETTE[i % len(PALETTE)],
                          note=it.get('note'), stale=note))
    meta = dict(generated=time.strftime('%Y-%m-%d %H:%M'),
                title=os.path.basename(CAD.rstrip('/')) or 'model',
                subtitle=' · '.join(p['name'] for p in parts)[:120],
                facts='')
    return {'meta': meta, 'parts': parts}


def _sources_sig(items):
    """Fingerprint of what every part is BUILT FROM, for auto-rebuild.

    _scene_sig below watches scenes.json -- the part LIST. This watches the
    part CONTENTS: the .scad (and anything it includes) for rendered parts, and
    the declared deps for meshes produced by an external command. Those are two
    different staleness questions and only the first one was ever asked, so a
    server went on serving a model that had been edited under it. That is not
    theoretical: on 2026-09-06 a cap was fixed in the .scad and the running
    viewer kept showing the broken one, because render() only re-checks mtimes
    at startup.

    Returns (signature, problems). A file that cannot be stat-ed contributes
    None to the signature and a line to `problems` -- it is NEVER quietly
    treated as unchanged, because "I could not look" and "it is current" are
    the two things a staleness check must not confuse.
    """
    sig, problems = [], []
    for it in items:
        try:
            if it.get('scad'):
                sig.append((it['mesh'], newest_source(it['scad'])))
            else:
                deps = it.get('deps') or []
                sig.append((it['mesh'],
                            max((os.path.getmtime(os.path.join(CAD, d))
                                 for d in deps), default=0.0)))
        except OSError as e:
            problems.append('%s: %s' % (it.get('name', '?'), e))
            sig.append((it['mesh'], None))
    return tuple(sig), problems


def _scene_sig(name):
    """A cheap fingerprint of one scene's part list, or None if unreadable.

    Unreadable is NOT "unchanged": it returns None and the caller keeps what it
    has rather than rebuilding from a half-written file.
    """
    if not name:
        return None
    try:
        sc = load_scenes().get(name)
        if not sc:
            return ('missing',)
        return (tuple((p.get('spec'), p.get('color'), tuple(p.get('flags') or ()))
                      for p in sc['parts']), tuple(sc.get('flags') or ()))
    except Exception:
        return None


def load_scenes():
    if not os.path.exists(SCENES):
        return {}
    return json.load(open(SCENES))


def serve(scene, items, port, open_browser, scene_name=None):
    """Serve cad/ with the scene at /scene.json and a /rebuild that re-renders.

    Rooted at cad/ and NOT at cad/viewer: http.server will not serve above its
    own root, so a server started in the viewer directory answers the page and
    404s every mesh -- which looks like a broken model, not a broken path.
    """
    # 'src' is the signature LAST ATTEMPTED, not last succeeded. That is
    # deliberate and it is what stops a render storm: a failing render leaves
    # the mesh older than its source, so a "did it succeed" test would report
    # stale forever and the page would re-render every poll. Recording the
    # attempt means one rebuild per source change, and a failure shows up in
    # the page's existing "N of M parts did NOT rebuild" banner instead.
    state = {'scene': scene, 'items': items, 'sig': _scene_sig(scene_name),
             'src': _sources_sig(items)[0]}

    def refresh():
        """Re-read scenes.json; rebuild if this scene's part list has changed.

        A SERVER OUTLIVES THE FILE IT WAS STARTED FROM. items was parsed once at
        startup, so every later edit to scenes.json -- a part added, removed or
        recoloured, by this session or another one sharing the tree -- was
        invisible until someone restarted. That is not a cosmetic staleness: a
        part REMOVED because it was proved to be in the wrong place went on being
        served, and looked exactly like a correct scene. It happened three times
        in one afternoon before it was worth fixing.

        Cheap: a signature of the scene's specs, compared per request.
        """
        if not scene_name:
            return
        sig = _scene_sig(scene_name)
        if sig is None or sig == state['sig']:
            return
        scenes = load_scenes()
        sc = scenes.get(scene_name)
        if not sc:
            print("  ! scene %r has disappeared from scenes.json, keeping the "
                  "last good one" % scene_name)
            state['sig'] = sig
            return
        sflags = sc.get('flags', [])
        fresh_items = [parse_spec(p['spec'], p.get('flags', sflags)) for p in sc['parts']]
        for it, p in zip(fresh_items, sc['parts']):
            it['color'] = p.get('color'); it['note'] = p.get('note')
            it['rebuild'] = p.get('rebuild'); it['deps'] = p.get('deps')
        print("scenes.json changed: %r now has %d part(s), rebuilding"
              % (scene_name, len(fresh_items)))
        state['items'] = fresh_items
        state['scene'] = build_scene(fresh_items)
        state['sig'] = sig
        state['src'] = _sources_sig(fresh_items)[0]

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=CAD, **kw)

        def _json(self, obj):
            body = json.dumps(obj).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.split('?')[0] in ('/scene.json', '/viewer/scene.json'):
                refresh()
                return self._json(state['scene'])
            if self.path.split('?')[0] in ('/stale', '/viewer/stale'):
                # STAT ONLY -- no render, no CGAL. This is polled, so it has to
                # stay cheap enough that polling is not itself the cost.
                refresh()
                sig, problems = _sources_sig(state['items'])
                return self._json({'stale': sig != state['src'],
                                   'problems': problems})
            if self.path.split('?')[0] in ('/rebuild', '/viewer/rebuild'):
                auto = 'auto=1' in (self.path.split('?') + [''])[1]
                print("rebuild requested from the page"
                      + (" (auto: a source changed)" if auto else ""))
                refresh()
                # An auto rebuild is NOT forced: render() already skips whatever
                # is current, so only the part whose model actually moved is
                # re-rendered. Forcing here would re-render a nine-part scene
                # every time one file was touched. The manual button still
                # forces, because that is what a human presses it for.
                fresh = build_scene(state['items'], force=not auto)
                state['src'] = _sources_sig(state['items'])[0]
                # Carry the scene's identity across. A rebuild that renamed the
                # scene back to its default is how the page came back titled
                # "cad" after showing "bed" a minute earlier.
                fresh['meta'].update(title=state['scene']['meta'].get('title'),
                                     subtitle=state['scene']['meta'].get('subtitle'))
                state['scene'] = fresh
                return self._json(state['scene'])
            return super().do_GET()

        def log_message(self, format, *args):
            pass                     # the render log is the interesting one

    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True

    # A FREE PORT, not a fixed one. 8777 in use by another session's viewer used
    # to fail with an OSError that reads like a bug in this script.
    if port == 0:
        s = socket.socket()
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]
        s.close()
    url = 'http://127.0.0.1:%d/viewer/' % port
    with Server(('127.0.0.1', port), Handler) as httpd:
        print("\n  %s\n  ctrl-c to stop\n" % url)
        if open_browser:
            webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print()


def main():
    ap = argparse.ArgumentParser(
        description='Open parts of the SCAD models in the local three.js viewer.',
        epilog='SPEC: mesh.stl | model.scad:part | model.scad:part=Label')
    ap.add_argument('specs', nargs='*', metavar='SPEC')
    ap.add_argument('--scene', help='a named scene from tools/scenes.json')
    ap.add_argument('--list', action='store_true', help='list named scenes and exit')
    ap.add_argument('--port', type=int, default=0, help='default: a free one')
    ap.add_argument('--no-open', action='store_true')
    ap.add_argument('--rebuild', action='store_true', help='re-render even if current')
    ap.add_argument('--print', dest='dump', action='store_true',
                    help='write viewer/scene.json and exit, without serving')
    args = ap.parse_args()

    scenes = load_scenes()
    if args.list or (not args.specs and not args.scene):
        print("named scenes (tools/view.py --scene NAME):")
        for name, sc in sorted(scenes.items()):
            print("  %-12s %s" % (name, sc.get('note', '')))
        print("\nor pass parts directly:")
        print("  tools/view.py o2_probe_head_end.scad:carrier")
        print("  tools/view.py exports/asa-carrier-print.stl")
        return 0 if args.list else 1

    items = []
    if args.scene:
        if args.scene not in scenes:
            sys.exit("view: no scene %r; --list to see them" % args.scene)
        sflags = scenes[args.scene].get('flags', [])
        for p in scenes[args.scene]['parts']:
            it = parse_spec(p['spec'], p.get('flags', sflags))
            it['color'] = p.get('color')
            it['note'] = p.get('note')
            it['rebuild'] = p.get('rebuild')
            it['deps'] = p.get('deps')
            if p.get('name'):
                it['name'] = p['name']
            items.append(it)
    for spec in args.specs:
        hits = sorted(glob.glob(spec)) if any(c in spec for c in '*?[') else [spec]
        for h in hits:
            items.append(parse_spec(h))
    if not items:
        sys.exit("view: nothing to show")

    print("view: %d part%s" % (len(items), '' if len(items) == 1 else 's'))
    scene = build_scene(items, force=args.rebuild)
    if args.scene:
        scene['meta'].update(title=args.scene,
                             subtitle=scenes[args.scene].get('note', ''))
    bad = [p for p in scene['parts'] if p['stale']]
    for p in bad:
        # The whole reason, not its first line: the first line is always
        # "FAILED to render:" and the useful part is what follows it.
        print("  ! %s: %s" % (p['name'],
                              '\n      '.join(p['stale'].splitlines())))
    if args.dump:
        json.dump(scene, open(os.path.join(VIEWER, 'scene.json'), 'w'), indent=1)
        print("wrote viewer/scene.json")
        return 1 if bad else 0
    # Refuse to serve a scene where NOTHING rendered: that page is a black
    # window with a warning nobody reads, and the shell is where the error
    # actually belongs.
    if bad and len(bad) == len(scene['parts']):
        sys.exit("view: nothing rendered -- see the errors above")
    serve(scene, items, args.port, not args.no_open, scene_name=args.scene)
    return 0


if __name__ == '__main__':
    sys.exit(main())
