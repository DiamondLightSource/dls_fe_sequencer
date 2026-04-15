# The purpose of __all__ is to define the public API of this module, and which
# objects are imported if we call "from dls_feSequencer.hello import *"
import enum
import logging
import types
from time import sleep
from typing import List

import cothread
import epicscorelibs.path.cothread
from cothread.catools import caget, camonitor, caput
from softioc import builder

import dls_feSequencer._version_git

__all__ = [
    "Action",
    "Condition",
    "FESequencer",
]


class Sequences(enum.Enum):
    Idle = 0
    Open = 1
    Close = 2
    Abort = 3


class Action:
    """Consolidates information required to perform an action (act of writing to a PV)
     in the sequencer

    Args:
        msg(str): Message to be printed to the console to describe the action to be
            performed
        componentKey(str): One of the following strings to allow instance of feComponent
            to be located:['ABSB','FV','SHTR','V2']
        pvSuffix(str): One of the following strings used to determine the exact
        PV: ['CON','STA','ILKSTA']
        value(str): Value to be written to the PV
    """

    def __init__(
        self,
        msg: str = "",
        componentKey: str = "",
        pvSuffix: str = "",
        value: str = "",
        preDelay=0,
        postDelay=1,
    ):
        self.msg = msg
        self.componentKey = componentKey
        self.pvSuffix = pvSuffix
        self.value = value
        self.preDelay = preDelay
        self.postDelay = postDelay


class Condition:
    """Consolidates information required to determine if a sequencer Action has been
    completed

    Args:
        msg(str): Message to be printed to the console when the sequencer is waiting for
            this condition
        componentKey(str): One of the following strings to allow instance of feComponent
            to be located:['ABSB','FV','SHTR','V2']
        pvSuffix(str): One of the following strings used to determine the exact readback
        PV: ['CON','STA','ILKSTA']
        value(List): Required value of the PV to satisfy condition
    """

    def __init__(
        self,
        msg: str = "",
        componentKey: str = "",
        pvSuffix: str = "",
        value: List = list(),
        preDelay=0,
        postDelay=0,
    ):
        self.msg = msg
        self.componentKey = componentKey
        self.pvSuffix = pvSuffix
        self.value = value
        self.preDelay = preDelay
        self.postDelay = postDelay

        if len(value) != 0:
            self.hasValue = True
        else:
            self.hasValue = False


# Class prototype
class FESequencer:
    pass


