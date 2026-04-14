import subprocess
import sys

from dls_fe_sequencer import __version__


def test_cli_version():
    cmd = [sys.executable, "-m", "dls_fe_sequencer", "--version"]
    assert subprocess.check_output(cmd).decode().strip() == __version__
