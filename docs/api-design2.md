# 다모여 AI API 명세 v2

> 상태: **AI 연동 목표 계약안** — 아직 합의가 필요한 정책은 14장에 분리
>
> 작성일: 2026-08-20
>
> 범위: Spring Boot Back과 FastAPI AI 서비스 사이의 API 계약

이 문서는 프로토타입 화면에서 필요한 AI 기능, 백엔드가 제안한 API 예시, 확정 DB 스키마와 현재 AI 구현을 종합한 **AI 파트 통합 API 명세**다. Front가 호출하는 `/api/**` API나 백엔드의 DB 구현 자체는 이 문서의 구현 범위가 아니다.

문서 간 내용이 다를 때는 다음 순서로 판단했다.

1. 화면 검토를 거쳐 확정된 [`api-spec.md`](api-spec.md)
2. Back의 기대 형식을 보여주는 [`backend-api-example.md`](backend-api-example.md)
3. 타입과 enum의 최종 근거인 [`db_schema.md`](db_schema.md)
4. [`api-design.md`](api-design.md) 마지막의 “러프하게 작성해본 api들” 1~7
5. 기존 AI 설계와 현재 코드

백엔드 예시와 큰 차이가 없으면 백엔드 예시를 우선했다. 차이가 큰 부분은 조용히 합치지 않고 마지막의 “현재 구현과 목표 계약의 차이” 및 “확인 필요 사항”에 남겼다.

단, DB 컬럼명·타입·enum은 위 순서와 관계없이 `db_schema.md`를 최종 근거로 사용한다.

---

## 1. 범위와 책임

### 1.1 AI 서비스가 담당하는 것

- 자연어에서 장기 개인 선호를 추출하고 Vocabulary에 매핑
- 모임 목적 대화를 한 문장으로 정리하고 제안 파이프라인 내부에서 컨텍스트로 구조화
- 참여자 날짜·선호·과거 모임 요약을 종합해 시간과 장소 후보를 최대 3개 생성
- 장소 검색 결과의 영업 정보 검증과 그룹 수준 선정 사유 생성

### 1.2 Back이 담당하는 것

- 사용자 인증·인가와 일정 생성자 권한 확인
- DB 조회·저장·UPSERT와 트랜잭션
- AI 입출력의 스키마·Vocabulary·날짜·장소 검증
- 비동기 작업(run), polling, generation 및 멱등성 관리
- 모임 상태 전이와 제안 확정
- Google Calendar OAuth 및 이벤트 생성
- AI 내부 응답을 Front 응답 DTO로 정규화

AI 서비스는 DB에 직접 접근하지 않는다. 따라서 이 문서에서 “선호 저장”, “목적 업데이트”, “제안 저장”이라고 표현하는 흐름도 실제 쓰기는 Back이 수행한다.

### 1.3 러프 요구사항과 AI API 매핑

| 러프 번호 | 화면 요구 | 사용하는 AI API |
| --- | --- | --- |
| 1, 2 | 온보딩 선호 추출 + 응답 문구 | `POST /ai/preferences/extract` |
| 3, 4 | 프로필 선호 업데이트 + 응답 문구 | `POST /ai/preferences/extract` 재사용 |
| 5 | 새 일정의 모임 목적 대화 | 매 턴 `POST /ai/meetings/{meetingId}/context/messages`, 최종 전송 시 `POST /ai/meetings/{meetingId}/context` |
| 6 | 시간·장소 Top 3 제안 | `POST /ai/meetings/{meetingId}/candidates` |
| 7 | 재생성("뒤로가기") | 전용 API 없음. `/context/messages`(멀티턴) → `/context`(요약) → `/candidates`를 그대로 재사용. 이전 세대에서 보여준 장소는 `excludedExternalPlaceIds`로 누적 전달 |

선호 추출과 답변 문구는 같은 처리 결과이므로 화면별 또는 기능별로 API를 나누지 않는다.

---

## 2. 엔드포인트 목록

| Method | Path | 목적 | 호출 주체 |
| --- | --- | --- | --- |
| `GET` | `/health` | AI 프로세스 생존 확인 | Back 또는 운영 인프라 |
| `POST` | `/ai/preferences/extract` | 자연어 개인 선호 추출 | Back |
| `POST` | `/ai/meetings/{meetingId}/context/messages` | 모임 목적 채팅 한 턴 | Back |
| `POST` | `/ai/meetings/{meetingId}/context` | 모임 목적 채팅 최종 전송 시 한 문장으로 정리 | Back |
| `POST` | `/ai/meetings/{meetingId}/candidates` | 시간·장소 후보 최대 3개 생성 | Back의 비동기 worker |

전용 재생성 API는 없다. "재생성"은 제품 흐름상 "뒤로가기"로 단순화됐다 — Back이 `/context/messages`(멀티턴 대화)로 되돌아가 목적을 다시 정리하고, `/context`로 재요약한 뒤 `/candidates`를 다시 호출한다. 이전 세대에서 이미 보여준 장소는 `/candidates`의 기존 `excludedExternalPlaceIds`에 누적해서 넣으면 된다. 9장 참고.

AI가 의존하는 Back API는 다음 하나다.

| Method | Path | 목적 | 호출 주체 |
| --- | --- | --- | --- |
| `GET` | `/internal/preference-vocabulary` | 현재 사용 가능한 Vocabulary 조회 | AI 서비스 |

---

## 3. 공통 규칙

### 3.1 형식

- AI API base path는 `/ai`다. 단, 운영용 health check는 `/health`다.
- 요청과 응답의 `Content-Type`은 `application/json`이다.
- JSON 필드명은 `camelCase`를 사용한다.
- DB의 BIGINT 식별자는 JSON `integer`로 전달한다.
- 날짜는 `YYYY-MM-DD`, 시각은 UTC offset을 포함한 ISO 8601 문자열을 사용한다.
  - 예: `2026-08-30T19:00:00+09:00`
- 배열 값이 없으면 `null`이 아니라 `[]`를 반환한다.
- 실제로 값이 없을 수 있는 단일 필드만 `null`을 허용한다.
- 응답 표에 정의된 필드는 항상 key를 포함한다. nullable 필드는 값이 없을 때 key를 생략하지 않고 `null`로 반환한다.
- 계약에 없는 JSON 필드는 거부한다. 단, 아직 구조가 확정되지 않은 `meetingMemory`만 확장 가능한 JSON object로 취급한다.
- 자연어 `messages`는 **전체 대화 이력이 아니라 이번 요청에서 새로 제출한 문장 목록**이다.
- 요청 표의 `필수=O`는 key를 반드시 보내야 한다는 뜻이고, 응답 표의 `nullable=O`는 key는 항상 보내되 값으로 `null`을 허용한다는 뜻이다.
- 모든 path의 `meetingId`는 1 이상의 정수여야 한다.

### 3.2 내부 인증

Back↔AI 통신은 외부에 공개하지 않는 내부 통신이다. 공유 Bearer token 또는 mTLS를 사용할 예정이지만 방식은 아직 확정되지 않았다. 인증 방식이 정해지면 모든 `/ai/**` 요청에 공통 적용한다.

### 3.3 AI 호출의 동기·비동기 경계

AI API 자체는 동기 응답을 반환한다. 오래 걸리는 제안 생성의 비동기 run 생성, polling, 재시도와 generation 보존은 Back이 담당한다.

예를 들어 Front의 `POST /api/meetings/{meetingId}/plan` 요청은 Back에서 `202 Accepted`를 반환하고, Back의 worker가 내부적으로 `POST /ai/meetings/{meetingId}/candidates`를 호출한다.

### 3.4 공통 오류 응답

```json
{
  "error": {
    "code": "MODEL_RESPONSE_INVALID",
    "message": "모델 응답이 계약된 스키마와 일치하지 않습니다.",
    "retryable": true,
    "requestId": "6e214a43-56a6-4b3b-a63c-14a1d3bb3c72"
  }
}
```

| 필드 | 타입 | 필수 | 의미 |
| --- | --- | --- | --- |
| `error` | `object` | O | 오류 정보 |
| `error.code` | `string` | O | 기계가 분기할 수 있는 안정적인 오류 코드 |
| `error.message` | `string` | O | 로그와 개발자 확인용 설명 |
| `error.retryable` | `boolean` | O | 동일 의미의 요청을 재시도할 수 있는지 여부 |
| `error.requestId` | `string \| null` | O | 요청에 `requestId`가 있었다면 그대로 반환하고, 해당 필드가 없는 API면 `null` |

