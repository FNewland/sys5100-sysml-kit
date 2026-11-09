/*
 * SYS 5100 starter model S2: remote-community microgrid.
 * PV + battery + inverter serving a clinic, a water plant and homes. All numbers are
 * illustrative or assumed until your team replaces them with evidence (see @Budget/@Evidence).
 * The battery carries change record CR-004 (NMC -> LFP, approved by CCB-07): see Week 11.
 * Expect one C4 WARN out of the box: growth allowances eat the 20 % system margin on peak
 * supply. That is a design conversation for G2, not a modelling error.
 * Check it:  ./kit check        Tables:  ./kit gen-table
 */
package RemoteMicrogrid {
    private import ScalarValues::*;
    private import ISQ::*;
    private import SI::*;
    private import SYS5100Lib::*;

    package Stakeholders {
        doc /* Who has a stake. The community energy committee operates and owns the system. */
        part def EnergyCommittee;
        part def ClinicStaff;
        part def Household;
        part def MaintenanceTechnician;

        concern def CriticalServiceContinuity {
            doc /* The clinic and the water plant keep running through an outage. */
            subject mg : Structure::Microgrid;
            stakeholder clinic : ClinicStaff;
            stakeholder committee : EnergyCommittee;
        }
        concern def EnergySovereignty {
            doc /* The community decides how the system runs and depends less on fuel deliveries. */
            subject mg : Structure::Microgrid;
            stakeholder committee : EnergyCommittee;
            stakeholder households : Household;
        }
        concern def LocalMaintainability {
            doc /* People who live there can keep it working with tools and parts they can get. */
            subject mg : Structure::Microgrid;
            stakeholder technician : MaintenanceTechnician;
        }
        concern criticalServiceContinuity : CriticalServiceContinuity;
        concern energySovereignty : EnergySovereignty;
        concern localMaintainability : LocalMaintainability;
    }

    package Structure {
        doc /* Sources and storage feed an inverter that supplies three load groups. */
        item def DCPower;
        item def ACPower;
        item def ControlSignal;

        port def DCPort      { out item p : DCPower; }
        port def ACPort      { out item p : ACPower; }
        port def ControlPort { out item c : ControlSignal; }

        interface def DCLink      { end source : DCPort;      end sink : ~DCPort; }
        interface def ACLink      { end source : ACPort;      end sink : ~ACPort; }
        interface def ControlLink { end source : ControlPort; end sink : ~ControlPort; }

        part def PVArray     { attribute ratedPower : PowerValue; port dcOut : DCPort; }
        part def BatteryBank {
            attribute capacity : EnergyValue;
            attribute usableFraction : Real;
            port dcOut : DCPort;
        }
        part def Inverter {
            attribute ratedPower : PowerValue;
            port pvIn : ~DCPort;
            port battIn : ~DCPort;
            port ctrlIn : ~ControlPort;
            port acOut : ACPort;
        }
        part def Controller { port ctrlOut : ControlPort; }
        part def Load {
            attribute peakPower : PowerValue;
            attribute averagePower : PowerValue;
            port acIn : ~ACPort;
        }

        part def Microgrid {
            part pv : PVArray;
            part battery : BatteryBank;
            part inverter : Inverter;
            part controller : Controller;
            part clinic : Load;
            part water : Load;
            part homes : Load;
            interface pvFeed   : DCLink      connect pv.dcOut to inverter.pvIn;
            interface battFeed : DCLink      connect battery.dcOut to inverter.battIn;
            interface control  : ControlLink connect controller.ctrlOut to inverter.ctrlIn;
            interface toClinic : ACLink      connect inverter.acOut to clinic.acIn;
            interface toWater  : ACLink      connect inverter.acOut to water.acIn;
            interface toHomes  : ACLink      connect inverter.acOut to homes.acIn;
        }

        part village : Microgrid {
            part :>> pv {
                attribute :>> ratedPower = 75 [kW] { @Evidence { grade = Basis::estimated; source = "DOC-02"; } }
            }
            part :>> battery {
                doc /* Storage chemistry changed from NMC to LFP by CR-004 (supplier lead time). */
                @ChangeRecord { crId = "CR-004"; status = CRStatus::approved; decidedBy = "CCB-07"; }
                attribute :>> capacity = 180 [kW*h] { @Evidence { grade = Basis::specified; source = "DOC-03"; } }
                attribute :>> usableFraction = 0.90 { @Evidence { grade = Basis::assumed; source = "HYP-02"; } }
            }
            part :>> inverter {
                attribute :>> ratedPower = 60 [kW] { @Budget { basis = Basis::calculated; growth = 0.0; } }
            }
            part :>> clinic {
                attribute :>> peakPower = 14 [kW]      { @Budget { basis = Basis::estimated; growth = 0.10; } }
                attribute :>> averagePower = 1.2 [kW]  { @Evidence { grade = Basis::estimated; source = "INT-04"; } }
            }
            part :>> water {
                attribute :>> peakPower = 9 [kW]       { @Budget { basis = Basis::estimated; growth = 0.10; } }
                attribute :>> averagePower = 0.8 [kW]  { @Evidence { grade = Basis::assumed; source = "HYP-03"; } }
            }
            part :>> homes {
                attribute :>> peakPower = 22 [kW]      { @Budget { basis = Basis::assumed; growth = 0.20; } }
                attribute :>> averagePower = 6.0 [kW]  { @Evidence { grade = Basis::assumed; source = "HYP-04"; } }
            }
        }
    }

    package Requirements {
        doc /* Team prefix MG-R. Each requirement names its evidence source. */
        private import Structure::*;
        private import Stakeholders::*;

        requirement def MicrogridRequirement { subject mg : Microgrid; }

        requirement <'MG-R01'> renewableShare : MicrogridRequirement {
            doc /* The microgrid shall supply at least 70 % of the community's annual electricity from on-site renewable sources. */
            @Evidence { grade = Basis::specified; source = "INT-01"; }
            frame energySovereignty;
        }
        requirement <'MG-R07'> peakSupply : MicrogridRequirement {
            doc /* The microgrid shall supply the combined peak load with at least 20 % system margin. */
            @Evidence { grade = Basis::specified; source = "DOC-01"; }
            frame criticalServiceContinuity;
            attribute systemMargin : Real = 0.20;
            attribute peakPowerMax : PowerValue = mg.inverter.ratedPower;
            require constraint { (mg.clinic.peakPower + mg.water.peakPower + mg.homes.peakPower)
                                 * (1 + systemMargin) <= mg.inverter.ratedPower }
        }
        requirement <'MG-R08'> outageAutonomy : MicrogridRequirement {
            doc /* The microgrid shall supply the clinic and the water plant for 72 h without diesel, with at least 10 % energy margin. */
            @Evidence { grade = Basis::specified; source = "INT-02"; }
            @Baseline { tag = "ABL-1.1"; }
            frame criticalServiceContinuity;
            attribute outageDuration : DurationValue = 72 [h];
            attribute supply : EnergyValue = mg.battery.capacity * mg.battery.usableFraction;
            attribute demand : EnergyValue = (mg.clinic.averagePower + mg.water.averagePower) * outageDuration;
            attribute marginMin : Real = 0.10;
        }
        requirement <'MG-R09'> moduleSwap : MicrogridRequirement {
            doc /* A trained community technician shall replace one battery module with hand tools in 2 h or less. */
            @Evidence { grade = Basis::specified; source = "INT-03"; }
            frame localMaintainability;
        }
        requirement <'MG-R10'> takeBack : MicrogridRequirement {
            doc /* Each battery module shall be covered by a supplier take-back agreement at end of life. */
            @Evidence { grade = Basis::assumed; source = "HYP-01"; }
            frame energySovereignty;
        }
    }

    package Verification {
        doc /* Method first in each doc: Test, Analysis, Inspection, Demonstration. */
        private import Structure::*;
        private import Requirements::*;

        verification def EnergyYieldAnalysis {
            doc /* Analysis: hourly simulation of one year of PV yield and load with local weather data. */
            subject mg : Microgrid;
            objective { verify renewableShare; verify peakSupply; }
        }
        verification def OutageBenchTest {
            doc /* Test: 72 h outage on the bench node with scaled critical loads; log state of charge. */
            subject mg : Microgrid;
            objective { verify outageAutonomy; }
        }
        verification def ModuleSwapDemo {
            doc /* Demonstration: a community technician swaps a module, timed, after training. */
            subject mg : Microgrid;
            objective { verify moduleSwap; }
        }
        verification def ContractInspection {
            doc /* Inspection: check the supply agreement for a take-back clause covering every module. */
            subject mg : Microgrid;
            objective { verify takeBack; }
        }
        verification yieldAnalysis : EnergyYieldAnalysis { subject :>> mg = village; }
        verification outageTest : OutageBenchTest { subject :>> mg = village; }
        verification swapDemo : ModuleSwapDemo { subject :>> mg = village; }
        verification contractCheck : ContractInspection { subject :>> mg = village; }
    }

    package Traceability {
        private import Requirements::*;
        private import Structure::*;
        satisfy renewableShare by village;
        satisfy peakSupply     by village;
        satisfy outageAutonomy by village;
        satisfy moduleSwap     by village;
        satisfy takeBack       by village;
    }
}
