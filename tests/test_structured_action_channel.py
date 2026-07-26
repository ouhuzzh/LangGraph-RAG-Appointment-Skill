import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "project"))

from api.sse import _detect_card_events, resolve_structured_action  # noqa: E402
from rag_agent.node_helpers import (  # noqa: E402
    _is_abort_request,
    _is_explicit_confirmation,
    _starts_with_polite_decline,
)


def _container_with_state(state: dict):
    session_memory = SimpleNamespace(get_state=lambda thread_id: dict(state))
    rag_system = SimpleNamespace(session_memory=session_memory)
    chat_interface = SimpleNamespace(rag_system=rag_system)
    return SimpleNamespace(chat_interface=chat_interface)


class ResolveStructuredActionTests(unittest.TestCase):
    def test_confirm_with_matching_id_returns_canonical_text(self):
        container = _container_with_state({"pending_confirmation_id": "abc123"})
        message, error = resolve_structured_action(
            container, "t1", {"type": "confirm_appointment", "confirmation_id": "abc123"}
        )
        self.assertEqual(message, "确认预约")
        self.assertEqual(error, "")

    def test_mismatched_id_is_rejected(self):
        container = _container_with_state({"pending_confirmation_id": "abc123"})
        message, error = resolve_structured_action(
            container, "t1", {"type": "confirm_appointment", "confirmation_id": "stale-id"}
        )
        self.assertEqual(message, "")
        self.assertIn("过期", error)

    def test_no_pending_confirmation_is_rejected(self):
        container = _container_with_state({"pending_confirmation_id": ""})
        _message, error = resolve_structured_action(
            container, "t1", {"type": "confirm_appointment", "confirmation_id": "abc123"}
        )
        self.assertIn("过期", error)

    def test_unknown_action_type_is_rejected(self):
        container = _container_with_state({"pending_confirmation_id": "abc123"})
        _message, error = resolve_structured_action(
            container, "t1", {"type": "delete_everything", "confirmation_id": "abc123"}
        )
        self.assertIn("无法识别", error)

    def test_abort_returns_canonical_abort_text(self):
        container = _container_with_state({"pending_confirmation_id": "abc123"})
        message, error = resolve_structured_action(
            container, "t1", {"type": "abort_appointment", "confirmation_id": "abc123"}
        )
        self.assertEqual(message, "算了，先不预约了")
        self.assertEqual(error, "")


class CanonicalTextContractTests(unittest.TestCase):
    """The canonical command texts must keep matching the rule gates —
    if these break, button clicks silently stop working."""

    def test_confirm_text_hits_confirmation_gate(self):
        self.assertTrue(_is_explicit_confirmation("确认预约", "appointment"))

    def test_abort_text_hits_abort_gate(self):
        self.assertTrue(_is_abort_request("算了，先不预约了"))

    def test_abort_text_is_not_a_polite_decline(self):
        # _should_continue_pending_action short-circuits on polite declines;
        # the canonical abort text must not be swallowed by that branch.
        self.assertFalse(_starts_with_polite_decline("算了，先不预约了"))


class CardEnrichmentTests(unittest.TestCase):
    def _extract_card(self, events):
        payload = events[-1].split("data: ", 1)[1].strip()
        return json.loads(json.loads(payload)["content"])

    def test_preview_card_carries_actions_when_confirmation_pending(self):
        state = {
            "pending_confirmation_id": "cid-9",
            "pending_action_type": "appointment",
            "pending_action_payload": {"department": "呼吸内科", "date": "2026-08-01", "time_slot": "上午"},
        }
        events = _detect_card_events("已为你锁定号源，请确认预约。", "t1", state)
        card = self._extract_card(events)
        self.assertEqual(card["card_type"], "appointment_preview")
        self.assertEqual(card["actions"][0]["confirmation_id"], "cid-9")
        self.assertEqual(card["details"]["department"], "呼吸内科")

    def test_preview_card_has_no_actions_without_pending_state(self):
        events = _detect_card_events("已为你锁定号源，请确认预约。", "t1", {})
        card = self._extract_card(events)
        self.assertNotIn("actions", card)


if __name__ == "__main__":
    unittest.main()
