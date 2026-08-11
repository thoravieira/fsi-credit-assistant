"""Chat model factory — one place that reads `LLM_MODEL`.

Nodes written before this file build their own model in a local `_default_llm()`
so tests can patch them per node; this factory serves the code that has no such
seam, notably the deep agent, which is constructed once per process.
"""

from langchain_core.language_models import BaseChatModel

from app.config import get_settings


def get_chat_model(temperature: float = 0.2) -> BaseChatModel:
    """A chat model that can call tools.

    `reasoning_effort="none"` is a requirement, not a preference. `LLM_MODEL` is
    a reasoning model, and the Chat Completions API refuses function tools while
    reasoning is on:

        Function tools with reasoning_effort are not supported for
        gpt-5.6-luna in /v1/chat/completions. To use function tools, use
        /v1/responses or set reasoning_effort to 'none'.

    The Responses API would allow both, at a latency cost the 15 s budget in
    SDD 06 §6 has no room for. Nodes that call no tools are unaffected either
    way, so one factory covers both.
    """
    from langchain_openai import ChatOpenAI

    settings = get_settings()
    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openai_api_key,
        temperature=temperature,
        reasoning_effort="none",
    )
