import unittest


class DailyAgentPackageTest(unittest.TestCase):
    def test_daily_agent_exports_daily_chat_agent(self):
        from daily_agent import DailyChatAgent

        self.assertTrue(callable(DailyChatAgent))


if __name__ == "__main__":
    unittest.main()