| HTTP | 의미 |
| --- | --- |
| `400` | JSON 형태는 맞지만 값, 문장 내용 또는 필드 조합이 잘못됨 |
| `401` | Back↔AI 인증 실패 |
| `422` | 필수 필드 누락, 타입·enum 불일치 또는 요청 필드 자체의 유효성 검증 실패 |
| `500` | AI 서비스 내부의 예상하지 못한 오류 |
| `502` | 연결된 LLM 또는 장소 제공자의 응답·프로토콜이 잘못됨 |
| `503` | Vocabulary, AI 모델 등 필수 의존성에 연결할 수 없음 |
| `504` | 전체 처리 제한 시간을 초과함 |

---

## 4. `GET /health`

### 목적과 호출 주체

Back 또는 운영 인프라가 AI 애플리케이션 프로세스의 생존 여부를 확인한다. LLM, Vocabulary, Kakao API까지 점검하는 readiness API는 아니다.

### Request

Request body 없음.

### Response `200 OK`

```json
{
  "status": "ok"
}
```

| 필드 | 타입 | nullable | 의미 |
| --- | --- | --- | --- |
| `status` | `string` | X | 프로세스가 요청을 처리할 수 있으면 고정값 `ok` |

### 검증 및 오류

입력값이 없는 운영용 API다. 프로세스가 응답하지 않거나 `200`이 아니면 호출 측에서 unavailable로 판단한다.

---

## 5. `GET /internal/preference-vocabulary`

> 이 API는 AI 서버가 제공하는 API가 아니라 **Back이 제공하고 AI가 호출하는 의존 계약**이다.

### 목적과 호출 주체

AI 서비스가 선호 추출에 사용할 표준 Vocabulary와 계층을 Back에서 조회한다. AI는 이 목록에 없는 코드를 새로 생성하지 않는다.

### Request

Request body 없음.

### Response `200 OK`

```json
{
  "vocabulary": [
    {
      "code": "SEAFOOD",
      "domain": "FOOD",
      "displayName": "해산물",
      "parentCode": null
    },
    {
      "code": "SHELLFISH",
      "domain": "FOOD",
      "displayName": "조개류",
      "parentCode": "SEAFOOD"
    }
  ]
}
```

| 필드 | 타입 | nullable | 의미 |
| --- | --- | --- | --- |
| `vocabulary` | `VocabularyEntry[]` | X | 현재 사용할 수 있는 전체 Vocabulary 목록 |
| `vocabulary[].code` | `string` | X | 전역에서 유일한 표준 코드 |
| `vocabulary[].domain` | `string` | X | 선호 영역. 값 목록은 DB 데이터가 기준이며 AI가 임의 enum을 만들지 않음 |
| `vocabulary[].displayName` | `string` | X | 사용자 화면에 표시할 이름 |
| `vocabulary[].parentCode` | `string \| null` | O | 상위 Vocabulary 코드. 최상위 항목이면 `null` |

### 검증 및 처리 규칙

- `code`는 응답 안에서 중복될 수 없다.
- `parentCode`가 있으면 같은 응답의 `code` 중 하나여야 한다.
- `vocabulary`는 최소 1개 항목을 포함해야 한다. 빈 목록은 정상 Vocabulary로 취급하지 않는다.
- `code`와 `displayName`은 100자 이하, `domain`은 50자 이하여야 한다.
- DB 스키마에 없는 `attribute` 필드는 사용하지 않는다.
- AI는 성공한 응답을 메모리에 캐시한다.
- 캐시 갱신 주기와 강제 갱신 방식은 확인 필요 사항이다.

### 오류

Back이 이 API에서 반환할 구체 오류 계약은 Back과 별도로 합의한다. AI가 조회 또는 파싱에 실패하면 AI 호출자에게 `503 VOCABULARY_UNAVAILABLE`을 반환한다.

---

## 6. `POST /ai/preferences/extract`

### 목적과 호출 주체

Back이 온보딩 또는 프로필 화면에서 받은 자연어를 전달하면, AI가 장기 개인 선호를 추출하고 Vocabulary에 매핑한다. AI는 응답만 만들며 사용자 식별과 DB UPSERT는 Back이 담당한다.

러프 요구 1~4를 이 API 하나로 처리한다.

### Request

```json
{
  "messages": [
    "매운 음식 좋아해"
  ]
}
```

| 필드 | 타입 | 필수 | 의미 |
| --- | --- | --- | --- |
| `messages` | `string[]` | O | 이번 제출에서 선택하거나 직접 입력한 자연어 문장 목록 |

### Response `200 OK`

```json
{
  "reply": "말씀해주신 내용을 선호에 반영했어요.",
  "extractedPreferences": [
    {
      "vocabularyCode": "SPICY_FOOD",
      "displayName": "매운 음식",
      "domain": "FOOD",
      "rawValue": "매운 음식",
      "sentiment": "POSITIVE",
      "strength": "MODERATE",
      "mappingType": "EXACT"
    }
  ]
}
```

| 필드 | 타입 | nullable | 의미 |
| --- | --- | --- | --- |
| `reply` | `string` | X | 사용자에게 표시할 응답. 순수 선호 입력이면 완료 문구, 잡담이 섞였으면 짧은 대화 응답 |
| `extractedPreferences` | `ExtractedPreference[]` | X | 추출된 장기 선호 목록. 선호가 없으면 `[]` |
| `extractedPreferences[].vocabularyCode` | `string \| null` | O | 표준 Vocabulary 코드. `UNMAPPED`일 때만 `null` |
| `extractedPreferences[].displayName` | `string \| null` | O | Vocabulary의 UI 표시 이름. `UNMAPPED`일 때 `null` |
| `extractedPreferences[].domain` | `string \| null` | O | Vocabulary의 선호 영역. `UNMAPPED`일 때 `null` |
| `extractedPreferences[].rawValue` | `string` | X | 사용자가 실제 언급한 대상 표현 |
| `extractedPreferences[].sentiment` | `POSITIVE \| NEGATIVE` | X | 대상에 대한 긍정 또는 부정 선호 |
| `extractedPreferences[].strength` | `WEAK \| MODERATE \| STRONG` | X | 선호 강도 3단계 |
| `extractedPreferences[].mappingType` | `EXACT \| GENERALIZED \| UNMAPPED` | X | Vocabulary 매핑 방식 |

### 검증 및 처리 규칙

- `messages`에는 공백이 아닌 문장이 최소 1개 있어야 한다.
- 각 문장은 trim 후 처리하며 유효 문장 사이의 순서는 유지한다.
- `messages`는 과거 대화 전체가 아니라 이번 제출분만 포함한다.
- AI는 Vocabulary에 없는 `vocabularyCode`를 생성하지 않는다.
- Vocabulary 목록이 비어 있으면 임의 코드를 허용하지 않고 `VOCABULARY_UNAVAILABLE`로 실패한다.
- `EXACT`는 사용자 표현과 코드가 직접 대응하는 경우다.
- `GENERALIZED`는 정확한 코드가 없어 안전한 상위 코드로 매핑한 경우다.
- `UNMAPPED`는 선호 표현이지만 매핑 가능한 코드가 없는 경우다. 이때 `vocabularyCode`, `displayName`, `domain`은 모두 `null`이어야 한다.
- `displayName`과 `domain`은 LLM이 생성하지 않는다. AI 서버가 캐시된 Vocabulary에서 `vocabularyCode`로 조회해 붙인다.
- `rawValue`, `sentiment`, `strength`, `mappingType`과 후보 `vocabularyCode`는 모델의 structured output으로 만들고, AI 서버가 전체 응답 스키마와 Vocabulary 소속 여부를 검증한다.
- 순수 선호 입력의 `reply`는 서버의 고정 완료 문구를 사용하고, 잡담이 섞였을 때만 모델이 짧은 대화 응답을 만든다.
- non-null `vocabularyCode`, `displayName`, `domain`, `rawValue`은 각각 DB 길이 제한인 100자, 100자, 50자, 255자를 넘을 수 없다.
- 한 응답에서 같은 `vocabularyCode`를 중복 반환하지 않는다. 같은 제출 안에 상반된 표현이 있으면 가장 마지막의 명시적 사용자 표현을 우선해 하나로 정리한다.
- Back은 non-null `vocabularyCode`를 다시 검증한 뒤 `(user_id, vocabulary_code)` 기준으로 UPSERT한다.
- DB의 `user_preferences.vocabulary_code`가 NOT NULL FK이므로 `UNMAPPED`는 일반 선호 테이블에 저장하거나 Front의 일반 선호 목록에 노출하지 않는다. 필요하면 별도 디버그 로그에만 남긴다.
- Back은 유효한 요청 문장을 줄바꿈(`\n`)으로 합쳐, 같은 제출에서 나온 각 선호 행의 `source_text`에 반드시 저장한다.

