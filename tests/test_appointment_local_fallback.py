import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "project"))

from rag_agent import appointment_nodes  # noqa: E402


class AppointmentLocalFallbackRoutingTests(unittest.TestCase):
    """handle_appointment_skill must fall back to the local-DB handlers (which
    carry slot hold + idempotency) when no MCP backend is bound, instead of
    dead-ending on 'please bind a hospital'. The MCP path runs only when a
    backend truly exists. Reschedule stays MCP-only."""

    def _state(self, intent):
        return {"intent": intent, "primary_intent": intent, "user_id": "u1", "messages": []}

    def test_appointment_without_mcp_uses_local_legacy(self):
        with patch.object(appointment_nodes.MCPAppointmentBackend, "try_create", return_value=None), \
             patch.object(appointment_nodes, "_handle_appointment_legacy", return_value={"ok": "legacy"}) as legacy:
            result = appointment_nodes.handle_appointment_skill(
                self._state("appointment"), MagicMock(), MagicMock(), mcp_pool=None,
            )
        legacy.assert_called_once()
        self.assertEqual(result, {"ok": "legacy"})

    def test_cancel_without_mcp_uses_local_cancel_legacy(self):
        with patch.object(appointment_nodes.MCPAppointmentBackend, "try_create", return_value=None), \
             patch.object(appointment_nodes, "_handle_cancel_appointment_legacy", return_value={"ok": "cancel"}) as legacy:
            result = appointment_nodes.handle_appointment_skill(
                self._state("cancel_appointment"), MagicMock(), MagicMock(), mcp_pool=None,
            )
        legacy.assert_called_once()
        self.assertEqual(result, {"ok": "cancel"})

    def test_appointment_with_mcp_stays_on_skill_path(self):
        # MCP backend available -> must NOT divert to the local handler.
        with patch.object(appointment_nodes.MCPAppointmentBackend, "try_create", return_value=object()), \
             patch.object(appointment_nodes, "_handle_appointment_legacy") as legacy:
            try:
                appointment_nodes.handle_appointment_skill(
                    self._state("appointment"), MagicMock(), MagicMock(), mcp_pool=MagicMock(),
                )
            except Exception:
                pass  # downstream skill logic may need more mocks; routing is the assertion
        legacy.assert_not_called()

    def test_reschedule_without_mcp_does_not_use_local(self):
        with patch.object(appointment_nodes.MCPAppointmentBackend, "try_create", return_value=None), \
             patch.object(appointment_nodes, "_handle_appointment_legacy") as legacy, \
             patch.object(appointment_nodes, "_handle_cancel_appointment_legacy") as cancel_legacy:
            try:
                appointment_nodes.handle_appointment_skill(
                    self._state("reschedule_appointment"), MagicMock(), MagicMock(), mcp_pool=None,
                )
            except Exception:
                pass
        legacy.assert_not_called()
        cancel_legacy.assert_not_called()


if __name__ == "__main__":
    unittest.main()
