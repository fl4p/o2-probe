OPENSCAD ?= openscad
SOURCE := o2_probe_rev_a.scad
OUT := exports

FIXTURE := membrane_fixture.scad
FIXTURE_PARTS := cartridge retainer chamber lid plenum die plug cavity
FIXTURE_STLS := $(addprefix $(OUT)/fixture-,$(addsuffix .stl,$(FIXTURE_PARTS)))

.PHONY: all clean preview response-candidate fixture head-provisional head-end-provisional

all: $(OUT)/enclosure.stl $(OUT)/probe_mockup.stl $(OUT)/membrane_cartridge.stl $(OUT)/diffusion_head.stl $(OUT)/cable_cap.stl $(OUT)/o2_probe_assembly.3mf

$(OUT):
	mkdir -p $(OUT)

$(OUT)/enclosure.stl: $(SOURCE) | $(OUT)
	$(OPENSCAD) --hardwarnings -D 'part="enclosure"' -o $@ $<

$(OUT)/probe_mockup.stl: $(SOURCE) | $(OUT)
	$(OPENSCAD) --hardwarnings -D 'part="probe"' -o $@ $<

$(OUT)/membrane_cartridge.stl: $(SOURCE) | $(OUT)
	$(OPENSCAD) --hardwarnings -D 'part="membrane"' -o $@ $<

$(OUT)/diffusion_head.stl: $(SOURCE) | $(OUT)
	$(OPENSCAD) --hardwarnings -D 'part="head"' -o $@ $<

$(OUT)/cable_cap.stl: $(SOURCE) | $(OUT)
	$(OPENSCAD) --hardwarnings -D 'part="cap"' -o $@ $<

$(OUT)/o2_probe_assembly.3mf: $(SOURCE) | $(OUT)
	$(OPENSCAD) --hardwarnings -D 'part="assembly"' -o $@ $<

preview: $(SOURCE) | $(OUT)
	$(OPENSCAD) --render --viewall --autocenter --projection=p --imgsize=1400,1000 --colorscheme=Tomorrow -D 'part="assembly"' -D 'exploded=true' -o $(OUT)/exploded-preview.png $<

response-candidate: o2_probe_response_candidate.scad | $(OUT)
	$(OPENSCAD) --hardwarnings -D 'part="assembly"' -o $(OUT)/response-candidate.3mf $<
	$(OPENSCAD) --render --viewall --autocenter --projection=p --imgsize=1400,1000 --colorscheme=Tomorrow -D 'part="assembly"' -D 'exploded=true' -o $(OUT)/response-candidate-preview.png $<

# Step-1 membrane fixture. The bypass cartridge is the known-bad calibration
# part and is built deliberately, never by `make all`.
fixture: $(FIXTURE_STLS) $(OUT)/fixture-cartridge-bypass.stl $(OUT)/membrane-fixture-preview.png

$(OUT)/fixture-%.stl: $(FIXTURE) | $(OUT)
	$(OPENSCAD) --hardwarnings -D 'part="$*"' -o $@ $<

$(OUT)/fixture-cartridge-bypass.stl: $(FIXTURE) | $(OUT)
	$(OPENSCAD) --hardwarnings -D 'part="cartridge"' -D 'bypass=true' -o $@ $<

$(OUT)/membrane-fixture-preview.png: $(FIXTURE) | $(OUT)
	$(OPENSCAD) --render --viewall --autocenter --projection=p --imgsize=1400,1000 \
		--colorscheme=Tomorrow -D 'part="assembly"' -D 'exploded=true' -o $@ $<

clean:
	rm -f $(FIXTURE_STLS) $(OUT)/fixture-cartridge-bypass.stl $(OUT)/membrane-fixture-preview.png
	rm -f $(OUT)/enclosure.stl $(OUT)/probe_mockup.stl $(OUT)/membrane_cartridge.stl $(OUT)/diffusion_head.stl $(OUT)/sensor_head.stl $(OUT)/cable_cap.stl $(OUT)/o2_probe_assembly.3mf $(OUT)/exploded-preview.png $(OUT)/response-candidate.3mf $(OUT)/response-candidate-preview.png

# Buried head. Measured inputs are refused by default; `head-provisional`
# supplies the documented placeholders so the geometry can be looked at.
HEAD := o2_probe_head.scad
HEAD_PROV := -D tube_od_meas=32.0 -D board_env_front=3.5 -D board_env_back=1.5 \
             -D cell_seated_h=8.8 -D accept_written_off=true

