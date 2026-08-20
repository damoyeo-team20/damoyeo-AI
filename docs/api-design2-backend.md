# 다모여 Back ↔ AI API 명세

> 백엔드 공유용 축약본
>
> 모든 AI API는 동기 JSON API다. 비동기 run, polling, DB 저장과 generation 관리는 Back이 담당한다.

## 1. 공통

### 엔드포인트

| Method | Path | 호출 주체 | 기능 | 구현 상태 |
| --- | --- | --- | --- | --- |
| `GET` | `/health` | Back/운영 인프라 | AI 서버 생존 확인 | ✅ 구현됨 |
| `GET` | `/internal/preference-vocabulary` | AI → Back | 선호 Vocabulary 조회 | ✅ 구현됨 (캐시 갱신 정책만 미정) |
| `POST` | `/ai/preferences/extract` | Back → AI | 개인 선호 추출 및 답변 생성 | ✅ 구현됨 |
| `POST` | `/ai/meetings/{meetingId}/context/messages` | Back → AI | 모임 목적 채팅 한 턴 | ✅ 구현됨 |
| `POST` | `/ai/meetings/{meetingId}/context` | Back → AI | 모임 목적 채팅 최종 전송 시 한 문장 요약 | ✅ 구현됨 |
| `POST` | `/ai/meetings/{meetingId}/candidates` | Back worker → AI | 시간·장소 후보 생성 | 🔴 미구현 — 목표 계약. 날짜 교집합 계산 주체도 미확정 |

전용 재생성(`/revise`) API는 없다. "재생성"은 제품 흐름상 "뒤로가기"로 단순화됐다 — Back이 `/context/messages`로 되돌아가 다시 대화하고 `/context`로 재요약한 뒤 `/candidates`를 다시 호출한다. 이전에 보여준 장소는 `/candidates`의 `excludedExternalPlaceIds`에 누적해서 채운다(6장 참고). 현재 코드에는 단일 `feedback` 기반 `/revise`가 아직 남아있으며, 삭제는 사용자 확인 후 진행한다.

🔴로 표시한 항목은 이 문서의 계약대로 지금 당장 연동하면 실패한다. 상세 격차는 [`api-design2.md`](api-design2.md) 13장 참고.

### 기본 규칙

- `Content-Type: application/json`
- 필드명은 `camelCase`를 사용한다.
- ID는 JSON `integer`, 날짜는 `YYYY-MM-DD`, 시각은 UTC offset이 포함된 ISO 8601을 사용한다.
- 정의되지 않은 필드는 거부한다. 단, `meetingMemory`는 확장 가능한 JSON object다.
- 배열 값이 없으면 `null`이 아니라 `[]`를 보낸다.
- `messages`에는 이번 요청에서 새로 제출한 문장만 넣는다.
- 모든 path의 `meetingId`는 1 이상의 정수다.
- 표의 `필수=O`는 key 필수, `nullable=O`는 key는 필수지만 값으로 `null`을 허용한다는 뜻이다.
- 내부 인증 방식은 별도 합의 후 `/ai/**`와 `/internal/**`에 공통 적용한다.

### 공통 오류 형식

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

`requestId`가 없는 API의 오류에서는 `error.requestId`가 `null`이다.

| HTTP | 의미 |
| --- | --- |
| `400` | 값 또는 필드 조합 오류 |
| `401` | 내부 인증 실패 |
| `422` | 필드 누락, 타입·enum·길이 또는 요청 유효성 오류 |
| `500` | AI 서비스 내부 오류 |
| `502` | LLM 또는 장소 제공자의 잘못된 응답 |
| `503` | 필수 의존성에 연결할 수 없음 |
| `504` | 전체 처리 제한 시간 초과 |

---

## 2. `GET /health`

AI 프로세스의 생존 여부를 확인한다. Request body는 없다.

### Response `200`

```json
{
  "status": "ok"
}
```

`status`는 고정값 `ok`다. LLM, Kakao, Vocabulary 상태까지 확인하는 readiness API는 아니다.

---

## 3. `GET /internal/preference-vocabulary`

Back이 제공하고 AI가 호출한다. Request body는 없다.

### Response `200`

