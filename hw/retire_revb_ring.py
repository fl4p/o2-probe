"""Retire only the optional Rev C ring branch from the pinned BOM39 source.

Recovery reference and electrical/mechanical caveats: plans/REVC-HEATED-RING.md.
This module is used by the Rev B migration before field synchronization/refill.
"""
from pathlib import Path
import importlib.util

# Exact IDs belong to the hash-pinned input in adopt_revb_interfaces.py.
# Remove the F3-only +12V_SW spur back to RH1.1, all +12V_HTR copper,
# and the Q2.3-to-J5.2 extension. Main-board heater copper is retained.
RETIRED_COPPER = {
    'fdc7373d-b9a7-48f6-aaf3-fd0f9f7a7739': '/+12V_SW',
    '5c46665f-a8b9-40b8-a883-e838903bec2f': '/+12V_SW',
    'f43c8c43-79dd-4c3b-8f9c-c894035c4404': '/+12V_SW',
    '6f509ee4-4dc0-4f2e-a1f3-a0d8e5def115': '/+12V_SW',
    '3c91a1a2-d85c-4953-ab7d-96fb10991644': '/+12V_HTR',
    '5a64111e-a627-4e8f-b994-fae494dbb535': '/+12V_HTR',
    'd94587e6-a0a5-4d06-9baa-dd5293d93f7f': '/+12V_HTR',
    '01e2342d-6690-4d4e-b236-c8ec888864c2': '/+12V_HTR',
    '8ad2b9b6-7995-45a9-8357-32f132e44d1c': '/+12V_HTR',
    '2bb3a2da-1309-4d1a-93f4-dbb5fec60a88': '/+12V_HTR',
    '76070c8b-6fc7-4adb-a516-0ff061d12118': '/+12V_HTR',
    'd730b024-7a1c-4875-adf9-69457c758cb0': '/HEATER_LOW',
    '13f5ea87-46aa-4b7d-9c58-b297851c1a97': '/HEATER_LOW',
    '139914d6-6488-4712-9e65-d7ce6e1abc19': '/HEATER_LOW',
    '3111a863-a449-46f3-9f37-d1dc01c560c4': '/HEATER_LOW',
    '61aaa953-2106-49b2-aa15-7cdb3d9fc5b7': '/HEATER_LOW',
}


def retire(board):
    fps = {f.GetReference(): f for f in board.GetFootprints()}
    if not {'J5', 'F3', 'RH1', 'RH2', 'Q2'} <= fps.keys():
        raise ValueError('Ring retirement input is incomplete')
    selected = [t for t in board.GetTracks() if t.m_Uuid.AsString() in RETIRED_COPPER]
    if len(selected) != len(RETIRED_COPPER):
        raise ValueError('Ring retirement copper differs from pinned source')
    for item in selected:
        if item.GetNetname() != RETIRED_COPPER[item.m_Uuid.AsString()]:
            raise ValueError('Ring retirement item has an unexpected net')
    for item in selected:
        board.Remove(item)
    for ref in ('J5', 'F3'):
        board.Remove(fps[ref])
    if any(t.GetNetname() == '/+12V_HTR' for t in board.GetTracks()):
        raise ValueError('Retired heater supply still has copper')
    # Keep detached SWIG proxies alive through the caller's refill/save.
    return selected + [fps['J5'], fps['F3']]


def retained_critical():
    """Use the reviewed two-layer critical geometry, minus 12 retired items."""
    path = Path(__file__).resolve().parent/'routing/2layer-bom39/critical_routes.py'
    spec = importlib.util.spec_from_file_location('bom39_critical_routes', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    prefix = len(module.DENSE_ESCAPE_TRACKS) + len(module.ROW_LOCAL_TRACKS) + len(module.CORRIDOR_SPINE_TRACKS)
    tracks = module.CRITICAL_TRACKS[prefix:]
    vias = module.CRITICAL_VIAS[len(module.DENSE_ESCAPE_VIAS)+len(module.CORRIDOR_SPINE_VIAS):]
    # Tuples are local coordinates of exactly the Q2-to-J5 extension.
    low_branch = {
        ((10.0, 102.19), (10.0, 102.60), (17.80, 102.60)),
        ((17.80, 102.60), (17.80, 105.50)),
        ((17.80, 104.60), (17.80, 105.50)),
    }
    kept_tracks = [t for t in tracks if t[0] != '/+12V_HTR'
                   and not (t[0] == '/HEATER_LOW' and t[3] in low_branch)]
    kept_vias = [v for v in vias if v[0] != '/+12V_HTR'
                 and not (v[0] == '/HEATER_LOW' and v[1:3] == (17.80, 104.60))]
    count = lambda ts, vs: sum(len(t[3])-1 for t in ts) + len(vs)
    if count(tracks, vias) != 63 or count(kept_tracks, kept_vias) != 51:
        raise ValueError('Reviewed critical inventory changed; re-evaluate retirement')
    return kept_tracks, kept_vias
