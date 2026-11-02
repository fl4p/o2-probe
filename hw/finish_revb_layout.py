#!/usr/bin/env python3
"""Apply reviewed Rev B legend changes and the R17 assembly-clearance correction."""
from pathlib import Path
import sys
import wx
_APP = wx.AppConsole()
import pcbnew


def finish(path):
    board = pcbnew.LoadBoard(str(path))
    fps = {f.GetReference(): f for f in board.GetFootprints()}
    # Move R17 above U4, clearing its body, lands and courtyard.
    # Join the nearby MENB trunk and give ground an external stitch.
    resistor = fps['R17']
    if (resistor.GetPosition().x, resistor.GetPosition().y) != (105000000, 127000000):
        raise ValueError('R17 input placement changed; review required')
    resistor.SetPosition(pcbnew.VECTOR2I_MM(105.8, 121.8))
    removed = []
    for t in list(board.GetTracks()):
        if t.m_Uuid.AsString() == 'ccf70ab6-80b8-48dd-8b5f-fa6b49da88ab':
            board.Remove(t); removed.append(t)
    # Select the old pad-to-elbow segment by its exact start, as its route
    # UUID is not a stable external interface.
    for t in list(board.GetTracks()):
        if (t.GetClass() == 'PCB_TRACK' and t.GetNetname() == '/AFE_MENB'
            and t.GetStart() == pcbnew.VECTOR2I_MM(105, 127.825)):
            board.Remove(t); removed.append(t)
    if len(removed) != 2:
        raise ValueError(f'Expected two old R17 tracks, got {len(removed)}')
    # Retire the old resistor-only back-layer spur and its now-unused via.
    old_spur = {'9baea2d6-c643-4700-8d41-89439aa20fd1',
                '0255c8e0-1849-4285-bd91-7a8dfd6107bf',
                '73504ca5-0dfc-4064-89b2-45c9fe14f774',
                '0b0657d4-0a28-403c-a161-dd0354fc535b',
                '6241fdee-94e7-4c07-b44c-e39413478c29',
                '7221c29c-4412-4c6c-9d28-8603565bde44'}
    count = 0
    for t in list(board.GetTracks()):
        if t.m_Uuid.AsString() in old_spur:
            board.Remove(t); removed.append(t); count += 1
    if count != len(old_spur):
        raise ValueError('Old R17 branch changed; review required')
    signal = next(p.GetNet() for p in resistor.Pads() if p.GetNumber() == '1')
    points = [(105.8,122.625),(104.9,123.3)]
    for a, z in zip(points, points[1:]):
        t = pcbnew.PCB_TRACK(board); t.SetLayer(pcbnew.F_Cu)
        t.SetStart(pcbnew.VECTOR2I_MM(*a)); t.SetEnd(pcbnew.VECTOR2I_MM(*z))
        t.SetWidth(pcbnew.FromMM(.18)); t.SetNet(signal); board.Add(t)
    ground = next(p.GetNet() for p in resistor.Pads() if p.GetNumber() == '2')
    via = pcbnew.PCB_VIA(board); via.SetPosition(pcbnew.VECTOR2I_MM(105.1,120.6))
    via.SetWidth(pcbnew.FromMM(.45)); via.SetDrill(pcbnew.FromMM(.2))
    via.SetViaType(pcbnew.VIATYPE_THROUGH); via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetNet(ground); board.Add(via)
    t = pcbnew.PCB_TRACK(board); t.SetLayer(pcbnew.F_Cu)
    t.SetStart(pcbnew.VECTOR2I_MM(105.8,120.975)); t.SetEnd(via.GetPosition())
    t.SetWidth(pcbnew.FromMM(.18)); t.SetNet(ground); board.Add(t)
    for ref in ('J103', 'J104'):
        fps[ref].SetFPID(pcbnew.LIB_ID('o2-probe', 'SolderWire_RaisedRelief_1x01'))
    # These long outlines describe the wire strain-relief/dressing envelope,
    # not a rigid component. Keep them on the assembly drawing, off the ink.
    for ref in ('J103', 'J104'):
        for item in fps[ref].GraphicalItems():
            if item.GetLayer() == pcbnew.F_SilkS:
                item.SetLayer(pcbnew.F_Fab)
    # The full cell body outline crosses the temperature sensor and gas-path
    # instruction. It belongs on the assembly drawing (the cell covers it).
    for item in fps['U11'].GraphicalItems():
        if item.GetClass() == 'PCB_SHAPE' and item.GetLayer() == pcbnew.F_SilkS and item.GetShape() == pcbnew.SHAPE_T_CIRCLE:
            item.SetLayer(pcbnew.F_Fab)
    # Potting and gas-path instructions must be readable during assembly,
    # including the instruction originally outside the board. They are drawing
    # annotations; test-point/connector labels remain on the physical board.
    for item in list(board.GetDrawings()):
        if item.GetClass() == 'PCB_TEXT' and item.GetText() in (
                'POT TO HERE', 'DO NOT OBSTRUCT', 'GAS / DO NOT POT'):
            if item.GetText() == 'POT TO HERE' and item.GetLayer() == pcbnew.B_SilkS:
                board.Remove(item); removed.append(item)
                continue  # one shared boundary annotation, not a mirrored duplicate
            item.SetLayer(pcbnew.Dwgs_User)
            annotation_y = {'POT TO HERE': 132, 'DO NOT OBSTRUCT': 148.5,
                            'GAS / DO NOT POT': 151}[item.GetText()]
            item.SetPosition(pcbnew.VECTOR2I_MM(128, annotation_y))
            item.SetMirrored(False)
        elif (item.GetClass() == 'PCB_SHAPE' and item.GetLayer() == pcbnew.B_SilkS
              and item.GetStart().y == 132000000 and item.GetEnd().y == 132000000):
            item.SetLayer(pcbnew.Dwgs_User)
    leader = pcbnew.PCB_SHAPE(board); leader.SetShape(pcbnew.SHAPE_T_SEGMENT)
    leader.SetLayer(pcbnew.Dwgs_User); leader.SetWidth(pcbnew.FromMM(.12))
    leader.SetStart(pcbnew.VECTOR2I_MM(120,132)); leader.SetEnd(pcbnew.VECTOR2I_MM(123,132))
    board.Add(leader)
    from adopt_revb_interfaces import fill_and_require_connected
    fill_and_require_connected(board)
    project = path.with_suffix('.kicad_pro')
    saved = project.read_bytes()
    pcbnew.SaveBoard(str(path), board)
    project.write_bytes(saved)
    print('Rev B layout: R17 relocated and reconnected; conflicting legend moved to assembly drawing')

if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('usage: finish_revb_layout.py BOARD.kicad_pcb')
    finish(Path(sys.argv[1]))
