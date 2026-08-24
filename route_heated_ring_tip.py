#!/usr/bin/env python3
"""Deterministically complete the aligned heated-ring tip routing."""

from __future__ import annotations

import os
from pathlib import Path
import sys

try:
    import wx

    _APP = wx.AppConsole()
    import pcbnew
except ImportError:
    sys.exit("run with KiCad's bundled Python")

from thermal_design import (ensure_gnd_bridge, ensure_heater_spreader,
                            ensure_thermal_gap, save_board_preserving_project)
from route_thermal_barrier import apply as route_thermal_barrier


HERE = Path(__file__).resolve().parent
SRC = Path(os.environ.get("O2_PCB_IN", HERE / "o2-probe.kicad_pcb"))
OUT = Path(os.environ.get("O2_PCB_OUT", HERE / "o2-probe.kicad_pcb"))
board = pcbnew.LoadBoard(str(SRC))
ORIGIN_X_MM = 100.0
ORIGIN_Y_MM = 50.0


def point(x: float, y: float):
    return pcbnew.VECTOR2I_MM(ORIGIN_X_MM + x, ORIGIN_Y_MM + y)


def segment(netname: str, layer: int, start, end, width: float):
    item = pcbnew.PCB_TRACK(board)
    item.SetNet(board.FindNet(netname))
    item.SetLayer(layer)
    item.SetStart(point(*start))
    item.SetEnd(point(*end))
    item.SetWidth(pcbnew.FromMM(width))
    board.Add(item)
    return item


def path(netname: str, layer: int, points, width: float):
    return [
        segment(netname, layer, start, end, width)
        for start, end in zip(points, points[1:])
        if start != end
    ]


def via(netname: str, position, diameter=0.25, drill=0.15):
    item = pcbnew.PCB_VIA(board)
    item.SetNet(board.FindNet(netname))
    item.SetPosition(point(*position))
    item.SetWidth(pcbnew.FromMM(diameter))
    item.SetDrill(pcbnew.FromMM(drill))
    item.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    board.Add(item)
    return item


def require_floorplan() -> None:
    footprints = {footprint.GetReference(): footprint for footprint in board.Footprints()}
    wanted = {
        "RH1": (5.0, 96.5), "RH2": (15.0, 96.5),
        "Q2": (10.0, 101.25), "R28": (6.5, 101.25),
        "R29": (13.5, 101.25), "TP6": (8.3, 103.0),
        "U12": (3.5, 101.5), "C20": (6.0, 101.5),
        "U10": (10.0, 102.0), "C21": (12.5, 102.5),
        "U14": (16.5, 101.0), "C23": (14.0, 100.0),
        "C24": (14.0, 102.0), "J5": (10.0, 105.5),
    }
    for reference, expected in wanted.items():
        footprint = footprints.get(reference)
        if footprint is None:
            raise SystemExit(f"missing {reference}; run adopt_heated_ring_tip.py first")
        position = footprint.GetPosition()
        actual = (
            round(pcbnew.ToMM(position.x) - ORIGIN_X_MM, 4),
            round(pcbnew.ToMM(position.y) - ORIGIN_Y_MM, 4),
        )
        if actual != expected:
            raise SystemExit(f"{reference} at {actual}, want {expected}")


