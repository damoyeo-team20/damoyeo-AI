# AI 파이프라인 내부 동작 상세

이 문서는 각 API가 호출됐을 때 **AI 내부에서 정확히 어떤 필드가 들어오고, 어떤 방식으로 처리해서, 어떤 필드를 돌려주는지**를 노드 단위로 설명합니다.

- Back↔AI의 **요청/응답 JSON 계약**(wire format)은 이 문서의 대상이 아닙니다 — 그건 [`api-design2-backend.md`](api-design2-backend.md)가 유일한 기준 문서이고, 여기서는 중복해서 적지 않습니다.
- 이 문서는 그 계약 **안쪽**, 즉 AI가 요청을 받은 뒤 LLM 프롬프트와 코드가 정확히 무슨 일을 하는지를 다룹니다.

## 먼저 바로잡을 오해 하나

"개인 선호 → 목적 대화 요약 → 날짜·시간 확정을 통해서 그룹 컨텍스트를 만들고, 그걸로 활동을 계획한다"는 흐름은 **하나로 이어진 계산이 아닙니다.** 이 세 가지는 서로 완전히 다른 시점에 호출되는 **독립된 API**입니다.

- 개인 선호(`/preferences/extract`)는 온보딩 때, 모임과 무관하게 미리 쌓입니다.
- 목적 대화 요약(`/context/messages`, `/context`)은 모임을 만들 때 한 번 호출되고 끝납니다.
- 날짜·시간 확정(`/schedule`)은 참여자들이 가능 날짜를 다 제출한 뒤, 또 별도로 호출됩니다.

AI는 호출 사이에 아무것도 기억하지 않습니다 (`app/graph/*_state.py`가 매 요청마다 새로 만들어지는 이유). "그룹 컨텍스트"라는 것은 AI가 만드는 게 아니라, **Back이 이 세 결과를 각각 DB에 저장해뒀다가**(`user_preferences`, `meetings.purpose`, `meetings.confirmed_start_at/end_at`) `/candidates`를 호출할 때 한 번에 모아서 실어 보내는 것입니다. 그래서 4단계(검색 계획→Kakao 후보 수집→컨텍스트·공정성 사전랭킹→선별 영업 검증→응답 조립)만 실제로 LangGraph 하나로 이어진 계산이고, 나머지는 각자 따로 노는 API입니다.

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
| 방식 | LLM 내부 DTO의 `vocabulary_code`(외부 alias `vocabularyCode`)를 `string \| null`로 받고, AI 서버가 실제 Vocabulary와 대조해 미등록 code를 `UNMAPPED`/`null`로 정규화 |
| 출력 | `preferences: ExtractedPreference[]` |

먼저 Back의 `GET /internal/preference-vocabulary`를 호출해 현재 Vocabulary 전체(`code`, `domain`, `displayName`, `parentCode`)를 가져옵니다. 프롬프트(`app/prompts/n_preference_extractor.py`)에 이 목록을 통째로 넣고 규칙을 줍니다.

| 규칙 | 내용 |
| --- | --- |
| Specificity 매핑 | 포괄적 발언("해산물은 별로야")은 상위 카테고리 code로, 구체적 발언("조개는 좋아")은 leaf code로 — 그래야 "해산물 싫은데 조개는 좋아" 같은 예외가 서로 다른 code로 저장돼 충돌하지 않는다 |
| `mappingType=EXACT` | 발화가 Vocabulary code와 직접 대응 |
| `mappingType=GENERALIZED` | 더 구체적인 leaf가 없어 상위 code로 매핑. `rawValue`는 원래 표현 그대로 보존 |
| `mappingType=UNMAPPED` | 대응되는 code가 Vocabulary 어디에도 없음. `vocabularyCode`는 반드시 `null`. AI 응답에는 포함하고 Back은 일반 선호 저장·Front 응답에서 제외 |
| `strength` | `WEAK`/`MODERATE`/`STRONG` 3단계만 (연속값 금지) |
| `sentiment` | `POSITIVE`/`NEGATIVE` |