```json
{
  "vocabulary": [
    {
      "code": "SEAFOOD",
      "domain": "FOOD",
      "displayName": "해산물",
      "parentCode": null
    }
  ]
}
```

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `vocabulary` | `VocabularyEntry[]` | O | 전체 Vocabulary. 최소 1개 |
| `vocabulary[].code` | `string` | O | 고유 표준 코드, 최대 100자 |
| `vocabulary[].domain` | `string` | O | 선호 영역, 최대 50자 |
| `vocabulary[].displayName` | `string` | O | 화면 표시 이름, 최대 100자 |
| `vocabulary[].parentCode` | `string \| null` | O | 상위 코드. 최상위면 `null` |

`code`는 중복될 수 없고, non-null `parentCode`는 같은 응답 안에 존재해야 한다.

---

## 4. `POST /ai/preferences/extract`

온보딩과 프로필에서 공통으로 사용한다. AI가 선호와 사용자용 답변을 함께 반환하고, Back이 로그인 사용자 기준으로 저장 또는 UPSERT한다.

### Request

```json
{
  "messages": [
    "매운 음식 좋아하고 시끄러운 곳은 싫어해"
  ]
}
```

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `messages` | `string[]` | O | 이번 제출의 자연어 문장. 공백이 아닌 문장 최소 1개 |

### Response `200`

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

| 필드 | 타입 | nullable | 설명 |
| --- | --- | --- | --- |
| `reply` | `string` | X | 사용자에게 표시할 답변 |
| `extractedPreferences` | `ExtractedPreference[]` | X | 추출된 선호. 없으면 `[]` |
| `[].vocabularyCode` | `string \| null` | O | Vocabulary 코드. `UNMAPPED`일 때만 `null` |
| `[].displayName` | `string \| null` | O | Vocabulary 표시 이름 |
| `[].domain` | `string \| null` | O | Vocabulary domain |
| `[].rawValue` | `string` | X | 사용자가 언급한 표현, 최대 255자 |
| `[].sentiment` | `POSITIVE \| NEGATIVE` | X | 긍정·부정 선호 |
| `[].strength` | `WEAK \| MODERATE \| STRONG` | X | 선호 강도 |
| `[].mappingType` | `EXACT \| GENERALIZED \| UNMAPPED` | X | Vocabulary 매핑 방식 |

규칙:

- `displayName`과 `domain`은 `vocabularyCode`로 Vocabulary에서 조회한 값이다.
- `UNMAPPED`이면 `vocabularyCode`, `displayName`, `domain`이 모두 `null`이다.
- non-null `vocabularyCode`, `displayName`, `domain`은 각각 100자, 100자, 50자 이하다.
- 한 응답에서 같은 non-null `vocabularyCode`를 중복 반환하지 않는다.
- Back은 `UNMAPPED`를 일반 선호 DB와 Front 응답에서 제외한다.
- Back은 non-null 결과를 `(user_id, vocabulary_code)` 기준으로 UPSERT한다.

| HTTP | code | 발생 조건 | retryable |
| --- | --- | --- | --- |
| `422` | `REQUEST_SCHEMA_INVALID` | `messages` 누락·타입 오류 또는 유효한 문장이 없음 | `false` |
| `503` | `VOCABULARY_UNAVAILABLE` | Vocabulary 조회·파싱 실패 | `true` |
| `503` | `MODEL_UNAVAILABLE` | LLM 호출 불가 | `true` |
| `502` | `MODEL_RESPONSE_INVALID` | 모델 결과가 응답 스키마와 불일치 | `true` |

---

## 5. 모임 목적 채팅 (2단계)

새 모임의 목적 대화를 채팅 형태로 주고받는다. 턴마다 요약하지 않고, 최종 전송 시 전체 대화를 한 번에 한 문장으로 정리한다 — 매 턴 요약하면 LLM 호출이 낭비되고, 요약의 요약이 반복되면서 원래 뉘앙스가 깎이기 때문이다.

AI는 상태를 저장하지 않는다 (LLM 호출 자체가 매번 독립적이라 이전 턴을 기억하지 못한다). Back이 `meeting_chat_messages`에서 해당 `meetingId`의 대화 원문을 조회해 매번 `history`로 통째로 실어 보내야 한다. 어떤 대화가 이 일정에 속하는지 필터링하는 건 전적으로 Back의 책임이며 AI 요청 스키마에는 `meetingId` 외의 필터 필드가 없다.

### 5.1 `POST /ai/meetings/{meetingId}/context/messages` — 채팅 한 턴

### Request

