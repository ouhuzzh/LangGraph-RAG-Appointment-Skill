import uuid
import os
import config
from db.vector_db_manager import VectorDbManager
from db.parent_store_manager import ParentStoreManager
from document_chunker import DocumentChuncker
from rag_agent.tools import ToolFactory
from rag_agent.graph import create_agent_graph
from core.observability import Observability

class RAGSystem:

    def __init__(self, collection_name=config.CHILD_COLLECTION):
        self.collection_name = collection_name
        self.vector_db = VectorDbManager()
        self.parent_store = ParentStoreManager()
        self.chunker = DocumentChuncker()
        self.observability = Observability()
        self.agent_graph = None
        self.thread_id = str(uuid.uuid4())
        self.recursion_limit = config.GRAPH_RECURSION_LIMIT

    def _create_llm(self):
        """根据配置创建 LLM 实例"""
        provider = config.LLM_PROVIDER
        llm_config = config.LLM_CONFIGS[provider]
        
        if provider == "openai":
            from langchain_openai import ChatOpenAI
            api_key = os.environ.get(llm_config["api_key_env"])
            if not api_key:
                raise ValueError(f"请设置环境变量 {llm_config['api_key_env']}")
            
            kwargs = {
                "model": llm_config["model"],
                "temperature": config.LLM_TEMPERATURE,
                "api_key": api_key,
            }
            base_url = os.environ.get(llm_config.get("base_url_env", ""))
            if base_url:
                kwargs["base_url"] = base_url
            return ChatOpenAI(**kwargs)
            
        elif provider == "anthropic":
            from langchain_anthropic import ChatAnthropic
            api_key = os.environ.get(llm_config["api_key_env"])
            if not api_key:
                raise ValueError(f"请设置环境变量 {llm_config['api_key_env']}")
            return ChatAnthropic(
                model=llm_config["model"],
                temperature=config.LLM_TEMPERATURE,
                api_key=api_key,
            )
            
        elif provider == "google":
            from langchain_google_genai import ChatGoogleGenerativeAI
            api_key = os.environ.get(llm_config["api_key_env"])
            if not api_key:
                raise ValueError(f"请设置环境变量 {llm_config['api_key_env']}")
            return ChatGoogleGenerativeAI(
                model=llm_config["model"],
                temperature=config.LLM_TEMPERATURE,
                google_api_key=api_key,
            )
            
        elif provider == "ollama":
            from langchain_ollama import ChatOllama
            return ChatOllama(
                model=llm_config["model"],
                temperature=config.LLM_TEMPERATURE,
                base_url=llm_config["base_url"],
            )
        else:
            raise ValueError(f"不支持的 LLM 提供商: {provider}")

    def initialize(self):
        self.vector_db.create_collection(self.collection_name)
        collection = self.vector_db.get_collection(self.collection_name)

        llm = self._create_llm()
        tools = ToolFactory(collection).create_tools()
        self.agent_graph = create_agent_graph(llm, tools)

    def get_config(self):
        cfg = {"configurable": {"thread_id": self.thread_id}, "recursion_limit": self.recursion_limit}
        handler = self.observability.get_handler()
        if handler:
            cfg["callbacks"] = [handler]
        return cfg

    def reset_thread(self):
        try:
            self.agent_graph.checkpointer.delete_thread(self.thread_id)
        except Exception as e:
            print(f"Warning: Could not delete thread {self.thread_id}: {e}")
        self.thread_id = str(uuid.uuid4())