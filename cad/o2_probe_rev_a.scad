/*
 * O2 probe Rev-A mechanical study
 * Units: millimetres. Z runs from the cable end toward the sensing tip.
 *
 * This is a parametric fit/communication model, not released geometry.
 * Production dimensions remain gated by the actual tube, PCB assembly,
 * SGX-OX-ROHS-Mini sample, membrane stack and potting fixture.
 */

$fn = 96;

part = "assembly";   // assembly, enclosure, probe, membrane, head, cap
exploded = false;

// Controlled PCB and cell dimensions.
pcb_width = 20;
pcb_length = 125;
pcb_thickness = 1;
pcb_z = 5;
pot_datum = pcb_z + 82;
cell_z = pcb_z + 93.5;
cell_diameter = 14.4;
cell_height = 8.3;

// Provisional enclosure interfaces.
tube_od = 32;
tube_id = 28;
tube_length = 135;
head_overlap = 10;
head_od = 36;
head_length = 40;
fit_clearance = 0.20;       // radial slip-fit allowance for prototypes
carrier_od = 27.3;
carrier_opening = 18.8;
carrier_thickness = 2.0;
membrane_thickness = 0.18;
cable_diameter = 6.4;

eps = 0.03;

module enclosure() {
    union() {
        difference() {
            cylinder(d=tube_od, h=tube_length);
            translate([0, 0, -eps]) cylinder(d=tube_id, h=tube_length + 2*eps);
        }

        // Four PCB-edge guide ribs. The 1.4 mm central slit accepts the
        // nominal 1.0 mm PCB and leaves coating/fit allowance.
        for (sx=[-1, 1], sy=[-1, 1]) {
            translate([
                sx < 0 ? -tube_id/2 : pcb_width/2,
                sy < 0 ? -2.0 : 0.7,
                pcb_z + 8
            ])
                cube([tube_id/2 - pcb_width/2, 1.3, 105]);
        }
    }
}

module rounded_board_2d(w, l, r) {
    hull() {
        for (x=[-w/2+r, w/2-r], z=[r, l-r])
            translate([x, z]) circle(r=r, $fn=28);
    }
}

module pcb_plate() {
    color("#246c57")
        rotate([90, 0, 0])
            linear_extrude(height=pcb_thickness, center=true)
                rounded_board_2d(pcb_width, pcb_length, 2);
}

module component_box(x, z, w, l, h, c="#1a2024") {
    color(c) translate([x-w/2, pcb_thickness/2, z-l/2]) cube([w, h, l]);
}

module probe() {
    translate([0, 0, pcb_z]) pcb_plate();

    // Cable lands and representative component envelope.
    for (x=[-7.5, -2.5, 2.5, 7.5])
        color("#d4aa3f") translate([x-1.6, pcb_thickness/2+0.01, pcb_z+1]) cube([3.2, 0.18, 6.2]);

    component_box(-5, pcb_z+17.5, 6, 8, 3.4);
    component_box(4.5, pcb_z+19.5, 7.2, 9, 4.5);
    component_box(0, pcb_z+37.5, 10, 12, 4.2);
    component_box(-5.8, pcb_z+56.5, 5.4, 7.2, 3.1);
    component_box(4.8, pcb_z+70.5, 6.4, 8.4, 3.5);

    // Potting datum and heater island are visually explicit.
    color("#ef6c4a") translate([-pcb_width/2-0.2, -0.65, pot_datum-0.28]) cube([pcb_width+0.4, 1.3, 0.56]);
    color("#bc7735") translate([-9, -0.68, pcb_z+86]) cube([18, 0.16, 22]);

    // SGX cell, axis normal to the PCB. Centre matches the controlled datum.
    color("#d5d7d4")
        translate([0, pcb_thickness/2, cell_z])
            rotate([-90, 0, 0]) cylinder(d=cell_diameter, h=cell_height);
    color("#939a99")
        translate([0, pcb_thickness/2+cell_height, cell_z])
            rotate([-90, 0, 0]) cylinder(d=10.6, h=0.4);

