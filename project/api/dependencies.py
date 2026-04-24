import threading

from core.chat_interface import ChatInterface
from core.document_manager import DocumentManager
from core.rag_system import RAGSystem


class ApiContainer:
    def __init__(self):
        self.rag_system = RAGSystem()
        self.rag_system.start_background_initialize()
        self.chat_interface = ChatInterface(self.rag_system)
        self.document_manager = DocumentManager(self.rag_system)
        self._chat_lock = threading.Lock()

    @property
    def chat_lock(self):
        return self._chat_lock


_container: ApiContainer | None = None
_container_lock = threading.Lock()


def get_container() -> ApiContainer:
    global _container
    if _container is None:
        with _container_lock:
            if _container is None:
                _container = ApiContainer()
    return _container


def set_container_for_tests(container):
    global _container
    _container = container

