# The purpose of __all__ is to define the public API of this module, and which
# objects are imported if we call "from dls_feSequencer.hello import *"
from __future__ import annotations

import enum
import logging
import types
from time import sleep

import cothread
from cothread.catools import caget, camonitor, caput
from softioc import builder

import dls_fe_sequencer

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
        component_key(str): One of the following strings to allow instance of
        feComponent
            to be located:['ABSB','FV','SHTR','V2']
        pv_suffix(str): One of the following strings used to determine the exact
        PV: ['CON','STA','ILKSTA']
        value(str): Value to be written to the PV
    """

    def __init__(
        self,
        msg: str = "",
        component_key: str = "",
        pv_suffix: str = "",
        value: str = "",
        pre_delay=0,
        post_delay=1,
    ):
        self.msg = msg
        self.component_key = component_key
        self.pv_suffix = pv_suffix
        self.value = value
        self.pre_delay = pre_delay
        self.post_delay = post_delay


class Condition:
    """Consolidates information required to determine if a sequencer Action has been
    completed

    Args:
        msg(str): Message to be printed to the console when the sequencer is waiting for
            this condition
        component_key(str): One of the following strings to allow instance of
        feComponent to be located:['ABSB','FV','SHTR','V2']
        pv_suffix(str): One of the following strings used to determine the exact
        readback PV: ['CON','STA','ILKSTA']
        value(List): Required value of the PV to satisfy condition
    """

    def __init__(
        self,
        msg: str = "",
        component_key: str = "",
        pv_suffix: str = "",
        value: list[str] | None = None,
        pre_delay=0,
        post_delay=0,
    ):
        self.msg = msg
        self.component_key = component_key
        self.pv_suffix = pv_suffix
        self.value: list[str] = value if value is not None else []
        self.pre_delay = pre_delay
        self.post_delay = post_delay

        if len(self.value) != 0:
            self.has_value = True
        else:
            self.has_value = False


class Status:
    def __init__(
        self, sequencer: FESequencer, front_end: str, caget_ptr: types.FunctionType
    ):
        self.sequencer = sequencer
        self.front_end = front_end
        self.step_number = 0
        self.sequence = Sequences.Idle
        self.action: Action = Action()
        self.condition: Condition = Condition()
        self.last_condition_msg = ""
        self.actioned = False
        self.caget = caget_ptr

        # Create PVs for sequencer EPICS interface
        builder.SetDeviceName(f"{front_end}-CS-SEQ-01")

        self.versionPV = builder.stringOut(
            "VERSION", DESC="Git version", initial_value=dls_fe_sequencer.__version__
        )
        self.step_numberPV = builder.aOut(
            "STEP", DESC="Current step number", initial_value=0
        )
        self.sequence_pv = builder.stringOut(
            "SEQUENCE",
            DESC="Name of running sequence",
            initial_value=Sequences.Idle.name,
        )
        self.action_pv = builder.stringOut(
            "ACTION_PV", DESC="Sequencer target PV name", initial_value="None"
        )
        self.action_val_pv = builder.stringOut(
            "ACTION_VAL", DESC="Value to be written to target", initial_value="None"
        )
        self.action_msg = builder.stringOut(
            "ACTION_MSG", DESC="Current step description", initial_value="None"
        )
        self.condition_pv = builder.stringOut(
            "CONDITION_PV", DESC="Sequencer readback PV name", initial_value="None"
        )
        self.condition_des_val_pv = builder.stringOut(
            "CONDITION_VAL", DESC="Desired value for readback", initial_value="None"
        )
        self.condition_act_val_pv = builder.stringOut(
            "CONDITION_ACT_VAL",
            DESC="Actual value of readback PV",
            initial_value="None",
        )
        self.condition_msg = builder.stringOut(
            "CONDITION_MSG",
            DESC="Condition before seq progression",
            initial_value="None",
        )

        cothread.Spawn(self.__update_pvs)

    def inc_step(self):
        self.step_number += 1

        # If this method is called when the action hasn't been actioned
        # it means the condition was met before the action. Therefore the
        # action will be skipped.
        if not self.actioned:
            print(f"ACTION:\t\t{self.action.msg}\033[1;34m Skipped \033[0;0m")

        self.actioned = False

    def __update_pvs(self):
        """Method to be run on a cothread to update locally generated PVs with sequencer
        information"""
        while 1:
            # Always update these PVs
            self.step_numberPV.set(self.step_number)
            self.sequence_pv.set(self.sequence.name)

            # If no sequence is running set all PVs to None to avoid outdated
            # information
            if self.sequence is Sequences.Idle or self.sequence is Sequences.Abort:
                self.action_pv.set("None")
                self.action_val_pv.set("None")
                self.action_msg.set("None")
                self.condition_pv.set("None")
                self.condition_des_val_pv.set("None")
                self.condition_act_val_pv.set("None")
                self.condition_msg.set("None")
            else:
                # Update step related PVs only if self.condition and self.action have
                # been initialised
                if type(self.condition) is Condition and type(self.action) is Action:
                    # Check action has been initialised with valid component_key
                    if self.action.component_key in self.sequencer.fe_components.keys():
                        self.action_pv.set(
                            self.sequencer.fe_components[self.action.component_key]
                            + ":"
                            + self.action.pv_suffix
                        )
                        self.action_val_pv.set(self.action.value)
                        self.action_msg.set(self.action.msg)

                    if (
                        self.condition.component_key
                        in self.sequencer.fe_components.keys()
                    ):
                        self.condition_pv.set(
                            self.sequencer.fe_components[self.condition.component_key]
                            + ":"
                            + self.condition.pv_suffix
                        )
                        self.condition_msg.set(self.condition.msg)

                    # If there are multiple acceptable condition values relfect this in
                    # a string and update the PV
                    if type(self.condition.value) is list:
                        all_conditions = ""
                        for val in self.condition.value:
                            all_conditions += f"{val} or "
                        self.condition_des_val_pv.set(
                            all_conditions[: all_conditions.rfind("or")]
                        )
                    else:
                        self.condition_des_val_pv.set(self.condition.value)

                    # Get the actual value of the readback PV for easy comparison to the
                    # desired value
                    condition_pv_name = self.condition_pv.get()
                    if len(condition_pv_name) > 10:
                        try:
                            condition_actual = self.caget(
                                condition_pv_name, datatype=str
                            )
                            self.condition_act_val_pv.set(condition_actual)
                        except Exception as e:
                            logging.error(f"\033[1;31m {e} \033[0;0m")

            cothread.Sleep(0.1)


class FESequencer:
    """Main class to instantiate the front end sequencer

    Args:
        front_end(str): Prefix of all PVs, the part of the PV that describes the front
            end, eg "FE16B"
        noOfAbsorber(int): Number of absorbers on the front end
        test(bool): Is it a method being executed by pytest?
    """

    def __init__(
        self,
        front_end: str,
        no_of_absorbers: int,
        test: bool = False,
        caput_ptr: types.FunctionType = caput,
        caget_ptr: types.FunctionType = caget,
        camonitor_ptr: types.FunctionType = camonitor,
    ):
        self.no_of_absorbers = no_of_absorbers
        self.beamline_control_pv = f"{front_end}-CS-BEAM-01:BLCON"
        self.path_status_pv = f"{front_end}-CS-BEAM-01:STA"
        self.caput = caput_ptr
        self.caget = caget_ptr
        self.camonitor = camonitor_ptr

        # feComponent objects
        self.fe_components = {}

        if no_of_absorbers == 2:
            self.fe_components["ABSB1"] = f"{front_end}-RS-ABSB-01"
            self.fe_components["ABSB"] = f"{front_end}-RS-ABSB-{no_of_absorbers:02d}"
        else:
            self.fe_components["ABSB"] = f"{front_end}-RS-ABSB-01"

        self.fe_components["FV"] = f"{front_end}-VA-FVALV-01"
        self.fe_components["PSHTR"] = f"{front_end}-PS-SHTR-01"
        self.fe_components["SHTR"] = f"{front_end}-PS-SHTR-02"
        self.fe_components["V1"] = f"{front_end}-VA-VALVE-01"
        self.fe_components["V2"] = f"{front_end}-VA-VALVE-02"
        self.fe_components["BEAM"] = f"{front_end}-CS-BEAM-01"

        self.close_sequence_actions: list[Action] = []
        self.close_sequence_conditions: list[Condition] = []
        self.open_sequence_actions: list[Action] = []
        self.open_sequence_conditions: list[Condition] = []

        # Create status object
        self.status = Status(self, front_end, self.caget)

        if not test:
            # Set BLCON to "Unknown" on boot
            self.caput(f"{front_end}-CS-BEAM-01:BLCON", 3)

            # Remove input field from beam status to allow writing
            # This will be missing with the test IOC
            try:
                self.caput(f"{front_end}-CS-BEAM-01:STA.INP", "")
            except Exception as e:
                logging.error(f"\033[1;31m {e} \033[0;0m")

            # Set initial state of beam path
            try:
                if (
                    self.caget(
                        f"{front_end}-RS-ABSB-{no_of_absorbers:02d}:STA", datatype=str
                    )
                    == "Open"
                ):
                    self.caput(self.fe_components["BEAM"] + ":STA", "Open")
                if (
                    self.caget(
                        f"{front_end}-RS-ABSB-{no_of_absorbers:02d}:STA", datatype=str
                    )
                    == "Closed"
                ):
                    self.caput(self.fe_components["BEAM"] + ":STA", "Closed")
            except Exception as e:
                logging.error(f"\033[1;31m {e} \033[0;0m")

            # Set monitor for beamline control
            try:
                self.camonitor(
                    f"{front_end}-CS-BEAM-01:BLCON",
                    self.__process_beamline_command,
                    datatype=str,
                )
            except Exception as e:
                logging.error(f"\033[1;31m {e} \033[0;0m")

            # Set monitor for the absorbers to update beam status
            # in the event that one is closed manually (not via sequencer)
            for component in self.fe_components:
                if "ABSB" in component or "SHTR" in component:
                    try:
                        self.camonitor(
                            f"{self.fe_components[component]}:STA",
                            self.__process_absorber_state_change,
                            datatype=str,
                        )
                    except Exception as e:
                        logging.error(f"\033[1;31m {e} \033[0;0m")

    def configure_close_sequence(self, actions, conditions):
        """Method to describe the seqence of actions and conditions for the closing
        sequence

        Args:
            actions(list[Action]): List of actions
            conditions(list[Condition]): List of conditions
        """
        assert len(actions) == len(conditions)

        for condition in conditions:
            assert type(condition.value) is list

        self.close_sequence_actions = actions
        self.close_sequence_conditions = conditions

    def configure_open_sequence(
        self, actions: list[Action], conditions: list[Condition]
    ):
        """Method to describe the seqence of actions and conditions for the opening
        sequence

        Args:
            actions(list[Action]): List of actions
            conditions(list[Condition]): List of conditions
        """
        assert len(actions) == len(conditions)

        for condition in conditions:
            assert type(condition.value) is list

        self.open_sequence_actions = actions
        self.open_sequence_conditions = conditions

    def __process_beamline_command(self, val):
        """Method called by BLCON camonitor. This method starts one of the sequences.

        args:
            var(str): Value of BLCON from camonitor
        """
        if val == "Open":
            self.__request_sequence_start(Sequences.Open)
        if val == "Close":
            self.__request_sequence_start(Sequences.Close)
        if val == "Abort":
            self.__request_sequence_start(Sequences.Abort)

    def __process_absorber_state_change(self, val):
        """Method called by ABSB, PSHTR and SHTR camonitor.

        This should capture any absorber state changes that happen when a sequence is
        not being executed and reflect them in BEAM-01:STA. It also sets BLCON to
        "Unknown" to allow the BLCON record to process whenever the beamline request
        another sequence.

        Args:
            val(str): Value of ABSB-XX:STA from camonitor (not actually used)

        """

        if self.status.sequence == Sequences.Idle:
            current_beam_sta = self.caget(
                f"{self.fe_components['BEAM']}:STA", datatype=str
            )
            current_beam_con = self.caget(
                f"{self.fe_components['BEAM']}:BLCON", datatype=str
            )
            new_beam_sta = current_beam_sta
            absb = self.caget(f"{self.fe_components['ABSB']}:STA", datatype=str)
            absb1 = absb
            pshtr = self.caget(f"{self.fe_components['PSHTR']}:STA", datatype=str)
            shtr = self.caget(f"{self.fe_components['SHTR']}:STA", datatype=str)

            if self.no_of_absorbers == 2:
                absb1 = self.caget(f"{self.fe_components['ABSB1']}:STA", datatype=str)

            if (
                absb == "Open"
                and absb1 == "Open"
                and pshtr == "Open"
                and shtr == "Open"
            ):
                new_beam_sta = "Open"

            if pshtr == "Closed" or shtr == "Closed":
                new_beam_sta = "Closed"

            if current_beam_sta != new_beam_sta:
                self.caput(f"{self.fe_components['BEAM']}:STA", new_beam_sta)
                current_beam_sta = new_beam_sta

            # If BLCON no longer matches BEAM:STA then set BLCON to "Unknown"
            # This ensures that when the beamline request a sequence that the BLCON
            # record will process.
            if current_beam_con != current_beam_sta:
                self.caput(f"{self.fe_components['BEAM']}:BLCON", "Unknown")

    def __request_sequence_start(self, command):
        """Method that sets the current sequence to a specified value to start a
        sequence

        args:
            command(Sequences): The sequence or command to act on
        """
        print(f"{command.name} command received")

        # If Abort command received AND sequencer is running, reset and flag Fault
        if command == Sequences.Abort and self.status.sequence != Sequences.Idle:
            self.status.sequence = Sequences.Idle
            self.__reset_sequencer()
            self.caput(f"{self.fe_components['BEAM']}:STA", "Fault")

        elif command != Sequences.Abort and self.status.sequence == Sequences.Idle:
            self.status.sequence = command

        # I new sequence is commanded, reset the sequencer and start the newly requested
        # one.
        elif command != Sequences.Abort and self.status.sequence != Sequences.Idle:
            self.__reset_sequencer()
            self.status.sequence = command

    def run(self):
        """To be called by the IOC, spawns the sequencer"""
        cothread.Spawn(self.__run)

    def __run(self):
        """Calls self.__run_sequence when a sequence is requested"""
        while 1:
            if self.status.sequence == Sequences.Open:
                self.__run_sequence(
                    self.open_sequence_actions, self.open_sequence_conditions
                )

            if self.status.sequence == Sequences.Close:
                self.__run_sequence(
                    self.close_sequence_actions, self.close_sequence_conditions
                )

            cothread.Sleep(0.5)

    def __reset_sequencer(self):
        """Reset sequencer"""
        self.status.step_number = 0
        self.status.actioned = False

    def __run_sequence(self, actions, conditions):
        """Method to act on current sequence step given by self.status.step_number

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

        if self.status.step_number == len(actions):
            print(f"{self.status.sequence.name} sequence complete")
            self.status.sequence = Sequences.Idle
            self.__reset_sequencer()
            return

        # Ensure the status object has the current Action and Condition
        self.status.action = actions[self.status.step_number]
        self.status.condition = conditions[self.status.step_number]

        # Check if value of readback PV is what is required for the next step
        # If the condition has no value then skip as no condition is required
        if self.status.condition.has_value:
            component_pv = self.fe_components[self.status.condition.component_key]
            readback_pv = f"{component_pv}:{self.status.condition.pv_suffix}"

            # Prevent continuous console logging whilst waiting for a condition
            if self.status.last_condition_msg != self.status.condition.msg:
                print(
                    f"CONDITION:\t{self.status.condition.msg}"
                    f"\033[1;33m In Progress \033[0;0m"
                )
                self.status.last_condition_msg = self.status.condition.msg

            # Don't bother with the pre-delay if the action hasn't been actioned
            if self.status.actioned:
                sleep(self.status.condition.pre_delay)

            # Check if the condition PV value == one of the desired values, if it is
            # move to the next step
            actual_condition_value = self.caget(readback_pv, datatype=str)
            for val in self.status.condition.value:
                if actual_condition_value == val:
                    print(
                        f"CONDITION:\t{self.status.condition.msg}"
                        f"\033[1;32m Completed \033[0;0m"
                    )
                    sleep(self.status.condition.post_delay)
                    self.status.inc_step()
                    return

        # Determine if an action needs to be performed
        if not self.status.actioned:
            # Do Action:
            if len(self.status.action.msg) > 1:
                print(f"ACTION:\t\t{self.status.action.msg}")
            sleep(self.status.action.pre_delay)
            self.caput(
                f"""{self.fe_components[self.status.action.component_key]}:{self.status.action.pv_suffix}""",
                self.status.action.value,
            )
            cothread.Yield()
            sleep(self.status.action.post_delay)
            self.status.actioned = True

            if not self.status.condition.has_value:
                self.status.inc_step()
