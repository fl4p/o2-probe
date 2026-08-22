OPENSCAD ?= openscad
SOURCE := o2_probe_rev_a.scad
OUT := exports

.PHONY: all clean preview

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

clean:
	rm -f $(OUT)/enclosure.stl $(OUT)/probe_mockup.stl $(OUT)/membrane_cartridge.stl $(OUT)/diffusion_head.stl $(OUT)/sensor_head.stl $(OUT)/cable_cap.stl $(OUT)/o2_probe_assembly.3mf $(OUT)/exploded-preview.png
