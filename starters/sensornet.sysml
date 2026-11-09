/*
 * SYS 5100 starter model S3: community sensor and alert network (e.g. flood early warning).
 * Three LoRa sensor nodes, a gateway, an alert server and a dashboard. Numbers are
 * illustrative or assumed: replace them with your bench data (Test Day) and interview evidence.
 * Check it:  ./kit check        Tables:  ./kit gen-table
 */
package CommunityAlertNetwork {
    private import ScalarValues::*;
    private import ISQ::*;
    private import SI::*;
    private import SYS5100Lib::*;

    package Stakeholders {
        doc /* Who has a stake. Data belongs to the community under its own terms. */
        part def Resident;
        part def EmergencyCoordinator;
        part def NetworkMaintainer;
        part def CommunityDataSteward;

        concern def TimelyWarning {
            doc /* People downstream get a warning early enough to act. */
            subject net : Structure::AlertNetwork;
            stakeholder residents : Resident;
            stakeholder coordinator : EmergencyCoordinator;
        }
        concern def AlertTrust {
            doc /* Alerts are believed: few false alarms, no spoofed alerts, no alert fatigue. */
            subject net : Structure::AlertNetwork;
            stakeholder residents : Resident;
        }
        concern def DataSovereignty {
            doc /* The community controls where its sensor data is kept and who may use it. */
            subject net : Structure::AlertNetwork;
            stakeholder steward : CommunityDataSteward;
        }
        concern def EasyUpkeep {
            doc /* Volunteers can keep the nodes running for a season. */
            subject net : Structure::AlertNetwork;
            stakeholder maintainer : NetworkMaintainer;
        }
        concern timelyWarning : TimelyWarning;
        concern alertTrust : AlertTrust;
        concern dataSovereignty : DataSovereignty;
        concern easyUpkeep : EasyUpkeep;
    }

    package Structure {
        doc /* Node -> gateway (LoRa) -> server (backhaul) -> dashboard. */
        item def RadioFrame;
        item def Packet;
        item def Alert;

        port def RadioPort    { out item radioFrame : RadioFrame; }
        port def BackhaulPort { out item pkt : Packet; }
        port def AlertPort    { out item alert : Alert; }

        interface def LoRaLink     { end node : RadioPort;    end gateway : ~RadioPort; }
        interface def BackhaulLink { end gateway : BackhaulPort; end server : ~BackhaulPort; }
        interface def AlertLink    { end server : AlertPort;  end display : ~AlertPort; }

        part def SensorNode {
            attribute latency : DurationValue;        // threshold crossing -> frame on air (P95)
            attribute packetLoss : Real;              // fraction over 1000 packets at 300 m
            attribute batteryEnergy : EnergyValue;
            attribute averagePower : PowerValue;      // at a 5-minute reporting interval
            port radio : RadioPort;
        }
        part def Gateway {
            attribute latency : DurationValue;        // frame received -> alert forwarded (P95)
            attribute rejectsUnsignedUplinks : Boolean;
            port radioIn : ~RadioPort;
            port uplink : BackhaulPort;
        }
        part def AlertServer {
            port backhaulIn : ~BackhaulPort;
            port alertOut : AlertPort;
        }
        part def Dashboard { port alertIn : ~AlertPort; }

        part def AlertNetwork {
            part node : SensorNode[3];
            part gateway : Gateway;
            part server : AlertServer;
            part dashboard : Dashboard;
            attribute alertLatency : DurationValue = node.latency + gateway.latency;
            interface radioLink : LoRaLink     connect node.radio to gateway.radioIn;
            interface backhaul  : BackhaulLink connect gateway.uplink to server.backhaulIn;
            interface display   : AlertLink    connect server.alertOut to dashboard.alertIn;
        }

        part ridgeNetwork : AlertNetwork {
            part :>> node {
                attribute :>> latency = 4.0 [s]         { @Budget { basis = Basis::estimated; growth = 0.20; } }
                attribute :>> packetLoss = 0.03         { @Evidence { grade = Basis::estimated; source = "DOC-02"; } }
                attribute :>> batteryEnergy = 10.8 [W*h] { @Evidence { grade = Basis::specified; source = "DOC-03"; } }
                attribute :>> averagePower = 0.02 [W]   { @Evidence { grade = Basis::estimated; source = "DOC-04"; } }
            }
            part :>> gateway {
                attribute :>> latency = 1.0 [s]         { @Budget { basis = Basis::assumed; growth = 0.20; } }
                attribute :>> rejectsUnsignedUplinks = true { @Evidence { grade = Basis::assumed; source = "HYP-02"; } }
            }
        }
    }

    package Requirements {
        doc /* Team prefix SN. */
        private import Structure::*;
        private import Stakeholders::*;

        requirement def NetworkRequirement { subject net : AlertNetwork; }

        requirement <'SN-003'> packetLoss : NetworkRequirement {
            doc /* Node-to-gateway packet loss shall not exceed 5 % over 1,000 packets at 300 m line of sight. */
            @Evidence { grade = Basis::specified; source = "INT-03"; }
            frame alertTrust;
            require constraint { net.node.packetLoss <= 0.05 }
        }
        requirement <'SN-007'> alertLatency : NetworkRequirement {
            doc /* An alert shall reach the gateway within 10 s of the threshold crossing, at the 95th percentile. */
            @Evidence { grade = Basis::specified; source = "INT-01"; }
            frame timelyWarning;
            attribute latencyMax : DurationValue = 10 [s];
            require constraint { net.alertLatency <= latencyMax }
        }
        requirement <'SN-011'> batteryLife : NetworkRequirement {
            doc /* Each node shall run 14 days on one battery at a 5-minute reporting interval, with at least 20 % energy margin. */
            @Evidence { grade = Basis::specified; source = "INT-04"; }
            frame easyUpkeep;
            attribute serviceInterval : DurationValue = 14 [d];
            attribute supply : EnergyValue = net.node.batteryEnergy;
            attribute demand : EnergyValue = net.node.averagePower * serviceInterval;
            attribute marginMin : Real = 0.20;
        }
        requirement <'SN-012'> dataLocation : NetworkRequirement {
            doc /* The network shall store sensor data only on servers that the community data steward designates. */
            @Evidence { grade = Basis::specified; source = "INT-02"; }
            frame dataSovereignty;
        }
        requirement <'SN-R21'> rejectSpoofedAlerts {
            doc /* The gateway shall discard each uplink frame that fails message authentication. */
            @RiskLink { riskId = "R-07"; threat = "STRIDE-S: spoofed node triggers false alert"; }
            @Evidence { grade = Basis::specified; source = "DOC-05"; }
            subject gw : Gateway;
            require constraint { gw.rejectsUnsignedUplinks }
        }
    }

    package Verification {
        private import Structure::*;
        private import Requirements::*;

        verification def RangeTest {
            doc /* Test: send 1,000 packets per node at 300 m; count losses at the gateway. */
            subject net : AlertNetwork;
            objective { verify packetLoss; }
        }
        verification def LatencyTest {
            doc /* Test: 200 injected alerts on the bench, timestamps logged at node and gateway. */
            subject net : AlertNetwork;
            objective { verify alertLatency; }
        }
        verification def BatteryLifeAnalysis {
            doc /* Analysis: measured duty-cycle current x reporting schedule, cross-checked by a 72 h bench run. */
            subject net : AlertNetwork;
            objective { verify batteryLife; }
        }
        verification def DataLocationInspection {
            doc /* Inspection: review server configuration and data-sharing agreement with the steward. */
            subject net : AlertNetwork;
            objective { verify dataLocation; }
        }
        verification def SpoofedUplinkTest {
            doc /* Test: replay 200 altered and 200 forged-address frames; count rejections and log times. */
            subject gw : Gateway;
            objective { verify rejectSpoofedAlerts; }
        }
        // After Test Day, e.g.:
        //   @TestVerdict { verdict = VerificationCases::VerdictKind::fail; asRun = "TD-03/run2"; ncr = "NCR-02"; }
        verification rangeTest : RangeTest { subject :>> net = ridgeNetwork; }
        verification latencyTest : LatencyTest { subject :>> net = ridgeNetwork; }
        verification batteryAnalysis : BatteryLifeAnalysis { subject :>> net = ridgeNetwork; }
        verification dataInspection : DataLocationInspection { subject :>> net = ridgeNetwork; }
        verification spoofTest : SpoofedUplinkTest { subject :>> gw = ridgeNetwork.gateway; }
    }

    package Traceability {
        private import Requirements::*;
        private import Structure::*;
        satisfy packetLoss          by ridgeNetwork;
        satisfy alertLatency        by ridgeNetwork;
        satisfy batteryLife         by ridgeNetwork;
        satisfy dataLocation        by ridgeNetwork;
        satisfy rejectSpoofedAlerts by ridgeNetwork.gateway;
    }
}
