import os
import sys
import tempfile
import unittest
from typing import TypedDict

sys.path.insert(0, r"D:\nageoffer\agentic-rag-for-dummies\project")

from langgraph.graph import END, START, StateGraph  # noqa: E402
from rag_agent.persistent_checkpointer import PersistentInMemorySaver  # noqa: E402


class CounterState(TypedDict):
    value: int


class PersistentCheckpointerTests(unittest.TestCase):
    def test_checkpoint_survives_reopen_and_delete_thread_clears_it(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "langgraph-checkpoints.pkl")
            saver = PersistentInMemorySaver(path)

            builder = StateGraph(CounterState)
            builder.add_node("increment", lambda state: {"value": state["value"] + 1})
            builder.add_edge(START, "increment")
            builder.add_edge("increment", END)
            graph = builder.compile(checkpointer=saver)

            config = {"configurable": {"thread_id": "thread-persist"}}
            result = graph.invoke({"value": 1}, config=config)

            self.assertEqual(result["value"], 2)
            reopened = PersistentInMemorySaver(path)
            self.assertIsNotNone(reopened.get_tuple(config))

            reopened.delete_thread("thread-persist")
            again = PersistentInMemorySaver(path)
            self.assertIsNone(again.get_tuple(config))
