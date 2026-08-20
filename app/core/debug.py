"""임시 디버깅 트레이스. 배포 전에 이 파일과 이 파일을 참조하는 곳을 전부 지운다.

요청 하나 처리하는 동안 각 노드가 LLM 원본 출력을 여기 기록해두면, main.py의 미들웨어가
응답 JSON 끝에 그대로 붙여서 내보낸다. 정식 계약 필드가 아니다.
"""

from contextvars import ContextVar

_trace: ContextVar[list] = ContextVar("_debug_trace")


def reset_debug_trace() -> None:
    _trace.set([])


def _to_jsonable(data: object) -> object:
    if hasattr(data, "model_dump"):
        try:
            return data.model_dump()
        except Exception:
            return repr(data)
    if isinstance(data, list):
        return [_to_jsonable(item) for item in data]
    return data


def record_debug(label: str, data: object) -> None:
    try:
        trace = _trace.get()
    except LookupError:
        return
    trace.append({"node": label, "raw": _to_jsonable(data)})


def get_debug_trace() -> list:
    try:
        return _trace.get()
    except LookupError:
        return []
