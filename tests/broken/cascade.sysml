/* Cascade fixture: the ISQ/SI imports are missing, so every quantity type and unit is unresolved.
 * The pilot reports many errors; ./kit check must show only the first 12 and say "fix the FIRST". */
package Cascade {
    private import SYS5100Lib::*;
    part def Cart {
        attribute m0 : MassValue = 1 [kg];
        attribute m1 : MassValue = 2 [kg];
        attribute m2 : MassValue = 3 [kg];
        attribute m3 : MassValue = 4 [kg];
        attribute m4 : MassValue = 5 [kg];
        attribute m5 : MassValue = 6 [kg];
        attribute m6 : MassValue = 7 [kg];
        attribute m7 : MassValue = 8 [kg];
        attribute m8 : MassValue = 9 [kg];
        attribute m9 : MassValue = 10 [kg];
        attribute m10 : MassValue = 11 [kg];
        attribute m11 : MassValue = 12 [kg];
        attribute m12 : MassValue = 13 [kg];
        attribute m13 : MassValue = 14 [kg];
        attribute m14 : MassValue = 15 [kg];
        attribute m15 : MassValue = 16 [kg];
    }
}
