import contextlib
import io
import unittest
from unittest.mock import patch

from scripts.run_scoped_request_eval import main


class ScopedEvalGuards(unittest.TestCase):
    def test_offline_default_never_reads_api_configuration(self):
        with patch("sys.argv", ["eval"]), patch("scripts.run_scoped_request_eval.configure_eval_environment") as configure, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(), 0)
        configure.assert_not_called()

    def test_live_requires_selected_case_and_review_before_api_configuration(self):
        for argv in (["--live"], ["--live", "--case", "A1-D01", "--turn", "2", "--experiment", "missing"]):
            with self.subTest(argv=argv), patch("sys.argv", ["eval", *argv]), patch("scripts.run_scoped_request_eval.configure_eval_environment") as configure, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as stopped:
                    main()
                self.assertEqual(stopped.exception.code, 2)
            configure.assert_not_called()
