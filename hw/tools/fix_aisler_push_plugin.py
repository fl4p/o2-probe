#!/usr/bin/env python3
"""Patch the installed "AISLER Push for KiCad" plugin so its uploads prepare.

Why
---
Plugin 0.3.2 added an ODB++ export (`odb.zip`) to the archive it uploads.
AISLER's CAM cannot ingest it: every upload containing `odb.zip` comes back
"Failed to prepare production data", with Dimension / Layer Count / Minimal
Drill Diameter all reported as "Not present" -- i.e. nothing was extracted at
all, which is an ingestion failure rather than a design-rule rejection.

Measured 2026-09-16 against project HAYAMAZV, one variable at a time:

    .kicad-push   odb.zip    result
    absent        present    FAIL   (revisions 1-4, the plugin's own output)
    present       present    FAIL   (revision 6)
    present       absent     READY  (revisions 5, 7)
    absent        absent     READY  (revision 8)

So `odb.zip` is necessary and sufficient for the failure, and the marker file
makes no difference either way.

This script comments out the ODB++ export. It also fixes a second, unrelated
bug in the same function: `open(magicFilename, 'a')` uses a bare relative name,
so the `.kicad-push` marker lands in the process's working directory instead of
the temp directory that gets zipped, and therefore never reaches AISLER. That
one is harmless -- see the table -- but it litters whatever directory pcbnew
happens to be sitting in, so it goes too.

Both edits are reversible: the original is kept as push_thread.py.aisler-orig,
and --revert puts it back.

Note on macOS permissions
-------------------------
The plugin lives under ~/Documents, which is TCC-protected. A shell that has
not been granted access to Documents or Full Disk Access sees the directory as
"Operation not permitted" / non-existent. If this script cannot find the
plugin, run it from Terminal.app and grant the prompt, or grant the calling
application access in System Settings > Privacy & Security > Files and Folders.
"""

import argparse
import glob
import os
import py_compile
import shutil
import sys
import tempfile

# The Plugin and Content Manager installs under the identifier with dots
# replaced by underscores; keep the dotted spelling as a fallback in case a
# future PCM changes its mind.
PKGS = ('com_github_aislerhq_PushForKiCad', 'com.github.aislerhq.PushForKiCad')
BACKUP_SUFFIX = '.aisler-orig'

ODB_CALL = "        self.exportODB(board, os.path.join(temp_dir, odbFilename), 'zip')"
ODB_REPLACEMENT = (
    "        # PATCHED: AISLER's CAM cannot ingest KiCad's ODB++ archive; any\n"
    "        # upload containing odb.zip fails with \"Failed to prepare\n"
    "        # production data\". Measured 2026-09-16. Re-enable once AISLER\n"
    "        # confirms their importer handles it.\n"
    "        # self.exportODB(board, os.path.join(temp_dir, odbFilename), 'zip')"
)

MAGIC_CALL = "        open(magicFilename, 'a').close()"
MAGIC_REPLACEMENT = (
    "        # PATCHED: was open(magicFilename, 'a'), a bare relative name, so the\n"
    "        # marker was written to the process CWD and never reached the zip.\n"
    "        open(os.path.join(temp_dir, magicFilename), 'a').close()"
)


def candidate_roots():
    """Every place KiCad's Plugin and Content Manager might have installed it."""
    home = os.path.expanduser('~')
    pats = []
    for pkg in PKGS:
        pats += [
            os.path.join(home, 'Documents', 'KiCad', '*', '3rdparty', 'plugins', pkg),
            os.path.join(home, 'Library', 'Preferences', 'kicad', '*', '3rdparty',
                         'plugins', pkg),
            os.path.join(home, '.local', 'share', 'kicad', '*', '3rdparty',
                         'plugins', pkg),
            os.path.join(home, 'KiCad', '*', '3rdparty', 'plugins', pkg),
        ]
        for var in ('KICAD10_3RD_PARTY', 'KICAD9_3RD_PARTY', 'KICAD_3RD_PARTY'):
            if os.environ.get(var):
                pats.append(os.path.join(os.environ[var], 'plugins', pkg))
    out = []
    for p in pats:
        out.extend(sorted(glob.glob(p)))
    return out