### 오류

| HTTP | code | 상황 | retryable |
| --- | --- | --- | --- |
| `422` | `REQUEST_SCHEMA_INVALID` | `messages` 누락·타입 불일치 또는 유효한 문장이 없음 | `false` |
| `503` | `VOCABULARY_UNAVAILABLE` | Vocabulary를 조회하거나 파싱할 수 없음 | `true` |
| `503` | `MODEL_UNAVAILABLE` | LLM을 호출할 수 없음 | `true` |
| `502` | `MODEL_RESPONSE_INVALID` | LLM 결과가 계약된 스키마와 맞지 않음 | `true` |

---

## 7. 모임 목적 채팅 (2단계)

### 설계 배경

처음에는 매 호출마다 `messages`(새 문장)와 `currentPurpose`(누적된 목적)를 함께 보내 매번 한 문장으로 재요약하는 단일 API였다. 이후 화면을 실제 채팅 UI(사용자가 여러 턴 대화하다가 "최종 전송하기"를 눌러야 확정)로 만들기로 하면서 두 가지 문제가 드러나 2단계로 나눴다.

1. **매 턴 재요약은 낭비다.** 사용자가 아직 대화 중인데 턴마다 "한 문장으로 정리"를 시도할 필요가 없다 — 최종 전송 시 한 번만 하면 된다.
2. **반복 요약은 품질이 떨어진다.** 턴1 요약 → 턴2에서 그 요약+새 발화를 다시 요약 → ... 식으로 이어붙이면 원래 뉘앙스가 조금씩 깎인다. 전체 원문을 한 번에 보고 요약하는 게 더 정확하다.

또한 AI는 상태를 저장하지 않는다는 원칙이 여기서도 그대로 적용된다. LLM 호출은 매번 완전히 독립적이라 이전 턴을 기억하지 못한다(실제로 이전 호출 내용을 전혀 언급하지 않은 채로 대화 기억을 그럴듯하게 지어내는 것까지 확인됨). 그래서 Back이 `meeting_chat_messages`에서 조회한 대화 원문을 매 호출 `history`로 통째로 실어 보내야 한다. 어떤 대화가 이 일정에 속하는지 필터링하는 것도 Back의 책임이다 — `meeting_chat_messages.meeting_id`가 이미 `meetings.id` 하나로 스코프되므로, AI 요청 스키마에는 `meetingId` 외의 필터 필드가 없다.

### Path parameter

| 필드 | 타입 | 필수 | 의미 |
| --- | --- | --- | --- |
| `meetingId` | `integer` | O | 대상 일정의 `meetings.id`. AI는 DB 조회에 사용하지 않고 추적·로그 상관관계에 사용 |

### 7.1 `POST /ai/meetings/{meetingId}/context/messages` — 채팅 한 턴

대화 중 매 사용자 발화마다 호출한다. 목적을 요약하지 않고 대화형으로만 반응한다.

#### Request

```json
{
  "history": [
    { "role": "USER", "content": "오랜만에 만나서 저녁 먹고 이야기하려고요" },
    { "role": "ASSISTANT", "content": "편안한 저녁 자리로 준비할게요. 원하시는 분위기가 있을까요?" }
  ],
  "message": "너무 시끄러운 곳은 피하고 싶어요"
}
```

| 필드 | 타입 | 필수 | 의미 |
| --- | --- | --- | --- |
| `history` | `ChatTurn[]` | O | 이전까지의 대화 전체. 첫 턴이면 `[]` |
| `history[].role` | `USER \| ASSISTANT` | O | `meeting_chat_messages.role`과 동일한 값 |
| `history[].content` | `string` | O | 해당 턴의 원문 |
| `message` | `string` | O | 이번 턴의 새 사용자 발화. 공백만 있으면 안 됨 |

#### Response `200 OK`

```json
{ "reply": "네, 조용한 곳으로 찾아볼게요. 더 말씀해주실 조건이 있을까요?" }
```

| 필드 | 타입 | nullable | 의미 |
| --- | --- | --- | --- |
| `reply` | `string` | X | 사용자에게 표시할 대화형 답변 |

#### 검증 및 처리 규칙

- `message`는 공백이 아닌 문자열이어야 한다.
- `history`의 각 항목은 순서를 유지한다 — AI는 이 순서를 그대로 대화 맥락으로 사용한다.
- 이 단계에서는 `purpose`를 만들지 않는다. 지역·날짜·시간대도 추출하거나 변경하지 않는다.
- `reply`는 모델의 structured output으로 만들고 AI 서버가 형식을 검증한다.
- Back은 이번 턴의 `message`와 응답 `reply`를 각각 `USER`/`ASSISTANT` 행으로 `meeting_chat_messages`에 저장한다. AI는 직접 저장하지 않는다.

#### 오류

| HTTP | code | 상황 | retryable |
| --- | --- | --- | --- |
| `422` | `REQUEST_SCHEMA_INVALID` | 필드 누락·타입 오류 또는 `message`가 공백뿐임 | `false` |
| `503` | `MODEL_UNAVAILABLE` | LLM을 호출할 수 없음 | `true` |
| `502` | `MODEL_RESPONSE_INVALID` | 응답이 스키마와 맞지 않음 | `true` |

---

### 7.2 `POST /ai/meetings/{meetingId}/context` — 최종 전송

사용자가 "최종 전송하기"를 누르면 그동안의 대화 전체를 한 번에 한 문장으로 요약한다. 기존 경로(`/ai/meetings/{meetingId}/context`)를 그대로 재사용한다 — 이 호출이 실제로 `purpose`를 만들어내는 지점이기 때문이다.

#### Request

```json
{
  "history": [
    { "role": "USER", "content": "오랜만에 만나서 저녁 먹고 이야기하려고요" },
    { "role": "ASSISTANT", "content": "편안한 저녁 자리로 준비할게요. 원하시는 분위기가 있을까요?" },
    { "role": "USER", "content": "너무 시끄러운 곳은 피하고 싶어요" },
    { "role": "ASSISTANT", "content": "네, 조용한 곳으로 찾아볼게요. 더 말씀해주실 조건이 있을까요?" }
  ]
}
```

| 필드 | 타입 | 필수 | 의미 |
| --- | --- | --- | --- |
| `history` | `ChatTurn[]` | O | 7.1에서 오간 대화 전체(마지막 턴까지 포함). `USER` 발화가 최소 1개 있어야 함 |

#### Response `200 OK`

```json
{
  "reply": "편안하게 대화할 수 있는 조용한 저녁 모임으로 정리했어요.",
  "purpose": "오랜만에 만나 조용한 곳에서 대화하는 저녁 식사"
}
```

| 필드 | 타입 | nullable | 의미 |
| --- | --- | --- | --- |
| `reply` | `string` | X | 요약 완료를 알리는 답변 |
| `purpose` | `string` | X | 대화 전체를 반영해 정리한 저장용 한 문장, 최대 1,000자 |

#### 검증 및 처리 규칙

- `history`에 `USER` 발화가 최소 1개 있어야 한다.
- `purpose`는 1,000자를 넘지 않는 한 문장이어야 한다.
- 지역·날짜·시간대는 이 API에서 추출하거나 변경하지 않는다. 해당 값은 UI에서 확정한 뒤 `/candidates` 요청으로 전달한다.
- 활동 힌트·분위기·제약 같은 구조화 값은 별도 외부 응답 필드로 저장하지 않고, 후보 생성 파이프라인이 `purpose`에서 내부 중간 상태로 다시 해석한다.
- `reply`와 `purpose`는 모델의 structured output으로 만들고 AI 서버가 길이와 형식을 검증한다.
- AI는 `purpose`를 직접 저장하지 않는다. Back이 성공 응답 검증 후 `meetings.purpose`에 저장한다.
- `currentPurpose` 같은 누적 상태 필드는 없다 — 매번 전체 원문을 보고 한 번에 요약하기 때문이다 (7장 설계 배경 참고).

#### 오류