def main() -> int:
    require_floorplan()

    # In2 is the low-impedance ground backbone.  The all-layer y=134 pour gap
    # splits its plane fill; one exact 0.15 mm In2 trace at the left edge web
    # preserves electrical continuity without restoring a broad heat bridge.
    # Vias sit in ground pads where practical.
    ensure_thermal_gap(board)
    ensure_heater_spreader(board)
    ensure_gnd_bridge(board)
    segment("/GND", pcbnew.F_Cu, (6.0, 101.02), (4.2, 101.1), 0.20)
    path("/GND", pcbnew.F_Cu,
         ((4.2, 101.1), (4.8, 101.1), (4.8, 100.5)), 0.20)
    via("/GND", (4.8, 100.5))
    segment("/GND", pcbnew.F_Cu, (10.0, 101.025), (9.8, 100.7), 0.20)
    via("/GND", (9.8, 100.7))
    segment("/GND", pcbnew.B_Cu, (10.95, 100.3125), (9.8, 100.7), 0.20)
    via("/GND", (13.0, 101.25))
    segment("/GND", pcbnew.B_Cu, (12.675, 101.25), (13.0, 101.25), 0.15)
    path("/GND", pcbnew.F_Cu,
         ((12.5, 102.02), (13.0, 101.52), (13.0, 101.25)), 0.15)
    path("/GND", pcbnew.F_Cu,
         ((13.52, 100.0), (13.0, 100.5), (13.0, 101.25)), 0.15)
    path("/GND", pcbnew.F_Cu,
         ((13.52, 102.0), (13.0, 101.5), (13.0, 101.25)), 0.15)

    path("/GND", pcbnew.F_Cu,
         ((15.7375, 101.0), (15.7375, 101.5), (15.15, 101.5)), 0.12)
    via("/GND", (15.15, 101.5))
    via("/GND", (17.2625, 100.5))
    via("/GND", (17.2625, 101.5))

    # SCL and SDA get separate In1 corridors.  Local F.Cu fanout is kept away
    # from the back-side switch pads and the original trunk tails are retained.
    path("/I2C_SCL", pcbnew.B_Cu,
         ((11.8, 100.75), (12.5, 99.5)), 0.09)
    via("/I2C_SCL", (12.5, 99.5))
    path("/I2C_SCL", pcbnew.F_Cu,
         ((10.65, 101.025), (10.4, 100.4), (10.0, 99.5)), 0.09)
    via("/I2C_SCL", (10.0, 99.5))
    path("/I2C_SCL", pcbnew.F_Cu,
         ((2.8, 101.9), (2.2, 102.7), (1.5, 102.7)), 0.09)
    via("/I2C_SCL", (1.5, 102.7))
    path("/I2C_SCL", pcbnew.In1_Cu,
         ((1.5, 102.7), (1.5, 99.5), (12.5, 99.5)), 0.09)
    path("/I2C_SCL", pcbnew.F_Cu,
         ((16.75, 100.2375), (17.5, 99.5)), 0.09)
    via("/I2C_SCL", (17.5, 99.5))
    segment("/I2C_SCL", pcbnew.In1_Cu, (12.5, 99.5), (17.5, 99.5), 0.09)

    path("/I2C_SDA", pcbnew.F_Cu,
         ((11.85, 101.65), (11.85, 102.3), (11.175, 102.975),
          (10.65, 102.975)), 0.09)
    path("/I2C_SDA", pcbnew.F_Cu,
         ((11.85, 102.3), (12.0, 103.5)), 0.09)
    via("/I2C_SDA", (12.0, 103.5))
    path("/I2C_SDA", pcbnew.F_Cu,
         ((2.8, 101.1), (2.0, 100.5), (0.7, 100.5)), 0.09)
    via("/I2C_SDA", (0.7, 100.5))
    path("/I2C_SDA", pcbnew.In1_Cu,
         ((0.7, 100.5), (0.7, 103.5), (12.0, 103.5)), 0.09)
    path("/I2C_SDA", pcbnew.F_Cu,
         ((17.2625, 101.0), (17.8, 101.0), (17.8, 103.5)), 0.09)
    via("/I2C_SDA", (17.8, 103.5))
    segment("/I2C_SDA", pcbnew.In1_Cu, (12.0, 103.5), (17.8, 103.5), 0.09)

    # Local sensor rail.  C20 and C21 are now the actual U12 and U10 bypasses;
    # C23/C24 and U14 remain an electrically complete DNP pressure option.
    path("/3V3D", pcbnew.F_Cu, ((4.2, 101.9), (6.0, 101.98)), 0.15)
    path("/3V3D", pcbnew.F_Cu,
         ((6.0, 101.98), (6.0, 103.9), (9.35, 103.9),
          (9.35, 102.975), (10.0, 102.975)), 0.15)
    path("/3V3D", pcbnew.F_Cu,
         ((9.35, 103.9), (9.35, 104.5), (12.5, 104.5),
          (12.5, 102.98)), 0.15)
    path("/3V3D", pcbnew.F_Cu,
         ((12.5, 104.5), (14.48, 104.5), (14.48, 102.0),
          (14.48, 100.0), (14.6, 98.4)), 0.15)
    path("/3V3D", pcbnew.F_Cu,
         ((14.48, 100.0), (15.2, 100.0), (15.7375, 100.5),
          (16.25, 100.2375)), 0.15)
    path("/3V3D", pcbnew.F_Cu,
         ((14.48, 102.0), (14.9, 102.6), (16.75, 102.6),
          (16.75, 101.7625)), 0.15)

    # U10 exposed pad reaches a via inside TP6's large hand-probe land; there
    # is no process-sensitive via under the fine-pitch temperature sensor.
    path("/TMP_CELL_EP", pcbnew.F_Cu,
         ((10.0, 102.0), (9.0, 102.0), (8.3, 103.0)), 0.18)
    via("/TMP_CELL_EP", (8.3, 103.0), 0.40, 0.20)

    # The two 2512 elements share a wide switched-low spreader.  The two J5
    # plated-slot castellations are joined by copper, so the removable metal
    # ring is not required for electrical continuity.
    path("/HEATER_LOW", pcbnew.B_Cu,
         ((5.0, 99.4625), (3.0, 101.0), (3.0, 103.5),
          (1.0, 104.5), (0.75, 105.5)), 0.80)
    path("/HEATER_LOW", pcbnew.B_Cu,
         ((15.0, 99.4625), (18.5, 98.5), (19.0, 104.0), (19.25, 105.5)), 0.80)
    segment("/HEATER_LOW", pcbnew.B_Cu, (0.75, 106.25), (19.25, 106.25), 0.80)
    segment("/HEATER_LOW", pcbnew.B_Cu, (10.0, 102.1875), (10.0, 106.25), 0.80)

    # Hardware-off gate network.  The middle In1 corridor crosses neither I2C
    # corridor; short B.Cu fanouts reach Q2 and the two bias resistors.
    path("/HEATER_GATE", pcbnew.F_Cu, ((9.35, 101.025), (8.3, 100.3)), 0.18)
    via("/HEATER_GATE", (8.3, 100.3))
    segment("/HEATER_GATE", pcbnew.B_Cu, (8.3, 100.3), (9.05, 100.3125), 0.18)
    path("/HEATER_GATE", pcbnew.In1_Cu,
         ((8.3, 100.3), (8.0, 101.8), (5.0, 101.8), (5.0, 102.8)), 0.18)
    via("/HEATER_GATE", (5.0, 102.8))
    segment("/HEATER_GATE", pcbnew.B_Cu, (5.0, 102.8), (5.675, 101.25), 0.18)
    path("/HEATER_GATE", pcbnew.In1_Cu,
         ((8.3, 100.3), (8.3, 100.1), (13.5, 100.1), (13.5, 103.0)), 0.18)
    via("/HEATER_GATE", (13.5, 103.0))
    segment("/HEATER_GATE", pcbnew.B_Cu, (13.5, 103.0), (14.325, 101.25), 0.18)

    # PWM changes to In1 beside its retained trunk, follows the right edge past
    # the SGX aperture, then crosses below the sensor routes.  The power feed
    # uses a separate In1 corridor and 0.40 mm copper to both heater elements.
    path("/HEATER_PWM", pcbnew.F_Cu, ((13.85, 85.6), (13.85, 86.5)), 0.18)
    via("/HEATER_PWM", (13.85, 86.5))
    path("/HEATER_PWM", pcbnew.In1_Cu,
         ((13.85, 86.5), (18.0, 90.0), (18.5, 90.5),
          (18.5, 104.2), (6.8, 104.6)), 0.18)
    via("/HEATER_PWM", (6.8, 104.6))
    segment("/HEATER_PWM", pcbnew.B_Cu, (6.8, 104.6), (7.325, 101.25), 0.18)

    via("/+12V_SW", (17.65, 94.3), 0.45, 0.20)
    path("/+12V_SW", pcbnew.B_Cu, ((17.65, 94.3), (15.0, 93.5375)), 0.40)
    path("/+12V_SW", pcbnew.In1_Cu,
         ((17.65, 94.3), (17.65, 92.5), (5.0, 92.5)), 0.40)
    via("/+12V_SW", (5.0, 92.5), 0.45, 0.20)
    segment("/+12V_SW", pcbnew.B_Cu, (5.0, 92.5), (5.0, 93.5375), 0.40)

    route_thermal_barrier(board)
    board.BuildConnectivity()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    save_board_preserving_project(board, OUT)
    print(f"wrote {OUT}: deterministic heated-ring tip routing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
