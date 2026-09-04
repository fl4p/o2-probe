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
	@v=`sed -n 's/.*Volumes: *\([0-9]*\).*/\1/p' $(OUT)/.mono.log | tail -1`; \
	 if [ "$$v" != "2" ]; then \
		echo "FAIL monobody: $$v volumes, expected 2 -- the head and the tube did not fuse"; \
		exit 1; \
	 fi; rm -f $(OUT)/.mono.log
	@echo "monobody: head and tube fused into one closed solid"

.PHONY: prototype-exploded
prototype-exploded: body-tube
	$(OPENSCAD) --hardwarnings $(HEAD_END_PROV) -D show_body=true \
		-D 'joint="monolithic"' \
		-D 'part="assembly"' -D exploded=true \
		--viewall --autocenter --projection=p --imgsize=1500,2300 \
		--camera=0,0,0,72,0,25,0 --colorscheme=Tomorrow \
		-o $(OUT)/prototype-exploded.png $(HEAD_END)
	cd .. && python3 cad/label-prototype.py
