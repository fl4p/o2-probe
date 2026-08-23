/*
 * O2 probe response candidate — communication model, NOT fabrication release.
 * Units: millimetres. Z runs from cable end toward sensing tip.
 *
 * Response-study constraints represented here:
 *   - measured effective local gas volume target <=5.0 cm3;
 *   - supported free PMV15T area target 180..190 mm2;
 *   - membrane dry-face-to-cavity access path <=0.25 mm;
 *   - two keyed, drainable lower-side membrane facets, one per PCB side;
 *   - both SGX gas faces and the provisional 3 mm rear PCB aperture open;
 *   - dry-side carrier heaters shown separately from the cell island.
 */

$fn = 96;
part = "assembly"; // assembly, enclosure, probe, shroud, seals, cartridges
exploded = false;

tube_od = 32;
tube_id = 28;
tube_length = 135;
pcb_width = 20;
pcb_length = 125;
pcb_thickness = 1;
pcb_z = 5;

cell_board_y = 107.5;
cell_z = pcb_z + cell_board_y;
cell_diameter = 14.4;
cell_height = 8.3;
rear_port_diameter = 3.0;

plenum_z0 = 101;
plenum_z1 = 124;
end_land = 3.55; // leaves 15.9 mm clear gas length around the 14.4 mm cell
shroud_od = 27.6;
shroud_id = 23.0; // compact spatial candidate; connected volume gate <=5.0 cm3

window_width = 10;
window_height = 10;
membrane_thickness = 0.18;
carrier_width = 15;
carrier_height = 15;
carrier_thickness = 2.0;
membrane_dry_gap = 0.25; // maximum gas path from membrane dry face to local cavity
carrier_inner_radius = shroud_id/2;
carrier_depth = tube_od/2 + carrier_thickness - carrier_inner_radius;
membrane_radius = shroud_id/2 + membrane_dry_gap;
window_angles = [45, 315]; // global atan2(Y,X): one PCB side each, both lower quadrants
facet_angles = [for (angle=window_angles) angle-90]; // cartridge local radial axis is +Y

eps = 0.03;

module rounded_board_2d(w, l, r) {
    hull()
        for (x=[-w/2+r, w/2-r], z=[r, l-r])
            translate([x,z]) circle(r=r, $fn=28);
}

module radial_cut(angle, width, height, zc) {
    rotate([0,0,angle])
        translate([-width/2, 0, zc-height/2])
            cube([width, tube_od, height]);
}

module candidate_enclosure() {
    color("#aeb9c1", 0.36)
        difference() {
            cylinder(d=tube_od, h=tube_length);
            translate([0,0,-eps]) cylinder(d=tube_id, h=tube_length+2*eps);
            for (angle=facet_angles)
                radial_cut(angle, window_width, window_height, cell_z);
        }
}

module candidate_probe() {
    color("#246c57")
        translate([0,0,pcb_z])
            rotate([90,0,0])
                linear_extrude(height=pcb_thickness, center=true)
                    rounded_board_2d(pcb_width, pcb_length, 2);

    // Thermally isolated cell island and its two main heater resistors.
    color("#bc7735") translate([-9,-0.68,cell_z-12]) cube([18,0.16,24]);
    for (x=[-6,6])
        color("#9a552c") translate([x-2.5,-1.1,cell_z-10]) cube([5,2.2,7]);

    // SGX cell axis normal to PCB; two gas faces remain lateral.
    color("#d5d7d4")
        translate([0,pcb_thickness/2,cell_z])
            rotate([-90,0,0]) cylinder(d=cell_diameter,h=cell_height);
    color("#939a99")
        translate([0,pcb_thickness/2+cell_height,cell_z])
            rotate([-90,0,0]) cylinder(d=10.6,h=0.4);

    // Visual rear routed aperture through the PCB, not a copper keepout.
    color("#111619")
        translate([0,-pcb_thickness/2-eps,cell_z])
            rotate([-90,0,0]) cylinder(d=rear_port_diameter,h=pcb_thickness+2*eps);
}