전체 Vocabulary(현재 seed 320개)를 JSON Schema의 거대한 enum으로 만들지는 않습니다. 목록은 의미 판단을 위해 프롬프트에 유지하되, Gemini에는 code를 단순 문자열로 받습니다. 출력 항목마다 서버가 code를 실제 Vocabulary에서 조회하고, 존재하면 `display_name`/`domain`을 원본에서 붙입니다. 존재하지 않거나 모델이 `UNMAPPED`로 반환한 code는 `vocabularyCode`/`displayName`/`domain`을 모두 `null`로 만들고 `mappingType=UNMAPPED`로 정규화합니다.

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

여기서부터가 실제로 하나의 LangGraph로 이어진 계산입니다(`app/graph/build_graph.py`). Back이 `meeting`(purpose/region), `confirmedSlot`(3단계 결과), `participants[].preferences`(1단계 결과 누적)를 한 번에 실어 보냅니다. 라우트와 그래프는 `participants[].userId` 경계를 그대로 보존합니다. 최종 문장은 여전히 특정 참여자를 지칭하지 않지만, 내부 계산에서는 각 참여자의 만족도를 따로 계산합니다.

### 4.1 Candidate Activity Decider — SearchPlan 생성

| | |
| --- | --- |
| 파일 | `app/graph/nodes/n_candidate_activity_decider.py` |
| 그래프 노드 | `decide_activities` |
| 입력 | `meeting.purpose`, `meeting.region`, `confirmed_slot`, `meeting_memory_summary`(지난 모임 요약, 없으면 "(없음)"), `participants[].preferences` |
| 방식 | LLM 구조화 출력 |
| 출력 | (정상) `search_plans`, `meeting_tags`, `summary` / (충돌) `action_required` |

이 파이프라인의 진입 노드이자 핵심 판단 지점입니다(`app/prompts/n_candidate_activity_decider.py`). 세 가지를 한 번에 결정합니다.

Back이 `confirmedSlot`을 UTC(`Z`)로 직렬화해도 프롬프트에는 `Asia/Seoul` 현지 시각으로
변환해 전달합니다. 예를 들어 `09:00Z~11:00Z`는 한국 시각 `18:00~20:00`으로 보입니다.
응답의 `proposedStartAt/EndAt`은 같은 실제 시점을 나타내는 원본 값을 그대로 사용합니다.

**① SearchPlan과 검색어** — 내부 검색 계획 1~4개, 각 계획마다 Kakao 키워드 검색에 바로 쓸 한글 검색어(`searchQueries`) 1~3개를 만듭니다. 과거의 `activity`라는 내부 모델 필드가 남아 있지만, 이 값은 최종 활동 확정값이 아니라 **후보 풀을 넓히는 검색 버킷의 label**입니다. 그래프 상태에서는 `search_plans`로 명확히 구분합니다.

각 계획은 생성 근거를 `source`로 표시합니다.

- `MEETING_PURPOSE`: 명시적인 모임 목적에서 나온 계획. 최소 1개 필수
- `PARTICIPANT_PREFERENCE`: 참여자 선호로 후보 범위를 넓히는 계획. 최대 2개
- `MEETING_MEMORY`: 과거 모임 요약에 실제 근거가 있을 때 만드는 계획. 최대 1개

서버는 최종 SearchPlan을 `MEETING_PURPOSE → PARTICIPANT_PREFERENCE → MEETING_MEMORY` 순으로 정렬합니다. 같은 Kakao 장소가 여러 계획에서 발견되면 뒤의 전역 중복 제거가 먼저 본 계획의 provenance를 보존하므로, 명시적 목적에서 나온 근거를 선호·과거 메모리보다 우선하기 위한 순서입니다.

**Specificity Wins 규칙**도 유지합니다. 넓은 범주 선호와 구체적 선호가 충돌하면 구체적인 쪽을 우선합니다 — "해산물은 별로야"(NEGATIVE)와 "조개는 좋아"(POSITIVE)가 같이 있어도 조개 관련 검색 계획을 배제하지 않습니다. `rationaleGroup`은 반드시 집단 수준 표현("참여자 다수가 술자리를 선호합니다" O, "A가 좋아해서" X)입니다. 지역은 Kakao 클라이언트가 별도로 붙이므로 LLM 검색어에서 중복 지역 접두사를 제거합니다.

