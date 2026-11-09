/*
 * SYS 5100 starter model S5: partner-sourced problem (blank scaffold).
 * Replace every TODO. Keep the shape: concerns -> requirements (with evidence) -> parts ->
 * satisfy -> verification. ./kit check will WARN on TODO text until G4, then FAIL.
 * Check it:  ./kit check        Tables:  ./kit gen-table
 */
package PartnerSystem {                       // TODO: rename to your team's system name
    private import ScalarValues::*;
    private import ISQ::*;
    private import SI::*;
    private import SYS5100Lib::*;

    package Stakeholders {
        doc /* TODO: who has a stake? Use your whose-system map (rights-holders, affected, future). */
        part def PartnerOrganisation;         // TODO: the partner who brought the problem
        part def AffectedPerson;              // TODO: someone affected but not involved

        concern def FirstConcern {
            doc /* TODO: what this stakeholder worries about, in their words (cite INT-nn). */
            subject sys : Structure::OurSystem;
            stakeholder partner : PartnerOrganisation;
            stakeholder affected : AffectedPerson;
        }
        concern firstConcern : FirstConcern;
    }

    package Structure {
        doc /* TODO: system -> elements. Add port defs and interface defs as interfaces appear. */
        item def TODOFlow;                    // TODO: what moves between elements (power, data, material)

        port def FlowPort { out item f : TODOFlow; }
        interface def FlowLink { end source : FlowPort; end sink : ~FlowPort; }

        part def ElementA {
            attribute mass : MassValue;       // TODO: replace with the quantities that matter to you
            port out1 : FlowPort;
        }
        part def ElementB {
            attribute mass : MassValue;
            port in1 : ~FlowPort;
        }
        part def OurSystem {
            part a : ElementA;
            part b : ElementB;
            interface link : FlowLink connect a.out1 to b.in1;
        }

        // The configured design point. Every value: a basis label and an evidence source.
        part design : OurSystem {
            part :>> a { attribute :>> mass = 1.0 [kg] { @Budget { basis = Basis::assumed; growth = 0.20; } } }
            part :>> b { attribute :>> mass = 2.0 [kg] { @Budget { basis = Basis::assumed; growth = 0.20; } } }
        }
    }

    package Requirements {
        doc /* TODO: choose a team prefix (e.g. PS-) and number from 01. */
        private import Structure::*;
        private import Stakeholders::*;

        requirement <'PS-01'> firstRequirement {
            doc /* TODO: The system shall <do what> <how well> <under what condition>. */
            @Evidence { grade = Basis::assumed; source = "HYP-01"; }
            subject sys : OurSystem;
            frame firstConcern;
            attribute massMax : MassValue = 10 [kg];     // TODO: a budget limit (C4 rolls up 'mass')
            require constraint { sys.a.mass + sys.b.mass <= massMax }
        }
    }

    package Verification {
        private import Structure::*;
        private import Requirements::*;

        verification def FirstCheck {
            doc /* Inspection: TODO describe how you will show PS-01 is met (test, analysis, inspection, demonstration). */
            subject sys : OurSystem;
            objective { verify firstRequirement; }
        }
        verification firstCheck : FirstCheck { subject :>> sys = design; }
    }

    package Traceability {
        private import Requirements::*;
        private import Structure::*;
        satisfy firstRequirement by design;
    }
}