head-provisional: | $(OUT)
	$(OPENSCAD) --hardwarnings $(HEAD_PROV) -D 'part="head"' -o $(OUT)/head.stl $(HEAD)
	$(OPENSCAD) --hardwarnings $(HEAD_PROV) -D 'part="retainer"' -o $(OUT)/head-retainer.stl $(HEAD)
	$(OPENSCAD) --hardwarnings $(HEAD_PROV) -D 'part="guard"' -o $(OUT)/head-guard.stl $(HEAD)
	$(OPENSCAD) --render --viewall --autocenter --projection=p --imgsize=1400,1000 \
		--colorscheme=Tomorrow $(HEAD_PROV) -D 'part="assembly"' -D exploded=true \
		-o $(OUT)/head-provisional-preview.png $(HEAD)

HEAD_END := o2_probe_head_end.scad
HEAD_END_PARTS := head carrier retainer cap cavity
# board_env_front/back corrected 2026-09-04 from 3.5/1.5. RV1, the 5 mm trimmer,
# is a Bourns 3224W on B.Cu -- the BACK -- so the tall face is the back, not the
# front. Front is L1 (L_6.3x6.3_H3). Checked in o2-probe.kicad_pcb, not assumed.
HEAD_END_PROV := -D tube_od_meas=32.0 -D board_env_front=3.0 -D board_env_back=5.0 \
                 -D cell_axial_len=13.0

# Every single-part render must come out as exactly one closed solid. CGAL
# reports that as "Volumes: 2" -- the body plus the infinite outer volume. An
# inverted cut that leaves a zero-thickness ring shows up here as 3, which is
# how the carrier shipped a bored-out spigot and no O-ring groove while every
# assert passed and the volume gate read clean.
head-end-provisional: | $(OUT)
	@for p in $(HEAD_END_PARTS); do \
		$(OPENSCAD) --hardwarnings $(HEAD_END_PROV) -D "part=\"$$p\"" \
			-o $(OUT)/head-end-$$p.stl $(HEAD_END) 2>$(OUT)/.$$p.log || \
			{ cat $(OUT)/.$$p.log; exit 1; }; \
		v=`sed -n 's/.*Volumes: *\([0-9]*\).*/\1/p' $(OUT)/.$$p.log | tail -1`; \
		if [ "$$v" != "2" ]; then \
			echo "FAIL $$p: $$v volumes, expected 2 (one closed solid)"; \
			exit 1; \
		fi; \
		if grep -q "not be a valid 2-manifold" $(OUT)/.$$p.log; then \
			echo "FAIL $$p: not 2-manifold"; exit 1; \
		fi; \
		rm -f $(OUT)/.$$p.log; \
	done
	@# The insert route is retained but not the default, so nothing rendered it.
	@# It gets the SAME solid-count gate: exit status alone would happily pass a
	@# multi-body render, which is the exact defect this target exists to catch.
	@for p in $(HEAD_END_PARTS); do \
		$(OPENSCAD) --hardwarnings $(HEAD_END_PROV) -D 'fastening="insert"' \
			-D "part=\"$$p\"" -o /dev/null --export-format asciistl \
			$(HEAD_END) >/dev/null 2>$(OUT)/.ins-$$p.log || \
			{ cat $(OUT)/.ins-$$p.log; echo "FAIL insert route: $$p"; exit 1; }; \
		v=`sed -n 's/.*Volumes: *\([0-9]*\).*/\1/p' $(OUT)/.ins-$$p.log | tail -1`; \
		if [ "$$v" != "2" ]; then \
			echo "FAIL insert route $$p: $$v volumes, expected 2"; exit 1; \
		fi; \
		if grep -q "not be a valid 2-manifold" $(OUT)/.ins-$$p.log; then \
			echo "FAIL insert route $$p: not 2-manifold"; exit 1; \
		fi; \
		rm -f $(OUT)/.ins-$$p.log; \
	done
	@echo "head-end: both fastening routes render, all parts closed solids"
	@# The 5.0 cm3 budget is a property of the MESH. cav_net is a hand-written
	@# model of the void and has been wrong before; measure what was built.
	@$(OPENSCAD) --hardwarnings $(HEAD_END_PROV) -D 'part="cavity"' \
		-o $(OUT)/head-end-cavity-ascii.stl --export-format asciistl \
		$(HEAD_END) 2>/dev/null
	python3 tools/stlvol.py --max 5000 $(OUT)/head-end-cavity-ascii.stl
	$(OPENSCAD) --render --viewall --autocenter --projection=p --imgsize=1400,1000 \
		--colorscheme=Tomorrow $(HEAD_END_PROV) -D 'part="assembly"' -D exploded=true \
		-o $(OUT)/head-end-preview.png $(HEAD_END)
	$(OPENSCAD) $(HEAD_END_PROV) -D 'part="plate"' -o $(OUT)/head-end-plate.3mf $(HEAD_END)
	@# The print-oriented STLs are TRACKED but were built by no target, so they
	@# silently went stale: on 2026-09-03 they still carried the Ø47 cap and the
	@# 39.10 flange a day after the spigot_land split moved them to Ø45 / 38.90.
	@# The part= dispatch already existed; only the target was missing.
	@for p in carrier retainer cap; do \
		$(OPENSCAD) --hardwarnings $(HEAD_END_PROV) -D "part=\"$$p-print\"" \
			-o $(OUT)/head-end-$$p-print.stl $(HEAD_END) 2>/dev/null || \
			{ echo "FAIL $$p-print"; exit 1; }; \
	done
	@echo "head-end: print-oriented STLs rebuilt"

