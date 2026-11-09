/*
 * SYS 5100 starter model S4: GNSS-denied road navigation.
 * A navigation unit fuses a GNSS receiver, an inertial unit and wheel odometry, and must
 * notice when GNSS is jammed or spoofed. Numbers are illustrative or assumed; your values come
 * from the GNSS-denied navigation simulator (teaching copy) and your interviews.
 * Check it:  ./kit check        Tables:  ./kit gen-table
 */
package GnssDeniedNav {
    private import ScalarValues::*;
    private import ISQ::*;
    private import SI::*;
    private import SYS5100Lib::*;

    package Stakeholders {
        doc /* Who has a stake, including people where the vehicle operates. */
        part def Driver;
        part def RescueCoordinator;
        part def PeopleNearby;

        concern def PositionIntegrity {
            doc /* The driver and the coordinator know when the position can be trusted. */
            subject nav : Structure::NavUnit;
            stakeholder driver : Driver;
            stakeholder coordinator : RescueCoordinator;
        }
        concern def ContinuityWithoutGnss {
            doc /* Guidance continues through tunnels, jamming and urban canyons. */
            subject nav : Structure::NavUnit;
            stakeholder driver : Driver;
        }
        concern def PrivacyOfPeopleNearby {
            doc /* Position logs do not become a record of other people's movements. */
            subject nav : Structure::NavUnit;
            stakeholder people : PeopleNearby;
        }
        concern positionIntegrity : PositionIntegrity;
        concern continuityWithoutGnss : ContinuityWithoutGnss;
        concern privacyOfPeopleNearby : PrivacyOfPeopleNearby;
    }

    package Structure {
        doc /* Interface to the GNSS receiver follows the integration spec (teaching copy). */
        private import Behaviour::*;
        item def PositionFix;
        item def InertialData;
        item def WheelTicks;
        item def Guidance;

        port def FixPort      { out item fix : PositionFix; }
        port def ImuPort      { out item imu : InertialData; }
        port def OdoPort      { out item ticks : WheelTicks; }
        port def GuidancePort { out item g : Guidance; }

        interface def ReceiverLink { end rxEnd : FixPort;      end navEnd : ~FixPort; }
        interface def ImuLink      { end src : ImuPort;        end dst : ~ImuPort; }
        interface def OdoLink      { end src : OdoPort;        end dst : ~OdoPort; }
        interface def DisplayLink  { end src : GuidancePort;   end dst : ~GuidancePort; }

        part def GnssReceiver {
            attribute fixRate : FrequencyValue;
            attribute detectionTime : DurationValue;    // one fix interval
            port fixOut : FixPort;
        }
        part def InertialUnit  { port imuOut : ImuPort; }
        part def WheelOdometer { port odoOut : OdoPort; }
        part def NavComputer {
            attribute driftRate : SpeedValue;           // dead-reckoning position error growth
            attribute spoofThreshold : LengthValue;     // GNSS vs dead-reckoning disagreement that flags a fix
            attribute detectionTime : DurationValue;    // consistency-check window
            attribute logRetention : DurationValue;
            port fixIn : ~FixPort;
            port imuIn : ~ImuPort;
            port odoIn : ~OdoPort;
            port guidanceOut : GuidancePort;
        }
        part def DriverDisplay {
            attribute detectionTime : DurationValue;    // time to show the 'GNSS untrusted' flag
            port guidanceIn : ~GuidancePort;
        }
        part def PositionEstimator;                      // logical element (what)

        part def NavUnit {
            part rx : GnssReceiver;
            part imu : InertialUnit;
            part odo : WheelOdometer;
            part nav : NavComputer;
            part display : DriverDisplay;
            interface rxToNav  : ReceiverLink connect rx.fixOut to nav.fixIn;
            interface imuToNav : ImuLink      connect imu.imuOut to nav.imuIn;
            interface odoToNav : OdoLink      connect odo.odoOut to nav.odoIn;
            interface navToDisplay : DisplayLink connect nav.guidanceOut to display.guidanceIn;
            exhibit state modes : NavModes;
        }

        part testVehicleNav : NavUnit {
            part :>> rx {
                attribute :>> fixRate = 5 [Hz]           { @Evidence { grade = Basis::specified; source = "DOC-01"; } }
                attribute :>> detectionTime = 0.2 [s]    { @Budget { basis = Basis::specified; growth = 0.0; } }
            }
            part :>> nav {
                attribute :>> driftRate = 0.25 [m/s]     { @Evidence { grade = Basis::estimated; source = "DOC-02"; } }
                attribute :>> spoofThreshold = 50 [m]    { @Evidence { grade = Basis::assumed; source = "HYP-01"; } }
                attribute :>> detectionTime = 1.0 [s]    { @Budget { basis = Basis::assumed; growth = 0.20; } }
                attribute :>> logRetention = 24 [h]      { @Evidence { grade = Basis::specified; source = "INT-04"; } }
            }
            part :>> display {
                attribute :>> detectionTime = 0.1 [s]    { @Budget { basis = Basis::estimated; growth = 0.10; } }
            }
        }
        part logical { part estimator : PositionEstimator; }
        allocate logical.estimator to testVehicleNav.nav;
    }

    package Behaviour {
        doc /* Navigation modes (read-only in the starter). */
        attribute def FixRejected;
        attribute def GnssLost;
        attribute def FixesConsistent;
        attribute def ErrorLimitReached;
        attribute def DriverAcknowledges;

        state def NavModes {
            entry; then gnssTrusted;
            state gnssTrusted;
            state gnssSuspect;
            state deadReckoning;
            state guidanceSuspended;

            transition trusted_to_suspect  first gnssTrusted   accept FixRejected        then gnssSuspect;
            transition trusted_to_dr       first gnssTrusted   accept GnssLost           then deadReckoning;
            transition suspect_to_dr       first gnssSuspect   accept GnssLost           then deadReckoning;
            transition suspect_to_trusted  first gnssSuspect   accept FixesConsistent    then gnssTrusted;
            transition dr_to_trusted       first deadReckoning accept FixesConsistent    then gnssTrusted;
            transition dr_to_suspended     first deadReckoning accept ErrorLimitReached  then guidanceSuspended;
            transition suspended_to_dr     first guidanceSuspended accept DriverAcknowledges then deadReckoning;
        }
    }

    package Requirements {
        doc /* Team prefix GN. */
        private import Structure::*;
        private import Stakeholders::*;

        requirement def NavRequirement { subject nav : NavUnit; }

        requirement <'GN-01'> fixInterface : NavRequirement {
            doc /* The navigation computer shall accept position fixes from the GNSS receiver at 5 Hz or more. */
            @Evidence { grade = Basis::specified; source = "DOC-01"; }
            frame positionIntegrity;
            require constraint { nav.rx.fixRate >= 5 [Hz] }
        }
        requirement <'GN-03'> deadReckoningError : NavRequirement {
            doc /* After 60 s without a trusted GNSS fix, the horizontal position error shall not exceed 20 m. */
            @Evidence { grade = Basis::specified; source = "INT-01"; }
            frame continuityWithoutGnss;
            attribute outageTime : DurationValue = 60 [s];
            attribute errorLimit : LengthValue = 20 [m];
            require constraint { nav.nav.driftRate * outageTime <= errorLimit }
        }
        requirement <'GN-05'> spoofingDetection : NavRequirement {
            doc /* The navigation unit shall flag a GNSS fix as untrusted within 2 s when the fix disagrees with the dead-reckoning estimate by more than 50 m. */
            @Evidence { grade = Basis::specified; source = "INT-02"; }
            @RiskLink { riskId = "R-03"; threat = "STRIDE-S: spoofed GNSS signal pulls the position estimate"; }
            frame positionIntegrity;
            attribute detectionTimeMax : DurationValue = 2 [s];
            require constraint { nav.nav.spoofThreshold <= 50 [m] }
        }
        requirement <'GN-07'> logRetention : NavRequirement {
            doc /* The navigation unit shall delete raw position logs within 24 h unless the driver flags an incident. */
            @Evidence { grade = Basis::specified; source = "INT-04"; }
            frame privacyOfPeopleNearby;
            require constraint { nav.nav.logRetention <= 24 [h] }
        }
    }

    package Verification {
        private import Structure::*;
        private import Requirements::*;

        verification def InterfaceTest {
            doc /* Test: replay recorded receiver output at 5 Hz and 10 Hz; check every fix is accepted. */
            subject nav : NavUnit;
            objective { verify fixInterface; }
        }
        verification def OutageSimulation {
            doc /* Analysis: simulator runs with GNSS removed for 60 s on 20 recorded routes; report P95 error. */
            subject nav : NavUnit;
            objective { verify deadReckoningError; }
        }
        verification def SpoofInjectionTest {
            doc /* Test: inject position offsets of 30, 60 and 200 m in the simulator; time the untrusted flag. */
            subject nav : NavUnit;
            objective { verify spoofingDetection; }
        }
        verification def LogInspection {
            doc /* Inspection: review log-deletion code and a 48 h soak-test log directory. */
            subject nav : NavUnit;
            objective { verify logRetention; }
        }
        verification interfaceTest : InterfaceTest { subject :>> nav = testVehicleNav; }
        verification outageSim : OutageSimulation { subject :>> nav = testVehicleNav; }
        verification spoofTest : SpoofInjectionTest { subject :>> nav = testVehicleNav; }
        verification logCheck : LogInspection { subject :>> nav = testVehicleNav; }
    }

    package Traceability {
        private import Requirements::*;
        private import Structure::*;
        satisfy fixInterface       by testVehicleNav;
        satisfy deadReckoningError by testVehicleNav;
        satisfy spoofingDetection  by testVehicleNav;
        satisfy logRetention       by testVehicleNav;
    }
}
