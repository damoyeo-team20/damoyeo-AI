import asyncio
from types import SimpleNamespace

from app.graph.nodes import n2_context_parser
from app.schemas.meeting_context import ChatTurn


class _ChatLLM:
    async def ainvoke(self, messages):
        self.received_messages = messages
        return SimpleNamespace(content="조용한 곳으로 찾아볼게요. 더 말씀해주실 조건이 있을까요?")


class _StructuredLLM:
    async def ainvoke(self, _messages):
        return SimpleNamespace(
            reply="편안한 저녁 모임으로 정리했어요.",
            purpose="오랜만에 만나 조용한 곳에서 대화하는 저녁 식사",
        )


def test_generate_context_reply_sends_history_and_new_message(monkeypatch):
    llm = _ChatLLM()
    monkeypatch.setattr(n2_context_parser, "get_llm", lambda: llm)

    history = [
        ChatTurn(role="USER", content="오랜만에 만나서 저녁 먹고 이야기하려고요"),
        ChatTurn(role="ASSISTANT", content="편안한 저녁 자리로 준비할게요."),
    ]
    response = asyncio.run(
        n2_context_parser.generate_context_reply(history, "너무 시끄러운 곳은 피하고 싶어요")
    )

    assert response.reply == "조용한 곳으로 찾아볼게요. 더 말씀해주실 조건이 있을까요?"
    roles = [m["role"] for m in llm.received_messages]
    assert roles == ["system", "user", "assistant", "user"]
    assert llm.received_messages[-1]["content"] == "너무 시끄러운 곳은 피하고 싶어요"


def test_finalize_meeting_context_summarizes_full_history(monkeypatch):
    class _LLM:
        def with_structured_output(self, _schema):
            return _StructuredLLM()

    monkeypatch.setattr(n2_context_parser, "get_llm", lambda: _LLM())

    history = [
        ChatTurn(role="USER", content="오랜만에 만나서 저녁 먹고 이야기하려고요"),
        ChatTurn(role="ASSISTANT", content="편안한 저녁 자리로 준비할게요."),
        ChatTurn(role="USER", content="너무 시끄러운 곳은 피하고 싶어요"),
    ]
    response = asyncio.run(n2_context_parser.finalize_meeting_context(history))

    assert response.purpose == "오랜만에 만나 조용한 곳에서 대화하는 저녁 식사"
    assert response.reply == "편안한 저녁 모임으로 정리했어요."
