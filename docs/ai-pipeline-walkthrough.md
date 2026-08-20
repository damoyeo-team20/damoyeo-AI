# AI 파이프라인 내부 동작 상세

이 문서는 각 API가 호출됐을 때 **AI 내부에서 정확히 어떤 필드가 들어오고, 어떤 방식으로 처리해서, 어떤 필드를 돌려주는지**를 노드 단위로 설명합니다.

- Back↔AI의 **요청/응답 JSON 계약**(wire format)은 이 문서의 대상이 아닙니다 — 그건 [`api-design2-backend.md`](api-design2-backend.md)가 유일한 기준 문서이고, 여기서는 중복해서 적지 않습니다.
- 이 문서는 그 계약 **안쪽**, 즉 AI가 요청을 받은 뒤 LLM 프롬프트와 코드가 정확히 무슨 일을 하는지를 다룹니다.

## 먼저 바로잡을 오해 하나

"개인 선호 → 목적 대화 요약 → 날짜·시간 확정을 통해서 그룹 컨텍스트를 만들고, 그걸로 활동을 계획한다"는 흐름은 **하나로 이어진 계산이 아닙니다.** 이 세 가지는 서로 완전히 다른 시점에 호출되는 **독립된 API**입니다.

- 개인 선호(`/preferences/extract`)는 온보딩 때, 모임과 무관하게 미리 쌓입니다.
- 목적 대화 요약(`/context/messages`, `/context`)은 모임을 만들 때 한 번 호출되고 끝납니다.
- 날짜·시간 확정(`/schedule`)은 참여자들이 가능 날짜를 다 제출한 뒤, 또 별도로 호출됩니다.

AI는 호출 사이에 아무것도 기억하지 않습니다 (`app/graph/*_state.py`가 매 요청마다 새로 만들어지는 이유). "그룹 컨텍스트"라는 것은 AI가 만드는 게 아니라, **Back이 이 세 결과를 각각 DB에 저장해뒀다가**(`user_preferences`, `meetings.purpose`, `meetings.confirmed_start_at/end_at`) `/candidates`를 호출할 때 한 번에 모아서 실어 보내는 것입니다. 그래서 4단계(활동 계획→장소 검색→검증→랭킹)만 실제로 LangGraph 하나로 이어진 계산이고, 나머지는 각자 따로 노는 API입니다.

```
[1] /preferences/extract  ─┐
[2] /context, /context/messages ─┼─ Back이 DB에 각각 저장 ─→ [4] /candidates 호출 시 한 번에 조립해서 전달
[3] /schedule ──────────────┘
```

---

## 1단계 — 개인 선호 (`POST /ai/preferences/extract`)

Back은 사용자가 이번에 새로 제출한 문장들(`messages: string[]`)을 `". "`로 이어붙여 하나의 `message` 문자열로 만든 뒤 그래프에 넣습니다.

### 1.1 Preference Router

| | |
| --- | --- |
| 파일 | `app/graph/nodes/n_preference_router.py` |
| 입력 | `message: str` |
| 방식 | LLM 구조화 출력 (개인 선호 입력 범위 판별) |
| 출력 | `route: IN_SCOPE \| OUT_OF_SCOPE` |

프롬프트 규칙(`app/prompts/n_preference_router.py`):
- 음식·음료·음주·분위기·활동 선호, 알레르기나 회피 조건이 하나라도 명확하면 `IN_SCOPE`.
- 인사, 사용법 질문, 날씨·뉴스·근황처럼 개인 선호가 전혀 없으면 `OUT_OF_SCOPE`.
- 여러 문장이 함께 들어와도 개인 선호가 하나라도 있으면 `IN_SCOPE`로 보내고, Extractor가 전체 입력에서
  선호만 골라낸다.
- 애매한 입력을 선호라고 억지로 해석하지 않는다.

이 결과에 따라 다음 노드로 분기합니다 (`app/graph/build_preference_graph.py`):

| route | 다음에 실행되는 노드 |
| --- | --- |
| `IN_SCOPE` | Preference Extractor → 추출 성공 시 고정 완료 문구 |
| `OUT_OF_SCOPE` | Preference Guardrail |

Extractor가 실제 선호를 하나도 만들지 못한 경우도 Preference Guardrail로 보냅니다.

### 1.2 Preference Extractor