| HTTP | code | 상황 | retryable |
| --- | --- | --- | --- |
| `422` | `REQUEST_SCHEMA_INVALID` | 필드 누락·타입이 잘못됐거나 `USER` 발화가 하나도 없음 | `false` |
| `503` | `MODEL_UNAVAILABLE` | LLM을 호출할 수 없음 | `true` |
| `502` | `MODEL_RESPONSE_INVALID` | 정리된 목적 응답이 스키마와 맞지 않음 | `true` |

---

## 8. `POST /ai/meetings/{meetingId}/candidates`

### 목적과 호출 주체

Back의 비동기 worker가 일정, 참여자별 가능 날짜와 개인 선호, 지난 모임 요약을 전달하면 AI 파이프라인이 시간과 장소가 결합된 후보를 최대 3개 반환한다.

러프 요구 6을 처리한다. Back은 AI 응답을 검증하고 저장한 뒤 별도의 Front용 제안 조회 응답으로 변환한다.

### Path parameter

| 필드 | 타입 | 필수 | 의미 |
| --- | --- | --- | --- |
| `meetingId` | `integer` | O | 대상 일정의 `meetings.id`. body의 `meeting.id`와 같아야 함 |

### Request

```json
{
  "contractVersion": "1.0",
  "requestId": "6e214a43-56a6-4b3b-a63c-14a1d3bb3c72",
  "meeting": {
    "id": 20,
    "purpose": "오랜만에 만나 조용한 곳에서 대화하는 저녁 식사",
    "region": "건대",
    "scheduleSearchFrom": "2026-08-23",
    "scheduleSearchTo": "2026-09-07",
    "preferredTimeOfDay": "EVENING",
    "durationMinutes": null,
    "timezone": "Asia/Seoul"
  },
  "participants": [
    {
      "userId": 1,
      "selectedDates": [
        "2026-08-30",
        "2026-09-01"
      ],
      "preferences": [
        {
          "vocabularyCode": "SPICY_FOOD",
          "sentiment": "POSITIVE",
          "strength": "MODERATE",
          "rawValue": "매운 음식"
        }
      ]
    },
    {
      "userId": 2,
      "selectedDates": [
        "2026-08-30"
      ],
      "preferences": []
    }
  ],
  "meetingMemory": {
    "summary": "지난 모임에서는 시끄러운 장소 때문에 대화하기 어려웠다."
  },
  "excludedExternalPlaceIds": []
}
```

#### 최상위 필드

| 필드 | 타입 | 필수 | 의미 |
| --- | --- | --- | --- |
| `contractVersion` | `string` | O | Back↔AI 내부 DTO 버전. 현재 값은 `1.0`. 문서 제목의 v2와는 별도 버전 |
| `requestId` | `UUID string` | O | 로그·트레이싱·오류 상관관계를 위한 요청 ID |
| `meeting` | `MeetingInput` | O | 이번 일정의 확정 입력 |
| `participants` | `ParticipantInput[]` | O | 이번 일정에 참여하는 사용자와 각 사용자 입력 |
| `meetingMemory` | `object \| null` | O | 같은 그룹의 과거 모임에서 압축한 JSON 컨텍스트. 없으면 `null` |
| `excludedExternalPlaceIds` | `string[]` | O | 이미 보여준 외부 장소 ID 전체. 최초 생성이면 `[]`(예전과 동일하게 동작)이고, 재생성("뒤로가기" 후 다시 생성)이면 Back이 지금까지의 모든 generation에서 보여준 `externalPlaceId`를 누적해서 채운다 |

#### `meeting`

| 필드 | 타입 | 필수 | 의미 |
| --- | --- | --- | --- |
| `meeting.id` | `integer` | O | `meetings.id` |
| `meeting.purpose` | `string` | O | `meetings.purpose`에 저장된 현재 목적. 재생성이면 `/context/messages`로 되돌아가 다시 나눈 대화를 `/context`로 재요약해 얻은 새 `purpose` |
| `meeting.region` | `string` | O | 장소 검색 지역 |
| `meeting.scheduleSearchFrom` | `date` | O | 일정 탐색 시작일 |
| `meeting.scheduleSearchTo` | `date` | O | 일정 탐색 종료일 |
| `meeting.preferredTimeOfDay` | `DAYTIME \| LATE_AFTERNOON \| EVENING \| ANY` | O | 모임 선호 시간대 |
| `meeting.durationMinutes` | `integer \| null` | O | 제안 종료 시각 계산에 사용할 모임 길이(분). `null`이면 v2 기본값 120분 사용 |
| `meeting.timezone` | `string` | O | IANA timezone. MVP 기본값은 `Asia/Seoul` |

`durationMinutes`는 백엔드 예시와 현재 DB에는 없지만 `proposedEndAt` 계산에는 길이가 필요하다. 별도 UI·DB 필드가 확정되기 전까지 Back은 `null`을 보내고 AI 서비스는 v2 기본값 120분을 사용한다.

#### `participants`

| 필드 | 타입 | 필수 | 의미 |
| --- | --- | --- | --- |
| `participants[].userId` | `integer` | O | 참여자의 `users.id` |
| `participants[].selectedDates` | `date[]` | O | 참여자가 가능하다고 제출한 날짜 목록. 가능 날짜가 없으면 `[]` |
| `participants[].preferences` | `ParticipantPreference[]` | O | Back이 DB에서 조회한 해당 사용자의 현재 개인 선호. 없으면 `[]` |
| `participants[].preferences[].vocabularyCode` | `string` | O | 저장된 표준 Vocabulary 코드. `UNMAPPED`는 전달하지 않음 |
| `participants[].preferences[].sentiment` | `POSITIVE \| NEGATIVE` | O | 선호 방향 |
| `participants[].preferences[].strength` | `WEAK \| MODERATE \| STRONG` | O | 선호 강도 |
| `participants[].preferences[].rawValue` | `string` | O | 선호가 추출된 실제 사용자 표현 |

#### 과거 컨텍스트와 제외 입력

| 필드 | 타입 | 필수 | 의미 |
| --- | --- | --- | --- |
| `meetingMemory.summary` | `string` | X | 권장 필드. 같은 그룹의 과거 모임 대화·결정을 압축한 요약 |
| `excludedExternalPlaceIds[]` | `string` | X | 현재 generation에서 다시 추천하지 않을 장소 ID |

`meetingMemory`의 전체 JSON 스키마는 아직 확정되지 않았다. AI는 우선 `summary`가 있을 때만 사용하고, `{}`도 유효한 입력으로 받는다.

### Response `200 OK` — 후보 생성 성공

```json
{
  "requestId": "6e214a43-56a6-4b3b-a63c-14a1d3bb3c72",
  "status": "OK",
  "appliedDurationMinutes": 120,
  "summary": "전원이 가능한 저녁 시간 중 조용하게 대화하기 좋은 장소를 우선했어요.",
  "meetingTags": [
    { "code": "CONVERSATION_FOCUSED", "label": "대화 중심" },
    { "code": "QUIET", "label": "차분한" }
  ],
  "suggestions": [
    {
      "rank": 1,
      "category": "한식",
      "placeProvider": "KAKAO",
      "externalPlaceId": "12345678",
      "name": "건대 예시 한식당",
      "address": "서울 광진구 예시로 1",
      "latitude": 37.5401,
      "longitude": 127.0692,
      "externalUrl": "https://place.map.kakao.com/12345678",
      "proposedStartAt": "2026-08-30T19:00:00+09:00",
      "proposedEndAt": "2026-08-30T21:00:00+09:00",
      "businessHours": "매일 11:30~22:00",
      "businessHoursVerified": true,
      "openAtMeetingTime": true,
      "matchedPreferenceDomains": [
        "FOOD"
      ],
      "reasons": [
        "참여자들이 공통으로 가능한 날짜예요.",
        "그룹의 음식 선호와 조용한 식사 목적을 함께 고려했어요.",
        "제안 시간에 영업 중인 것으로 확인됐어요."
      ],
      "tags": [
        { "code": "HIGH_GROUP_FIT", "label": "그룹 선호와 적합도 높음" },
        { "code": "AVAILABLE_AT_MEETING_TIME", "label": "모임 시간에 이용 가능" }
      ],
      "sourceUrls": [
        "https://place.map.kakao.com/12345678"
      ],
      "checkedAt": "2026-08-20T03:11:00Z"
    }
  ],
  "actionRequired": null,
  "verificationTimedOut": false
}
```

