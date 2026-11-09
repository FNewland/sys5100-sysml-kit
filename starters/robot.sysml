/* SYS 5100 starter S1: autonomous campus delivery robot. Values indicative (GenCDF toy pack
 * delivery_robot). Every value carries a basis (@Budget/@Evidence); replace HYP- sources with
 * INT-/OBS-/DOC- evidence as it comes in.  Check: ./kit check   Tables: ./kit gen-table */
package CampusDeliveryRobot {
    private import ScalarValues::*;
    private import ISQ::*;
    private import SI::*;
    private import SYS5100Lib::*;

    package Stakeholders {
        doc /* Who has a stake, and what they worry about. */
        part def Pedestrian; part def WheelchairUser; part def Customer; part def FacilitiesManager;
        concern def PedestrianSafety {
            doc /* People sharing the sidewalk must not be hit, tripped or blocked. */
            subject robot : Structure::DeliveryRobot;
            stakeholder pedestrian : Pedestrian;
            stakeholder wheelchairUser : WheelchairUser;
        }
        concern def TimelyDelivery {
            doc /* A parcel ordered anywhere on campus arrives on one charge. */
            subject robot : Structure::DeliveryRobot;
            stakeholder customer : Customer;
        }
        concern def CampusOperability {
            doc /* Facilities staff can monitor, stop and recover the robot. */
            subject robot : Structure::DeliveryRobot;
            stakeholder facilities : FacilitiesManager;
        }
        concern pedestrianSafety : PedestrianSafety; concern timelyDelivery : TimelyDelivery;
        concern campusOperability : CampusOperability;
    }

    package Structure {
        doc /* Robot -> five subsystems, typed ports, conjugate interfaces. */
        private import Behaviour::*;
        item def ElectricalPower; item def SensorData; item def DriveCommand; item def Telemetry;
        port def PowerPort     { out item power : ElectricalPower; }
        port def DataPort      { out item data : SensorData; }
        port def CommandPort   { out item cmd : DriveCommand; }
        port def TelemetryPort { out item tm : Telemetry; }
        interface def PowerLink   { end supplier : PowerPort;  end consumer : ~PowerPort; }
        interface def SensorLink  { end source : DataPort;     end sink : ~DataPort; }
        interface def CommandLink { end source : CommandPort;  end sink : ~CommandPort; }
        part def Component { attribute mass : MassValue; }
        part def Chassis :> Component { attribute width : LengthValue; }
        part def DriveUnit :> Component {
            attribute maxDeceleration : AccelerationValue;
            attribute reactionTime : TimeValue;
            attribute specificConsumption;   // energy per kg per km
            port pwrIn : ~PowerPort;
            port cmdIn : ~CommandPort;
        }
        part def Battery :> Component {
            attribute capacity : EnergyValue;
            port pwrOut : PowerPort;
        }
        part def ComputeUnit :> Component {
            attribute telemetryRate : FrequencyValue;
            port pwrIn : ~PowerPort;
            port sensorIn : ~DataPort;
            port cmdOut : CommandPort;
            port tmOut : TelemetryPort;
        }
        part def SensorSuite :> Component {
            port pwrIn : ~PowerPort;
            port dataOut : DataPort;
        }
        part def DeliveryRobot {
            attribute payloadMass : MassValue;
            attribute maxSpeed : SpeedValue;
            part chassis : Chassis;
            part drive : DriveUnit;
            part battery : Battery;
            part compute : ComputeUnit;
            part sensors : SensorSuite;
            attribute grossMass : MassValue = chassis.mass + drive.mass + battery.mass
                                              + compute.mass + sensors.mass + payloadMass;
            attribute stoppingDistance : LengthValue =
                maxSpeed * drive.reactionTime + maxSpeed * maxSpeed / (2 * drive.maxDeceleration);
            interface powerDrive   : PowerLink   connect battery.pwrOut to drive.pwrIn;
            interface powerCompute : PowerLink   connect battery.pwrOut to compute.pwrIn;
            interface powerSensors : PowerLink   connect battery.pwrOut to sensors.pwrIn;
            interface perception   : SensorLink  connect sensors.dataOut to compute.sensorIn;
            interface motionCmd    : CommandLink connect compute.cmdOut to drive.cmdIn;
            port opsLink : TelemetryPort;            // boundary port to campus operations
            bind compute.tmOut = opsLink;
            exhibit state modes : RobotModes;
        }
        // The configured design point. Budgeted values: @Budget (basis + growth allowance).
        part campusRobot : DeliveryRobot {
            attribute :>> payloadMass = 10 [kg] { @Budget { basis = Basis::specified; growth = 0.0; } }
            attribute :>> maxSpeed = 1.6 [m/s]  { @Evidence { grade = Basis::assumed; source = "HYP-01"; } }
            part :>> chassis {
                attribute :>> mass = 8.0 [kg]   { @Budget { basis = Basis::assumed; growth = 0.20; } }
                attribute :>> width = 0.62 [m]  { @Evidence { grade = Basis::estimated; source = "DOC-03"; } }
            }
            part :>> drive {
                attribute :>> mass = 3.5 [kg]   { @Budget { basis = Basis::assumed; growth = 0.20; } }
                attribute :>> maxDeceleration = 2.5 [m/s^2] { @Evidence { grade = Basis::assumed; source = "HYP-02"; } }
                attribute :>> reactionTime = 0.2 [s]        { @Evidence { grade = Basis::assumed; source = "HYP-02"; } }
                attribute :>> specificConsumption = 0.9 [W*h/(kg*km)] { @Evidence { grade = Basis::assumed; source = "HYP-03"; } }
            }
            part :>> battery {
                attribute :>> mass = 1.5 [kg]   { @Budget { basis = Basis::calculated; growth = 0.05; } }
                attribute :>> capacity = 225 [W*h] { @Evidence { grade = Basis::calculated; source = "DOC-04"; } }
            }
            part :>> compute {
                attribute :>> mass = 1.0 [kg]   { @Budget { basis = Basis::estimated; growth = 0.10; } }
                attribute :>> telemetryRate = 2 [Hz] { @Evidence { grade = Basis::estimated; source = "DOC-05"; } }
            }
            part :>> sensors {
                attribute :>> mass = 1.5 [kg]   { @Budget { basis = Basis::estimated; growth = 0.10; } }
            }
        }
        // Functions (logical) allocated to subsystems (physical).
        part logical { part perceiveObstacle; part controlMotion; part stopSafely; }
        allocate logical.perceiveObstacle to campusRobot.sensors;
        allocate logical.controlMotion to campusRobot.compute;
        allocate logical.stopSafely to campusRobot.drive;
    }

    package Behaviour {
        doc /* Operating modes (read-only in the starter). Every mode must be reachable from idle. */
        attribute def Dispatch; attribute def Delivered; attribute def FaultDetected; attribute def FaultCleared;
        attribute def StopCommand; attribute def OperatorAttends; attribute def RecoveryDone;
        state def RobotModes {
            entry; then idle;
            state idle; state delivering; state degraded; state recovery; state safeStop;
            transition idle_to_delivering     first idle       accept Dispatch        then delivering;
            transition delivering_to_idle     first delivering accept Delivered       then idle;
            transition delivering_to_degraded first delivering accept FaultDetected   then degraded;
            transition degraded_to_delivering first degraded   accept FaultCleared    then delivering;
            transition delivering_to_safeStop first delivering accept StopCommand     then safeStop;
            transition degraded_to_safeStop   first degraded   accept StopCommand     then safeStop;
            transition safeStop_to_recovery   first safeStop   accept OperatorAttends then recovery;
            transition recovery_to_idle       first recovery   accept RecoveryDone    then idle;
        }
    }

    package Requirements {
        doc /* Each requirement: id <'REQ-nn'>, doc text, subject, evidence source, constraint where possible. */
        private import Structure::*;
        private import Stakeholders::*;
        requirement def RobotRequirement { subject robot : DeliveryRobot; }
        requirement <'REQ-01'> grossMassLimit : RobotRequirement {
            doc /* The robot gross mass, including a full payload, shall not exceed 45 kg. */
            @Evidence { grade = Basis::specified; source = "DOC-01"; }
            frame pedestrianSafety;
            attribute massMax : MassValue = 45 [kg];
            require constraint { robot.grossMass <= massMax }
        }
        requirement <'REQ-02'> payloadCapacity : RobotRequirement {
            doc /* The robot shall carry a payload of at least 10 kg. */
            @Evidence { grade = Basis::specified; source = "INT-01"; }
            frame timelyDelivery;
            require constraint { robot.payloadMass >= 10 [kg] }
        }
        requirement <'REQ-03'> rangePerCharge : RobotRequirement {
            doc /* The robot shall complete an 8 km delivery circuit on one charge at full payload. */
            @Evidence { grade = Basis::specified; source = "INT-02"; }
            frame timelyDelivery;
        }
        requirement <'REQ-04'> stoppingDistance : RobotRequirement {
            doc /* From maximum speed, the robot shall stop within 1.5 m of detecting an obstacle. */
            @Evidence { grade = Basis::specified; source = "INT-05"; }
            frame pedestrianSafety;
            require constraint { robot.stoppingDistance <= 1.5 [m] }
        }
        requirement <'REQ-04.1'> driveDeceleration {
            doc /* Derived from REQ-04: the drive unit shall decelerate at 2.0 m/s^2 or more on dry paving. */
            subject drive : DriveUnit;
            require constraint { drive.maxDeceleration >= 2.0 [m/s^2] }
        }
        requirement <'REQ-05'> speedLimit : RobotRequirement {
            doc /* The robot shall not exceed 1.7 m/s on shared paths. */
            @Evidence { grade = Basis::specified; source = "OBS-01"; }
            frame pedestrianSafety;
            require constraint { robot.maxSpeed <= 1.7 [m/s] }
        }
        requirement <'REQ-06'> energyMargin : RobotRequirement {
            doc /* Installed battery energy shall exceed the 8 km full-payload mission energy by at least 10 %. */
            @Evidence { grade = Basis::specified; source = "DOC-02"; }
            frame timelyDelivery;
            attribute missionRange : LengthValue = 8 [km];
            attribute supply : EnergyValue = robot.battery.capacity;
            attribute demand : EnergyValue = robot.drive.specificConsumption * robot.grossMass * missionRange;
            attribute marginMin : Real = 0.10;
        }
        requirement <'REQ-07'> safeStopOnFault : RobotRequirement {
            doc /* On a stop command or an unrecoverable fault, the robot shall enter safe-stop within 0.5 s. */
            @Evidence { grade = Basis::specified; source = "INT-04"; }
            frame pedestrianSafety;
            frame campusOperability;
        }
        requirement <'REQ-08'> telemetryRate : RobotRequirement {
            doc /* The robot shall send position and health telemetry to operations at least once per second. */
            @Evidence { grade = Basis::specified; source = "INT-06"; }
            frame campusOperability;
            require constraint { robot.compute.telemetryRate >= 1 [Hz] }
        }
        requirement <'REQ-09'> pathWidth : RobotRequirement {
            doc /* The robot shall be no wider than 0.7 m, leaving room for a wheelchair on a 2 m path. */
            @Evidence { grade = Basis::specified; source = "INT-03, OBS-02"; }
            frame pedestrianSafety;
            require constraint { robot.chassis.width <= 0.7 [m] }
        }
    }

    package Verification {
        doc /* How each requirement will be shown to be met. Doc starts with the method. */
        private import Structure::*;
        private import Requirements::*;
        verification def MassInspection {
            doc /* Inspection: weigh the loaded robot on a calibrated scale; measure its width. */
            subject robot : DeliveryRobot; objective { verify grossMassLimit; verify payloadCapacity; verify pathWidth; }
        }
        verification def RangeTest {
            doc /* Test: drive the 8 km campus circuit at full payload; log state of charge. */
            subject robot : DeliveryRobot; objective { verify rangePerCharge; verify energyMargin; }
        }
        verification def BrakingTest {
            doc /* Test: 20 emergency stops from maximum speed on dry and wet paving. */
            subject robot : DeliveryRobot; objective { verify stoppingDistance; verify speedLimit; verify driveDeceleration; }
        }
        verification def FaultInjectionDemo {
            doc /* Demonstration: inject sensor and link faults; observe mode changes and telemetry. */
            subject robot : DeliveryRobot; objective { verify safeStopOnFault; verify telemetryRate; }
        }
        // After Test Day add the verdict, e.g.
        //   @TestVerdict { verdict = VerificationCases::VerdictKind::pass; asRun = "TD-02/run1"; ncr = "none"; }
        verification massInspection : MassInspection { subject :>> robot = campusRobot; }
        verification rangeTest : RangeTest { subject :>> robot = campusRobot; }
        verification brakingTest : BrakingTest { subject :>> robot = campusRobot; }
        verification faultDemo : FaultInjectionDemo { subject :>> robot = campusRobot; }
    }

    package Traceability {
        doc /* Which design element claims to satisfy which requirement. */
        private import Requirements::*;
        private import Structure::*;
        satisfy grossMassLimit by campusRobot;   satisfy payloadCapacity by campusRobot;
        satisfy rangePerCharge by campusRobot;   satisfy stoppingDistance by campusRobot;
        satisfy speedLimit by campusRobot;       satisfy energyMargin by campusRobot;
        satisfy safeStopOnFault by campusRobot;  satisfy telemetryRate by campusRobot;
        satisfy pathWidth by campusRobot;
        satisfy driveDeceleration by campusRobot.drive;   // derived requirement -> subsystem
    }
}