```json
{
  "history": [
    { "role": "USER", "content": "오랜만에 만나서 저녁 먹고 이야기하려고요" },
    { "role": "ASSISTANT", "content": "편안한 저녁 자리로 준비할게요. 원하시는 분위기가 있을까요?" }
  ],
  "message": "너무 시끄러운 곳은 피하고 싶어요"
}
```

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `history` | `ChatTurn[]` | O | 이전까지의 대화 전체. 첫 턴이면 `[]` |
| `history[].role` | `USER \| ASSISTANT` | O | `meeting_chat_messages.role`과 동일 |
| `history[].content` | `string` | O | 해당 턴의 원문 |
| `message` | `string` | O | 이번 턴의 새 사용자 발화. 공백만 있으면 안 됨 |

### Response `200`

```json
{ "reply": "네, 조용한 곳으로 찾아볼게요. 더 말씀해주실 조건이 있을까요?" }
```

| 필드 | 타입 | nullable | 설명 |
| --- | --- | --- | --- |
| `reply` | `string` | X | 사용자에게 표시할 대화형 답변 |

이 단계에서는 `purpose`를 만들지 않는다. Back은 이번 턴의 `message`와 응답 `reply`를 각각 `USER`/`ASSISTANT` 행으로 `meeting_chat_messages`에 저장한다.

| HTTP | code | 발생 조건 | retryable |
| --- | --- | --- | --- |
| `422` | `REQUEST_SCHEMA_INVALID` | 필드 누락·타입 오류 또는 `message`가 공백뿐임 | `false` |
| `503` | `MODEL_UNAVAILABLE` | LLM 호출 불가 | `true` |
| `502` | `MODEL_RESPONSE_INVALID` | 모델 결과가 응답 스키마와 불일치 | `true` |

### 5.2 `POST /ai/meetings/{meetingId}/context` — 최종 전송

사용자가 "최종 전송하기"를 누르면 그동안의 대화 전체를 한 번에 요약한다.

### Request

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

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `history` | `ChatTurn[]` | O | 5.1에서 오간 대화 전체 (마지막 턴까지 포함). `USER` 발화가 최소 1개 있어야 함 |

### Response `200`

```json
{
  "reply": "편안하게 대화할 수 있는 조용한 저녁 모임으로 정리했어요.",
  "purpose": "오랜만에 만나 조용한 곳에서 대화하는 저녁 식사"
}
```

| 필드 | 타입 | nullable | 설명 |
| --- | --- | --- | --- |
| `reply` | `string` | X | 요약 완료를 알리는 답변 |
| `purpose` | `string` | X | 저장용 한 문장, 최대 1,000자 |

지역·날짜·시간대는 이 API에서 변경하지 않는다. Back은 응답 검증 후 `purpose`를 `meetings.purpose`에 저장한다. `currentPurpose` 같은 누적 상태 필드는 없다 — 매번 전체 원문을 보고 한 번에 요약하기 때문이다.

| HTTP | code | 발생 조건 | retryable |
| --- | --- | --- | --- |
| `422` | `REQUEST_SCHEMA_INVALID` | 필드 누락·타입 오류 또는 `USER` 발화가 하나도 없음 | `false` |
| `503` | `MODEL_UNAVAILABLE` | LLM 호출 불가 | `true` |
| `502` | `MODEL_RESPONSE_INVALID` | 모델 결과가 응답 스키마와 불일치 | `true` |

---

## 6. `POST /ai/meetings/{meetingId}/candidates`