**② meetingTags** — 이번 자리의 성격. 4개의 독립된 축, **같은 축에서 최대 1개만**:

| 축 | 선택지 |
| --- | --- |
| 무엇을 하는가 | `ACTIVE` / `CONVERSATION_FOCUSED` |
| 먹고 마시기 | `MEAL_INCLUDED`(독립) / `ALCOHOL_FRIENDLY` / `NO_ALCOHOL` |
| 분위기 | `LIVELY` / `QUIET` |
| 예산 | `BUDGET_FRIENDLY` |

근거가 약한 축은 아예 비웁니다(억지로 채우지 않음). 프롬프트 지시만 믿지 않고 서버 validator도 `ACTIVE/CONVERSATION_FOCUSED`, `ALCOHOL_FRIENDLY/NO_ALCOHOL`, `LIVELY/QUIET`처럼 같은 축의 상반된 태그가 함께 오면 `MODEL_RESPONSE_INVALID`로 거부합니다.

**③ summary** — 이번 제안을 무엇을 기준으로 골랐는지 한 문장.

**충돌 처리**: 모임 목적과 참여자 기존 선호가 강하게 충돌하면(예: 목적은 술자리인데 다수가 음주 비선호) `status=CONFLICT`을 반환하고 검색 계획을 비웁니다. 이 경우 뒤 노드들은 실행되지 않고 그래프가 즉시 종료됩니다 — `action_required`(`type=PREFERENCE_CONFLICT`, `hostRequest`=모임 목적, `conflictingPreferenceCodes`)로 응답합니다.

### 4.2 Candidate Place Search — 비-LLM

| | |
| --- | --- |
| 파일 | `app/graph/nodes/l_candidate_place_search.py` |
| 그래프 노드 | `search_places` |
| 입력 | `meeting.region`, `search_plans`(4.1의 각 검색어), `excluded_external_place_ids` |
| 방식 | Kakao Local API 키워드 검색 (LLM 아님) |
| 출력 | `place_candidates`(최대 15개), `search_metrics` |

각 SearchPlan의 `searchQueries`로 Kakao Local API(`search/keyword.json`)를 `"{region} {검색어}"` 형태로 호출합니다. 검색어 하나당 최대 5개를 요청하고, 동시에 실행하는 검색은 최대 4개로 제한합니다.

검색 결과는 바로 상위 3개로 자르지 않습니다. 먼저 `excludedExternalPlaceIds`를 제거합니다. 하나의 계획 안에서도 여러 query 결과를 한 개씩 번갈아 섞어 첫 검색어가 계획의 5개 자리를 독점하지 않게 합니다. 그다음 계획별 후보도 round-robin으로 합치면서 전역 장소 중복을 제거합니다. 한 계획은 최대 5개, 전체는 최대 15개입니다. 이 두 단계의 균형 선택으로 공정성 계산 전에 후보 폭을 확보합니다.

Kakao 응답에서 가져오는 값은 `id`, `place_name`, `road_address_name`(없으면 `address_name`), `category_name`, `place_url`, 좌표(`y`=위도, `x`=경도, 문자열에서 숫자로 변환)입니다. 각 후보에는 어떤 SearchPlan에서 왔는지 `search_plan_label/source/rationale`도 함께 보존합니다.

### 4.3 Candidate Context/Fairness Pre-Ranker

| | |
| --- | --- |
| 파일 | `app/graph/nodes/n_candidate_ranker.py`, `app/graph/fairness.py` |
| 그래프 노드 | `rank_and_explain` |
| 입력 | `place_candidates`(최대 15개), `participants[].preferences`, `meeting.purpose` |
| 방식 | LLM 의미 관계 판정 + hard gate + 순수 Python 만족도·공정성 계산 |
| 출력 | `ranked_candidates`(영업 검증 우선순위) |

비용이 큰 웹 영업 검증 전에 모든 Kakao 후보를 평가해 우선순위를 만듭니다. 파일명은 기존 `n_candidate_ranker.py`를 유지하지만, 이 노드가 만드는 것은 최종 API의 1~3위가 아니라 **어떤 후보부터 영업 검증할지 정하는 사전랭킹**입니다.

