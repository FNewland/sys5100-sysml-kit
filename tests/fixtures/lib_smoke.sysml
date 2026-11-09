package LibSmoke {
    private import SYS5100Lib::*;
    private import ISQ::*;
    private import SI::*;
    private import VerificationCases::*;
    part def Box { attribute mass : MassValue; }
    part box : Box {
        attribute :>> mass = 2 [kg] { @Evidence { grade = Basis::measured; source = "OBS-01"; } @Budget { basis = Basis::measured; growth = 0.05; } }
        @ChangeRecord { crId = "CR-001"; status = CRStatus::approved; decidedBy = "CCB-01"; }
    }
    requirement <'T-01'> light {
        doc /* The box shall have a mass of 3 kg or less. */
        @RiskLink { riskId = "R-01"; threat = "none"; }
        @Baseline { tag = "G2-baseline"; }
        subject b : Box;
        require constraint { b.mass <= 3 [kg] }
    }
    satisfy light by box;
    verification def Weigh { subject b : Box; objective { verify light; } }
    verification weigh : Weigh { subject :>> b = box;
        @TestVerdict { verdict = VerdictKind::pass; asRun = "TD-01"; ncr = "none"; } }
}