    for (x=[-2.54, 0, 2.54])
        color("#d4aa3f")
            translate([x, -1.6, cell_z-2.5])
                rotate([-90, 0, 0]) cylinder(d=0.64, h=2.5, $fn=16);
}

module membrane() {
    // PP carrier ring.
    color("#ece8dc")
        difference() {
            cylinder(d=carrier_od, h=carrier_thickness);
            translate([0,0,-eps]) cylinder(d=carrier_opening, h=carrier_thickness+2*eps);
        }

    // Nominal 0.18 mm PMV15T coupon. This surface is visual geometry, not a
    // suggestion to print the functional membrane.
    color("#f7f3e7", 0.82)
        translate([0,0,carrier_thickness]) cylinder(d=carrier_opening-0.3, h=membrane_thickness);

    // Smooth PP support grid, kept off the compost-facing debris guard.
    color("#dedbd1")
        intersection() {
            translate([0,0,carrier_thickness+membrane_thickness])
                union() {
                    for (v=[-4.5, 0, 4.5]) {
                        translate([-8.8, v-0.38, 0]) cube([17.6, 0.76, 0.28]);
                        translate([v-0.38, -8.8, 0]) cube([0.76, 17.6, 0.28]);
                    }
                }
            translate([0,0,carrier_thickness+membrane_thickness-eps])
                cylinder(d=carrier_opening-0.5, h=0.34);
        }
}

module sensor_head() {
    difference() {
        union() {
            // Clamp collar and lower membrane shoulder.
            cylinder(d=head_od, h=14);
            translate([0,0,14]) cylinder(d=head_od, h=head_length-14);
        }

        // Slip over the enclosure for the first 10 mm.
        translate([0,0,-eps]) cylinder(d=tube_od + 2*fit_clearance, h=head_overlap+eps);

        // Carrier pocket and open stand-off chamber.
        translate([0,0,head_overlap]) cylinder(d=carrier_od+0.35, h=4.1);
        translate([0,0,14-eps]) cylinder(d=24, h=head_length-16+eps);

        // Eight lateral/downslope coarse-guard windows.
        for (a=[0:45:315])
            rotate([0,0,a]) translate([-4.2, 10.5, 18]) cube([8.4, 12, 16]);

        // Axial drainage hole and six smaller drain apertures.
        translate([0,0,head_length-2.1]) cylinder(d=7, h=3);
        for (a=[0:60:300])
            rotate([0,0,a]) translate([9.5,0,head_length-2.1]) cylinder(d=3.2, h=3);
    }
}

module cable_cap() {
    difference() {
        union() {
            cylinder(d=tube_id-0.4, h=14);
            translate([0,0,-3.5]) cylinder(d=head_od, h=3.5);
        }
        // Water-blocked cable passage, offset from the PCB plane.
        translate([0,6,-4]) cylinder(d=cable_diameter, h=19);
        // Board-locating slot continues through the potted plug.
        translate([-10.4,-0.7,5]) cube([20.8,1.4,10]);
    }

    // Overlap the flange by 0.2 mm so the exported cap remains manifold.
    color("#111619") translate([0,6,-23.5]) cylinder(d=cable_diameter, h=20.2);
}

module assembly(explode=false) {
    e = explode ? 46 : 0;

    color("#b7c1c9", 0.32) enclosure();
    translate([-e,0,0]) probe();
    translate([e,0,tube_length+2]) membrane();
    translate([e*1.25,0,tube_length-head_overlap]) color("#d96735") sensor_head();
    translate([-e*0.6,0,0]) color("#252b2f") cable_cap();
}

if (part == "enclosure") enclosure();
else if (part == "probe") probe();
else if (part == "membrane") membrane();
else if (part == "head") sensor_head();
else if (part == "cap") cable_cap();
else assembly(exploded);