def find_targets(explicit):
    """Every installed copy -- a machine may carry one per KiCad major."""
    roots = [explicit] if explicit else candidate_roots()
    out = []
    for root in roots:
        # The PCM flattens the package: the modules sit directly in the
        # package directory, not in the plugins/ subdirectory the source zip
        # uses. Accept both.
        for rel in (('push_thread.py',), ('plugins', 'push_thread.py')):
            f = os.path.join(root, *rel)
            if os.path.isfile(f) and f not in out:
                out.append(f)
    return out


def atomic_write(path, text):
    """Never leave a half-written plugin behind if we die mid-write."""
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=d)
    try:
        with os.fdopen(fd, 'w') as fh:
            fh.write(text)
        shutil.copystat(path, tmp)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def compiles(target):
    """A plugin that does not compile silently vanishes from the toolbar, so
    never leave one behind unchecked. py_compile refuses /dev/null as a cfile,
    hence the temp file."""
    fd, cfile = tempfile.mkstemp(suffix='.pyc')
    os.close(fd)
    try:
        py_compile.compile(target, doraise=True, cfile=cfile)
        return None
    except py_compile.PyCompileError as exc:
        return str(exc)
    finally:
        if os.path.exists(cfile):
            os.unlink(cfile)


def revert(target):
    backup = target + BACKUP_SUFFIX
    if not os.path.isfile(backup):
        print('No backup at %s -- nothing to revert.' % backup)
        return 1
    shutil.copy2(backup, target)
    print('Reverted %s from %s' % (target, backup))
    return 0


def patch(target):
    src = open(target).read()

    if ODB_CALL not in src and 'PATCHED' in src:
        err = compiles(target)
        if err:
            print('Already patched but DOES NOT COMPILE: %s\n%s' % (target, err))
            return 3
        print('Already patched (and compiles): %s' % target)
        return 0

    if ODB_CALL not in src:
        print('ERROR: could not find the exportODB call in %s.' % target)
        print('       The plugin version is probably not 0.3.2. Not touching it.')
        return 2

    new = src.replace(ODB_CALL, ODB_REPLACEMENT, 1)

    if MAGIC_CALL in new:
        new = new.replace(MAGIC_CALL, MAGIC_REPLACEMENT, 1)
    else:
        print('NOTE: marker-file line not found; skipping that fix (harmless).')

    backup = target + BACKUP_SUFFIX
    if not os.path.exists(backup):
        shutil.copy2(target, backup)
        print('Backed up  %s' % backup)

    atomic_write(target, new)

    err = compiles(target)
    if err:
        shutil.copy2(backup, target)
        print('ERROR: patched file does not compile; rolled back.\n%s' % err)
        return 3

    print('Patched    %s' % target)
    print('Restart KiCad for the change to take effect.')
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--plugin-dir', help='path to the PushForKiCad directory')
    ap.add_argument('--revert', action='store_true',
                    help='restore the original push_thread.py')
    args = ap.parse_args()

    targets = find_targets(args.plugin_dir)
    if not targets:
        print('Could not locate push_thread.py. Looked in:')
        for r in candidate_roots() or ['(no candidate roots matched)']:
            print('  %s' % r)
        print('\nIf the path exists but reads as "Operation not permitted", this')
        print('process lacks macOS permission for ~/Documents. Run from Terminal')
        print('and accept the prompt, or pass --plugin-dir explicitly.')
        return 1

    rc = 0
    for target in targets:
        rc = max(rc, revert(target) if args.revert else patch(target))
    return rc


if __name__ == '__main__':
    sys.exit(main())
