import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, r"D:\nageoffer\agentic-rag-for-dummies\project")

from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402
from rag_agent.nodes import handle_appointment, handle_cancel_appointment  # noqa: E402


def make_tool_message(name: str, args: dict) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": f"call-{name}", "type": "tool_call"}],
    )


class FakeToolLLM:
    def __init__(self, responses):
        self.responses = list(responses)

    def with_config(self, **kwargs):
        return self

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        return self.responses.pop(0)


class FakeAppointmentService:
    def __init__(self):
        self.created = []
        self.cancelled = []
        self.schedules = []
        self.candidate_calls = []
        self.next_schedule = None
        self.next_booking = None
        self.next_candidates = []
        self.next_cancel_result = None

    def find_available_schedule(self, department, schedule_date, time_slot, doctor_name=None):
        self.schedules.append((department, schedule_date, time_slot, doctor_name))
        return self.next_schedule

    def create_appointment(self, thread_id, department, schedule_date, time_slot, doctor_name=None):
        self.created.append((thread_id, department, schedule_date, time_slot, doctor_name))
        return self.next_booking

    def find_candidate_appointments(self, thread_id, appointment_no=None, department=None, schedule_date=None):
        self.candidate_calls.append((thread_id, appointment_no, department, schedule_date))
        return list(self.next_candidates)

    def cancel_appointment(self, thread_id, appointment_id):
        self.cancelled.append((thread_id, appointment_id))
        return self.next_cancel_result


