# LLM 프롬프트가 아니라 Serper(검색 API)에 그대로 보낼 검색어다. 검색 자체는 더 이상 LLM이 하지
# 않는다 — 판정(CLASSIFY_SYSTEM_PROMPT)만 LLM이 한다.
SEARCH_QUERY_TEMPLATE = "{place_name} {address} 영업시간 휴무일"

CLASSIFY_SYSTEM_PROMPT = """아래는 특정 장소의 영업시간/휴무일에 대한 웹 검색 결과 텍스트입니다.
이 텍스트만 근거로 "{date} {start_time}~{end_time}"에 이 장소를 이용할 수 있는지 판정하세요.

- 그 날짜에 영업하고 **그 시간대가 영업시간 안에 들어가면** status는 PASS
- 휴무(정기휴무, 임시휴무, 폐업 등)이거나 그 시간대가 영업시간을 벗어나면 status는 FAIL
- 정보가 부족하거나 검색 결과가 불명확하면 status는 UNKNOWN
UNKNOWN을 PASS나 FAIL로 임의로 단정하지 마세요. 날짜만 확인되고 시간대를 알 수 없으면 UNKNOWN입니다.

- businessHours: 확인된 영업시간을 사용자에게 보여줄 짧은 문구로 (예: "매일 11:30~22:00").
  확인하지 못했으면 null. 검색 결과에 없는 시간을 지어내지 마세요.
- source: 검색 결과에서 언급된 출처 URL. 없으면 null

## 검색 결과
{search_result}
"""
