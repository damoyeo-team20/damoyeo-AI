"""N1 Smalltalk Handler.

라우터가 분리해낸 잡담 부분에 짧게 반응하면서, Vocabulary에 실제로 존재하는 카테고리를 근거로
사용자가 어떤 선호를 말하면 되는지 구체적으로 유도한다.
"""

import logging

from app.core.errors import AIServiceError
from app.core.llm import get_llm
from app.graph.preference_state import PreferenceState
from app.prompts.n1_smalltalk_handler import SYSTEM_PROMPT
from app.services.vocabulary_client import VocabularyEntry, fetch_vocabulary

logger = logging.getLogger(__name__)


def _extract_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and "text" in block:
                parts.append(block["text"])
        return "\n".join(parts)
    return str(content)


def _format_domains(vocabulary: list[VocabularyEntry]) -> str:
    """domain/attribute만 주면 LLM이 그 안의 구체 예시(code)를 지어내므로, 실제 code를 몇 개씩 함께 보여준다."""
    groups: dict[tuple[str, str], list[str]] = {}
    for entry in vocabulary:
        groups.setdefault((entry.domain, entry.attribute), []).append(entry.code)

    lines = [
        f"- domain={domain}, attribute={attribute}, 실제 code 예시: {', '.join(codes[:5])}"
        for (domain, attribute), codes in sorted(groups.items())
    ]
    return "\n".join(lines) if lines else "(비어있음)"


async def handle_smalltalk(state: PreferenceState) -> dict:
    smalltalk_text = state.get("smalltalk_text") or state["message"]

    # 잡담 응대는 Vocabulary가 있으면 더 구체적인 예시를 들 뿐, 없어도 반드시 응답은 나가야 한다.
    # Back이 죽었다고 잡담 처리까지 통째로 실패하면 안 되므로 조회 실패를 흡수한다.
    try:
        vocabulary = await fetch_vocabulary()
    except AIServiceError:
        logger.warning("스몰톡 처리 중 Vocabulary 조회 실패 — 예시 없이 진행")
        vocabulary = []

    llm = get_llm()
    system = SYSTEM_PROMPT.format(
        vocabulary_domains=_format_domains(vocabulary),
        smalltalk_text=smalltalk_text,
    )
    response = await llm.ainvoke(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": smalltalk_text},
        ]
    )

    return {"assistant_reply": _extract_text(response.content)}
