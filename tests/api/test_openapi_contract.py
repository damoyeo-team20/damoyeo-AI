import hashlib
import json

from app.main import app


_OPENAPI_SHA256 = "fc42d50c1601d8fad0f9f05ad2219cb8183655ea0c21f68ea0d2b1e4cf1829dc"


def test_openapi_contract_is_unchanged():
    """Back↔AI wire schema(필드명·타입·구조)가 의도치 않게 바뀌지 않았는지 감시한다.

    docstring처럼 스키마 description에만 영향을 주는 변경도 이 해시를 바꾸므로, 실패하면
    구조 변경인지 문서 문구 변경인지 diff로 확인한 뒤 의도된 변경이면 이 상수를 갱신한다.
    """

    canonical_json = json.dumps(
        app.openapi(),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()

    assert hashlib.sha256(canonical_json).hexdigest() == _OPENAPI_SHA256