class AppointmentFlowTests(unittest.TestCase):
    def test_handle_appointment_prepares_preview_before_execution(self):
        llm = FakeToolLLM(
            [
                make_tool_message(
                    "AppointmentActionCall",
                    {
                        "action": "prepare_booking",
                        "department": "呼吸内科",
                        "date": "明天",
                        "time_slot": "上午",
                        "doctor_name": "张医生",
                        "clarification": "",
                    },
                )
            ]
        )
        service = FakeAppointmentService()
        tomorrow = date.today() + timedelta(days=1)
        service.next_schedule = {
            "schedule_id": 1,
            "doctor_id": 10,
            "department_id": 20,
            "schedule_date": tomorrow,
            "time_slot": "morning",
            "quota_available": 3,
            "doctor_name": "张医生",
            "department_name": "呼吸内科",
        }
        state = {
            "thread_id": "thread-1",
            "messages": [HumanMessage(content="帮我预约明天上午呼吸内科张医生")],
            "appointment_context": {},
            "recommended_department": "",
        }

        result = handle_appointment(state, llm, service)

        self.assertEqual(result["pending_action_type"], "appointment")
        self.assertEqual(result["pending_action_payload"]["department"], "呼吸内科")
        self.assertIn("确认预约", result["messages"][0].content)
        self.assertEqual(service.created, [])

    def test_handle_appointment_confirmation_executes_booking(self):
        llm = FakeToolLLM([])
        service = FakeAppointmentService()
        service.next_booking = {
            "appointment_no": "APTBOOK123",
            "department": "呼吸内科",
            "date": "2026-04-18",
            "time_slot": "morning",
            "doctor_name": "张医生",
            "status": "booked",
        }
        state = {
            "thread_id": "thread-2",
            "messages": [HumanMessage(content="确认预约")],
            "appointment_context": {},
            "pending_action_type": "appointment",
            "pending_action_payload": {
                "department": "呼吸内科",
                "date": "2026-04-18",
                "time_slot": "morning",
                "doctor_name": "张医生",
            },
            "pending_confirmation_id": "confirm-1",
        }

        result = handle_appointment(state, llm, service)

        self.assertEqual(service.created[0][1], "呼吸内科")
        self.assertEqual(result["pending_action_type"], "")
        self.assertEqual(result["last_appointment_no"], "APTBOOK123")
        self.assertIn("预约成功", result["messages"][0].content)

    def test_handle_appointment_non_explicit_confirmation_does_not_execute(self):
        llm = FakeToolLLM(
            [
                make_tool_message(
                    "AppointmentActionCall",
                    {
                        "action": "prepare_booking",
                        "department": "心内科",
                        "date": "明天",
                        "time_slot": "下午",
                        "doctor_name": "",
                        "clarification": "",
                    },
                )
            ]
        )
        service = FakeAppointmentService()
        tomorrow = date.today() + timedelta(days=1)
        service.next_schedule = {
            "schedule_id": 2,
            "doctor_id": 11,
            "department_id": 21,
            "schedule_date": tomorrow,
            "time_slot": "afternoon",
            "quota_available": 5,
            "doctor_name": "李医生",
            "department_name": "心内科",
        }
        state = {
            "thread_id": "thread-3",
            "messages": [HumanMessage(content="可以")],
            "appointment_context": {},
            "pending_action_type": "appointment",
            "pending_action_payload": {
                "department": "呼吸内科",
                "date": tomorrow.isoformat(),
                "time_slot": "morning",
                "doctor_name": "张医生",
            },
            "pending_confirmation_id": "confirm-2",
            "recommended_department": "",
        }

        result = handle_appointment(state, llm, service)

        self.assertEqual(service.created, [])
        self.assertEqual(result["pending_action_type"], "appointment")
        self.assertIn("确认预约", result["messages"][0].content)

    def test_handle_cancel_appointment_requires_candidate_selection_when_ambiguous(self):
        llm = FakeToolLLM(
            [
                make_tool_message(
                    "CancelActionCall",
                    {
                        "action": "prepare_cancellation",
                        "appointment_no": "",
                        "department": "心内科",
                        "date": "明天",
                        "clarification": "",
                    },
                )
            ]
        )
        service = FakeAppointmentService()
        tomorrow = date.today() + timedelta(days=1)
        service.next_candidates = [
            {
                "appointment_id": 1,
                "appointment_no": "APT001",
                "appointment_date": tomorrow,
                "time_slot": "morning",
                "department": "心内科",
                "doctor_name": "李医生",
            },
            {
                "appointment_id": 2,
                "appointment_no": "APT002",
                "appointment_date": tomorrow,
                "time_slot": "afternoon",
                "department": "心内科",
                "doctor_name": "王医生",
            },
        ]
        state = {
            "thread_id": "thread-4",
            "messages": [HumanMessage(content="帮我取消明天心内科的预约")],
            "appointment_context": {},
            "last_appointment_no": "",
        }

        result = handle_cancel_appointment(state, llm, service)

        self.assertEqual(result["pending_action_type"], "")
        self.assertEqual(len(result["pending_candidates"]), 2)
        self.assertIn("第 1 个", result["messages"][0].content)

    def test_handle_cancel_appointment_candidate_selection_prepares_preview(self):
        llm = FakeToolLLM([])
        tomorrow = date.today() + timedelta(days=1)
        state = {
            "thread_id": "thread-5",
            "messages": [HumanMessage(content="取消第 2 个")],
            "pending_candidates": [
                {
                    "appointment_id": 1,
                    "appointment_no": "APT001",
                    "appointment_date": tomorrow,
                    "time_slot": "morning",
                    "department": "心内科",
                    "doctor_name": "李医生",
                },
                {
                    "appointment_id": 2,
                    "appointment_no": "APT002",
                    "appointment_date": tomorrow,
                    "time_slot": "afternoon",
                    "department": "心内科",
                    "doctor_name": "王医生",
                },
            ],
        }

        result = handle_cancel_appointment(state, llm, FakeAppointmentService())

        self.assertEqual(result["pending_action_type"], "cancel_appointment")
        self.assertEqual(result["pending_action_payload"]["appointment_id"], "2")
        self.assertIn("确认取消", result["messages"][0].content)

    def test_handle_cancel_appointment_confirmation_executes_cancellation(self):
        llm = FakeToolLLM([])
        service = FakeAppointmentService()
        service.next_cancel_result = {
            "appointment_no": "APT900",
            "date": "2026-04-19",
            "time_slot": "afternoon",
            "department": "心内科",
            "status": "cancelled",
        }
        state = {
            "thread_id": "thread-6",
            "messages": [HumanMessage(content="确认取消")],
            "pending_action_type": "cancel_appointment",
            "pending_action_payload": {
                "appointment_id": "9",
                "appointment_no": "APT900",
                "department": "心内科",
                "date": "2026-04-19",
                "time_slot": "afternoon",
            },
            "pending_confirmation_id": "confirm-3",
        }

        result = handle_cancel_appointment(state, llm, service)

        self.assertEqual(service.cancelled[0], ("thread-6", 9))
        self.assertEqual(result["pending_action_type"], "")
        self.assertIn("已为你取消预约", result["messages"][0].content)


if __name__ == "__main__":
    unittest.main()