#### 최상위 응답 필드

| 필드 | 타입 | nullable | 의미 |
| --- | --- | --- | --- |
| `requestId` | `UUID string` | X | 요청의 `requestId`를 그대로 반환 |
| `status` | `OK \| NO_COMMON_SLOT \| CONFLICT \| NO_CANDIDATE` | X | 후보 생성 결과 상태 |
| `appliedDurationMinutes` | `integer` | X | 후보 시각 계산에 실제 적용한 모임 길이. 입력이 `null`이면 120 |
| `summary` | `string` | X | 전체 제안 방향을 설명하는 그룹 수준 문장 |
| `meetingTags` | `Tag[]` | X | 참여자 선호를 종합한 "이번 자리의 성격" 배지. 4개 독립 축(무엇을 하는가/먹고 마시기/분위기/예산), 축마다 최대 1개. 근거 없으면 `[]` |
| `suggestions` | `Suggestion[]` | X | 순위순 후보. 최대 3개이며 없으면 `[]` |
| `actionRequired` | `ActionRequired \| null` | O | 사용자 판단이 필요할 때의 설명. `OK`이면 `null` |
| `verificationTimedOut` | `boolean` | X | 영업 검증 제한 시간 때문에 검증된 후보만 부분 반환했는지 여부 |

#### `suggestions[]`

| 필드 | 타입 | nullable | 의미 |
| --- | --- | --- | --- |
| `suggestions[].rank` | `integer` | X | 1부터 시작하는 추천 순위 |
| `suggestions[].category` | `string` | X | 장소 제공자가 반환한 장소 카테고리. Vocabulary domain과 다름 |
| `suggestions[].placeProvider` | `KAKAO` | X | `externalPlaceId`를 발급한 장소 제공자 |
| `suggestions[].externalPlaceId` | `string` | X | 외부 장소 제공자의 고유 ID |
| `suggestions[].name` | `string` | X | 매장 또는 장소 이름 |
| `suggestions[].address` | `string` | X | 도로명 또는 지번 주소 |
| `suggestions[].latitude` | `number` | X | 위도, 범위 `-90..90` |
| `suggestions[].longitude` | `number` | X | 경도, 범위 `-180..180` |
| `suggestions[].externalUrl` | `URI string \| null` | O | 장소 상세 페이지. 제공되지 않으면 `null` |
| `suggestions[].proposedStartAt` | `datetime` | X | 제안 모임 시작 시각 |
| `suggestions[].proposedEndAt` | `datetime` | X | 제안 모임 종료 시각 |
| `suggestions[].businessHours` | `string \| null` | O | 확인한 영업시간 표시 문자열. 확인하지 못하면 `null` |
| `suggestions[].businessHoursVerified` | `boolean` | X | 신뢰 가능한 출처에서 영업시간을 확인했는지 여부 |
| `suggestions[].openAtMeetingTime` | `boolean \| null` | O | 제안 시각 영업 확인 결과. 확인하지 못하면 `null` |
| `suggestions[].matchedPreferenceDomains` | `string[]` | X | 후보 선정에 실제로 기여한 `preference_vocabulary.domain` 목록 |
| `suggestions[].reasons` | `string[]` | X | 특정 개인을 지목하지 않는 그룹 수준 선정 사유 (문장) |
| `suggestions[].tags` | `Tag[]` | X | 이 장소를 추천한 이유 배지. 근거 없으면 `[]`. `AVAILABLE_AT_MEETING_TIME`은 LLM이 고르지 않고 `businessHoursVerified`/`openAtMeetingTime`에서 서버가 파생시킨다 (사실 판정이라 LLM이 고르면 확인 안 된 정보를 단정하게 됨) |
| `suggestions[].sourceUrls` | `URI string[]` | X | 영업 검증과 장소 정보의 근거 URL 목록 |

#### `Tag`

| 필드 | 타입 | nullable | 의미 |
| --- | --- | --- | --- |
| `code` | `string` | X | 고정된 값 목록 중 하나. LLM이 임의 문자열을 만들지 못하도록 응답 스키마에서 enum으로 제약 |
| `label` | `string` | X | 화면에 그대로 노출할 표시 문구. LLM이 아니라 서버가 code→label 매핑 테이블로 붙인다 (LLM이 문구까지 만들면 매번 표현이 흔들려 프론트가 매핑할 수 없음) |

`meetingTags` 값 목록 (4개 독립 축):

| 축 | code | label |
| --- | --- | --- |
| 무엇을 하는가 | `ACTIVE` | 활동형 |
| 무엇을 하는가 | `CONVERSATION_FOCUSED` | 대화 중심 |
| 먹고 마시기 (독립) | `MEAL_INCLUDED` | 식사 겸용 |
| 먹고 마시기 | `ALCOHOL_FRIENDLY` | 술 가능 |
| 먹고 마시기 | `NO_ALCOHOL` | 술 없이 |
| 분위기 | `LIVELY` | 왁자지껄 |
| 분위기 | `QUIET` | 차분한 |
| 예산 | `BUDGET_FRIENDLY` | 가성비 |

`suggestions[].tags` 값 목록 (예산 관련 태그 없음 — 장소 제공자 응답에 가격 정보가 없어 판단 근거 자체가 없기 때문):

| code | label | 생성 주체 |
| --- | --- | --- |
| `MATCHES_ACTIVITY` | 정한 활동에 적합 | LLM |
| `HIGH_GROUP_FIT` | 그룹 선호와 적합도 높음 | LLM |
| `GOOD_FOR_MEAL` | 식사하기 좋음 | LLM |
| `GOOD_FOR_DRINKS` | 술자리 적합 | LLM |
| `AVAILABLE_AT_MEETING_TIME` | 모임 시간에 이용 가능 | 서버(코드) |
| `suggestions[].checkedAt` | `datetime` | X | 외부 정보를 마지막으로 확인한 시각 |

AI 내부 결과에는 DB 저장 전이므로 `suggestionId`가 없다. Back이 검증·저장하면서 ID와 generation을 부여한다.

`matchedPreferenceDomains`는 장소 카테고리와 다른 값이다. 모델은 후보 판단에 사용한 `vocabularyCode`를 내부 structured output으로 반환하고, AI 서버가 해당 코드를 Vocabulary 캐시로 검증한 뒤 `domain`을 조회해 중복 제거한다. LLM이 domain 문자열을 직접 만들지 않는다. 여러 영역이 기여할 수 있으므로 단일 `domain`이 아닌 배열로 반환한다.

아래의 `NO_COMMON_SLOT`, `CONFLICT`, `NO_CANDIDATE` 예시는 각각 독립된 요청에서 나올 수 있는 도메인 결과 예시다.

### Response `200 OK` — 공통 가능 시간이 없음

```json
{
  "requestId": "6e214a43-56a6-4b3b-a63c-14a1d3bb3c72",
  "status": "NO_COMMON_SLOT",
  "appliedDurationMinutes": 120,
  "summary": "모든 참여자가 가능한 날짜를 찾지 못했어요.",
  "suggestions": [],
  "actionRequired": {
    "type": "NO_COMMON_SLOT",
    "message": "탐색 기간이나 참여자 가능 날짜를 조정해주세요."
  },
  "verificationTimedOut": false
}
```

### Response `200 OK` — 목적과 참여자 선호 충돌

```json
{
  "requestId": "6e214a43-56a6-4b3b-a63c-14a1d3bb3c72",
  "status": "CONFLICT",
  "appliedDurationMinutes": 120,
  "summary": "모임 목적과 참여자 선호가 충돌해 확인이 필요해요.",
  "suggestions": [],
  "actionRequired": {
    "type": "PREFERENCE_CONFLICT",
    "message": "주최자는 술자리를 원하지만 참여자 선호와 충돌합니다.",
    "hostRequest": "가볍게 술 한잔",
    "conflictingPreferenceCodes": [
      "ALCOHOL"
    ]
  },
  "verificationTimedOut": false
}
```

### Response `200 OK` — 유효한 장소 후보가 없음

```json
{
  "requestId": "6e214a43-56a6-4b3b-a63c-14a1d3bb3c72",
  "status": "NO_CANDIDATE",
  "appliedDurationMinutes": 120,
  "summary": "조건과 영업시간을 만족하는 장소를 찾지 못했어요.",
  "suggestions": [],
  "actionRequired": {
    "type": "NO_CANDIDATE",
    "message": "지역이나 모임 조건을 조정한 뒤 다시 요청해주세요."
  },
  "verificationTimedOut": false
}
```