| | |
| --- | --- |
| 파일 | `app/graph/nodes/n_preference_extractor.py` |
| 입력 | 가드레일을 통과한 `message` 전체 |
| 방식 | LLM 구조화 출력. 응답 스키마의 `vocabularyCode` 필드를 **매 요청마다 실제 Vocabulary 코드 목록으로 동적 `Literal` 제약** — 목록에 없는 코드는 애초에 출력될 수 없다 |
| 출력 | `preferences: ExtractedPreference[]` |

먼저 Back의 `GET /internal/preference-vocabulary`를 호출해 현재 Vocabulary 전체(`code`, `domain`, `displayName`, `parentCode`)를 가져옵니다. 프롬프트(`app/prompts/n_preference_extractor.py`)에 이 목록을 통째로 넣고 규칙을 줍니다.

| 규칙 | 내용 |
| --- | --- |
| Specificity 매핑 | 포괄적 발언("해산물은 별로야")은 상위 카테고리 code로, 구체적 발언("조개는 좋아")은 leaf code로 — 그래야 "해산물 싫은데 조개는 좋아" 같은 예외가 서로 다른 code로 저장돼 충돌하지 않는다 |
| `mappingType=EXACT` | 발화가 Vocabulary code와 직접 대응 |
| `mappingType=GENERALIZED` | 더 구체적인 leaf가 없어 상위 code로 매핑. `rawValue`는 원래 표현 그대로 보존 |
| `mappingType=UNMAPPED` | 대응되는 code가 Vocabulary 어디에도 없음. `vocabularyCode`는 반드시 `null`. 이 항목도 배열에서 버리지 않고 그대로 포함 (저장 여부는 Back이 결정) |
| `strength` | `WEAK`/`MODERATE`/`STRONG` 3단계만 (연속값 금지) |
| `sentiment` | `POSITIVE`/`NEGATIVE` |

출력 항목마다 코드가 있으면 `display_name`/`domain`은 **LLM이 아니라 서버가** 방금 조회한 Vocabulary에서 그대로 찾아 붙입니다 (LLM 산출값 아님). `UNMAPPED`면 둘 다 `null`.

### 1.3 Preference Guardrail — 비-LLM

| | |
| --- | --- |
| 파일 | `app/graph/nodes/l_preference_guardrail.py` |
| 입력 | `OUT_OF_SCOPE` 입력 또는 추출 결과가 빈 상태 |
| 방식 | 고정 응답(LLM 호출 없음) |
| 출력 | `assistant_reply: str` |

범위 밖 입력에 자연스러운 잡담을 이어가지 않고 다음 고정 문구로 화면의 목적을 다시 안내합니다.

> 좋아하거나 피하고 싶은 음식, 음주 여부, 원하는 분위기나 활동을 알려주세요.

정상 추출이 끝난 경우도 LLM을 다시 호출하지 않고 고정 완료 문구를 반환합니다.

---

## 2단계 — 모임 목적 대화 (`POST /ai/meetings/{id}/context/messages`, `/context`)

### 2.1 Context Router

| | |
| --- | --- |
| 파일 | `app/graph/nodes/n_context_router.py` |
| 입력 | `candidate_dates`, `history`, `message` |
| 방식 | LLM 구조화 출력 (범위 및 날짜 변경 의도 분류) |
| 출력 | `route: IN_SCOPE \| OUT_OF_SCOPE \| DATE_CHANGE` |

모든 발화에서 목적·분위기·활동·장소 조건은 `IN_SCOPE`, 무관한 대화와 이 화면이 처리하지 않는
지역·시간 변경은 `OUT_OF_SCOPE`로 분류합니다. `candidate_dates`가 있을 때만 날짜 변경 의사를
`DATE_CHANGE`로 출력할 수 있도록 응답 스키마의 허용값도 요청마다 바뀝니다.

`IN_SCOPE`는 **2.2 Context Parser**, `DATE_CHANGE`는 **2.3 Context Date Reselector**,
`OUT_OF_SCOPE`는 **2.4 Context Guardrail**로 분기합니다.

### 2.2 Context Parser — 채팅 한 턴

| | |
| --- | --- |
| 파일 | `app/graph/nodes/n_context_parser.py` (`generate_context_reply`) |
| 입력 | `history: ChatTurn[]`, `message: str` |
| 방식 | 일반 LLM 호출(구조화 출력 아님) |
| 출력 | `reply: str` |

