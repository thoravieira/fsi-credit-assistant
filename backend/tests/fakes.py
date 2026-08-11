"""Test doubles shared across the graph and agent tests.

Wiring and routing are asserted with fakes; model *output* never is (SDD 14 §2).
"""

from collections.abc import Iterator

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGenerationChunk


class ScriptedChatModel(GenericFakeChatModel):
    """Replays a fixed list of `AIMessage`s, tool calls included.

    Two overrides are needed to stand in for a real model inside a deep agent:

    - `bind_tools`, because `GenericFakeChatModel` raises `NotImplementedError`
      and the agent factory calls it unconditionally;
    - `_stream`, because the inherited one splits each message into *character*
      chunks and drops `tool_calls` along the way. The negotiation wrapper
      streams its agent (SDD 06 §6), so every test would otherwise exercise a
      model that cannot call a tool.

    One chunk per scripted message keeps `tool_calls` intact — verified: the
    chunk's validator turns them into `tool_call_chunks` and back.
    """

    def __init__(self, responses: list[AIMessage]):
        super().__init__(messages=iter(responses))

    def bind_tools(self, tools, **kwargs):
        return self

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs,
    ) -> Iterator[ChatGenerationChunk]:
        message = next(self.messages)
        chunk = ChatGenerationChunk(
            message=AIMessageChunk(content=message.content, tool_calls=message.tool_calls)
        )
        if run_manager:
            run_manager.on_llm_new_token(message.content, chunk=chunk)
        yield chunk


def tool_call(name: str, call_id: str = "call-1", **args) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])