`actionRequired`는 `type`에 따라 다음 두 형태 중 하나다.

시간 또는 장소 후보가 없는 경우:

| 필드 | 타입 | nullable | 의미 |
| --- | --- | --- | --- |
| `actionRequired.type` | `NO_COMMON_SLOT \| NO_CANDIDATE` | X | 필요한 사용자 개입의 종류 |
| `actionRequired.message` | `string` | X | 사용자에게 전달할 조정 안내 |

선호 충돌인 경우:

| 필드 | 타입 | nullable | 의미 |
| --- | --- | --- | --- |
| `actionRequired.type` | `PREFERENCE_CONFLICT` | X | 모임 목적과 선호 충돌 |
| `actionRequired.message` | `string` | X | 사용자에게 전달할 충돌 안내 |
| `actionRequired.hostRequest` | `string` | X | 충돌 판단의 기준이 된 `meeting.purpose` |
| `actionRequired.conflictingPreferenceCodes` | `string[]` | X | 충돌에 관련된 Vocabulary 코드 |

### 검증 및 처리 규칙

- `meetingId`, `meeting.id`, `participants[].userId`는 1 이상의 정수여야 한다.
- `meetingId`와 `meeting.id`는 같아야 한다.
- `contractVersion`은 지원 중인 버전이어야 한다.
- `requestId`는 유효한 UUID여야 하고 `timezone`은 유효한 IANA timezone이어야 한다.
- `meeting.purpose`는 1,000자 이하, `meeting.region`은 100자 이하여야 한다.
- `participants`에는 최소 1명이 있어야 하며 `userId`는 중복될 수 없다.
- 모든 `selectedDates`는 탐색 기간 안에 있어야 한다. AI는 중복 날짜를 제거하고 오름차순으로 정규화한다.
- 저장된 `vocabularyCode`는 실존 코드여야 하며 같은 사용자의 선호 목록에서 중복될 수 없다.
- `rawValue`는 255자를 넘을 수 없다.
- `scheduleSearchFrom`은 `scheduleSearchTo`보다 늦을 수 없다.
- `durationMinutes`가 있으면 양의 정수여야 한다. `null`이면 v2 기본값 120분을 사용한다.
- 적용할 길이는 `preferredTimeOfDay`의 v2 시각 범위보다 길 수 없다. 예를 들어 `LATE_AFTERNOON`의 최대 길이는 180분이다.
- `excludedExternalPlaceIds`는 중복될 수 없다.
- 후보 생성의 입력 우선순위는 확정 UI 값(`region`, 탐색 기간, 시간대, 길이, timezone) → 최종 `meeting.purpose` → 과거 `meetingMemory` 순서다. `excludedExternalPlaceIds`는 이 순위와 무관한 강제 제외 조건이다.
- **[미확정]** 백엔드 내부 DTO가 `selectedDates`를 AI에 전달하는 예시를 참고해 AI의 비-LLM 시간 계산 단계가 날짜 교집합을 구하는 안을 검토했으나, Back이 계산해서 `confirmedSlot`으로 넘겨주는 기존 안과 아직 확정되지 않았다 — 14장 확인 필요 사항 참고.
- 날짜만 제출하는 MVP에서는 `preferredTimeOfDay`, `durationMinutes`, `timezone`으로 구체 시각을 만든다.
- 각 suggestion은 시간과 장소가 결합된 하나의 후보이며 서로 다른 시간 또는 장소를 가질 수 있다.
- `status=OK`이면 후보는 1~3개다. 유효한 장소가 하나도 없으면 `NO_CANDIDATE`를 반환한다.
- `rank`는 1부터 끊김 없이 증가하고 배열 순서와 같아야 한다. `externalPlaceId`도 응답 안에서 중복될 수 없다.
- `proposedStartAt`의 날짜는 모든 참여자의 가능 날짜 교집합 안에 있어야 하며 `proposedEndAt`은 시작보다 늦어야 한다.
- `proposedEndAt - proposedStartAt`은 `appliedDurationMinutes`와 같아야 하고, 시작·종료가 선택한 `preferredTimeOfDay` 범위를 벗어날 수 없다.
- `matchedPreferenceDomains`는 요청에 포함된 실존 preference code에서 파생된 domain만 허용하며 중복을 제거한다.
- 장소명·주소·좌표·외부 ID·URL은 장소 제공자 결과에서 가져오며 LLM이 만들지 않는다. 영업 관련 boolean과 확인 시각은 검증 단계가 코드로 정하고, `summary`와 `reasons`만 모델이 그룹 수준 문장으로 작성한다.
- 각 suggestion에는 그룹 수준 `reasons`가 최소 1개 있어야 한다.
- 각 suggestion의 `sourceUrls`도 최소 1개여야 하며, 사용한 장소 정보 또는 영업 검증 출처만 포함한다.
- `FAIL`, 즉 제안 시각에 영업하지 않는다고 확인된 장소는 `suggestions`에 포함하지 않는다.
- 제안 시각 영업을 확인했으면 `businessHoursVerified=true`, `businessHours`는 non-null, `openAtMeetingTime=true`다.
- 확인을 시도했으나 결론을 내리지 못한 장소는 `businessHoursVerified=false`, `openAtMeetingTime=null`로 포함할 수 있다.
- 폐점이 확인된 장소는 반환하지 않으므로 정상 suggestion의 `openAtMeetingTime`은 `false`가 될 수 없다.
- `checkedAt`은 영업 정보 확인을 시도한 시각이다.
- `verificationTimedOut=true`이면 제한 시간 전에 검증을 완료했거나 UNKNOWN 판정을 받은 후보만 반환한다. 확인을 시작하지 못한 후보는 포함하지 않는다.
- 영업 검증이 시간 내 끝나지 않았어도 반환 가능한 후보가 1개 이상이면 `OK`, 1~3개 후보와 `verificationTimedOut=true`를 반환한다. 반환 가능한 후보가 하나도 없으면 부분 성공으로 보지 않고 `504 CANDIDATE_GENERATION_TIMEOUT`을 반환한다.
- `status`와 `actionRequired`의 조합은 고정된다: `OK`이면 `actionRequired=null`, 나머지 상태이면 `suggestions=[]`이고 상태에 맞는 action이 필수다.
- 추천 사유는 그룹 수준으로 표현하며 특정 참여자의 취향을 노출하지 않는다.
- `NO_COMMON_SLOT`, `CONFLICT`, `NO_CANDIDATE`는 시스템 장애가 아니므로 HTTP 오류가 아니라 `200`의 상태 응답이다.

### 오류

| HTTP | code | 상황 | retryable |
| --- | --- | --- | --- |
| `400` | `MEETING_ID_MISMATCH` | path와 body의 일정 ID가 다름 | `false` |
| `400` | `INVALID_DATE_RANGE` | 탐색 기간이 역전됨 | `false` |
| `400` | `INVALID_SELECTED_DATES` | 참여자 날짜가 탐색 범위를 벗어남 | `false` |
| `400` | `INVALID_DURATION_FOR_TIME_OF_DAY` | 모임 길이가 선택한 시간대 범위보다 김 | `false` |
| `400` | `UNSUPPORTED_CONTRACT_VERSION` | 지원하지 않는 내부 DTO 버전 | `false` |
| `400` | `INVALID_PLANNING_INPUT` | 참여자 중복 등 값의 의미나 필드 조합이 잘못됨 | `false` |
| `422` | `REQUEST_SCHEMA_INVALID` | 필수 필드 누락, 타입 또는 enum이 잘못됨 | `false` |
| `503` | `VOCABULARY_UNAVAILABLE` | 선호 코드 검증용 Vocabulary를 사용할 수 없음 | `true` |
| `503` | `MODEL_UNAVAILABLE` | LLM을 호출할 수 없음 | `true` |
| `502` | `MODEL_RESPONSE_INVALID` | 활동 결정·랭킹 결과가 스키마와 맞지 않음 | `true` |
| `502` | `PLACE_PROVIDER_ERROR` | 장소 검색 제공자 호출 실패 | `true` |
| `504` | `CANDIDATE_GENERATION_TIMEOUT` | 전체 후보 생성 제한 시간 초과 | `true` |

---

## 9. 재생성("뒤로가기") — 전용 API 없음

`POST /ai/meetings/{meetingId}/revise`는 목표 계약에서 제거했다.