`history`를 `user`/`assistant` role의 대화 메시지로 그대로 변환해서 쌓고, 새 `message`를 마지막에 붙여 보냅니다. 고정 시스템 프롬프트(`app/prompts/n_context_parser.py`의 `CHAT_SYSTEM_PROMPT`, 매 호출 동일 — 템플릿 변수 없음) 규칙:
- 응답 1~2문장.
- **지역/날짜/시간대는 이 대화에서 절대 묻거나 언급하지 않는다** (다른 화면에서 이미 정해짐).
- `history`가 전체 대화이므로 처음 언급한 것처럼 되묻지 않는다.

### 2.3 Context Date Reselector

| | |
| --- | --- |
| 파일 | `app/graph/nodes/n_context_date_reselector.py` |
| 입력 | `candidate_dates`, `history`, `message` |
| 방식 | LLM 구조화 출력. `chosenDate`를 후보 날짜들로 동적 `Literal` **+ `null` 허용**으로 제약 |
| 출력 | `reply: str`, `candidate_dates`(바뀌었으면 `selected` 위치 이동, 아니면 그대로) |

후보 날짜 목록을 프롬프트에 넣고(`app/prompts/n_context_date_reselector.py`) LLM이 `chosenDate`(후보 중 하나 또는 `null`)와 `reply`를 냅니다.
- 발화가 특정 날짜를 명확히 가리키면 그 날짜를 고른다.
- "다른 날로 바꾸고 싶어"처럼 방향만 말하고 어떤 날짜인지 불명확하면 `chosenDate`를 `null`로 두고 — 코드에서 `candidate_dates`를 그대로 유지하고 `reply`로 되묻는다.
- 사용자가 요일을 말하면 **요일은 날짜로부터 직접 계산해서 판단**하고(프롬프트에 요일을 붙여 보여주지 않음, `n_schedule_resolver`와 동일한 방식), 그 요일에 해당하는 후보만 고른다.
- `chosenDate`는 반드시 후보 목록의 날짜 문자열과 정확히 동일해야 한다 — 요일이나 다른 텍스트를 덧붙이지 않는다 (2026-08-21, `/schedule`에서 겪었던 것과 같은 파싱 실패 버그를 여기서도 미리 방지).

### 2.4 Context Guardrail — 비-LLM

| | |
| --- | --- |
| 파일 | `app/graph/nodes/l_context_guardrail.py` |
| 입력 | `OUT_OF_SCOPE` 입력, 요청의 `candidate_dates` |
| 방식 | 고정 응답(LLM 호출 없음) |
| 출력 | `reply`, 변경하지 않은 `candidate_dates` |

잡담에 답하지 않고 "이번 모임의 목적, 원하는 분위기나 활동, 꼭 반영할 조건을 알려주세요."라고
안내합니다. 요청에 날짜 후보가 있었다면 `selected` 상태까지 그대로 돌려줍니다.

### 2.5 Context Parser — 최종 요약

| | |
| --- | --- |
| 파일 | `app/graph/nodes/n_context_parser.py` (`finalize_meeting_context`) |
| 입력 | `history: ChatTurn[]` (`USER` 발화 최소 1개, 스키마가 강제) |
| 방식 | LLM 구조화 출력 |
| 출력 | `reply: str`, `purpose: str` (최대 1,000자) |

대화 전체를 `"{role}: {content}"` 줄로 이어붙여 한 번에 넘깁니다(`FINALIZE_SYSTEM_PROMPT`). `purpose`는 목적·분위기·조건을 하나의 자연스러운 문장으로 요약 — 지역/날짜/시간대와 범위 밖 입력·가드레일 안내·날짜 변경 대화는 포함하지 않습니다. 대화에 실질 내용이 없으면 "특별한 요청 없이 편하게 모이는 자리" 같은 일반 문장으로 답하라는 규칙이 있습니다 (빈 값 금지).

---

## 3단계 — 날짜·시간 확정 (`POST /ai/meetings/{id}/schedule`)

### 3.1 Schedule Resolver

| | |
| --- | --- |
| 파일 | `app/graph/nodes/n_schedule_resolver.py` |
| 입력 | `commonAvailableDates: date[]`(Back이 계산한 전원 가능 날짜, 최소 1개), `preferredTimeOfDay`, `durationMinutes`(`null`이면 120) |
| 방식 | LLM 구조화 출력. `chosenDate`를 `commonAvailableDates`로 동적 `Literal` 제약 |
| 출력 | `chosen_date`, `reason: str` |

