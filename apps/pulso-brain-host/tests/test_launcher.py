from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


APP_DIR = Path(__file__).resolve().parents[1]


class LauncherTest(unittest.TestCase):
    def test_early_native_style_exit_is_reported_with_signal(self):
        with tempfile.TemporaryDirectory() as temporary:
            runtime_dir = Path(temporary) / "state"
            runner = Path(temporary) / "fake-runner.sh"
            runner.write_text(
                "#!/usr/bin/env bash\nulimit -c 0\nkill -ABRT \"$$\"\n",
                encoding="utf-8",
            )
            runner.chmod(0o755)
            environment = {
                **os.environ,
                "PULSO_BRAIN_RUNTIME_DIR": str(runtime_dir),
                "PULSO_BRAIN_RUNNER": str(runner),
                "PULSO_STARTUP_GRACE_S": "1",
            }

            result = subprocess.run(
                [str(APP_DIR / "start.sh")],
                cwd=APP_DIR,
                env=environment,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("exited during its 1s startup check", result.stderr)
            exit_record = (runtime_dir / "brain-host.exit").read_text(encoding="utf-8")
            self.assertIn("exit_code=134", exit_record)
            self.assertIn("signal=6", exit_record)
            self.assertFalse((runtime_dir / "brain-host.pid").exists())

    def test_supervised_process_can_be_inspected_and_stopped(self):
        with tempfile.TemporaryDirectory() as temporary:
            runtime_dir = Path(temporary) / "state"
            runner = Path(temporary) / "fake-runner.sh"
            runner.write_text(
                "#!/usr/bin/env bash\n"
                "trap 'exit 0' TERM INT\n"
                "while true; do sleep 0.1; done\n",
                encoding="utf-8",
            )
            runner.chmod(0o755)
            environment = {
                **os.environ,
                "PULSO_BRAIN_RUNTIME_DIR": str(runtime_dir),
                "PULSO_BRAIN_RUNNER": str(runner),
                "PULSO_STARTUP_GRACE_S": "1",
            }

            started = subprocess.run(
                [str(APP_DIR / "start.sh")],
                cwd=APP_DIR,
                env=environment,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            self.assertEqual(started.returncode, 0, started.stdout + started.stderr)
            inspected = subprocess.run(
                [str(APP_DIR / "status.sh")],
                cwd=APP_DIR,
                env=environment,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            self.assertEqual(inspected.returncode, 0, inspected.stdout + inspected.stderr)
            self.assertIn("process=running", inspected.stdout)
            self.assertIn("health=unknown", inspected.stdout)

            stopped = subprocess.run(
                [str(APP_DIR / "stop.sh")],
                cwd=APP_DIR,
                env=environment,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            self.assertEqual(stopped.returncode, 0, stopped.stdout + stopped.stderr)
            self.assertFalse((runtime_dir / "brain-host.pid").exists())
            exit_record = (runtime_dir / "brain-host.exit").read_text(encoding="utf-8")
            self.assertIn("exit_code=0", exit_record)
            self.assertIn("signal=0", exit_record)

    def test_status_does_not_label_process_state_as_live_health(self):
        with tempfile.TemporaryDirectory() as temporary:
            environment = {
                **os.environ,
                "PULSO_BRAIN_RUNTIME_DIR": temporary,
            }
            result = subprocess.run(
                [str(APP_DIR / "status.sh")],
                cwd=APP_DIR,
                env=environment,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("process=stopped", result.stdout)
            self.assertNotIn("live", result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