Back worker가 일정·참여자·개인 선호·과거 모임 요약을 전달하면 AI가 시간과 장소가 결합된 후보를 최대 3개 반환한다.

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
        "2026-08-30"
      ],
      "preferences": [
        {
          "vocabularyCode": "SPICY_FOOD",
          "sentiment": "POSITIVE",
          "strength": "MODERATE",
          "rawValue": "매운 음식"
        }
      ]
    }
  ],
  "meetingMemory": {},
  "excludedExternalPlaceIds": []
}
```

### Request fields

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `contractVersion` | `string` | O | 현재 `1.0` |
| `requestId` | `UUID string` | O | 요청 추적 ID |
| `meeting.id` | `integer` | O | path의 `meetingId`와 동일해야 함 |
| `meeting.purpose` | `string` | O | `meetings.purpose`의 현재 목적. 재생성이면 `/context/messages`+`/context`로 다시 얻은 새 목적, 최대 1,000자 |
| `meeting.region` | `string` | O | 장소 검색 지역, 최대 100자 |
| `meeting.scheduleSearchFrom` | `date` | O | 탐색 시작일 |
| `meeting.scheduleSearchTo` | `date` | O | 탐색 종료일 |
| `meeting.preferredTimeOfDay` | `PreferredTimeOfDay` | O | 선호 시간대 |
| `meeting.durationMinutes` | `integer \| null` | O | 모임 길이. `null`이면 120분 |
| `meeting.timezone` | `IANA timezone` | O | MVP 기본 `Asia/Seoul` |
| `participants` | `Participant[]` | O | 최소 1명 |
| `participants[].userId` | `integer` | O | 참여자 ID |
| `participants[].selectedDates` | `date[]` | O | 참여 가능 날짜 |
| `participants[].preferences` | `Preference[]` | O | 저장된 개인 선호. 없으면 `[]` |
| `participants[].preferences[].vocabularyCode` | `string` | O | 실존 Vocabulary 코드 |
| `participants[].preferences[].sentiment` | `POSITIVE \| NEGATIVE` | O | 선호 방향 |
| `participants[].preferences[].strength` | `WEAK \| MODERATE \| STRONG` | O | 선호 강도 |
| `participants[].preferences[].rawValue` | `string` | O | 원래 표현 |
| `meetingMemory` | `object \| null` | O | 과거 모임 요약. 없으면 `null`; `summary` 사용 가능 |
| `meetingMemory.summary` | `string` | X | 선택 필드. 같은 그룹의 과거 모임 요약 |
| `excludedExternalPlaceIds` | `string[]` | O | 이미 보여준 외부 장소 ID 전체. 최초 생성이면 `[]`이고, 재생성("뒤로가기" 후 다시 생성)이면 지금까지 모든 generation에서 보여준 ID를 누적해서 채운다 |

### Response `200` — 성공

```json
{
  "requestId": "6e214a43-56a6-4b3b-a63c-14a1d3bb3c72",
  "status": "OK",
  "appliedDurationMinutes": 120,
  "summary": "전원이 가능한 저녁 시간 중 대화하기 좋은 장소를 우선했어요.",
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
        "그룹의 선호와 대화 중심 목적을 함께 고려했어요."
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

### Response fields

| 필드 | 타입 | nullable | 설명 |
| --- | --- | --- | --- |
| `requestId` | `UUID string` | X | 요청 ID echo |
| `status` | `CandidateStatus` | X | 생성 결과 |
| `appliedDurationMinutes` | `integer` | X | 실제 적용한 모임 길이 |
| `summary` | `string` | X | 전체 제안 설명 |
| `meetingTags` | `Tag[]` | X | 참여자 선호를 종합한 "이번 자리의 성격" 배지. 근거가 없으면 `[]` |
| `suggestions` | `Suggestion[]` | X | 순위순 후보, 최대 3개 |
| `actionRequired` | `ActionRequired \| null` | O | 사용자 결정이 필요할 때의 정보 |
| `verificationTimedOut` | `boolean` | X | 영업 검증 부분 timeout 여부 |
| `suggestions[].rank` | `integer` | X | 1부터 시작하는 순위 |
| `suggestions[].category` | `string` | X | 장소 제공자 카테고리 |
| `suggestions[].placeProvider` | `KAKAO` | X | 장소 제공자 |
| `suggestions[].externalPlaceId` | `string` | X | 외부 장소 ID |
| `suggestions[].name` | `string` | X | 장소 이름 |
| `suggestions[].address` | `string` | X | 주소 |
| `suggestions[].latitude` | `number` | X | 위도 `-90..90` |
| `suggestions[].longitude` | `number` | X | 경도 `-180..180` |
| `suggestions[].externalUrl` | `URI \| null` | O | 장소 상세 URL |
| `suggestions[].proposedStartAt` | `datetime` | X | 제안 시작 시각 |
| `suggestions[].proposedEndAt` | `datetime` | X | 제안 종료 시각 |
| `suggestions[].businessHours` | `string \| null` | O | 표시용 영업시간 |
| `suggestions[].businessHoursVerified` | `boolean` | X | 영업시간 확인 여부 |
| `suggestions[].openAtMeetingTime` | `boolean \| null` | O | 제안 시각 영업 여부. 미확인이면 `null` |
| `suggestions[].matchedPreferenceDomains` | `string[]` | X | 선정에 기여한 Vocabulary domain |
| `suggestions[].reasons` | `string[]` | X | 그룹 수준 선정 사유 (문장) |
| `suggestions[].tags` | `Tag[]` | X | 이 장소를 추천한 이유 배지. 근거가 없으면 `[]`. `AVAILABLE_AT_MEETING_TIME`은 LLM이 고르지 않고 `businessHoursVerified`/`openAtMeetingTime`에서 서버가 파생시킨다 |
| `suggestions[].sourceUrls` | `URI[]` | X | 장소·영업 정보 출처 |
| `suggestions[].checkedAt` | `datetime` | X | 외부 정보 확인 시각 |

### `Tag`

| 필드 | 타입 | nullable | 설명 |
| --- | --- | --- | --- |
| `code` | `string` | X | 고정된 값 목록 중 하나. 프론트가 이모지·색상 등 스타일 분기에 사용 |
| `label` | `string` | X | 화면에 그대로 노출할 표시 문구. Back/Front는 매핑 테이블 없이 그대로 렌더링 |

모든 태그는 `{code, label}` 쌍으로 내려간다. 값은 고정 목록으로 제한되며(LLM이 임의 문자열을 만들지 못하도록 응답 스키마에서 제약), 해당하는 태그가 없으면 빈 배열이 정상이다 — 억지로 채우지 않는다.

`meetingTags`는 4개의 독립된 축으로 구성되며 같은 축에서는 최대 1개만 선택된다.

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

`suggestions[].tags`의 값 목록. 예산 관련 태그는 없다 — 장소 제공자 응답에 가격 정보가 없어 판단 근거 자체가 없기 때문이다.

| code | label | 생성 주체 |
| --- | --- | --- |
| `MATCHES_ACTIVITY` | 정한 활동에 적합 | LLM |
| `HIGH_GROUP_FIT` | 그룹 선호와 적합도 높음 | LLM |
| `GOOD_FOR_MEAL` | 식사하기 좋음 | LLM |
| `GOOD_FOR_DRINKS` | 술자리 적합 | LLM |
| `AVAILABLE_AT_MEETING_TIME` | 모임 시간에 이용 가능 | 서버(코드) |

### CandidateStatus

| `status` | `suggestions` | `actionRequired` |
| --- | --- | --- |
| `OK` | 1~3개 | `null` |
| `NO_COMMON_SLOT` | `[]` | `{type: "NO_COMMON_SLOT", message}` |
| `NO_CANDIDATE` | `[]` | `{type: "NO_CANDIDATE", message}` |
| `CONFLICT` | `[]` | `{type: "PREFERENCE_CONFLICT", message, hostRequest, conflictingPreferenceCodes}` |

| `actionRequired` 필드 | 타입 | 조건 |
| --- | --- | --- |
| `type` | `NO_COMMON_SLOT \| NO_CANDIDATE \| PREFERENCE_CONFLICT` | 항상 필수 |
| `message` | `string` | 항상 필수 |
| `hostRequest` | `string` | `PREFERENCE_CONFLICT`일 때 필수 |
| `conflictingPreferenceCodes` | `string[]` | `PREFERENCE_CONFLICT`일 때 필수 |

필수 규칙:

- `scheduleSearchFrom <= scheduleSearchTo`
- `selectedDates`는 탐색 기간 안에 있어야 하며 사용자별 ID와 선호 코드는 중복될 수 없다.
- `durationMinutes`는 non-null이면 양의 정수이고 선택 시간대 범위보다 짧거나 같아야 한다.
- `participants[].preferences[].rawValue`는 255자 이하다.
- `excludedExternalPlaceIds`는 중복될 수 없다.
- **[미확정]** AI의 코드 로직이 참여자 날짜 교집합과 구체 시각을 계산하는 안을 검토 중이나, Back이 계산해서 `confirmedSlot`으로 넘겨주는 기존 안과 아직 확정되지 않았다 — 추후 논의.
- `durationMinutes=null`이면 `appliedDurationMinutes=120`이다.
- `rank`는 1부터 끊김 없이 증가하고 장소 ID는 중복될 수 없다.
- 제안 날짜는 참여자 가능 날짜 교집합 안에 있어야 하며, 종료-시작 길이는 `appliedDurationMinutes`와 같고 선택 시간대 범위 안에 있어야 한다.
- 각 후보의 `reasons`와 `sourceUrls`는 최소 1개다.
- 확인 결과 폐점인 장소는 반환하지 않는다.
- 영업 확인 완료 시 `businessHoursVerified=true`, `businessHours!=null`, `openAtMeetingTime=true`다.
- 영업 확인 불가 시 `businessHoursVerified=false`, `openAtMeetingTime=null`일 수 있다.
- `matchedPreferenceDomains`는 요청의 Vocabulary code에서 파생된 값이다.
- timeout 후 후보가 1개 이상이면 `OK`와 `verificationTimedOut=true`, 하나도 없으면 `504`를 반환한다.
- `NO_COMMON_SLOT`, `NO_CANDIDATE`, `CONFLICT`는 시스템 오류가 아니므로 HTTP `200`으로 반환한다.

| HTTP | code | 발생 조건 | retryable |
| --- | --- | --- | --- |
| `400` | `MEETING_ID_MISMATCH` | path와 body의 일정 ID가 다름 | `false` |
| `400` | `INVALID_DATE_RANGE` | 탐색 기간이 역전됨 | `false` |
| `400` | `INVALID_SELECTED_DATES` | 참여자 날짜가 탐색 범위를 벗어남 | `false` |
| `400` | `INVALID_DURATION_FOR_TIME_OF_DAY` | 모임 길이가 선택 시간대보다 김 | `false` |
| `400` | `UNSUPPORTED_CONTRACT_VERSION` | 지원하지 않는 DTO 버전 | `false` |
| `400` | `INVALID_PLANNING_INPUT` | 참여자 중복 등 필드 조합 오류 | `false` |
| `422` | `REQUEST_SCHEMA_INVALID` | 필드 누락 또는 타입·enum 오류 | `false` |
| `503` | `VOCABULARY_UNAVAILABLE` | 선호 코드 검증용 Vocabulary 사용 불가 | `true` |
| `503` | `MODEL_UNAVAILABLE` | LLM 호출 불가 | `true` |
| `502` | `MODEL_RESPONSE_INVALID` | 모델 결과가 응답 스키마와 불일치 | `true` |
| `502` | `PLACE_PROVIDER_ERROR` | 장소 제공자 호출 실패 | `true` |
| `504` | `CANDIDATE_GENERATION_TIMEOUT` | 전체 후보 생성 제한 시간 초과 | `true` |

### PreferredTimeOfDay

| 값 | 현지 시각 범위 |
| --- | --- |
| `DAYTIME` | `11:00 <= start`, `end <= 15:00` |
| `LATE_AFTERNOON` | `15:00 <= start`, `end <= 18:00` |
| `EVENING` | `18:00 <= start`, `end <= 23:00` |
| `ANY` | `11:00 <= start`, `end <= 23:00` |

적용 모임 길이는 선택한 시간대 범위보다 길 수 없다.

---

## 7. 재생성("뒤로가기") — 전용 API 없음

`POST /ai/meetings/{meetingId}/revise`는 목표 계약에서 제거했다. "재생성"은 제품 흐름상 전용 화면이 아니라 목적 대화 화면(5장)으로의 "뒤로가기"로 구현되므로, 별도 엔드포인트나 `currentDraftPurpose`/`currentSuggestions`/`uiChangeRequests` 같은 전용 스키마가 필요 없다.

대체 흐름:

1. Back이 사용자를 `/context/messages` 대화 화면으로 되돌린다 (5.1장).
2. 사용자가 다시 "최종 전송하기"를 누르면 `/context`로 새 `purpose`를 받는다 (5.2장).
3. Back이 `/candidates`를 다시 호출한다. 이때 지금까지 모든 generation에서 보여준 `externalPlaceId`를 누적해 `excludedExternalPlaceIds`에 채운다(6장) — 목록이 비어 있으면 예전과 동일하게 동작하고, 채워져 있으면 해당 장소를 제외한다. 새로 추가한 필드가 아니라 6장에 이미 있던 필드다.
4. 특정 장소 하나만 콕 집어 제외하는 대화형 협상은 지원하지 않는다 — 다시 시작하면 이전에 보여준 것 전체가 제외 대상이다.

현재 코드에는 단일 `feedback` 기반 `/revise`가 아직 남아있다. 삭제는 사용자 확인 후 진행한다.