최대 15개를 Gemini 구조화 출력 한 번에 넣지 않습니다. 후보를 5개씩 최대 3 batch로 나누고 `asyncio.gather`로 병렬 평가한 뒤 결과를 merge합니다. 각 batch와 merge 결과 모두 후보·참여자·선호 관계의 완전성을 검증하고, 이후 원래 place list 순서로 점수화하므로 모델 배열 순서에 의존하지 않습니다. 출력 크기는 제한하면서 누락된 평가가 조용히 섞이는 것도 막습니다.

LLM은 후보를 고르거나 숫자 점수를 만들지 않고, 모든 후보를 정확히 한 번씩 평가합니다. 후보마다 두 종류의 제한된 의미 관계와 집단 수준 `reasons`·일반 태그를 반환합니다.

#### 모임 목적 적합성은 hard gate

`contextRelation`은 다음 셋 중 하나입니다.

| 관계 | 처리 |
| --- | --- |
| `DIRECT` | 명시적인 모임 목적에 직접 부합. 공정성 계산 대상으로 유지 |
| `PARTIAL` | 함께 고려할 수 있는 후보. 공정성 계산 대상으로 유지 |
| `NONE` | 모임 목적과 관련 있다는 근거가 없음. **영업 검증 전에 제외** |

`NONE`을 `0점` 같은 수식 가중치로 넣지 않습니다. 개인 선호 점수가 높아도 명시적 모임 목적과 무관하면 후보 자격 자체가 없다는 gate 정책입니다. 공정성은 목적을 만족한 후보끼리만 비교합니다. `DIRECT/PARTIAL`은 공정성 수식에 숫자로 섞지 않으며, 공정성 값까지 같은 경우에만 `DIRECT`를 tie-break로 우선합니다.

#### 참여자 선호 관계와 공정성 계산

각 후보와 모든 `(userId, vocabularyCode)` 쌍의 `preferenceRelation`은 다음 셋 중 하나입니다.

| 관계 | 내부 값 | 의미 |
| --- | ---: | --- |
| `DIRECT` | `1.0` | 후보가 선호 대상과 직접 대응 |
| `PARTIAL` | `0.5` | 일부 관련 |
| `NONE` | `0.0` | 관련 근거 없음 |

relation은 긍정·부정을 뜻하지 않습니다. 예를 들어 매운 음식점은 `SPICY_FOOD/POSITIVE`와 `SPICY_INTOLERANT/NEGATIVE` 모두 `DIRECT`입니다. 서버가 요청의 `sentiment`를 적용해 전자는 높은 만족도, 후자는 낮은 만족도로 바꿉니다.

모델 결과의 후보 ID·사용자 ID·선호 코드와 완전성을 서버가 대조합니다. 입력에 없거나 중복된 ID가 있거나 후보 또는 선호 평가가 하나라도 빠지면 `502 MODEL_RESPONSE_INVALID`입니다. 검증을 통과하면 `app/graph/fairness.py`가 다음 수식을 계산합니다.

```text
POSITIVE → d(p)=+1       NEGATIVE → d(p)=-1
WEAK=1, MODERATE=2, STRONG=3

q(i,p,c) = 0.5 + 0.5 × d(p) × relationValue
u(i,c)   = 해당 참여자 선호 q의 강도 가중평균
S(c)     = 모든 참여자 u의 평균
F(c)     = 모든 참여자 u의 최솟값
Score(c) = 100 × [0.7 × S(c) + 0.3 × F(c)]
```

선호가 없는 참여자는 `u(i,c)=0.5`의 중립값입니다. 일반 `STRONG + NEGATIVE` 직접 충돌은 만족도 `0.0`까지 내려가지만 즉시 제거하지 않습니다. 코드가 `_ALLERGY`로 끝나는 알레르기 Vocabulary와 후보가 `DIRECT`일 때만 안전 조건으로 veto합니다.

