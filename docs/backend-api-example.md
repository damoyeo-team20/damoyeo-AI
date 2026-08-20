# Backend API Example (참고용)

> 백엔드에서 제안한 AI API 형식 예시입니다. **최종 기준은 [api-design2-backend.md](api-design2-backend.md)**이며,
> 이 문서는 백엔드가 어떤 형태를 기대하는지 비교·참고하는 용도로만 둡니다.

## 9. AI 연동 예정 API 계약

이 절의 API는 아직 구현되지 않은 예정 계약이다. 프론트는 아래 HTTP 계약만
사용하고, 백엔드 내부에서 사용하는 AI 모델·프롬프트·응답 형식은 노출하지 않는다.

AI 호출 결과는 신뢰하지 않고 백엔드에서 JSON 스키마 검증, vocabulary 검증,
날짜·시간 범위 검증, 장소 필드 검증을 통과한 데이터만 DB에 저장한다.

### 개인 선호 채팅

```
POST /api/users/me/preferences/chat
```

```json
{
  "messages": ["매운 음식 좋아해", "조용한 분위기가 좋아"]
}
```

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

- 로그인한 본인의 선호만 변경할 수 있다.
- 추출 결과는 `(user_id, vocabulary_code)` 기준 UPSERT한다.
- `UNMAPPED` 결과는 디버깅 목적으로만 보관하고 일반 선호 목록에는 노출하지 않는다.
- 빈 `messages`는 `400 INVALID_CHAT_MESSAGES`다.
- AI 응답 파싱 또는 검증 실패는 `502 AI_RESPONSE_INVALID`다.

### 모임 목적 채팅

```
POST /api/meetings/{meetingId}/context-chat
```

```json
{
  "messages": ["오랜만에 만나서 저녁 먹고 이야기하려고요"]
}
```

```json
{
  "reply": "오랜만의 편안한 저녁 자리로 이해했어요.",
  "purpose": "오랜만에 만나 대화하는 저녁 식사",
  "meetingId": 20,
  "updatedAt": "2026-08-19T07:15:00Z"
}
```

- `DRAFT` 상태에서 일정 생성자만 호출할 수 있다.
- 사용자와 AI의 원문은 `meeting_chat_messages`에 순서대로 저장한다.
- 정제된 목적은 `meetings.purpose`에 저장한다.
- 압축 장기기억은 백엔드 내부에서 `meeting_memories`에 갱신한다.
- 프론트는 원문·메모리 저장 방식을 알 필요가 없다.

### AI 조율 실행

```
POST /api/meetings/{meetingId}/plan
Idempotency-Key: {UUID}
```

Request Body 없음. 예정 계약에서는 비동기 작업을 만들고 `202 Accepted`를 반환한다.

```json
{
  "runId": 101,
  "meetingId": 20,
  "status": "QUEUED",
  "createdAt": "2026-08-19T08:10:00Z"
}
```

- `READY_TO_PLAN` 상태에서 일정 생성자만 호출할 수 있다.
- 동일 `Idempotency-Key` 재요청은 같은 `runId`를 반환해 중복 AI 호출을 막는다.
- 실행 생성과 동시에 일정 상태는 `PLANNING`으로 바뀐다.
- 현재 구현은 임시로 동기 `200 MeetingResponse`를 반환하므로 AI 연동 시 위 계약으로 변경한다.

### AI 조율 진행 상태 조회

```
GET /api/meetings/{meetingId}/agent-runs/{runId}
```

```json
{
  "runId": 101,
  "meetingId": 20,
  "status": "RUNNING",
  "currentStep": "SEARCHING_PLACES",
  "steps": [
    { "code": "CALCULATING_OVERLAP", "status": "COMPLETED" },
    { "code": "SUMMARIZING_PREFERENCES", "status": "COMPLETED" },
    { "code": "DETERMINING_PLACE_TYPE", "status": "COMPLETED" },
    { "code": "SEARCHING_PLACES", "status": "RUNNING" },
    { "code": "VERIFYING_BUSINESS_INFO", "status": "PENDING" }
  ],
  "error": null,
  "createdAt": "2026-08-19T08:10:00Z",
  "updatedAt": "2026-08-19T08:10:05Z"
}
```

```
AgentRunStatus: QUEUED | RUNNING | SUCCEEDED | FAILED
AgentRunStepStatus: PENDING | RUNNING | COMPLETED | FAILED
```