# The labelled exploded drawing. Both files used to be built by hand, which is
# how the labeller ended up with pixel windows that only fitted one particular
# render. Kept at 1600x1200: the stack got taller when the PCB tip was added
# below the head, and the preview size crops it.
.PHONY: head-end-exploded
# NO --render here, deliberately. --render goes through CGAL, which discards
# every color() in assembly() and hands back the colorscheme's default teal --
# and the labeller identifies parts BY COLOUR, so a --render image silently
# labels nothing. Preview mode (OpenCSG) keeps the colours.
head-end-exploded: | $(OUT)
	$(OPENSCAD) --viewall --autocenter --projection=p --imgsize=1600,1200 \
		--camera=0,0,0,72,0,25,0 \
		--colorscheme=Tomorrow $(HEAD_END_PROV) -D 'part="assembly"' -D exploded=true \
		-o $(OUT)/head-end-exploded.png $(HEAD_END)
	cd .. && python3 cad/label-exploded.py

# The ASA, no-weld carrier: the parts to actually print, with the clamped
# membrane bed. Three switches have to move together and none of them is
# cosmetic, which is why this is its own target rather than a note in a doc:
#
#   carrier_material=asa   no weld is possible to ASA, so the membrane is
#                          clamped -- that IS this build
#   carrier_fab=printed    turns on the measured shrinkage compensation on the
#                          radial groove root. Exporting the machined geometry
#                          and printing it is how carrier 1 came out at 24.800
#                          and squeezed 14.90% against a 15% floor
#   oring_sorting=sorted   a printed carrier's +/-0.09 plus a catalogue ring's
#                          +/-0.08 spends 15.06 of 15 squeeze points and the
#                          band assert fires. Micrometering the Ø24 x 1.5 rings
#                          on receipt is not optional on this route
#
# The clamped bed's own ring (17 x 2.5, on hand) wants the same micrometer --
# see face_sorting in the model and PRINTING-HEAD-END.md.
#
# WHICH RADIAL RING THE EXPORTS ARE CUT FOR. Default onhand-22x2, and that is not
# a preference: Fab confirmed 2026-09-05 there is no 24 x 1.5 in the building, so
# a part exported for the sourced ring is a part that cannot be assembled today.
# The MODEL's default is still "ors116787" -- the design of record is unchanged
# and `make head-end-asa RING=ors116787` builds it -- but what lands in exports/,
# and therefore what print.sh slices, is the ring that exists.
#
# The ring sizes the spigot (Ø22 -> Ø25.8 against Ø24 -> Ø26.8), so this is a
# different part, not a different note on the same part. exports/asa-PROVENANCE
# records which one, because two STLs that differ by 1 mm of spigot look
# identical in a file listing and identical on a plate.
RING ?= onhand-22x2
ASA := $(HEAD_END_PROV) -D 'carrier_material="asa"' -D 'carrier_fab="printed"' \
       -D 'oring_sorting="sorted"' -D 'mem_seal="clamped"' \
       -D 'radial_ring="$(RING)"'

