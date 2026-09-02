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
HEAD_END_PROV := -D tube_od_meas=32.0 -D board_env_front=3.5 -D board_env_back=1.5 \
                 -D cell_axial_len=13.0

head-end-provisional: | $(OUT)
	@for p in $(HEAD_END_PARTS); do \
		$(OPENSCAD) --hardwarnings $(HEAD_END_PROV) -D "part=\"$$p\"" \
			-o $(OUT)/head-end-$$p.stl $(HEAD_END); \
	done
	$(OPENSCAD) --render --viewall --autocenter --projection=p --imgsize=1400,1000 \
		--colorscheme=Tomorrow $(HEAD_END_PROV) -D 'part="assembly"' -D exploded=true \
		-o $(OUT)/head-end-preview.png $(HEAD_END)
	$(OPENSCAD) $(HEAD_END_PROV) -D 'part="plate"' -o $(OUT)/head-end-plate.3mf $(HEAD_END)
