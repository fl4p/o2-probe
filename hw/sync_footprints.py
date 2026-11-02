#!/usr/bin/env python3
"""Refresh placed footprints from their named libraries without moving copper.

KiCad reports a library mismatch when a placed copy has been edited or when an
upstream library changed.  This script replaces each copy with the current
library definition while preserving placement, schematic path, assembly flags,
custom fields, and pad nets.  Run with KiCad's bundled Python.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

try:
    import wx
    _APP = wx.AppConsole()
    import pcbnew
except ImportError:
    sys.exit("run with KiCad's bundled Python")


HERE = Path(__file__).resolve().parent
KICAD_FP = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints")
PROJECT_FP = HERE / "lib" / "o2-probe.pretty"
TMP117_FP = HERE / "lib" / "tmp117-probe.pretty"


def library_path(nickname: str) -> Path:
    if nickname == "o2-probe":
        return PROJECT_FP
    if nickname == "tmp117-probe":
        return TMP117_FP
    return KICAD_FP / f"{nickname}.pretty"


def pad_nets(footprint: pcbnew.FOOTPRINT) -> dict[str, pcbnew.NETINFO_ITEM]:
    result: dict[str, pcbnew.NETINFO_ITEM] = {}
    for pad in footprint.Pads():
        number = pad.GetNumber()
        if number and pad.GetNet() is not None:
            result[number] = pad.GetNet()
    return result


def schematic_components() -> dict[str, dict[str, object]]:
    """Return authoritative footprint IDs and custom fields by reference."""
    xml_path = HERE / "o2-probe.xml"
    if not xml_path.is_file():
        return {}
    root = ET.parse(xml_path).getroot()
    result: dict[str, dict[str, object]] = {}
    for component in root.findall("./components/comp"):
        ref = component.attrib.get("ref", "")
        result[ref] = {
            "footprint": component.findtext("footprint", ""),
            "fields": {
                prop.attrib["name"]: prop.attrib.get("value", "")
                for prop in component.findall("property")
                if prop.attrib.get("name") not in ("Sheetname", "Sheetfile", "dnp")
            },
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("board", nargs="?", default=str(HERE / "o2-probe.kicad_pcb"))
    parser.add_argument("--output", "-o")
    args = parser.parse_args()
    source = Path(args.board).resolve()
    output = Path(args.output).resolve() if args.output else source

    board = pcbnew.LoadBoard(str(source))
    originals = list(board.Footprints())
    components = schematic_components()
    refreshed = 0

    for old in originals:
        reference = old.GetReference()
        component = components.get(reference, {})
        desired_fpid = str(component.get("footprint", ""))
        if desired_fpid and ":" in desired_fpid:
            nickname, item_name = desired_fpid.split(":", 1)
        else:
            fpid = old.GetFPID()
            nickname = fpid.GetLibNickname()
            item_name = fpid.GetLibItemName()
        if not nickname or not item_name:
            raise SystemExit(f"{old.GetReference()}: footprint has no library identifier")
        libdir = library_path(nickname)
        new = pcbnew.FootprintLoad(str(libdir), item_name)
        if new is None:
            raise SystemExit(f"{old.GetReference()}: cannot load {nickname}:{item_name} from {libdir}")

        value = old.GetValue()
        position = old.GetPosition()
        orientation = old.GetOrientation()
        back = old.GetLayer() == pcbnew.B_Cu
        path = old.GetPath()
        nets = pad_nets(old)
        fields = {
            field.GetName(): field.GetText()
            for field in old.GetFields()
            if field.GetName() not in ("Reference", "Value")
        }
        fields.update(component.get("fields", {}))

        # The footprint must belong to a board before Flip() is safe in KiCad's
        # Python bindings.  Add it, then restore every instance-only property.
        board.Add(new)
        new.SetFPID(pcbnew.LIB_ID(nickname, item_name))
        new.SetReference(reference)
        new.SetValue(value)
        new.SetPath(path)
        new.SetPosition(position)
        if back:
            new.Flip(position, False)
        new.SetOrientation(orientation)
        new.SetDNP(old.IsDNP())
        new.SetExcludedFromBOM(old.IsExcludedFromBOM())
        new.SetExcludedFromPosFiles(old.IsExcludedFromPosFiles())
        for name, text in fields.items():
            new.SetField(name, text)
        for field in new.GetFields():
            field.SetVisible(False)
        new.Reference().SetLayer(pcbnew.B_Fab if back else pcbnew.F_Fab)

        for pad in new.Pads():
            if pad.GetNumber() in nets:
                pad.SetNet(nets[pad.GetNumber()])

        board.Remove(old)
        refreshed += 1

    board.BuildConnectivity()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(str(output), board)
    print(f"wrote {output}: refreshed {refreshed} placed footprints")


if __name__ == "__main__":
    main()