프롬프트(`app/prompts/n_schedule_resolver.py`)에 날짜 목록을 순수 ISO 문자열로만 보여주고(요일 안 붙임) 규칙을 줍니다:
- 목록에 **실제로 있는 날짜 중 하나만** 고른다.
- `reason`은 요일 특성(평일/주말)처럼 실제 근거가 있는 한 문장. "가장 빠른 날이라서" 같은 무의미한 설명 금지.
- 모임 목적은 이 프롬프트에 안 주어짐 — 날짜 자체에서 판단 가능한 근거만 사용.
- **"chosenDate는 반드시 목록의 날짜 문자열과 정확히 동일해야 한다. 요일이나 다른 텍스트를 덧붙이지 않는다."** (이전에 요일을 붙여 보여줘서 파싱이 깨졌던 실제 프로덕션 버그를 고친 규칙 — 2.3 Context Date Reselector에도 같은 규칙이 적용돼 있다)

### 3.2 Schedule Slot Builder — 비-LLM

| | |
| --- | --- |
| 파일 | `app/graph/nodes/l_schedule_slot_builder.py` |
| 입력 | `chosen_date`, `preferred_time_of_day`, `duration_minutes`, `timezone` |
| 방식 | 순수 계산 (LLM 아님) |
| 출력 | `resolvedStartAt`, `resolvedEndAt` |

시간대별 창(윈도우)이 코드에 고정돼 있습니다.

| `preferredTimeOfDay` | 시각 범위 |
| --- | --- |
| `DAYTIME` | 11:00 ~ 15:00 |
| `LATE_AFTERNOON` | 15:00 ~ 18:00 |
| `EVENING` | 18:00 ~ 23:00 |
| `ANY` | 11:00 ~ 23:00 |

계산: **시작 시각 = 그 창의 시작 시각**(예: EVENING이면 18:00), **종료 시각 = 시작 + durationMinutes**. `durationMinutes`가 창의 길이보다 길면(예: LATE_AFTERNOON 180분인데 200분 요청) `400 INVALID_DURATION_FOR_TIME_OF_DAY`로 거부합니다. 같은 입력이면 항상 같은 결과 — 판단이 아니라 계산이라 LLM을 쓰지 않습니다.

---

## 4단계 — 장소 후보 생성 (`POST /ai/meetings/{id}/candidates`)

여기서부터가 실제로 하나의 LangGraph로 이어진 계산입니다(`app/graph/build_graph.py`). Back이 `meeting`(purpose/region), `confirmedSlot`(3단계 결과), `participants[].preferences`(1단계 결과 누적)를 한 번에 실어 보내면, 라우트가 `participants`의 선호를 전부 펼쳐서 참여자 구분 없는 하나의 리스트(`participant_preferences`)로 합친 뒤 그래프에 넣습니다 — **후보 선정은 항상 집단 수준으로 판단하고, 개별 참여자를 지칭하지 않습니다.**

### 4.1 Candidate Activity Decider

| | |
| --- | --- |
| 파일 | `app/graph/nodes/n_candidate_activity_decider.py` |
| 입력 | `meeting.purpose`, `meeting.region`, `confirmed_slot`, `meeting_memory_summary`(지난 모임 요약, 없으면 "(없음)"), `participant_preferences` |
| 방식 | LLM 구조화 출력 |
| 출력 | (정상) `activities`, `meeting_tags`, `summary` / (충돌) `action_required` |

이 파이프라인의 진입 노드이자 핵심 판단 지점입니다(`app/prompts/n_candidate_activity_decider.py`). 세 가지를 한 번에 결정합니다.

**① activities와 검색어** — 활동 1~3개, 각각 Kakao 키워드 검색에 바로 쓸 한글 검색어(`searchQueries`) 1~3개. **Specificity Wins 규칙**: 넓은 범주 선호와 구체적 선호가 충돌하면 구체적인 쪽이 이깁니다 — "해산물은 별로야"(NEGATIVE)와 "조개는 좋아"(POSITIVE)가 같이 있어도 조개 관련 활동을 배제하지 않습니다. `rationaleGroup`은 반드시 집단 수준 표현("참여자 다수가 술자리를 선호합니다" O, "A가 좋아해서" X).

