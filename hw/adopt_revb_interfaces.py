#!/usr/bin/env python3
"""Migrate the archived BOM39 route to the completed Rev B interfaces.

This edits the routed candidate, never the Rev A main board. Run with KiCad
Python, then perform the checks in the completion record.
The input hash pins the copper being surgically changed; a different board
requires review rather than guessing which pieces to remove.
"""
from pathlib import Path
import hashlib
import sys
import wx
_APP = wx.AppConsole()
import pcbnew
import gen_sch

HERE=Path(__file__).resolve().parent
SOURCE=HERE/'routing/2layer-bom39/o2-probe.kicad_pcb'
EXPECTED='e5518b691b8e102b25d7eba50df3a84a05001f40fe1d0e0a043a1fe01b1ee3da'

def pos(x,y): return pcbnew.VECTOR2I_MM(x,y)

def fill_and_require_connected(b):
    if not b.BuildConnectivity():
        raise ValueError('Could not build pre-fill connectivity')
    if not pcbnew.ZONE_FILLER(b).Fill(b.Zones()):
        raise ValueError('Zone refill failed; cached copper is not verification')
    if not b.BuildConnectivity():
        raise ValueError('Could not build post-fill connectivity')
    c=b.GetConnectivity();c.RecalculateRatsnest()
    if c.GetUnconnectedCount(False):
        raise ValueError('Refilled candidate has unconnected copper; not saving')