.PHONY: head-end-asa
head-end-asa: | $(OUT)
	@# The bed is quantized to the BUILD, so the build has to be the one that
	@# slices it. This compares the model's layer height, first layer and line
	@# width against profiles/process_asa_seal.json, which is what print.sh uses.
	python3 tools/profile_check.py
	@for p in carrier retainer; do \
		$(OPENSCAD) --hardwarnings $(ASA) -D "part=\"$$p\"" \
			-o $(OUT)/asa-$$p.stl $(HEAD_END) 2>$(OUT)/.asa-$$p.log || \
			{ cat $(OUT)/.asa-$$p.log; exit 1; }; \
		v=`sed -n 's/.*Volumes: *\([0-9]*\).*/\1/p' $(OUT)/.asa-$$p.log | tail -1`; \
		if [ "$$v" != "2" ]; then \
			echo "FAIL asa-$$p: $$v volumes, expected 2"; exit 1; \
		fi; \
		rm -f $(OUT)/.asa-$$p.log; \
	done
	@for p in carrier retainer; do \
		$(OPENSCAD) --hardwarnings $(ASA) -D "part=\"$$p-print\"" \
			-o $(OUT)/asa-$$p-print.stl $(HEAD_END) 2>/dev/null || \
			{ echo "FAIL asa-$$p-print"; exit 1; }; \
	done
	@# NO PAIRED PLATE. tools/seal_check.sh refuses a multi-object plate and it is
	@# right to: identical parts measured 0 mTorr singly and 18 mTorr nine-up
	@# (PRINTING-BODY-TUBE.md). These two parts carry the seal, so they are
	@# sliced one per plate by ./print.sh, not arranged together here.
	@# PROVENANCE. What these STLs were cut for, beside the STLs, because the
	@# radial ring is a 1 mm difference in spigot diameter and nothing in an STL
	@# says which ring it expects. print.sh can assert on this file if it wants a
	@# gate; at minimum a human reading exports/ can see it.
	@{ echo "asa-carrier-print.stl, asa-retainer-print.stl"; \
	   echo "built    $$(date '+%Y-%m-%d %H:%M')"; \
	   echo "radial   $(RING)"; \
	   echo "bed      clamped, O-ring 17 x 2.5 in the RETAINER underside"; \
	   echo "carrier  ASA, printed, shrinkage-compensated groove root"; \
	   echo "rings    micrometer them: oring_sorting=sorted is assumed"; \
	   $(OPENSCAD) $(ASA) -D 'part="carrier"' -o /dev/null --export-format asciistl \
	     $(HEAD_END) 2>&1 | sed -n 's/^ECHO: "\(RADIAL O-RING\|PP carrier\)/  \1/p' \
	     | sed 's/"$$//'; } > $(OUT)/asa-PROVENANCE
	@cat $(OUT)/asa-PROVENANCE
	@echo "ASA carrier + retainer: exports/asa-*-print.stl -- slice singly, ./print.sh slice carrier"

# ---------------------------------------------------------------- body tube
# Printed ASA body for prototype 1: unpotted Rev-A board, no heater ring.
# `tube` and `cap` must each come out as ONE closed solid (CGAL "Volumes: 2");
# `dam` is deliberately two halves and reads 3, so it is gated separately.
BODY := o2_probe_body_tube.scad

