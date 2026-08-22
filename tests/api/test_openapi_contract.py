import hashlib
import json

from app.main import app


_OPENAPI_SHA256 = "02f467ae714c2d0baea71182eb791de6292a506bc40d1c0548e052180d773db2"


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
