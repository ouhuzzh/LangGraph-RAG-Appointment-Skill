import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "project"))

from core.chat_interface import SILENT_NODES  # noqa: E402


class SilentNodeCoverageTests(unittest.TestCase):
    """Internal reasoning nodes call an LLM but must never stream tokens to the
    user. stream_mode='messages' emits every node's LLM output, filtered only by
    SILENT_NODES — a node that reasons in JSON and is missing here leaks raw
    structured output into the chat (defect #14: plan_tasks leaked its task JSON
    plus a disobedient bridge sentence)."""

    def test_plan_tasks_is_silent(self):
        self.assertIn("plan_tasks", SILENT_NODES)

    def test_known_reasoning_nodes_are_silent(self):
        for node in ("rewrite_query", "intent_router", "plan_tasks", "decompose_tasks", "self_eval"):
            with self.subTest(node=node):
                self.assertIn(node, SILENT_NODES)

    def test_appointment_nodes_are_silent(self):
        # Appointment nodes only call the LLM to parse slots into a tool call;
        # their real replies are constructed strings returned via graph state.
        # Streaming the parsing filler leaked a dead-end acknowledgement
        # ("好的，我先查一下…") and hid the discovery/preview message (defect #15).
        for node in ("handle_appointment", "handle_appointment_skill", "handle_cancel_appointment"):
            with self.subTest(node=node):
                self.assertIn(node, SILENT_NODES)


if __name__ == "__main__":
    unittest.main()
