#!/usr/bin/env python3
"""run() is reachable, on every transport shape, before it touches hardware.

THE GAP THIS EXISTS FOR. Every other suite here drives o2p_update's functions
directly - negotiate_baud, resync, push - and the BLE runner imports the Bus
helpers. Nothing called run(). So a NameError on its first working statement
survived a green board: `find_probe(line, bus)` was written above the line that
assigns `line`, and both --port and --swd raised UnboundLocalError immediately.
Found by review, 2026-09-08.

It is deliberately a SMOKE test and not a behaviour test. It asserts that run()
gets far enough to make a decision on a link that answers nothing, which is the
one property the missing coverage would have caught, and it does not pin what
that decision is - that belongs in test_baud.py, where the fakes are real
enough to mean something.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import o2p_update as u


class SilentLink:
    """Answers nothing, the way an unplugged lead does."""

    baud = 9600

    def exchange(self, adu, expect_len):
        del adu, expect_len
        return b""

    def set_baud(self, baud):
        self.baud = baud

    def close(self):
        pass


class SilentSwdLink(SilentLink):
    """No set_baud, the way SwdLink has none - the other transport shape."""

    set_baud = None


def args_for(**over):
    a = dict(bridge=False, addr=3, baud=9600, status=True, abort=False,
             stay=False, no_speedup=False, image=None, boot=False)
    a.update(over)
    return argparse.Namespace(**a)


FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print("  ok   %s" % name)
    else:
        FAILURES.append(name)
        print("  FAIL %s %s" % (name, detail))


# What may come out of run() against a link that answers nothing, and what may
# not. An IOError is a RESULT here - a silent lead is the ordinary field
# condition, and this tool lets it out to the caller rather than dressing it up
# (that predates this file and is not what it is testing). A name or type error
# is never a result: it means run() cannot be executed at all, which is exactly
# the state that shipped and the only thing asserted below.
ALLOWED = (IOError, OSError, SystemExit)
STRUCTURAL = (NameError, UnboundLocalError, AttributeError, TypeError)


def is_executable(link, args, name):
    try:
        rc = u.run(args, link)
    except STRUCTURAL as e:
        check(name, False, "%s: %s" % (type(e).__name__, e))
        return
    except ALLOWED:
        check(name, True)              # reached the wire and reported
        return
    except Exception as e:
        check(name, False, "unexpected %s: %s" % (type(e).__name__, e))
        return
    check(name, isinstance(rc, int), "returned %r" % (rc,))


def main():
    print("run() smoke")
    is_executable(SilentLink(), args_for(), "--port --status is executable")
    is_executable(SilentSwdLink(), args_for(), "--swd --status is executable")
    is_executable(SilentLink(), args_for(no_speedup=True),
                      "--no-speedup is executable")
    is_executable(SilentLink(), args_for(status=False, abort=True),
                      "--abort is executable")
    is_executable(SilentLink(), args_for(status=False, stay=True),
                      "--stay is executable")

    print("all passed" if not FAILURES else "%d FAILED" % len(FAILURES))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