class Status:
    def __init__(
        self, sequencer: FESequencer, frontEnd: str, cagetPtr: types.FunctionType
    ):
        self.sequencer = sequencer
        self.frontEnd = frontEnd
        self.stepNumber = 0
        self.sequence = Sequences.Idle
        self.action: Action = Action()
        self.condition: Condition = Condition()
        self.lastConditionMsg = ""
        self.actioned = False
        self.caget = cagetPtr

        # Create PVs for sequencer EPICS interface
        builder.SetDeviceName(f"{frontEnd}-CS-SEQ-01")

        self.versionPV = builder.stringOut(
            "VERSION", DESC="Git version", initial_value=dls_feSequencer.__version__
        )
        self.stepNumberPV = builder.aOut(
            "STEP", DESC="Current step number", initial_value=0
        )
        self.sequencePV = builder.stringOut(
            "SEQUENCE", DESC="Name of running sequence", initial_value=Sequences.Idle.name
        )
        self.actionPV = builder.stringOut(
            "ACTION_PV", DESC="Sequencer target PV name", initial_value="None"
        )
        self.actionValPV = builder.stringOut(
            "ACTION_VAL", DESC="Value to be written to target", initial_value="None"
        )
        self.actionMsg = builder.stringOut(
            "ACTION_MSG", DESC="Current step description", initial_value="None"
        )
        self.conditionPV = builder.stringOut(
            "CONDITION_PV", DESC="Sequencer readback PV name", initial_value="None"
        )
        self.conditionDesValPV = builder.stringOut(
            "CONDITION_VAL", DESC="Desired value for readback", initial_value="None"
        )
        self.conditionActValPV = builder.stringOut(
            "CONDITION_ACT_VAL", DESC="Actual value of readback PV", initial_value="None"
        )
        self.conditionMsg = builder.stringOut(
            "CONDITION_MSG", DESC="Condition before seq progression", initial_value="None"
        )

        cothread.Spawn(self.__updatePVs)

    def incStep(self):
        self.stepNumber += 1

        # If this method is called when the action hasn't been actioned
        # it means the condition was met before the action. Therefore the
        # action will be skipped.
        if not self.actioned:
            print(f"ACTION:\t\t{self.action.msg}\033[1;34m Skipped \033[0;0m")

        self.actioned = False

    def __updatePVs(self):
        """Method to be run on a cothread to update locally generated PVs with sequencer
        information"""
        while 1:
            # Always update these PVs
            self.stepNumberPV.set(self.stepNumber)
            self.sequencePV.set(self.sequence.name)

            # If no sequence is running set all PVs to None to avoid outdated
            # information
            if self.sequence == Sequences.Idle or self.sequence == Sequences.Abort:
                self.actionPV.set("None")
                self.actionValPV.set("None")
                self.actionMsg.set("None")
                self.conditionPV.set("None")
                self.conditionDesValPV.set("None")
                self.conditionActValPV.set("None")
                self.conditionMsg.set("None")
            else:

                # Update step related PVs only if self.condition and self.action have
                # been initialised
                if type(self.condition) == Condition and type(self.action) == Action:

                    # Check action has been initialised with valid componentKey
                    if self.action.componentKey in self.sequencer.feComponents.keys():
                        self.actionPV.set(
                            self.sequencer.feComponents[self.action.componentKey]
                            + ":"
                            + self.action.pvSuffix
                        )
                        self.actionValPV.set(self.action.value)
                        self.actionMsg.set(self.action.msg)

                    if self.condition.componentKey in self.sequencer.feComponents.keys():
                        self.conditionPV.set(
                            self.sequencer.feComponents[self.condition.componentKey]
                            + ":"
                            + self.condition.pvSuffix
                        )
                        self.conditionMsg.set(self.condition.msg)

                    # If there are multiple acceptable condition values relfect this in
                    # a string and update the PV
                    if type(self.condition.value) == list:
                        all_conditions = ""
                        for val in self.condition.value:
                            all_conditions += f"{val} or "
                        self.conditionDesValPV.set(
                            all_conditions[: all_conditions.rfind("or")]
                        )
                    else:
                        self.conditionDesValPV.set(self.condition.value)

                    # Get the actual value of the readback PV for easy comparison to the
                    # desired value
                    conditionPVName = self.conditionPV.get()
                    if len(conditionPVName) > 10:
                        try:
                            conditionActual = self.caget(conditionPVName, datatype=str)
                            self.conditionActValPV.set(conditionActual)
                        except Exception as e:
                            logging.error(f"\033[1;31m {e} \033[0;0m")

            cothread.Sleep(0.1)


