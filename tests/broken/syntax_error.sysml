/* Syntax-error fixture: one missing ';' (line 9) and one keyword used as a name (line 12).
 * The pilot reports several errors; ./kit check must show at most 12 and say "fix the FIRST". */
package SyntaxBroken {
    private import ISQ::*;
    private import SI::*;
    private import SYS5100Lib::*;
    part def Cart {
        attribute mass : MassValue
        attribute width : LengthValue;
    }
    part def Shelf { attribute part : MassValue; }
    part cart : Cart { attribute :>> mass = 4 [kg]; }
    requirement <'X-01'> light {
        doc /* The cart shall have a mass of 5 kg or less. */
        subject c : Cart;
        require constraint { c.mass <= 5 [kg] }
    }
    satisfy light by cart;
}