**② meetingTags** — 이번 자리의 성격. 4개의 독립된 축, **같은 축에서 최대 1개만**:

| 축 | 선택지 |
| --- | --- |
| 무엇을 하는가 | `ACTIVE` / `CONVERSATION_FOCUSED` |
| 먹고 마시기 | `MEAL_INCLUDED`(독립) / `ALCOHOL_FRIENDLY` / `NO_ALCOHOL` |
| 분위기 | `LIVELY` / `QUIET` |
| 예산 | `BUDGET_FRIENDLY` |

근거가 약한 축은 아예 비웁니다 (억지로 채우지 않음).

**③ summary** — 이번 제안을 무엇을 기준으로 골랐는지 한 문장.

**충돌 처리**: 모임 목적과 참여자 기존 선호가 강하게 충돌하면(예: 목적은 술자리인데 다수가 음주 비선호) `status=CONFLICT`을 반환하고 `activities`는 비웁니다. 이 경우 뒤 노드들은 아예 실행되지 않고 그래프가 즉시 종료됩니다 — `action_required`(`type=PREFERENCE_CONFLICT`, `hostRequest`=모임 목적, `conflictingPreferenceCodes`)로 응답합니다.

### 4.2 Candidate Place Search — 비-LLM

| | |
| --- | --- |
| 파일 | `app/graph/nodes/l_candidate_place_search.py` |
| 입력 | `meeting.region`, `activities`(4.1의 각 검색어), `excluded_external_place_ids` |
| 방식 | Kakao Local API 키워드 검색 (LLM 아님) |
| 출력 | `place_candidates` |

활동마다 `searchQueries` 각각으로 Kakao Local API(`search/keyword.json`)를 `"{region} {검색어}"`로 호출합니다(활동당 검색어 하나마다 최대 3개 조회). 이미 나온 `kakao_place_id`(이번 실행 내 중복, `excludedExternalPlaceIds`)는 걸러내고, 활동별로 모은 결과를 **최대 3개까지만** 남깁니다. Kakao 응답에서 가져오는 값: `id`, `place_name`, `road_address_name`(없으면 `address_name`), `category_name`, `place_url`, 좌표(`y`=위도, `x`=경도, 문자열로 와서 숫자로 변환).

### 4.3 Candidate Place Verifier

| | |
| --- | --- |
| 파일 | `app/graph/nodes/n_candidate_place_verifier.py` |
| 입력 | `place_candidates`, `confirmed_slot`(날짜/시작/종료 시각) |
| 방식 | 검색(Serper API) → 판정(LLM 구조화 출력), 장소별 **병렬** 실행, 전체 20초 타임아웃 |
| 출력 | `verified_places`, `verification_timed_out` |

장소마다 검색 한 번(비-LLM) + LLM 판정 한 번을 합니다.