module local_shroud() {
    color("#e4e1d8", 0.72)
        difference() {
            union() {
                translate([0,0,plenum_z0])
                    difference() {
                        cylinder(d=shroud_od,h=plenum_z1-plenum_z0);
                        translate([0,0,-eps]) cylinder(d=shroud_id,h=plenum_z1-plenum_z0+2*eps);
                    }
                // End sealing lands; production seals must close around the board.
                for (z=[plenum_z0,plenum_z1-end_land])
                    translate([0,0,z])
                        difference() {
                            cylinder(d=shroud_od,h=end_land);
                            translate([-10.4,-1.0,-eps]) cube([20.8,2.0,end_land+2*eps]);
                        }
            }
            for (angle=facet_angles)
                radial_cut(angle,window_width+0.6,window_height+0.6,cell_z);
        }
}

module board_end_seals() {
    // Compressible overmould/gasket frames close the generous rigid shroud
    // slots around the PCB. The inner opening deliberately interferes with the
    // nominal PCB envelope; material/process detail is still a release item.
    for (z=[plenum_z0,plenum_z1-end_land])
        color("#202427")
            translate([-10.4,-1.0,z])
                difference() {
                    cube([20.8,2.0,end_land]);
                    translate([0.5,0.55,-eps]) cube([19.8,0.9,end_land+2*eps]);
                }
}

module circumferential_shroud_seals() {
    // Continuous bond/overmould fills the entire shroud/tube annulus. It is a
    // seal and volume displacement, not connected gas inventory.
    color("#202427")
        translate([0,0,plenum_z0])
            difference() {
                cylinder(d=tube_id+0.1,h=plenum_z1-plenum_z0);
                translate([0,0,-eps])
                    cylinder(d=shroud_od-0.1,h=plenum_z1-plenum_z0+2*eps);
            }
}

module all_seals() {
    board_end_seals();
    circumferential_shroud_seals();
}

module one_cartridge(angle) {
    rotate([0,0,angle]) {
        // Deep keyed PP well: the coupon sits at its inner end, only 0.25 mm
        // from the connected cavity. The open outer well is external to the
        // membrane and must stay drainable behind the stand-off guard.
        color("#ece8dc")
            translate([-carrier_width/2,carrier_inner_radius,cell_z-carrier_height/2])
                difference() {
                    cube([carrier_width,carrier_depth,carrier_height]);
                    translate([(carrier_width-window_width)/2,-eps,(carrier_height-window_height)/2])
                        cube([window_width,carrier_depth+2*eps,window_height]);
                }

        // PMV15T coupon; visual only, never print as the functional membrane.
        color("#f7f3e7",0.85)
            translate([-window_width/2,membrane_radius,cell_z-window_height/2])
                cube([window_width,membrane_thickness,window_height]);

        // Smooth PP cross support: two 0.4 mm bars obstruct ~7.8% of each
        // 10x10 aperture, leaving ~184 mm2 projected free area across two facets.
        color("#dedbd1") {
            translate([-0.2,membrane_radius+membrane_thickness,cell_z-window_height/2])
                cube([0.4,0.28,window_height]);
            translate([-window_width/2,membrane_radius+membrane_thickness,cell_z-0.2])
                cube([window_width,0.28,0.4]);
        }

        // Dry-side low-power carrier heater beside the recessed coupon.
        color("#c87932")
            translate([-carrier_width/2+0.8,membrane_radius-0.22,cell_z-carrier_height/2+0.8])
                difference() {
                    cube([carrier_width-1.6,0.22,carrier_height-1.6]);
                    translate([(carrier_width-window_width)/2-0.8,-eps,(carrier_height-window_height)/2-0.8])
                        cube([window_width,0.22+2*eps,window_height]);
                }

        // Stand-off coarse guard: open lower edge is the drain.
        color("#d56b3f")
            for (x=[-6,-2,2,6])
                translate([x-0.45,tube_od/2+4.0,cell_z-7]) cube([0.9,1.0,13]);
        color("#d56b3f")
            translate([-7,tube_od/2+4.0,cell_z+6]) cube([14,1.0,1.0]);
    }
}

module cartridges() {
    for (angle=facet_angles) one_cartridge(angle);
}

module assembly(explode=false) {
    e = explode ? 18 : 0;
    candidate_enclosure();
    translate([-e,0,0]) candidate_probe();
    translate([e*0.25,0,0]) local_shroud();
    translate([e*0.25,0,0]) all_seals();
    translate([e,0,0]) cartridges();
}

if (part == "enclosure") candidate_enclosure();
else if (part == "probe") candidate_probe();
else if (part == "shroud") local_shroud();
else if (part == "seals") all_seals();
else if (part == "cartridges") cartridges();
else assembly(exploded);
