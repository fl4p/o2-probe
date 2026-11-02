"""Local bypass and buck output/filter skeleton for current Rev B."""
import sys as _sys, pathlib as _pathlib  # hw/ root: this script moved to pcb-steps/
_sys.path.insert(1, str(_pathlib.Path(__file__).resolve().parent.parent))
import author_revb_power as base
PLACEMENT={
 'R7':(101.55,92.,180,'B.Cu'),
 'C16':(109.,109.6,0,'F.Cu'),'C25':(102.7,106.8,90,'F.Cu'),
 'C11':(102.,83.4,0,'F.Cu'),'C3':(115.4,75.,90,'F.Cu'),
 'C7':(111.2,108.7,0,'B.Cu'),'R32':(107.,106.8,-90,'B.Cu'),
 'C8':(118.,80.5,-90,'B.Cu'),
}
ROUTES=[
 ('/3V3A',.2,'F.Cu',['U7.6',(109.,110.4),'C16.1']),
 ('GND',.2,'F.Cu',['C16.2',(110.9,109.6)]),
 ('GND',.2,'F.Cu',['U7.7',(108.5,110.7)]),
 ('/3V3A',.2,'F.Cu',['C25.1',(102.7,107.45),(102.025,108.125),'U4.8']),
 ('GND',.2,'F.Cu',['C25.2',(103.325,106.32)]),
 ('/3V3D',.2,'F.Cu',['C11.1',(101.52,85.15),'U5.8']),
 ('GND',.25,'F.Cu',['C11.2',(103.2,83.4)]),
 ('/3V3D',.5,'F.Cu',['L1.2',(114.375,77.5),'C3.1']),
 ('GND',.4,'F.Cu',['C3.2',(116.4,73.525)]),
 ('/3V3A',.3,'B.Cu',['R32.2',(107.,108.7),'C7.1']),
 ('GND',.3,'B.Cu',['C7.2',(113.9,108.7)]),
 ('/VIN_MON',.15,'B.Cu',['R26.2','R27.1']),
 ('/VIN_MON',.15,'B.Cu',['R26.2',(113.45,104.925),'D8.1']),
]
VIAS=[('GND',110.9,109.6),('GND',108.5,110.7),('GND',103.325,106.32),('GND',103.2,83.4),('GND',116.4,73.525),('GND',113.9,108.7)]
def apply(board):
 old=(base.PLACEMENT,base.ROUTES,base.VIAS)
 try:
  base.PLACEMENT,base.ROUTES,base.VIAS=PLACEMENT,ROUTES,VIAS
  base.place(board);return base.author(board)
 finally:base.PLACEMENT,base.ROUTES,base.VIAS=old