.PHONY: body-tube
body-tube: | $(OUT)
	@for p in tube cap; do \
		$(OPENSCAD) --hardwarnings -D "part=\"$$p\"" \
			-o $(OUT)/body-$$p.stl $(BODY) 2>$(OUT)/.b-$$p.log || \
			{ cat $(OUT)/.b-$$p.log; exit 1; }; \
		v=`sed -n 's/.*Volumes: *\([0-9]*\).*/\1/p' $(OUT)/.b-$$p.log | tail -1`; \
		if [ "$$v" != "2" ]; then \
			echo "FAIL $$p: $$v volumes, expected 2 (one closed solid)"; exit 1; \
		fi; \
		if grep -q "not be a valid 2-manifold" $(OUT)/.b-$$p.log; then \
			echo "FAIL $$p: not 2-manifold"; exit 1; \
		fi; \
		rm -f $(OUT)/.b-$$p.log; \
	done
	@# Print orientation for the cap: gland face DOWN. As modelled the 3 mm
	@# closed end sits on top of the dia-27.7 tube seat, so slicing body-cap.stl
	@# as-is starts that roof in mid-air. body-cap-print.stl is the one that goes
	@# on a plate; body-cap.stl stays for the assembly views.
	@$(OPENSCAD) --hardwarnings -D 'part="cap-print"' -o $(OUT)/body-cap-print.stl \
		$(BODY) 2>$(OUT)/.b-capp.log || { cat $(OUT)/.b-capp.log; exit 1; }
	@v=`sed -n 's/.*Volumes: *\([0-9]*\).*/\1/p' $(OUT)/.b-capp.log | tail -1`; \
	 if [ "$$v" != "2" ]; then \
		echo "FAIL cap-print: $$v volumes, expected 2"; exit 1; \
	 fi; rm -f $(OUT)/.b-capp.log
	@$(OPENSCAD) --hardwarnings -D 'part="dam"' -o $(OUT)/body-dam.stl \
		$(BODY) 2>$(OUT)/.b-dam.log || { cat $(OUT)/.b-dam.log; exit 1; }
	@v=`sed -n 's/.*Volumes: *\([0-9]*\).*/\1/p' $(OUT)/.b-dam.log | tail -1`; \
	 if [ "$$v" != "3" ]; then \
		echo "FAIL dam: $$v volumes, expected 3 (two halves)"; exit 1; \
	 fi; rm -f $(OUT)/.b-dam.log
	@echo "body-tube: tube and cap are closed solids, dam is two halves"
	@# The bayonet is the one feature here that can be geometrically wrong while
	@# every part still renders perfectly. Prove the kinematics, not the mesh:
	@# clear all the way in at the entry angle, clear through the twist, and
	@# INTERFERING as soon as it is pulled from the locked pocket.
	python3 tools/bayonet_check.py
	$(OPENSCAD) --viewall --autocenter --projection=p --imgsize=1500,1100 \
		--camera=0,0,0,68,0,32,0 --colorscheme=Tomorrow \
		-D 'part="assembly"' -D exploded=true \
		-o $(OUT)/body-tube-preview.png $(BODY)

# The WHOLE probe, exploded and labelled -- head stack, board, cell, and the
# prototype-1 printed body. It imports the body STLs, so body-tube runs first.
# Prototype 1's whole body as ONE printed solid: the head with the printed tube
# fused to it, so there is no bonded joint and no adhesive to qualify. Depends on
# body-tube because it unions that target's STL -- build them out of order and
# the union is silently made from a stale tube.
.PHONY: monobody
monobody: body-tube
	$(OPENSCAD) --hardwarnings $(HEAD_END_PROV) -D 'joint="monolithic"' \
		-D 'part="monobody"' -o $(OUT)/body-monobody.stl $(HEAD_END) \
		2>$(OUT)/.mono.log || { cat $(OUT)/.mono.log; exit 1; }
	@# openscad EXITS 0 on a failed import(). A mistyped path made the monobody
	@# the head alone for who knows how long -- "ERROR: Unsupported file format"
	@# on stderr, exit 0, and a head by itself is a fine closed solid so
	@# `Volumes: 2` passed. Fail on ERROR as well as on the count.
	@if grep -q '^ERROR' $(OUT)/.mono.log; then \
		echo "FAIL monobody: openscad reported an ERROR and still exited 0:"; \
		grep '^ERROR' $(OUT)/.mono.log; \
		exit 1; \
	 fi
	@v=`sed -n 's/.*Volumes: *\([0-9]*\).*/\1/p' $(OUT)/.mono.log | tail -1`; \
	 if [ "$$v" != "2" ]; then \
		echo "FAIL monobody: $$v volumes, expected 2 -- the head and the tube did not fuse"; \
		exit 1; \
	 fi; rm -f $(OUT)/.mono.log
	@echo "monobody: head and tube fused into one closed solid"
	@# ...which `Volumes: 2` does NOT actually prove. Two cylinders sharing a
	@# face report 2 as well, and a tube LONGER than the head expects overlaps
	@# it, deletes material, and still reports 2. interface_check.py weighs the
	@# union against its parts and cross-checks every number the two files
	@# duplicate. 2026-09-05 Codex review, finding 7.
	python3 tools/interface_check.py

