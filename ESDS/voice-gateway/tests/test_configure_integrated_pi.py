from __future__ import annotations

import importlib.util
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).parents[1] / "scripts" / "configure_integrated_pi.py"
SPEC = importlib.util.spec_from_file_location("configure_integrated_pi", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class IntegratedPiConfigTests(unittest.TestCase):
    def test_consent_requires_explicit_acknowledgement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            voice_env = root / "voice" / "env"
            agent_env = root / "agent" / "env"
            agent_data = root / "data"
            voice_env.parent.mkdir(parents=True)
            voice_env.write_text("DASHSCOPE_API_KEY=test-key\n", encoding="utf-8")
            with (
                patch.object(MODULE, "VOICE_ENV", voice_env),
                patch.object(MODULE, "AGENT_ENV", agent_env),
                patch.object(MODULE, "AGENT_DATA", agent_data),
                patch.object(MODULE, "device_id", return_value="esds-pi-test"),
            ):
                MODULE.configure(acknowledge_consent=False)
                pending = MODULE.read_env(agent_env)
                self.assertEqual(
                    pending["VOICE_CONSENT_ACKNOWLEDGED"], "false"
                )
                self.assertEqual(MODULE.check(), 1)

                MODULE.configure(acknowledge_consent=True)
                agent = MODULE.read_env(agent_env)
                voice = MODULE.read_env(voice_env)
                self.assertEqual(agent["VOICE_CONSENT_ACKNOWLEDGED"], "true")
                self.assertEqual(
                    agent["VOICE_BRIDGE_TOKEN"],
                    voice["ESDS_AGENT_BRIDGE_TOKEN"],
                )
                self.assertEqual(MODULE.check(), 0)
                self.assertEqual(
                    stat.S_IMODE(agent_env.stat().st_mode), 0o600
                )


if __name__ == "__main__":
    unittest.main()