### 왜 없앴는가

제품 흐름에서 "재생성"은 실제로는 "뒤로가기"다 — 화면상 새로운 재생성 전용 대화가 아니라, 사용자가 목적 대화 화면(러프 요구 5)으로 되돌아가 다시 대화하는 것으로 구현된다. `/revise`가 하려던 것(피드백을 멀티턴으로 정리, 한 문장 목적 갱신, 지역·날짜·시간 변경 감지)은 이미 있는 `/context/messages` + `/context`(7장)로 그대로 처리된다. 별도 엔드포인트, `currentDraftPurpose`/`currentSuggestions`/`uiChangeRequests` 같은 전용 스키마를 유지할 이유가 없다.

지역·날짜·시간 변경 감지(`uiChangeRequests`)도 함께 없앤다 — 뒤로가기는 애초에 그 화면들을 다시 지나가므로 UI 값은 사용자가 해당 화면에서 직접 바꾼다. AI가 자연어에서 변경 의도를 추론해 되물을 필요가 없다.

### 대체 흐름

1. Back이 "다시 시작" 진입점에서 사용자를 `/context/messages` 대화 화면으로 되돌린다(7.1장). 이전 대화를 이어가는지 새로 시작하는지는 Back의 UX 판단이다 — AI는 상태를 저장하지 않으므로 `history`를 무엇으로 채워 보내든 그대로 받는다.
2. 사용자가 다시 "최종 전송하기"를 누르면 `/context`(7.2장)로 새 `purpose`를 받는다.
3. Back이 `/candidates`(8장)를 다시 호출한다. 이때 `excludedExternalPlaceIds`에 지금까지 모든 generation에서 보여준 `externalPlaceId`를 누적해서 채운다 — 목록이 비어 있으면 예전과 동일하게 동작하고, 채워져 있으면 AI가 해당 장소를 후보에서 제외한다. 이 필드는 이미 8장에 있던 것으로, 재생성을 위해 새로 추가한 필드가 아니다.
4. 특정 장소 하나만 콕 집어 제외하는 대화형 협상(예: "1번 장소만 빼줘")은 지원하지 않는다 — 다시 시작하면 이전에 보여준 것 전체가 제외 대상이다. 세밀한 부분 재생성이 필요해지면 그때 다시 설계한다.

---

## 10. 공통 enum

### 10.1 `PreferredTimeOfDay`

| 값 | v2 시각 범위 | 의미 |
| --- | --- | --- |
| `DAYTIME` | `11:00 <= start`, `end <= 15:00` | 점심을 포함한 낮 시간대 |
| `LATE_AFTERNOON` | `15:00 <= start`, `end <= 18:00` | 늦은 오후 시간대 |
| `EVENING` | `18:00 <= start`, `end <= 23:00` | 저녁 시간대 |
| `ANY` | `11:00 <= start`, `end <= 23:00` | 특정 시간대 선호 없음 |

경계는 `meeting.timezone`의 현지 시각을 기준으로 한다. 여러 시작 시각이 가능하면 모임 목적, 영업시간과 전체 후보 순위를 함께 고려하고, 조건이 같으면 더 이른 날짜와 시각을 우선한다. 이 범위를 바꾸면 시간 산출 의미가 달라지므로 `contractVersion`을 올린다.

### 10.2 Preference enum

| 구분 | 값 | 의미 |
| --- | --- | --- |
| `sentiment` | `POSITIVE` | 좋아하거나 원하는 대상 |
| `sentiment` | `NEGATIVE` | 싫어하거나 피하려는 대상 |
| `strength` | `WEAK` | 약한 선호 |
| `strength` | `MODERATE` | 일반적인 선호 |
| `strength` | `STRONG` | 강한 선호 또는 강한 회피 |
| `mappingType` | `EXACT` | 사용자 표현과 코드가 직접 대응 |
| `mappingType` | `GENERALIZED` | 안전한 상위 코드로 일반화 |
| `mappingType` | `UNMAPPED` | 매핑할 코드가 없음 |

### 10.3 후보 생성 상태

| 값 | 의미 |
| --- | --- |
| `OK` | 후보를 정상 생성함 |
| `NO_COMMON_SLOT` | 모든 참여자가 가능한 날짜가 없음 |
| `CONFLICT` | 모임 목적과 참여자 선호가 충돌해 사용자 확인이 필요함 |
| `NO_CANDIDATE` | 공통 시간은 있지만 조건과 영업시간을 만족하는 장소가 없음 |

---

## 11. Back이 AI 응답을 사용하는 방법

이 절은 Back API를 새로 정의하는 것이 아니라 AI 입출력의 사용 목적만 설명한다.

### 11.1 개인 선호

1. Back이 로그인 사용자의 `messages`를 `/ai/preferences/extract`에 전달한다.
2. AI가 `reply`와 `extractedPreferences`를 반환한다.
3. Back이 Vocabulary와 enum을 검증한다.
4. `UNMAPPED`를 제외한 결과를 `(user_id, vocabulary_code)` 기준으로 UPSERT한다.
5. Back은 `UNMAPPED`를 제외한 항목만 같은 `extractedPreferences` 필드명으로 Front 응답 DTO에 담는다.

온보딩 성공 또는 건너뛰기 시 `users.onboarding_completed`를 변경하는 것은 Back의 화면 흐름 책임이며 AI 호출 계약에 포함하지 않는다.

### 11.2 모임 목적

1. 대화 턴마다 Back이 `meeting_chat_messages`에서 조회한 `history`와 새 `message`를 `/ai/meetings/{meetingId}/context/messages`에 전달한다.
2. AI가 대화형 `reply`만 반환한다. Back이 이번 턴의 사용자 발화와 AI 답변을 `meeting_chat_messages`에 순서대로 저장한다.
3. 사용자가 최종 전송하면 Back이 전체 `history`를 `/ai/meetings/{meetingId}/context`에 전달한다.
4. AI가 `reply`와 정리된 한 문장 `purpose`를 반환한다.
5. AI 응답 검증에 성공하면 `purpose`를 `meetings.purpose`에 저장한다.

### 11.3 제안 생성

1. Back이 DB에서 일정, 참여자, 개인 선호, 선택 날짜와 과거 모임 요약을 조립한다.
2. Back의 worker가 `/ai/meetings/{meetingId}/candidates`를 호출한다.
3. AI가 시간+장소 후보를 최대 3개 또는 사용자 결정이 필요한 도메인 상태를 반환한다.
4. `OK`이면 Back이 외부 장소 ID, 좌표, URL, 날짜·시간과 enum을 검증한다.
5. 검증에 성공한 `OK` 후보에 suggestion ID와 generation을 부여해 저장한다.

### 11.4 재생성("뒤로가기")

전용 API 없이 11.2·11.3을 그대로 반복한다 (9장 참고).

1. Back이 사용자를 목적 대화 화면으로 되돌려 `/context/messages`를 다시 호출한다 (11.2와 동일한 흐름).
2. 사용자가 다시 최종 전송하면 `/context`로 새 `purpose`를 받아 `meetings.purpose`를 갱신한다.
3. Back이 `/candidates`를 다시 호출하면서, 지금까지 모든 generation에서 보여준 `externalPlaceId`를 누적한 목록을 `excludedExternalPlaceIds`에 채운다.
4. `OK` 결과의 검증·저장까지 성공하면 새 활성 generation을 커밋한다. 오류나 사용자 결정 필요 상태이면 기존 값과 활성 generation을 유지한다.

---

## 12. 백엔드 예시와의 정렬 결과