남은 후보는 `Score → F → S → contextRelation(DIRECT 우선) → 원래 Kakao 순서`로 정렬합니다. 여기서 최대 3개로 자르지 않고 모든 생존 후보를 `ranked_candidates`에 남깁니다. 이 순서가 다음 단계의 웹 검증 우선순위입니다. LLM 응답 배열의 순서는 결과에 영향을 주지 않습니다.

개인 만족도와 공정성 점수는 Back 응답에 새 필드로 추가하지 않습니다. LangSmith에서는 그래프 노드 `rank_and_explain` 아래 후보별 `fairness_score` child span에서 `participantSatisfaction`, 평균 `S`, 최저 `F`, 최종 `score`, `vetoed`를 확인할 수 있습니다.

### 4.4 Candidate Place Verifier — 선별 웹 검증

| | |
| --- | --- |
| 파일 | `app/graph/nodes/n_candidate_place_verifier.py` |
| 그래프 노드 | `verify_places` |
| 입력 | `ranked_candidates`, `confirmed_slot`(날짜/시작/종료 시각) |
| 방식 | 상위 6개 병렬 검증 → usable 3개 미만이면 다음 3개씩 반복, 모든 batch가 공통 20초 예산 사용 |
| 출력 | `verified_places`, `verification_timed_out`, `verification_metrics` |

최대 15개 전체를 곧바로 웹 검색하지 않습니다. 사전랭킹 1~6위를 initial batch로 병렬 검증하고, 그 결과 `PASS/UNKNOWN`인 usable 후보가 3개보다 적을 때만 다음 순위 후보를 3개씩 fallback batch로 검증합니다. usable 3개 확보, ranked 후보 소진, 공통 20초 deadline 중 하나에서 멈춥니다. 모든 batch는 같은 deadline을 공유합니다. usable은 “영업이 확인됐다”가 아니라 **최종 후보로 남길 수 있다**는 뜻입니다.

장소 하나의 검증은 다음 순서입니다.