.PHONY: prototype-exploded
prototype-exploded: body-tube
	$(OPENSCAD) --hardwarnings $(HEAD_END_PROV) -D show_body=true \
		-D 'joint="monolithic"' \
		-D 'part="assembly"' -D exploded=true \
		--viewall --autocenter --projection=p --imgsize=1500,2300 \
		--camera=0,0,0,72,0,25,0 --colorscheme=Tomorrow \
		-o $(OUT)/prototype-exploded.png $(HEAD_END)
	cd .. && python3 cad/label-prototype.py

# The REAL KiCad board inside the body. Preview only -- 215k facets of board
# mesh, so never --render. The STL comes from KiCad 10's own exporter; rebuild
# it with `make board-mesh` when the board changes.
KICAD_CLI ?= /Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
HW := /Users/fab/dev/ee/hw/o2-probe

.PHONY: board-mesh
board-mesh: | $(OUT)
	cd $(HW) && $(KICAD_CLI) pcb export stl --force --no-dnp --subst-models \
		--include-tracks --include-pads \
		-o $(CURDIR)/$(OUT)/o2-probe-board.stl o2-probe.kicad_pcb
	python3 tools/stl_ascii_to_binary.py $(OUT)/o2-probe-board.stl \
		$(OUT)/o2-probe-board-bin.stl
	python3 tools/board_tip.py $(OUT)/o2-probe-board-bin.stl \
		$(OUT)/o2-probe-board-tip-30mm.stl

# The body with half of it cut away, baked by CGAL so the viewer has no CSG in
# it -- which is what makes View > Thrown Together usable on this model. A live
# difference() would draw its own 120 mm cutting block in that mode.
.PHONY: body-section
body-section: monobody | $(OUT)
	$(OPENSCAD) --hardwarnings --render -D 'part="cutbody"' \
		-o $(OUT)/body-monobody-section.stl o2_probe_board_in_body.scad

.PHONY: board-in-body
board-in-body: monobody body-section board-mesh | $(OUT)
	$(OPENSCAD) --viewall --autocenter --projection=p --imgsize=1500,1400 \
		--camera=0,0,0,68,0,25,0 --colorscheme=Tomorrow \
		-D 'part="section"' -o $(OUT)/board-in-body.png o2_probe_board_in_body.scad
	python3 tools/board_clearance.py

# Local three.js viewer: the printed body with the real KiCad board inside it.
# Every surface is DoubleSide, so nothing vanishes when you rotate past it --
# which is the one thing OpenSCAD's preview will not do. Served over http
# because file:// blocks the STL fetches; nothing leaves the machine.
# ------------------------------------------------------------------- viewer
# `make print-HEAD_END_PROV` -- tools/view.py reads the render flags from here
# rather than keeping its own copy, which is how a viewer ends up rendering a
# different part than the Makefile does.
#
# $(info), not echo: the values contain single quotes of their own
# (-D 'carrier_material="asa"'), and any echo -- however quoted -- hands them to
# a shell that eats them. The flags then arrive at OpenSCAD as bare identifiers,
# which is an UNDEF assignment, not a string. $(info) never sees a shell.
.PHONY: print-%
print-%:
	$(info $($*))
	@:

# One command for any part of any model. It renders what is missing or stale,
# picks a FREE port and opens the browser:
#     make view SCENE=bed                  (named scenes: tools/scenes.json)
#     make view PARTS="o2_probe_head_end.scad:carrier"
#     make view PARTS="exports/asa-carrier-print.stl"
#     python3 tools/view.py --list
.PHONY: view
view:
	@python3 tools/view.py $(if $(SCENE),--scene $(SCENE)) $(PARTS)

.PHONY: viewer viewer-parts
# The body+board scene keeps its generator, because that one READS DIMENSIONS
# out of the model to place the board and the cap -- tools/view.py cannot, and
# must not, guess them. Everything else goes through `make view`.
viewer-parts: monobody board-mesh
	python3 tools/make_viewer_parts.py

viewer: viewer-parts
	@python3 tools/view.py exports/body-monobody.stl --no-open --print >/dev/null || true
	@python3 -c "import webbrowser,sys; sys.exit(0)"
	@echo "serving on http://127.0.0.1:8777/viewer/?parts=parts.json   (ctrl-c to stop)"
	@(sleep 1; open "http://127.0.0.1:8777/viewer/?parts=parts.json") &
	@python3 -m http.server 8777 --bind 127.0.0.1
