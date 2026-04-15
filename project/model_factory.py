import config


def _require_setting(value, name, provider):
    if value:
        return value
    raise ValueError(f"Missing required setting `{name}` for provider `{provider}`.")


def _create_openai_chat(model, temperature, api_key, base_url=None):
    from langchain_openai import ChatOpenAI

    kwargs = {
        "model": model,
        "temperature": temperature,
        "api_key": api_key,
    }
    if base_url:
        kwargs["base_url"] = base_url
    return ChatOpenAI(**kwargs)


def _create_openai_embeddings(model, api_key, base_url=None):
    from langchain_openai import OpenAIEmbeddings

    kwargs = {
        "model": model,
        "api_key": api_key,
    }
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAIEmbeddings(**kwargs)


def get_chat_model(provider=None):
    provider_name = (provider or config.ACTIVE_LLM_PROVIDER).lower()

    if provider_name == "deepseek":
        api_key = _require_setting(config.DEEPSEEK_API_KEY, "DEEPSEEK_API_KEY", provider_name)
        return _create_openai_chat(
            model=config.LLM_MODEL,
            temperature=config.LLM_TEMPERATURE,
            api_key=api_key,
            base_url=config.DEEPSEEK_BASE_URL,
        )

    if provider_name == "openai":
        api_key = _require_setting(config.OPENAI_API_KEY, "OPENAI_API_KEY", provider_name)
        return _create_openai_chat(
            model=config.LLM_MODEL,
            temperature=config.LLM_TEMPERATURE,
            api_key=api_key,
            base_url=config.OPENAI_BASE_URL or None,
        )

    if provider_name == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=config.LLM_MODEL,
            temperature=config.LLM_TEMPERATURE,
            base_url=config.OLLAMA_BASE_URL,
        )

    raise ValueError(f"Unsupported LLM provider: {provider_name}")


def get_embedding_model(provider=None):
    provider_name = (provider or config.ACTIVE_EMBEDDING_PROVIDER).lower()

    if provider_name in {"openai", "openai_compatible"}:
        api_key = _require_setting(config.OPENAI_API_KEY, "OPENAI_API_KEY", provider_name)
        return _create_openai_embeddings(
            model=config.EMBEDDING_MODEL,
            api_key=api_key,
            base_url=config.OPENAI_BASE_URL or None,
        )

    if provider_name == "deepseek":
        api_key = _require_setting(config.DEEPSEEK_API_KEY, "DEEPSEEK_API_KEY", provider_name)
        return _create_openai_embeddings(
            model=config.EMBEDDING_MODEL,
            api_key=api_key,
            base_url=config.DEEPSEEK_BASE_URL,
        )

    if provider_name == "huggingface_local":
        from langchain_huggingface import HuggingFaceEmbeddings

        return HuggingFaceEmbeddings(model_name=config.EMBEDDING_MODEL)

    if provider_name == "ollama":
        from langchain_ollama import OllamaEmbeddings

        return OllamaEmbeddings(model=config.EMBEDDING_MODEL, base_url=config.OLLAMA_BASE_URL)

    raise ValueError(f"Unsupported embedding provider: {provider_name}")