class FESequencer:
    """Main class to instantiate the front end sequencer

    Args:
        frontEnd(str): Prefix of all PVs, the part of the PV that describes the front
            end, eg "FE16B"
        noOfAbsorber(int): Number of absorbers on the front end
        test(bool): Is it a method being executed by pytest?
    """

    def __init__(
        self,
        frontEnd: str,
        noOfAbsorbers: int,
        test: bool = False,
        caputPtr: types.FunctionType = caput,
        cagetPtr: types.FunctionType = caget,
        camonitorPtr: types.FunctionType = camonitor,
    ):
        self.noOfAbsorbers = noOfAbsorbers
        self.beamlineControlPV = f"{frontEnd}-CS-BEAM-01:BLCON"
        self.pathStatusPV = f"{frontEnd}-CS-BEAM-01:STA"
        self.caput = caputPtr
        self.caget = cagetPtr
        self.camonitor = camonitorPtr

        # feComponent objects
        self.feComponents = dict()

        if noOfAbsorbers == 2:
            self.feComponents["ABSB1"] = f"{frontEnd}-RS-ABSB-01"
            self.feComponents["ABSB"] = f"{frontEnd}-RS-ABSB-{noOfAbsorbers:02d}"
        else:
            self.feComponents["ABSB"] = f"{frontEnd}-RS-ABSB-01"

        self.feComponents["FV"] = f"{frontEnd}-VA-FVALV-01"
        self.feComponents["PSHTR"] = f"{frontEnd}-PS-SHTR-01"
        self.feComponents["SHTR"] = f"{frontEnd}-PS-SHTR-02"
        self.feComponents["V1"] = f"{frontEnd}-VA-VALVE-01"
        self.feComponents["V2"] = f"{frontEnd}-VA-VALVE-02"
        self.feComponents["BEAM"] = f"{frontEnd}-CS-BEAM-01"

        self.closeSequenceActions: List[Action] = list()
        self.closeSequenceConditions: List[Condition] = list()
        self.openSequenceActions: List[Action] = list()
        self.openSequenceConditions: List[Condition] = list()

        # Create status object
        self.status = Status(self, frontEnd, self.caget)

        if not test:
            # Set BLCON to "Unknown" on boot
            self.caput(f"{frontEnd}-CS-BEAM-01:BLCON", 3)

            # Remove input field from beam status to allow writing
            # This will be missing with the test IOC
            try:
                self.caput(f"{frontEnd}-CS-BEAM-01:STA.INP", "")
            except Exception as e:
                logging.error(f"\033[1;31m {e} \033[0;0m")

            # Set initial state of beam path
            try:
                if (
                    self.caget(
                        f"{frontEnd}-RS-ABSB-{noOfAbsorbers:02d}:STA", datatype=str
                    )
                    == "Open"
                ):
                    self.caput(self.feComponents["BEAM"] + ":STA", "Open")
                if (
                    self.caget(
                        f"{frontEnd}-RS-ABSB-{noOfAbsorbers:02d}:STA", datatype=str
                    )
                    == "Closed"
                ):
                    self.caput(self.feComponents["BEAM"] + ":STA", "Closed")
            except Exception as e:
                logging.error(f"\033[1;31m {e} \033[0;0m")

            # Set monitor for beamline control
            try:
                self.camonitor(
                    f"{frontEnd}-CS-BEAM-01:BLCON",
                    self.__processBeamlineCommand,
                    datatype=str,
                )
            except Exception as e:
                logging.error(f"\033[1;31m {e} \033[0;0m")

            # Set monitor for the absorbers to update beam status
            # in the event that one is closed manually (not via sequencer)
            for component in self.feComponents:
                if "ABSB" in component or "SHTR" in component:
                    try:
                        self.camonitor(
                            f"{self.feComponents[component]}:STA",
                            self.__processAbsorberStateChange,
                            datatype=str,
                        )
                    except Exception as e:
                        logging.error(f"\033[1;31m {e} \033[0;0m")

    def configureCloseSequence(self, actions, conditions):
        """Method to describe the seqence of actions and conditions for the closing sequence

        Args:
            actions(list[Action]): List of actions
            conditions(list[Condition]): List of conditions
        """
        assert len(actions) == len(conditions)

        for condition in conditions:
            assert type(condition.value) is list

        self.closeSequenceActions = actions
        self.closeSequenceConditions = conditions

    def configureOpenSequence(self, actions: List[Action], conditions: List[Condition]):
        """Method to describe the seqence of actions and conditions for the opening sequence

        Args:
            actions(list[Action]): List of actions
            conditions(list[Condition]): List of conditions
        """
        assert len(actions) == len(conditions)

        for condition in conditions:
            assert type(condition.value) is list

        self.openSequenceActions = actions
        self.openSequenceConditions = conditions

    def __processBeamlineCommand(self, val):
        """Method called by BLCON camonitor. This method starts one of the sequences.

        args:
            var(str): Value of BLCON from camonitor
        """
        if val == "Open":
            self.__requestSequenceStart(Sequences.Open)
        if val == "Close":
            self.__requestSequenceStart(Sequences.Close)
        if val == "Abort":
            self.__requestSequenceStart(Sequences.Abort)

    def __processAbsorberStateChange(self, val):
        """Method called by ABSB, PSHTR and SHTR camonitor.

        This should capture any absorber state changes that happen when a sequence is not being
        executed and reflect them in BEAM-01:STA. It also sets BLCON to "Unknown" to allow the
        BLCON record to process whenever the beamline request another sequence.

        Args:
            val(str): Value of ABSB-XX:STA from camonitor (not actually used)

        """

        if self.status.sequence == Sequences.Idle:
            currentBeamSta = self.caget(f'{self.feComponents["BEAM"]}:STA', datatype=str)
            currentBeamCon = self.caget(
                f'{self.feComponents["BEAM"]}:BLCON', datatype=str
            )
            newBeamSta = currentBeamSta
            absb = self.caget(f'{self.feComponents["ABSB"]}:STA', datatype=str)
            absb1 = absb
            pshtr = self.caget(f'{self.feComponents["PSHTR"]}:STA', datatype=str)
            shtr = self.caget(f'{self.feComponents["SHTR"]}:STA', datatype=str)

            if self.noOfAbsorbers == 2:
                absb1 = self.caget(f'{self.feComponents["ABSB1"]}:STA', datatype=str)

            if absb == "Open" and absb1 == "Open" and pshtr == "Open" and shtr == "Open":
                newBeamSta = "Open"

            if pshtr == "Closed" or shtr == "Closed":
                newBeamSta = "Closed"

            if currentBeamSta != newBeamSta:
                self.caput(f'{self.feComponents["BEAM"]}:STA', newBeamSta)
                currentBeamSta = newBeamSta

            # If BLCON no longer matches BEAM:STA then set BLCON to "Unknown"
            # This ensures that when the beamline request a sequence that the BLCON
            # record will process.
            if currentBeamCon != currentBeamSta:
                self.caput(f'{self.feComponents["BEAM"]}:BLCON', "Unknown")

    def __requestSequenceStart(self, command):
        """Method that sets the current sequence to a specified value to start a sequence

        args:
            command(Sequences): The sequence or command to act on
        """
        print(f"{command.name} command received")

        # If Abort command received AND sequencer is running, reset and flag Fault
        if command == Sequences.Abort and self.status.sequence != Sequences.Idle:
            self.status.sequence = Sequences.Idle
            self.__resetSequencer()
            self.caput(f"{self.feComponents['BEAM']}:STA", "Fault")

        elif command != Sequences.Abort and self.status.sequence == Sequences.Idle:
            self.status.sequence = command

        # I new sequence is commanded, reset the sequencer and start the newly requested one.
        elif command != Sequences.Abort and self.status.sequence != Sequences.Idle:
            self.__resetSequencer()
            self.status.sequence = command

    def run(self):
        """To be called by the IOC, spawns the sequencer"""
        cothread.Spawn(self.__run)

    def __run(self):
        """Calls self.__runSequence when a sequence is requested"""
        while 1:
            if self.status.sequence == Sequences.Open:
                self.__runSequence(self.openSequenceActions, self.openSequenceConditions)

            if self.status.sequence == Sequences.Close:
                self.__runSequence(
                    self.closeSequenceActions, self.closeSequenceConditions
                )

            cothread.Sleep(0.5)

    def __resetSequencer(self):
        """Reset sequencer"""
        self.status.stepNumber = 0
        self.status.actioned = False

    def __runSequence(self, actions, conditions):
        """Method to act on current sequence step given by self.status.stepNumber

        This method has no state and has no while loops. When called with its set of
        actions and conditions it should
        always complete. It never waits for a condition to be true and will not do any
        long term blocking. It takes
        a list of Action and Condition objects but only acts on the ones that are
        relevant to the step number

        args:
            actions(list): List of Action objects descibing the current sequence
            conditions(list): List of Condition objects describing the current sequence
        """

        if self.status.stepNumber == len(actions):
            print(f"{self.status.sequence.name} sequence complete")
            self.status.sequence = Sequences.Idle
            self.__resetSequencer()
            return

        # Ensure the status object has the current Action and Condition
        self.status.action = actions[self.status.stepNumber]
        self.status.condition = conditions[self.status.stepNumber]

        # Check if value of readback PV is what is required for the next step
        # If the condition has no value then skip as no condition is required
        if self.status.condition.hasValue:
            readbackPV = f"""{self.feComponents[self.status.condition.componentKey]}:{self.status.condition.pvSuffix}"""

            # Prevent continuous console logging whilst waiting for a condition
            if self.status.lastConditionMsg != self.status.condition.msg:
                print(
                    f"CONDITION:\t{self.status.condition.msg}\033[1;33m In Progress \033[0;0m"
                )
                self.status.lastConditionMsg = self.status.condition.msg

            # Don't bother with the pre-delay if the action hasn't been actioned
            if self.status.actioned:
                sleep(self.status.condition.preDelay)

            # Check if the condition PV value == one of the desired values, if it is
            # move to the next step
            actualConditionValue = self.caget(readbackPV, datatype=str)
            for val in self.status.condition.value:
                if actualConditionValue == val:
                    print(
                        f"CONDITION:\t{self.status.condition.msg}\033[1;32m Completed \033[0;0m"
                    )
                    sleep(self.status.condition.postDelay)
                    self.status.incStep()
                    return

        # Determine if an action needs to be performed
        if not self.status.actioned:
            # Do Action:
            if len(self.status.action.msg) > 1:
                print(f"ACTION:\t\t{self.status.action.msg}")
            sleep(self.status.action.preDelay)
            self.caput(
                f"""{self.feComponents[self.status.action.componentKey]}:{self.status.action.pvSuffix}""",
                self.status.action.value,
            )
            cothread.Yield()
            sleep(self.status.action.postDelay)
            self.status.actioned = True

            if not self.status.condition.hasValue:
                self.status.incStep()
