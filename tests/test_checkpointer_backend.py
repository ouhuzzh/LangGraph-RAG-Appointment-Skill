import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "project"))

import config  # noqa: E402
from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402
from rag_agent import graph as graph_module  # noqa: E402
from rag_agent.persistent_checkpointer import PersistentInMemorySaver  # noqa: E402


class CheckpointerBackendTests(unittest.TestCase):
    """Backend selection for the graph checkpointer (pickle | postgres, fail-open)."""

    def _tmp_ckpt_path(self):
        tmp = tempfile.TemporaryDirectory(prefix="ckpt-backend-")
        self.addCleanup(tmp.cleanup)
        return str(Path(tmp.name) / "ckpt.pkl")

    def test_default_backend_is_persistent_file(self):
        with patch.object(config, "GRAPH_CHECKPOINT_BACKEND", "pickle"), \
             patch.object(config, "ENABLE_PERSISTENT_GRAPH_CHECKPOINT", True), \
             patch.object(config, "LANGGRAPH_CHECKPOINT_PATH", self._tmp_ckpt_path()):
            checkpointer = graph_module._build_checkpointer()
        self.assertIsInstance(checkpointer, PersistentInMemorySaver)

    def test_memory_backend_when_persistence_disabled(self):
        with patch.object(config, "GRAPH_CHECKPOINT_BACKEND", "pickle"), \
             patch.object(config, "ENABLE_PERSISTENT_GRAPH_CHECKPOINT", False):
            checkpointer = graph_module._build_checkpointer()
        self.assertIs(type(checkpointer), InMemorySaver)

    def test_postgres_backend_used_when_available(self):
        sentinel = object()
        with patch.object(config, "GRAPH_CHECKPOINT_BACKEND", "postgres"), \
             patch.object(graph_module, "_build_postgres_checkpointer", return_value=sentinel):
            self.assertIs(graph_module._build_checkpointer(), sentinel)

    def test_postgres_backend_fails_open_to_pickle(self):
        # Postgres unavailable must NOT crash boot — fall back to the file saver.
        with patch.object(config, "GRAPH_CHECKPOINT_BACKEND", "postgres"), \
             patch.object(graph_module, "_build_postgres_checkpointer", return_value=None), \
             patch.object(config, "ENABLE_PERSISTENT_GRAPH_CHECKPOINT", True), \
             patch.object(config, "LANGGRAPH_CHECKPOINT_PATH", self._tmp_ckpt_path()):
            checkpointer = graph_module._build_checkpointer()
        self.assertIsInstance(checkpointer, PersistentInMemorySaver)


if __name__ == "__main__":
    unittest.main()