1. **검색**: `app/services/serper_client.py`로 [Serper](https://serper.dev) 검색 API를 호출합니다. 검색어는 `"{place_name} {address} 영업시간 휴무일"`(`app/prompts/n_candidate_place_verifier.py`의 `SEARCH_QUERY_TEMPLATE`, LLM 프롬프트가 아니라 순수 문자열). 상위 5개 결과(제목·스니펫·출처 URL)를 받아 텍스트로 정리합니다.
   > 원래는 Gemini의 `google_search` grounding 도구로 이 단계까지 LLM이 직접 검색했지만, grounding이 일반 텍스트 생성과 별도의 훨씬 빡빡한 할당량을 갖고 있어 자주 `429`가 나서 검색만 Serper로 분리했습니다(2026-08-21). 판정 단계는 원래부터 grounding과 무관한 일반 Gemini 호출이라 그대로입니다.
2. **판정**: 검색 결과 텍스트만 근거로 구조화 출력 `{status, businessHours, source}` 생성(`CLASSIFY_SYSTEM_PROMPT`, 기존과 동일). `status`는 `PASS`(그 시간대가 영업시간 안)/`FAIL`(휴무 또는 시간대 벗어남)/`UNKNOWN`(정보 부족) 3-state. **`UNKNOWN`을 임의로 `PASS`/`FAIL`로 단정하지 않습니다.**

20초 안에 못 끝난 작업은 취소되고 결과에서 빠지며(`verification_timed_out=true`), 검색/판정 중 예외가 나면 해당 장소는 `UNKNOWN`으로 남습니다. `app/core/config.py`의 `SKIP_BUSINESS_HOURS_VERIFICATION` 플래그가 켜져 있으면 검색·판정을 아예 생략하고 즉시 `UNKNOWN`을 반환합니다(빠른 로컬 테스트용).

### 4.4 Candidate Ranker

| | |
| --- | --- |
| 파일 | `app/graph/nodes/n_candidate_ranker.py` |
| 입력 | `verified_places`(`FAIL` 제외), `participant_preferences`, `meeting.purpose`, `activities`의 `rationale_group` |
| 방식 | LLM 구조화 출력 + 서버 후처리 |
| 출력 | `suggestions` (최대 3개) |

`FAIL`이 아닌 후보(`PASS`, `UNKNOWN` 포함)만 LLM에 넘깁니다. 프롬프트(`app/prompts/n_candidate_ranker.py`)에는 장소당 `kakaoPlaceId`/`activity`/`activityRationale`/`name`/`category`/`verificationStatus`만 전달됩니다(영업시간 문구·좌표 등은 안 줌). LLM이 내는 것:

- `ranked`: 최대 3개, 순서가 곧 순위. 후보마다 `reasons`(1~3개, 집단 수준 문장, 최소 1개 필수), `matchedPreferenceCodes`(요청에 실제 있는 코드만), `tags`(`MATCHES_ACTIVITY`/`HIGH_GROUP_FIT`/`GOOD_FOR_MEAL`/`GOOD_FOR_DRINKS` 중 확실한 것만 — `AVAILABLE_AT_MEETING_TIME`은 이 목록에서 아예 제외돼 있어 LLM이 고를 수 없음).

서버가 이후 붙이는 값(LLM 산출 아님):
- `AVAILABLE_AT_MEETING_TIME` 태그와 `openAtMeetingTime`: 4.3의 `verification_status == PASS`일 때만 `true`로 붙임. `UNKNOWN`이면 태그도 안 붙고 `openAtMeetingTime`도 `null`.
- `matchedPreferenceDomains`: LLM이 고른 `matchedPreferenceCodes`를 실제 요청에 있던 코드와 대조해서(없는 코드는 버림) Vocabulary의 `domain`으로 변환.
- `proposedStartAt`/`proposedEndAt`: 3단계에서 확정된 `confirmedSlot`을 모든 제안에 그대로 사용(제안마다 다른 시각을 계산하지 않음).
- `sourceUrls`: 4.3의 `place_url` + `verification_source`를 중복 제거해서.

LLM이 존재하지 않는 `kakaoPlaceId`를 답하면 그 항목은 조용히 버려지고(개수는 채우지 않고 다음 항목으로), 최종적으로 최대 3개까지만 `suggestions`에 담깁니다.

---

## 전체 데이터 흐름 한눈에 보기

```
[Back]
  meeting.purpose, meeting.region     ← 2단계(Context) 결과, DB(meetings.purpose)에서
  confirmedSlot                       ← 3단계(Schedule) 결과, DB(meetings.confirmed_*)에서
  participants[].preferences          ← 1단계(Preference) 결과 누적, DB(user_preferences)에서
        │
        ▼  (참여자 구분 없이 하나의 리스트로 펼침)
┌─────────────────────────────────────────────────────────┐
│ Candidate Activity Decider (LLM)                         │
│  → activities[], meetingTags[], summary                  │
│  → (충돌 시) actionRequired로 즉시 종료                    │
└─────────────────────────────────────────────────────────┘
        │ activities[].searchQueries
        ▼
┌─────────────────────────────────────────────────────────┐
│ Candidate Place Search (Kakao, 비-LLM)                    │
│  → place_candidates[]                                    │
└─────────────────────────────────────────────────────────┘
        │
        ▼ (장소별 병렬, 최대 20초)
┌─────────────────────────────────────────────────────────┐
│ Candidate Place Verifier (Serper 검색 + LLM 구조화 판정)   │
│  → verified_places[] (PASS/FAIL/UNKNOWN)                 │
└─────────────────────────────────────────────────────────┘
        │ (FAIL 제외)
        ▼
┌─────────────────────────────────────────────────────────┐
│ Candidate Ranker (LLM + 서버 후처리)                       │
│  → suggestions[] (최대 3개, rank·reasons·tags·domains)     │
└─────────────────────────────────────────────────────────┘
```
