from dls_fe_sequencer.fe_sequencer import Action, Condition, FESequencer

front_end = "FExxI"
no_of_absorbers = 2
s = FESequencer(front_end, no_of_absorbers, True)


def test_constructor():
    assert s.beamline_control_pv == f"{front_end}-CS-BEAM-01:BLCON"
    assert s.fe_components["ABSB"] == f"{front_end}-RS-ABSB-{no_of_absorbers:02d}"
    assert s.fe_components["FV"] == f"{front_end}-VA-FVALV-01"
    assert s.fe_components["SHTR"] == f"{front_end}-PS-SHTR-02"
    assert s.fe_components["V2"] == f"{front_end}-VA-VALVE-02"
    assert s.fe_components["BEAM"] == f"{front_end}-CS-BEAM-01"


def test_configure_close_sequence():

    close_actions = []
    close_actions.append(Action("Updating beam status", "BEAM", "STA", "Closing"))
    close_actions.append(Action("Closing absorber", "ABSB", "CON", "Close"))
    close_actions.append(Action("Closing SHTR 02", "SHTR", "CON", "Close"))
    close_actions.append(Action("Closing V2", "V2", "CON", "Close"))
    close_actions.append(Action("Updating beam status", "BEAM", "STA", "Closed"))

    close_conditions = []
    close_conditions.append(Condition())
    close_conditions.append(
        Condition("Waiting for absorber to close", "ABSB", "STA", ["Closed"])
    )
    close_conditions.append(
        Condition("Waiting for Shutter to close", "SHTR", "STA", ["Closed"])
    )
    close_conditions.append(
        Condition("Waiting for V2 to close", "V2", "STA", ["Closed"])
    )
    close_conditions.append(Condition())

    s.configure_close_sequence(close_actions, close_conditions)
    assert s.close_sequence_actions == close_actions
    assert s.close_sequence_conditions == close_conditions


def test_configure_open_sequence():
    open_actions = []
    open_actions.append(Action("Updating beam status", "BEAM", "STA", "Opening"))
    open_actions.append(Action("Resetting FV1", "FV", "CON", "Reset"))
    open_actions.append(Action("Arming FV1", "FV", "CON", "Arm"))
    open_actions.append(Action("Resetting V2", "V2", "CON", "Reset"))
    open_actions.append(Action("Opening V2", "V2", "CON", "Open"))
    open_actions.append(Action("Resetting Shutter 2", "SHTR", "CON", "Reset"))
    open_actions.append(Action("Opening Shutter 2", "SHTR", "CON", "Open"))
    open_actions.append(Action("Resetting Absorber", "ABSB", "CON", "Reset"))
    open_actions.append(Action("Opening Absorber", "ABSB", "CON", "Open"))
    open_actions.append(Action("Updating beam status", "BEAM", "STA", "Open"))

    open_conditions = []
    open_conditions.append(Condition())
    open_conditions.append(
        Condition("Waiting for FV1 to reset", "FV", "ILKSTA", ["OK", "Run Ilks Ok"])
    )
    open_conditions.append(
        Condition("Waiting for FV1 to arm", "FV", "STA", ["Open Armed"])
    )
    open_conditions.append(
        Condition("Waiting for V2 to reset", "V2", "ILKSTA", ["OK", "Run Ilks Ok"])
    )
    open_conditions.append(Condition("Waiting for V2 to Open", "V2", "STA", ["Open"]))
    open_conditions.append(
        Condition(
            "Waiting for Shutter 2 to reset", "SHTR", "ILKSTA", ["OK", "Run Ilks Ok"]
        )
    )
    open_conditions.append(
        Condition("Waiting for Shutter 2 to Open", "SHTR", "STA", ["Open"])
    )
    open_conditions.append(
        Condition(
            "Waiting for Absorber to reset", "ABSB", "ILKSTA", ["OK", "Run Ilks Ok"]
        )
    )
    open_conditions.append(
        Condition("Waiting for Absorber to Open", "ABSB", "STA", ["Open"])
    )
    open_conditions.append(Condition())

    s.configure_open_sequence(open_actions, open_conditions)
    assert s.open_sequence_actions == open_actions
    assert s.open_sequence_conditions == open_conditions
