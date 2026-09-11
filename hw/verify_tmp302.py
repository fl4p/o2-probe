#!/usr/bin/env python3
"""Fresh native geometry audit for the TMP302 addition; DRC/ERC remain mandatory."""
import hashlib,json,sys,time
from pathlib import Path
import wx
APP=wx.AppConsole()
import pcbnew as p
from verify_revb_95 import copper,xy
ROOT=Path(__file__).resolve().parent
BASE=ROOT/'routing/revb-89/o2-probe.kicad_pcb'
BASE_SHA='283224fdf2e3ed3900043cf840596c73f5cb2672007a587459b459eb014a348a'

def footprint(f):
 return (f.GetValue(),(f.GetFPID().GetLibNickname(),f.GetFPID().GetLibItemName()),xy(f.GetPosition()),f.GetLayer(),f.GetOrientationDegrees(),
         sorted((a.GetNumber(),a.GetNetname(),xy(a.GetPosition()),xy(a.GetSize()),xy(a.GetDrillSize()),a.GetShape(),a.GetAttribute(),a.GetOrientationDegrees(),tuple(a.GetLayerSet().Seq()),a.GetRoundRectRadiusRatio()) for a in f.Pads()))

def outline(b):
 q=p.SHAPE_POLY_SET()
 if not b.GetBoardPolygonOutlines(q,False):raise ValueError('Invalid outline')
 return q.Format()

def check(path):
 start=time.monotonic()
 if hashlib.sha256(BASE.read_bytes()).hexdigest()!=BASE_SHA:raise ValueError('Baseline changed')
 old=p.LoadBoard(str(BASE));b=p.LoadBoard(str(path))
 if not b:raise ValueError('Board unavailable')
 fs={f.GetReference():f for f in b.GetFootprints()};prior={f.GetReference():f for f in old.GetFootprints()}
 if set(fs)!=set(prior)|{'U16','C35'} or len(fs)!=101:raise ValueError('Footprint inventory changed')
 for ref,f in prior.items():
  if footprint(f)!=footprint(fs[ref]):raise ValueError('Retained footprint changed: '+ref)
 if outline(b)!=outline(old):raise ValueError('Outline/thermal slots changed')
 if b.GetCopperLayerCount()!=2 or b.GetDesignSettings().GetBoardThickness()!=old.GetDesignSettings().GetBoardThickness():raise ValueError('Stackup changed')
 orig=copper(old);new=copper(b)
 # Four replaced local segments, identified by their original endpoint geometry.
 removed={uid for uid,v in orig.items() if (v[0],v[1],v[3]) in {
 ('/3V3D',p.F_Cu,frozenset([(115.358299,136.0),(114.48,136.0)])),
 ('/3V3D',p.F_Cu,frozenset([(112.5,136.98),(113.5,136.98)])),
 ('/3V3D',p.F_Cu,frozenset([(113.5,136.98),(114.48,136.0)])),
 ('/GND',p.B_Cu,frozenset([(112.5,136.0),(115.9,135.8)]))}}
 # KiCad stores the first endpoint rounded to 115.358300 in some saves.
 removed.add('11561d3a-1c76-473c-8165-025477dea63a')
 if len(removed)!=4 or not removed<=set(orig):raise ValueError('Unknown replacement geometry')
 for uid,v in orig.items():
  if uid not in removed and new.get(uid)!=v:raise ValueError('Retained copper changed: '+uid)
 if set(new)&removed:raise ValueError('Old local segments still present')
 for uid,v in new.items():
  if uid in orig:continue
  if v[0] not in {'/GND','/3V3D','/HEATER_GATE'} or not all(112.4<=x<=117.1 and 135.2<=y<=138.3 for x,y in v[3]):raise ValueError('Unexpected new copper scope')
 u=fs['U16'];c=fs['C35']
 if u.GetValue()!='TMP302BDRLR' or xy(u.GetPosition())!=(114.4,136.5) or u.GetLayer()!=p.F_Cu or u.GetOrientationDegrees()!=0:raise ValueError('U16 identity/pose changed')
 expected={'1':'/3V3D','2':'/GND','3':'/HEATER_GATE','4':'/3V3D','5':'/3V3D','6':'/3V3D'}
 pads=list(u.Pads())
 if len(pads)!=6 or {a.GetNumber():a.GetNetname() for a in pads}!=expected:raise ValueError('TMP302 pin map changed')
 for a in pads:
  n=int(a.GetNumber());want=(-.74 if n<=3 else .74,{1:-.5,2:0,3:.5,4:.5,5:0,6:-.5}[n])
  if xy(a.GetPosition()-u.GetPosition())!=want or xy(a.GetSize())!=(.67,.3) or xy(a.GetDrillSize())!=(0,0) or a.GetAttribute()!=p.PAD_ATTRIB_SMD or abs(a.GetRoundRectRadiusRatio()-1/6)>1e-6:raise ValueError('TI land pattern changed')
 if c.GetValue()!='100n' or xy(c.GetPosition())!=(117,136.5) or {a.GetNumber():a.GetNetname() for a in c.Pads()}!={'1':'/3V3D','2':'/GND'}:raise ValueError('Bypass changed')
 return {'outline_mm':[20,89],'footprints':101,'retained_footprints':99,'replaced_local_segments':4,'added_copper_items':len(set(new)-set(orig)),'TMP302_trip_C':85,'nominal_hysteresis_C':10,'seconds':round(time.monotonic()-start,3)}
if __name__=='__main__':
 result=check(sys.argv[1]);Path(sys.argv[2]).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
