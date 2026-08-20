SEARCH_PROMPT = """"{place_name}"({address})의 {date} 기준 영업시간과 정기 휴무일을 웹 검색으로 확인해줘.
영업시간, 휴무 요일, 그리고 {date} {start_time}~{end_time} 시간대에 실제로 영업하는지 여부를 알아낸 대로
알려줘. 어떤 출처(사이트/글)에서 확인했는지도 URL과 함께 알려줘. 정보를 찾지 못했으면 찾지 못했다고
명확히 말해줘."""

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