def migrate(source,output):
    if hashlib.sha256(source.read_bytes()).hexdigest()!=EXPECTED:
        raise ValueError('Input is not the pinned, reviewed BOM39 route')
    b=pcbnew.LoadBoard(str(source)); fps={f.GetReference():f for f in b.GetFootprints()}
    def net(name):
        for n in b.GetNetInfo().NetsByName().values():
            if n.GetNetname()==name:return n
        n=pcbnew.NETINFO_ITEM(b,name);b.Add(n);return n
    def pad(ref,num):return next(p for p in fps[ref].Pads() if p.GetNumber()==str(num))
    def track(a,z,netname,width=.09,layer=pcbnew.B_Cu):
        t=pcbnew.PCB_TRACK(b);t.SetStart(pos(*a));t.SetEnd(pos(*z));t.SetWidth(pcbnew.FromMM(width));t.SetLayer(layer);t.SetNet(net(netname));b.Add(t)
    def via(at,netname,diameter=.45,drill=.2):
        v=pcbnew.PCB_VIA(b);v.SetPosition(pos(*at));v.SetWidth(pcbnew.FromMM(diameter));v.SetDrill(pcbnew.FromMM(drill));v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetNet(net(netname));b.Add(v)
    # Preserve DE -> PC6/R7; remove only the spur into the former /RE pin.
    remove={
        ((104.0591,96.6399),(103.165,95.7458)),
        ((103.165,95.7458),(103.165,94.475)),
    }
    removed=0
    detached=[]
    for t in list(b.GetTracks()):
        if t.GetClass()!='PCB_TRACK' or t.GetNetname()!='/RS485_DE':continue
        pair=tuple((round(p.x/1e6,4),round(p.y/1e6,4)) for p in [t.GetStart(),t.GetEnd()])
        if pair in remove or pair[::-1] in remove:b.Remove(t);detached.append(t);removed+=1
    if removed!=2:raise ValueError(f'Expected two DE spur segments, found {removed}')
    pad('U5',2).SetNet(net('/RS485_RE'));pad('U6',31).SetNet(net('/RS485_RE'))
    # Schematic removed EXP_INT. The inherited routed candidate retained this
    # orphan net on U6.21; it has no copper and must be an explicit NC.
    if any(t.GetNetname()=='/EXP_INT' for t in b.GetTracks()):raise ValueError('Unexpected EXP_INT copper')
    pad('U6',21).SetNet(net('unconnected-(U6-PB2-Pad21)'))
    r=pcbnew.FootprintLoad('/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints/Resistor_SMD.pretty','R_0603_1608Metric')
    if r is None:raise ValueError('R45 footprint unavailable')
    b.Add(r);r.SetReference('R45');r.SetValue('47k');r.SetFPID(pcbnew.LIB_ID('Resistor_SMD','R_0603_1608Metric'))
    r.SetPosition(pos(107.5,92.7));r.Flip(r.GetPosition(),False)
    r.SetPath(pcbnew.KIID_PATH('/'+gen_sch.uid('sym', 'R45')))
    for p in r.Pads():p.SetNet(net('/RS485_RE' if p.GetNumber()=='1' else '/GND'))
    r.Reference().SetLayer(pcbnew.B_Fab)
    for f in r.GetFields():f.SetVisible(False)
    # Route found with KRT, then reviewed and authored here: centre every
    # endpoint on its via, and keep holes outside the R45 / LQFP solder lands.
    re_paths=[
        (pcbnew.F_Cu,[(103.165,94.475),(103.2,94.5),(103.2,96.5)]),
        (pcbnew.B_Cu,[(103.2,96.5),(103.9,97.1),(106.9,97.1),(107.2,96.8)]),
        (pcbnew.F_Cu,[(107.2,96.8),(107.5,96.5),(107.5,93.3)]),
        (pcbnew.B_Cu,[(107.5,93.3),(108.2,92.7),(108.325,92.7)]),
        (pcbnew.F_Cu,[(109.3,94.88),(109.6,94.75),(110.3375,94.75)]),
    ]
    for layer,path in re_paths:
        for a,z in zip(path,path[1:]):track(a,z,'/RS485_RE',.18,layer)
    for at in [(103.2,96.5),(107.2,96.8),(107.5,93.3)]:via(at,'/RS485_RE')
    via((109.3,94.88),'/RS485_RE',.25,.15)
    # A 0.3793 mm outward jog opens the back-layer corridor beside the DE
    # via; this avoids putting a drill in the MCU or resistor solder lands.
    shifted=0
    for t in list(b.GetTracks()):
        if t.GetClass()!='PCB_TRACK' or t.GetNetname()!='/3V3D':continue
        a=t.GetStart();z=t.GetEnd()
        if (a.x,a.y,z.x,z.y)==(109670700,95809300,109670700,92445700):
            b.Remove(t);detached.append(t);shifted+=1
    if shifted!=1:raise ValueError('Expected the single 3V3D corridor segment')
    path=[(109.6707,95.8093),(110.05,95.0),(110.05,93.1),(109.6707,92.4457)]
    for a,z in zip(path,path[1:]):track(a,z,'/3V3D',.18)
    track((108.325,92.7),(108.95,92.7),'/RS485_RE',.09)
    via((108.95,92.7),'/RS485_RE',.25,.15)
    track((108.95,92.7),(109.3,92.9),'/RS485_RE',.09,pcbnew.F_Cu)
    via((109.3,92.9),'/RS485_RE',.25,.15)
    path=[(109.3,92.9),(109.65,93.25),(109.65,94.55),(109.3,94.88)]
    for a,z in zip(path,path[1:]):track(a,z,'/RS485_RE',.09)
    track((106.675,92.7),(105.85,92.65),'/GND',.15)
    via((105.85,92.65),'/GND',.3,.15)
    # This pour region had no pad until R45 was added. Stitch it to the
    # existing F.Cu ground below U5.5, outside that pin's solder land.
    via((105.67,90.85),'/GND',.3,.15)
    via((106.6,91.1),'/GND',.3,.15)
    # Correct D7's DBZ pinout and move it beside the cell's CE pad, away from
    # the former cramped +12V / I2C corridor. Its ground via reaches F.Cu GND.
    d=fps['D7'];d.SetPosition(pos(103.8,138.0));d.SetOrientationDegrees(180)
    d.SetValue('TPD2E2U06-Q1');d.SetField('MPN','TPD2E2U06QDBZRQ1')
    pad('D7',1).SetNet(net('/CELL_CE'));pad('D7',2).SetNet(net('unconnected-(D7-IO2-Pad2)'));pad('D7',3).SetNet(net('/GND'))
    # Remove obsolete D7 ground spur and the CE fork that made the TVS a stub.
    ids={'3b9b5256-729b-4bd2-86ad-79ab64ca5a9c','c9c21126-59d3-42e7-a41d-eae6f70a741c',
         '3d287eb8-022b-4e25-a251-b1ff8b5750f9','6928b784-d2b4-43fa-8e86-fcf0d8d71d45','98064297-b00f-4d86-ab61-72d2dd190ec3','ba1b947e-be42-454c-8715-56535d4010ec'}
    removed=0
    for t in list(b.GetTracks()):
        if t.m_Uuid.AsString() in ids:b.Remove(t);detached.append(t);removed+=1
    if removed!=len(ids):raise ValueError(f'Expected {len(ids)} CE/GND segments, found {removed}')
    # Protected branch passes through the clamp land. The cell reaches this
    # land before continuing cableward to R42; no shunt stub remains.
    ce=pad('D7',1).GetPosition(); ce=(ce.x/1e6,ce.y/1e6)
    path=[(108.0,132.35),(108.7175,137.05),(108.7175,137.45),(105.9,137.45),(105.9,137.05),ce]
    for a,z in zip(path,path[1:]):track(a,z,'/CELL_CE')
    path=[ce,(105.9,138.1),(105.9,140.1),(107.46,140.1),(107.46,141.0)]
    for a,z in zip(path,path[1:]):track(a,z,'/CELL_CE')
    gp=pad('D7',3).GetPosition();gp=(gp.x/1e6,gp.y/1e6)
    # A via outside the SMD land avoids an unqualified via-in-pad solder joint.
    gvia=(102.8625,138.85);track(gp,gvia,'/GND',.3);via(gvia,'/GND')
    # Bond the existing narrow thermal-web ground strap into the main F.Cu
    # pour. Its old endpoint only grazed a fill corner, giving refill-dependent
    # connectivity. This extension is outside the thermal barrier.
    track((100.5,133.0),(101.4,132.1),'/GND',.15,pcbnew.F_Cu)
    via((101.4,132.1),'/GND',.3,.15)
    fps['R42'].SetValue('1k 1%');fps['R42'].SetField('MPN','RC0603FR-071KL')
    from retire_revb_ring import retire
    detached.extend(retire(b))
    # Align current symbol fields/paths; retain explicitly accepted local wire
    # footprints and every existing placement/copper decision except above.
    for f in b.GetFootprints():
        spec=gen_sch.INST[f.GetReference()]
        f.SetValue(spec['value']);f.SetPath(pcbnew.KIID_PATH('/'+gen_sch.uid('sym', f.GetReference())))
        if spec.get('mpn'):f.SetField('MPN',spec['mpn'])
        if spec.get('note'):f.SetField('Design Note',spec['note'])
        for field in f.GetFields():
            if field.GetName() in ('MPN','Design Note'):
                field.SetVisible(False)
    fill_and_require_connected(b)
    # pcbnew SaveBoard may rewrite the project file; preserve the reviewed
    # constraints exactly. Direct CLI refill/DRC is independently required.
    project=output.with_suffix('.kicad_pro'); saved=project.read_bytes() if project.exists() else None
    pcbnew.SaveBoard(str(output),b)
    if saved is not None:project.write_bytes(saved)
    print('Migrated: R45/PC7 receiver path, D7 ground/package, R42, current symbol fields')

if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit('usage: adopt_revb_interfaces.py OUTPUT.kicad_pcb')
    migrate(SOURCE,Path(sys.argv[1]))