1. **검색**: `app/services/serper_client.py`로 [Serper](https://serper.dev) 검색 API를 호출합니다. 검색어는 `"{place_name} {address} 영업시간 휴무일"`이라는 고정 문자열입니다. 상위 5개 결과의 제목·스니펫·출처 URL을 텍스트로 정리합니다.
   > 원래는 Gemini의 `google_search` grounding 도구로 검색했지만 일반 생성과 별도의 할당량 때문에 `429`가 자주 발생해 검색만 Serper로 분리했습니다. Gemini는 검색 결과 판정만 담당합니다.
2. **현지 시각 정규화**: `confirmedSlot`이 UTC(`Z`)여도 날짜·시작·종료를 `Asia/Seoul`로 바꿔 국내 매장 영업시간과 같은 기준으로 비교합니다.
3. **판정과 근거 정규화**: Gemini가 검색 결과 텍스트만 근거로 `{status, businessHours, source}`를 구조화 출력합니다. 서버는 `source`가 실제 Serper 결과 URL 중 하나인지 allowlist로 대조합니다. `PASS/FAIL`인데 유효한 source가 없거나, `PASS`인데 `businessHours`가 없으면 확정 판정을 그대로 쓰지 않고 `UNKNOWN`으로 낮춥니다.

| 상태 | 의미 | usable 여부 |
| --- | --- | --- |
| `PASS` | 해당 날짜에 영업하고 모임 시간 전체가 영업시간 안 | usable |
| `FAIL` | 휴무·폐업 또는 모임 시간대가 영업시간 밖 | 제외 |
| `UNKNOWN` | 결과 없음·정보 부족·충돌·오류·timeout | usable, 단 영업 확인 표시는 하지 않음 |

`UNKNOWN`을 `PASS`나 `FAIL`로 단정하지 않습니다. 검색·판정 예외 또는 deadline 내 미완료 task도 장소 정보를 버리지 않고 `UNKNOWN`으로 복원합니다. 그래서 `UNKNOWN`은 usable 수에는 포함되지만 이후 `businessHoursVerified=false`, `openAtMeetingTime=null`로 구분됩니다. 첫 6개가 모두 `UNKNOWN`이어도 usable 후보는 충분하므로 fallback 검색을 시작하지 않습니다.

`SKIP_BUSINESS_HOURS_VERIFICATION`이 켜져 있으면 검색·판정을 생략하고 `UNKNOWN`으로 처리합니다. `verification_metrics`에는 사전랭킹 후보 수, 검증 대상으로 처리한 후보 수, usable 후보 수를 내부 관측값으로 남깁니다.

### 4.5 Candidate Suggestion Builder — 비-LLM

| | |
| --- | --- |
| 파일 | `app/graph/nodes/l_candidate_suggestion_builder.py` |
| 그래프 노드 | `build_suggestions` |
| 입력 | `verified_places`, `ranked_candidates`, `confirmed_slot` |
| 방식 | `FAIL` 제외 + 사전랭킹 순서 보존 + 기존 DTO 조립 |
| 출력 | `suggestions`(최대 3개) |

검증된 장소 중 `PASS/UNKNOWN`만 남기고 사전랭킹 순서를 그대로 유지해 최대 3개를 선택합니다. 이 노드에는 LLM 호출이 없습니다. Pre-Ranker가 만든 `reasons`와 일반 태그를 사용하되, 사실 판정 값은 코드가 붙입니다.

- `AVAILABLE_AT_MEETING_TIME`, `businessHoursVerified=true`, `openAtMeetingTime=true`: `verification_status == PASS`일 때만 파생
- `UNKNOWN`: `businessHoursVerified=false`, `openAtMeetingTime=null`, 이용 가능 태그 없음
- `matchedPreferenceDomains`: 실제 선정에 기여한 긍정 선호 코드를 Vocabulary `domain`으로 변환
- `proposedStartAt/EndAt`: 3단계의 `confirmedSlot` 원본 사용
- `sourceUrls`: Kakao 장소 URL과 영업시간 근거 URL 중복 제거. Kakao 응답의 URL이 비어 있으면 신뢰한 `kakao_place_id`로 `https://place.map.kakao.com/{id}`를 파생해 `externalUrl`과 최소 한 개의 `sourceUrls`를 보장

공정성 점수, contextRelation, verificationStatus 같은 내부 필드는 Back 응답에 추가하지 않습니다. 기존 `Suggestion` DTO와 최대 3개라는 계약을 그대로 유지하면서 내부 선택 순서만 바꾼 구조입니다.

---

## 전체 데이터 흐름 한눈에 보기

```
[Back]
  meeting.purpose, meeting.region     ← 2단계(Context) 결과, DB(meetings.purpose)에서
  confirmedSlot                       ← 3단계(Schedule) 결과, DB(meetings.confirmed_*)에서
  participants[].preferences          ← 1단계(Preference) 결과 누적, DB(user_preferences)에서
        │
        ▼  (userId별 선호 경계 유지)
┌─────────────────────────────────────────────────────────┐
│ Candidate Activity Decider (LLM)                         │
│  → SearchPlan 1~4개, meetingTags[], summary               │
│  → (충돌 시) actionRequired로 즉시 종료                    │
└─────────────────────────────────────────────────────────┘
        │ searchPlans[].searchQueries
        ▼
┌─────────────────────────────────────────────────────────┐
│ Candidate Place Search (Kakao, 비-LLM)                    │
│  → 계획별 최대 5개, 전체 placeCandidates 최대 15개          │
└─────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│ Candidate Context/Fairness Pre-Ranker (후보 5개씩 병렬)      │
│  context NONE hard gate → Python u/S/F/Score 사전랭킹      │
│  → rankedCandidates[] (최종 3개가 아니라 검증 우선순위)      │
└─────────────────────────────────────────────────────────┘
        │ 상위 1~6위
        ▼
┌─────────────────────────────────────────────────────────┐
│ Candidate Place Verifier (Serper + Gemini, 공통 20초)       │
│  1~6위 병렬 → usable<3이면 다음 3개씩 반복                  │
│  PASS/UNKNOWN=usable, FAIL=제외                            │
└─────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│ Candidate Suggestion Builder (비-LLM)                     │
│  사전랭킹 순서를 유지해 기존 Suggestion DTO 최대 3개 조립     │
└─────────────────────────────────────────────────────────┘
```