| 항목 | 채택한 결론 |
| --- | --- |
| 선호 입력 | 백엔드 예시와 동일하게 `messages: string[]` 사용 |
| 사용자 응답 필드 | `assistantReply` 대신 백엔드 예시와 같은 `reply` 사용 |
| 선호 표시 정보 | `displayName`, `domain`을 AI 응답에도 포함. LLM이 아니라 캐시 조회로 생성 |
| 선호 배열명 | 의미 차이가 없으므로 백엔드 예시와 같은 `extractedPreferences`로 통일 |
| 잘못된 선호 입력 | Back↔AI는 `422 REQUEST_SCHEMA_INVALID`, Back은 이를 Front 계약의 `400 INVALID_CHAT_MESSAGES`로 변환 |
| 모임 목적 | 백엔드가 필요로 하는 정제된 `purpose`와 `reply`를 AI가 반환 |
| 목적 누적 입력 | `currentPurpose` 누적 방식 대신 채팅 UI에 맞춰 `/context/messages`(턴별) + `/context`(최종 전체 `history` 요약) 2단계로 분리 (7장 참고). Back의 Front 응답에는 path에서 아는 `meetingId`와 Back이 만든 `updatedAt`을 추가 |
| 비동기 처리 | run·polling은 Back 책임, AI 호출은 동기 |
| 제안 필드 | 백엔드 예시 필드를 우선하고 러프 요구의 실제 `businessHours`, `matchedPreferenceDomains`를 보완 |
| 제안 ID | AI는 반환하지 않고 Back이 저장하면서 생성 |
| 재생성 | 백엔드 예시의 단일 `202 regenerate`나 별도 `/revise` 대신, 제품 흐름의 "뒤로가기"에 맞춰 `/context/messages`+`/context`+`/candidates`를 재사용. 전용 재생성 API·스키마 없음 (9장) |
| 재생성 시 이전 후보 제외 | 새 필드를 추가하지 않고 `/candidates`에 이미 있던 `excludedExternalPlaceIds`를 그대로 사용. Back이 지금까지의 모든 generation에서 보여준 `externalPlaceId`를 누적해 채움 |
| 시간 교집합 | **미확정.** 백엔드 내부 DTO의 `selectedDates` 전달 형태를 참고해 AI의 비-LLM 단계가 계산하는 안을 검토했으나, 기존 `service-proposal.md`의 Back 계산안과 아직 확정되지 않음 — 14장 참고 |
| 후보 태그 | 기존 구현의 `meetingTags`, `suggestions[].tags`를 목표 계약에도 유지. `reasons`(문장)와 `tags`(배지)는 서로 대체가 아니라 병행 |
| 과거 모임 기억 | 백엔드 예시의 확장 가능한 `{}` 형태를 유지하되 AI는 우선 선택 필드 `summary`만 사용 |
| 캘린더 등록 | 백엔드 예시를 우선해 Back 책임으로 두고 AI API 범위에서 제외. 이는 `ai-part-proposal.md`의 L9 AI 오케스트레이션 그림과 다름 |

---

## 13. 현재 구현과 목표 계약의 차이

이 문서의 모든 항목이 현재 코드에 구현됐다는 뜻은 아니다. 코드는 사용자 확인 후 별도 작업으로 변경한다.

| API | 현재 구현 | 목표 계약과의 차이 |
| --- | --- | --- |
| 공통 | 내부 인증 없음. FastAPI 기본 422와 일부 `AIServiceError`만 사용 | 공통 인증과 `{code,message,retryable,requestId}` 오류 envelope 구현 필요 |
| `GET /health` | 구현됨 | 목표와 일치 |
| `GET /internal/preference-vocabulary` client | 첫 사용 시 조회 후 무기한 캐시 | 캐시 갱신과 빈 목록·중복 코드·부모 참조 검증 필요 |
| `POST /ai/preferences/extract` | `messages`, `reply`, `preferences`, `displayName`, `domain` 구현 | 응답 배열을 `extractedPreferences`로 변경하고 `reply` non-null, 공통 오류, 중복 코드와 `UNMAPPED` 조합 검증 보강 필요 |
| `POST /ai/meetings/{meetingId}/context/messages`, `POST /ai/meetings/{meetingId}/context` | 구현됨. 7.1/7.2 계약대로 `history`+`message` → `reply` (메시지), `history` → `reply`+`purpose` (최종) | 목표와 일치. `uiInputs`/`meetingContext`/`conflictsWithUi`는 폐기하고 대화 요약 하나로 대체했다 |
| `POST /ai/meetings/{meetingId}/candidates` | 이미 확정된 `confirmedSlot`과 현재 중첩형 후보 스키마를 사용. `meetingTags`, `candidates[].tags`는 이미 구현됨 | 참여자 날짜 교집합(**미확정 — 14장 참고**), 새 내부 DTO와 flat suggestion 응답으로 변경 검토. 복수 `sourceUrls`, 확인 시각, 좌표, 실제 영업시간, domain 보완 필요. 태그는 유지하되 필드명을 `candidates`→`suggestions`에 맞춰 옮기는 정도만 필요. `excluded` 디버그 필드는 목표 응답에서 제거 검토 중 |
| 후보 영업 검증 | 시작 날짜에 영업하는지만 판단 | `proposedStartAt..EndAt` 실제 시각에 영업하는지 검증해야 함 |
| `POST /ai/meetings/{meetingId}/revise` | 단일 `feedback`을 받아 라우팅만 수행하는 코드가 아직 남아있음 | **목표 계약에서 엔드포인트 자체를 제거.** 재생성은 `/context/messages`+`/context`+`/candidates` 재사용으로 대체 (9장). 코드 삭제는 사용자 확인 후 진행 |

특히 현재 후보 검증은 날짜만 확인하면서 `AVAILABLE_AT_MEETING_TIME` 의미를 사용하므로, 코드 변경 시 실제 제안 시각 기준 검증으로 바로잡아야 한다.

---

## 14. 확인 필요 사항

API의 큰 경계와 필드는 정의할 수 있지만 다음 정책은 팀 합의가 필요하다.

1. **Back↔AI 인증 방식**: 공유 Bearer token과 mTLS 중 무엇을 사용할지.
1-1. **시간 교집합(L3) 계산 주체**: AI의 비-LLM 단계가 참여자 날짜 교집합을 계산하는 안을 검토했으나, 확정된 게 아니다. Back이 계산해서 `confirmedSlot`으로 넘겨주는 기존 안과 아직 결론 나지 않았고 추후 다시 논의한다. 이 문서의 `participants[].selectedDates` 입력과 "AI가 계산" 서술은 검토안이지 확정이 아니다.
2. **날짜보다 세밀한 가능 시간**: MVP는 `selectedDates`만 받지만, 사용자별 시간 단위 가능 여부가 필요하면 `availableSlots[{startAt,endAt}]` 계약을 추가해야 한다.
3. **Meeting Memory 생성 주체와 갱신 시점**: 이 문서는 AI 입력을 최소한의 `summary`로 정했지만 언제 요약하고 갱신할지는 미정이다.
4. **Vocabulary 캐시 갱신**: TTL, Back 변경 알림 또는 수동 refresh 중 어떤 방식을 쓸지.
5. **후보 생성 timeout과 재시도 횟수**: Back worker와 AI 서버의 제한 시간을 함께 정해야 한다.
6. **사용자 결정 필요 결과의 Back 상태 매핑**: AI의 `NO_COMMON_SLOT`, `CONFLICT`, `NO_CANDIDATE`를 Back의 run·meeting 상태와 Front 화면에 어떻게 연결할지 Back 계약에서 정해야 한다.
7. **자연어 입력 상한**: `messages`, `meetingMemory`의 최대 개수와 글자 수는 모델 비용·timeout 기준을 정한 뒤 확정해야 한다.
8. **가능 날짜 데이터 원천**: `selectedDates`를 어느 Back 저장소 또는 Calendar 결과에서 조립할지와 시간 단위 `availableSlots` 확장 여부는 아직 미정이다.
9. **재생성 시 `excludedExternalPlaceIds` 누적 저장소**: Back이 "지금까지 모든 generation에서 보여준 `externalPlaceId`"를 어디에 쌓아둘지는 AI 계약과 무관한 Back 내부 설계다 — AI는 상태를 저장하지 않으므로 Back이 매 `/candidates` 호출마다 완성된 목록을 보내주기만 하면 된다. `db_schema.md`의 "아직 구현되지 않은 테이블" 목록에 있는 `meeting_suggestions`가 이 역할을 할 것으로 보이지만 스키마가 아직 공유되지 않았다. 같은 목록의 `revision_requests`는 `/revise` 제거로 더 이상 필요 없을 가능성이 높다 — db_schema.md 쪽에서 확인 필요.

---

## 15. 명세에서 의도적으로 제외한 것

- Front가 호출하는 `/api/**` 전체 명세
- 회원가입·로그인·그룹·초대·일정 CRUD API
- 참여자 날짜 제출 API
- Back의 agent run polling API
- Back의 제안 저장·조회·확정 API
- Back의 DB 테이블 상세 설계와 migration
- Google Calendar 연결·등록 API
- 실제 장소 예약 API

이 기능들은 AI API의 호출 전후에 필요하지만 Back의 구현 분야이므로 이 문서에서는 계약 대상으로 확장하지 않는다.