- MVP는 1~2초 간격 polling을 사용한다.
- 성공하면 일정 상태는 `PROPOSING`, 실패하면 `FAILED`로 전환한다.
- 실패 응답의 `error`는 `{ "code", "message", "retryable" }` 형태다.
- SSE는 polling으로 성능 문제가 확인될 때 추가한다.

### 제안 목록 조회

```
GET /api/meetings/{meetingId}/suggestions
```

```json
{
  "meetingId": 20,
  "status": "PROPOSING",
  "summary": "대화하기 좋은 저녁 식사 장소를 우선했어요.",
  "suggestions": [
    {
      "id": 501,
      "rank": 1,
      "category": "음식점",
      "name": "건대 예시 식당",
      "address": "서울 광진구 예시로 1",
      "latitude": 37.5401,
      "longitude": 127.0692,
      "externalUrl": "<https://place.map.kakao.com/12345>",
      "proposedStartAt": "2026-08-30T19:00:00+09:00",
      "proposedEndAt": "2026-08-30T21:00:00+09:00",
      "businessHoursVerified": true,
      "openAtMeetingTime": true,
      "reasons": ["그룹 선호 적합", "모임 시간 이용 가능"],
      "sourceUrls": ["<https://example.com/place>"],
      "checkedAt": "2026-08-19T08:11:00Z"
    }
  ]
}
```

- 일정이 `PROPOSING`일 때 그룹 멤버가 조회할 수 있다.
- 확인되지 않은 영업 정보는 `null` 또는 `false`로 반환하고 추측해 채우지 않는다.
- 개인별 선호는 노출하지 않고 그룹 단위 추천 이유만 반환한다.
- 외부 장소 ID, 출처 URL, 확인 시각을 저장해 재검증할 수 있어야 한다.

### 제안 재생성

```
POST /api/meetings/{meetingId}/suggestions/regenerate
Idempotency-Key: {UUID}
```

```json
{
  "messages": ["조금 더 조용하고 가격이 낮은 곳으로 찾아줘"]
}
```

Response `202 Accepted`:

```json
{
  "runId": 102,
  "meetingId": 20,
  "status": "QUEUED",
  "createdAt": "2026-08-19T08:20:00Z"
}
```

- `PROPOSING` 상태에서 일정 생성자만 호출할 수 있다.
- 사유 원문은 별도의 재생성 요청 이력에 저장한다.
- 기존 제안을 덮어쓰지 않고 세대(generation)를 구분해 보존한다.
- 일정 상태는 다시 `PLANNING`으로 변경한다.

### 제안 확정

```
POST /api/meetings/{meetingId}/suggestions/{suggestionId}/confirm
Idempotency-Key: {UUID}
```

Request Body 없음.

```json
{
  "meetingId": 20,
  "suggestionId": 501,
  "status": "CONFIRMED",
  "confirmedStartAt": "2026-08-30T19:00:00+09:00",
  "confirmedEndAt": "2026-08-30T21:00:00+09:00",
  "place": {
    "name": "건대 예시 식당",
    "address": "서울 광진구 예시로 1",
    "externalUrl": "<https://place.map.kakao.com/12345>"
  }
}
```

- `PROPOSING` 상태에서 일정 생성자만 호출할 수 있다.
- 해당 일정의 현재 generation에 속한 제안만 확정할 수 있다.
- 확정과 `meetings` 상태·일시 갱신은 하나의 DB 트랜잭션으로 처리한다.
- Calendar 등록은 확정 트랜잭션과 분리하고 참여자별 성공·실패를 별도로 기록한다.

### 백엔드에서 AI 서비스로 전달할 내부 계약

프론트는 이 JSON을 만들거나 전달하지 않는다. 백엔드가 DB 데이터를 읽어 AI 호출용
DTO로 조립한다. 모델 변경에 대비해 `contractVersion`을 포함한다.

```json
{
  "contractVersion": "1.0",
  "requestId": "6e214a43-56a6-4b3b-a63c-14a1d3bb3c72",
  "meeting": {
    "id": 20,
    "purpose": "오랜만에 만나 대화하는 저녁 식사",
    "region": "건대",
    "scheduleSearchFrom": "2026-08-23",
    "scheduleSearchTo": "2026-09-07",
    "preferredTimeOfDay": "EVENING",
    "timezone": "Asia/Seoul"
  },
  "participants": [
    {
      "userId": 1,
      "selectedDates": ["2026-08-30"],
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
  "revisionMessages": []
}
```

백엔드는 AI 응답을 그대로 프론트에 전달하지 않는다. 내부 응답을 검증하고 정규화한
뒤 `meeting_suggestions` 등에 저장하고, 프론트에는 위의 제안 목록 계약만 반환한다.
