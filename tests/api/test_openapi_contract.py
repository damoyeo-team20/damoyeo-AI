import hashlib
import json

from app.main import app


_PRE_FAIRNESS_OPENAPI_SHA256 = (
    "ddf055d6a44648d3c6f60092e00df22dac1a4ac1b8c84095d763e3059bf8519c"
)


def test_fairness_change_does_not_modify_external_openapi_contract():
    """공정성 계산은 AI 내부 변경이며 Back↔AI wire schema는 그대로여야 한다."""

    canonical_json = json.dumps(
        app.openapi(),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()

    assert hashlib.sha256(canonical_json).hexdigest() == _PRE_FAIRNESS_OPENAPI_SHA256
