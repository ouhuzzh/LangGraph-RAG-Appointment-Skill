import os
import pickle
import tempfile
from collections import defaultdict
from threading import RLock

from langgraph.checkpoint.memory import InMemorySaver


class PersistentInMemorySaver(InMemorySaver):
    """Persist LangGraph checkpoints to a local file while keeping InMemory semantics."""

    def __init__(self, path: str):
        super().__init__()
        self.path = os.path.abspath(path)
        self._lock = RLock()
        self._last_mtime = None
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._reload_from_disk(force=True)

    def _make_storage(self):
        return defaultdict(lambda: defaultdict(dict))

    def _snapshot(self) -> dict:
        return {
            "storage": {
                thread_id: {
                    checkpoint_ns: dict(checkpoints)
                    for checkpoint_ns, checkpoints in namespaces.items()
                }
                for thread_id, namespaces in self.storage.items()
            },
            "writes": {
                key: dict(value)
                for key, value in self.writes.items()
            },
            "blobs": dict(self.blobs),
        }

    def _restore(self, payload: dict) -> None:
        storage = self._make_storage()
        for thread_id, namespaces in (payload.get("storage") or {}).items():
            storage[thread_id] = defaultdict(
                dict,
                {
                    checkpoint_ns: dict(checkpoints)
                    for checkpoint_ns, checkpoints in (namespaces or {}).items()
                },
            )
        self.storage = storage
        self.writes = defaultdict(
            dict,
            {
                tuple(key): dict(value)
                for key, value in (payload.get("writes") or {}).items()
            },
        )
        self.blobs = dict(payload.get("blobs") or {})

    def _reload_from_disk(self, *, force: bool = False) -> None:
        if not os.path.exists(self.path):
            if force or self._last_mtime is not None:
                self.storage = self._make_storage()
                self.writes = defaultdict(dict)
                self.blobs = {}
                self._last_mtime = None
            return

        mtime = os.path.getmtime(self.path)
        if not force and self._last_mtime is not None and mtime <= self._last_mtime:
            return

        with open(self.path, "rb") as handle:
            payload = pickle.load(handle)
        self._restore(payload if isinstance(payload, dict) else {})
        self._last_mtime = mtime

    def _persist_to_disk(self) -> None:
        directory = os.path.dirname(self.path)
        os.makedirs(directory, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix="langgraph-checkpoint-", suffix=".tmp", dir=directory)
        try:
            with os.fdopen(fd, "wb") as handle:
                pickle.dump(self._snapshot(), handle, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(tmp_path, self.path)
            self._last_mtime = os.path.getmtime(self.path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def get_tuple(self, config):
        with self._lock:
            self._reload_from_disk()
            return super().get_tuple(config)

    def list(self, config, *, filter=None, before=None, limit=None):
        with self._lock:
            self._reload_from_disk()
            items = list(super().list(config, filter=filter, before=before, limit=limit))
        for item in items:
            yield item

    def put(self, config, checkpoint, metadata, new_versions):
        with self._lock:
            self._reload_from_disk()
            result = super().put(config, checkpoint, metadata, new_versions)
            self._persist_to_disk()
            return result

    def put_writes(self, config, writes, task_id, task_path=""):
        with self._lock:
            self._reload_from_disk()
            super().put_writes(config, writes, task_id, task_path)
            self._persist_to_disk()

    def delete_thread(self, thread_id: str) -> None:
        with self._lock:
            self._reload_from_disk()
            super().delete_thread(thread_id)
            self._persist_to_disk()
