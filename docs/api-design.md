# 다모여 AI API 설계

> 기준 문서: [ai-part-proposal.md](ai-part-proposal.md) (AI 파트 기획서, 최종 계약 포함)
> 이 문서는 기획서를 근거로 실제 구현(`app/schemas/`, `app/api/routes/`)과 1:1로 맞춰 정리한 것이다.
> 기획서 자체가 아직 열어둔 사항(12장 오픈 이슈)은 이 문서에서도 미정으로 남겨둔다.

## 공통 규칙

- Base path: `/ai`
- Back → AI 단방향 호출. 응답은 Back이 가공 없이 그대로 Front에 전달(passthrough)하므로, **AI가 반환하는 필드명·구조가 곧 Front가 받는 형태**라는 전제로 설계한다.
- 모든 LLM 호출은 **structured output(JSON Schema)** 으로 강제한다. 프롬프트 지시만으로 JSON 형식을 기대하지 않는다.
- 인증: Back-AI 간 내부 통신이므로 서비스 간 공유 시크릿(`Authorization: Bearer <internal-token>` 또는 mTLS)을 가정. **미정 — 클라우드 담당자와 확정 필요.**
- 에러 응답 공통 포맷 ([app/schemas/common.py](../app/schemas/common.py)):
  ```json
  {
    "error": {
      "code": "STRING_ENUM",
      "message": "사람이 읽을 수 있는 설명"
    }
  }
  ```
- `strength`는 **`LOW` / `MEDIUM` / `HIGH` 3단계**다 (기획서 12장 오픈 이슈 #2 — 한 차례 연속값안을 채택했다가 2026-08-19 팀 논의로 3단계안으로 재확정). AI는 3단계 값을 그대로 반환하며, 수치 변환이 필요하면 Back이 담당한다.

---

## 0. (내부 보조) `GET /internal/preference-vocabulary`

Back이 호스팅, AI가 기동 시 1회 호출해 인메모리 캐싱한다 ([app/services/vocabulary_client.py](../app/services/vocabulary_client.py)).

```json
// Response (Back → AI)
{
  "vocabulary": [
    { "code": "SEAFOOD", "domain": "FOOD", "attribute": "CATEGORY", "parentCode": null },
    { "code": "SHELLFISH", "domain": "FOOD", "attribute": "CATEGORY", "parentCode": "SEAFOOD" },
    { "code": "PORK", "domain": "FOOD", "attribute": "INGREDIENT", "parentCode": "MEAT" }
  ]
}
```

AI 서버는 이 목록으로 매칭 후보(leaf + 상위 카테고리)를 구성해 LLM structured output의 `enum` 제약(Literal)에 사용한다. TTL/갱신 트리거는 미정 — 현재는 기동 시 1회 캐싱.

---

## 1. `POST /ai/preferences/extract`

자연어 발화 → Vocabulary 매핑된 구조화 선호 추출 (N1). 온보딩 1회 + 이후 선호 추가/수정 시 호출.

### Request

```json
{
  "userId": "string",
  "message": "해산물은 완전 싫어하는데 조개는 진짜 좋아해. 아 근데 어제 야구 봤어?",
  "conversationId": "string | null"
}
```

### Response `200`

```json
{
  "preferences": [
    { "vocabularyCode": "SEAFOOD", "rawValue": "해산물", "sentiment": "NEGATIVE", "strength": "HIGH", "mappingType": "EXACT" },
    { "vocabularyCode": "SHELLFISH", "rawValue": "조개", "sentiment": "POSITIVE", "strength": "HIGH", "mappingType": "EXACT" }
  ],
  "assistantReply": "야구 재미있으셨겠어요! 어떤 음식 좋아하시는지 더 이야기해 볼까요?"
}
```

- `mappingType`은 `EXACT` / `GENERALIZED` / **`UNMAPPED`** 세 가지다. `UNMAPPED`는 "선호로 보이는데 대응 code가 없는" 경우로, `vocabularyCode: null` + 원문 `rawValue`를 그대로 담아 **preferences 배열에 포함**한다 (저장 여부는 Back이 결정).
- 선호 발화가 아예 아닌 순수 잡담("어제 야구 봤어?")은 preferences에 넣지 않고 `assistantReply`로만 응답한다. `UNMAPPED`(선호이지만 매핑 실패)와 "잡담"(애초에 선호가 아님)은 서로 다른 케이스로 구분해서 처리한다.
- `vocabularyCode`가 non-null이면 항상 Vocabulary 실존 코드. 새 코드를 임의 생성하지 않는다(구조화 출력의 `Literal` 제약으로 강제).
- 저장 키 `(userId, vocabularyCode)`의 **UPSERT**는 Back의 책임. AI는 발화 기준 추출 결과만 반환한다.

### 에러

| code | 상황 |
| --- | --- |
| `VOCABULARY_UNAVAILABLE` | `/internal/preference-vocabulary` 조회 실패 |

---

## 2. `POST /ai/meetings/{meetingId}/context`

주최자의 자연어 요청 해석 (N2). **지역·시간은 UI 입력이 항상 우선**하며 LLM이 지역을 추론하지 않는다.

### Request

```json
{
  "hostMessage": "이번엔 팀원들이랑 캐주얼하게 술 한잔 하고 싶어요. 견과류 알레르기 있는 사람 있어서 그건 빼주세요.",
  "uiInputs": {
    "region": "강남역",
    "dateRange": { "start": "2026-08-24", "end": "2026-08-28" },
    "timeRange": { "start": "18:00", "end": "22:00" }
  }
}
```

### Response `200`

```json
{
  "meetingContext": {
    "activityHints": ["술자리"],
    "meetingTone": "캐주얼",
    "explicitConstraints": ["견과류 알레르기 있는 사람이 있어서 그건 빼주세요"]
  },
  "conflictsWithUi": []
}
```

**자연어와 UI 입력이 불일치하는 경우** (발화 "홍대" vs UI region "강남역"):

```json
{
  "meetingContext": { "activityHints": ["술자리"], "meetingTone": "캐주얼", "explicitConstraints": [] },
  "conflictsWithUi": [
    {
      "field": "region",
      "uiValue": "강남역",
      "mentionedValue": "홍대",
      "question": "지역을 강남역으로 설정하셨는데, 홍대를 말씀하신 것 같아요. 어느 쪽으로 진행할까요?"
    }
  ]
}
```

- `activityHints`: 활동 유형 힌트. `meetingTone`: 모임 분위기. `explicitConstraints`: 주최자가 명시한 조건(알레르기, 예산 등) 목록 — 이 세 필드가 기획서 5장의 `{meeting_tone, activity_hints[], explicit_constraints[]}`에 대응한다.
- `conflictsWithUi`가 비어있지 않으면 Back/Front는 주최자에게 되물어야 한다. AI는 임의로 UI 값을 덮어쓰지 않는다.

---

## 3. `POST /ai/meetings/{meetingId}/candidates`

활동 결정(N4) + 장소 검색(L5, Kakao) + 영업 검증(N6, 웹검색) + 랭킹(N7)을 LangGraph 파이프라인 하나로 처리.

### Request

```json
{
  "confirmedSlot": { "date": "2026-08-25", "startTime": "18:00", "endTime": "21:00" },
  "region": "강남역",
  "meetingContext": { "activityHints": ["술자리"], "meetingTone": "CASUAL" },
  "participantPreferences": [
    { "userId": "u1", "vocabularyCode": "MEAT", "sentiment": "POSITIVE", "strength": 0.7 },
    { "userId": "u2", "vocabularyCode": "SEAFOOD", "sentiment": "NEGATIVE", "strength": 0.6 }
  ],
  "blockedDomains": ["PC_ROOM"]
}
```

- `participantPreferences`는 Back이 요청 본문에 포함해 주는 형태로 설계했다 (기획서: "Back이 요청에 포함해서 주거나, AI가 Back의 조회용 API를 호출한다" — 어느 쪽인지는 여전히 미확정).
- `blockedDomains`: 호불호가 크게 갈리는 장소 유형(PC방 등)은 참여자/주최자가 명시적으로 언급하기 전엔 후보로 고려하지 않는다.

### Response `200` — 정상

```json
{
  "status": "OK",
  "candidates": [
    {
      "activity": "이자카야",
      "place": { "kakaoPlaceId": "12345678", "name": "산다라 강남점", "address": "서울 강남구 ...", "category": "일식주점" },
      "verification": {
        "status": "PASS",
        "evidence": "네이버 플레이스 기준 매일 17시~02시 영업",
        "source": "naver place",
        "confidence": 0.9
      },
      "rationale": "참여자 다수가 선호하는 술자리 분위기에 잘 어울리는 장소입니다."
    }
  ],
  "excluded": [
    { "activity": "해산물 전문점", "reason": "참여자 중 해산물에 대한 부정적 선호가 있어 배제했습니다." },
    { "activity": "PC방", "reason": "blockedDomains에 포함되어 배제했습니다." }
  ],
  "verificationTimedOut": false
}
```

- 추천 사유(`rationale`)는 항상 **집단 수준 표현**만 사용한다 ("참여자 선호와 높은 적합도" O, "A가 술을 좋아해서" X).
- `verification.status`는 `PASS` / `FAIL` / `UNKNOWN` 3-state.
  - `FAIL`인 후보는 `candidates` 배열에서 **아예 제외**한다.
  - `UNKNOWN`은 후보에 **포함**하되 표시만 한다. `PASS`/`FAIL`로 임의로 단정하지 않는다.
  - `evidence`/`source`/`confidence`는 판정 근거 투명성을 위해 추가된 필드다 (기획서 5장 N6 출력 `{verdict, evidence, source, confidence}`에 대응. 필드명은 `verdict` 대신 다른 3-state 필드와 통일해 `status`로 유지).
- `excluded`: N4가 고려했지만 최종적으로 선택하지 않은 활동 유형과 사유. 기획서 5장 N4 출력의 `excluded[]`에 대응 — 디버깅·시연 투명성 목적.
- `verificationTimedOut: true`면 전체 타임아웃으로 일부 후보만 검증 완료된 상태로 반환됐다는 뜻.

### Response `200` — 충돌

```json
{
  "status": "CONFLICT",
  "conflict": {
    "reason": "주최자는 술자리를 원하지만, 참여자 다수가 음주를 선호하지 않습니다.",
    "hostRequest": "가볍게 술 한잔",
    "conflictingPreferences": ["ALCOHOL"]
  },
  "candidates": [],
  "excluded": []
}
```

### 에러

| code | 상황 |
| --- | --- |
| `KAKAO_API_KEY_MISSING` | `KAKAO_REST_API_KEY` 미설정 |
| `KAKAO_API_ERROR` | Kakao Local API 호출 실패 |

---

## 4. `POST /ai/meetings/{meetingId}/revise`

재탐색 피드백을 어느 단계부터 재실행할지 라우팅 (N8). **LLM은 라우팅 판단만 하고, 실제 재실행은 오케스트레이터/Back의 책임**이다.

### Request

```json
{
  "feedback": "다 좋은데 좀 더 조용한 곳으로 바꿔줄 수 있어? 1층이었으면 좋겠어.",
  "currentCandidates": [ /* 직전 candidates 응답 재전달, 또는 meetingId로 서버가 조회 */ ]
}
```

### Response `200`

```json
{
  "rerouteTo": "PLACE",
  "addedConstraints": ["조용한 분위기 선호", "1층 매장 선호"],
  "message": "조용하고 1층에 있는 장소로 다시 찾아드릴게요!"
}
```

- `rerouteTo` 값: `TIME` (시간대 재조율) / `ACTIVITY` (활동부터 재검토, `/candidates` 재호출) / `PLACE` (활동은 유지, 장소만 재검토).
- `addedConstraints`는 **이번 피드백에서 새로 생긴 제약만** 담는다 — 기획서의 `MeetingState.revision_history[]`(N8 누적 제약)에 이어 붙이는 구조를 전제로 한다. 다만 이 누적 상태를 요청 사이 어디에 보관할지는 **기획서 12장 오픈 이슈 #8에서도 미정으로 남아있다** (예: LangGraph checkpointer를 `meetingId` 기준으로 사용하는 방안 제안됨 — 아직 미구현). 현재 구현은 매 호출을 독립적으로 처리하고, 누적은 Back이 담당한다고 가정한다.
- `TIME` 케이스의 Back-Front 재조율 흐름도 기획서에서 미정으로 명시되어 있다.

---

## 아직 열려 있는 사항 (ai-part-proposal.md 12장과 동일)

1. Back-AI 간 인증 방식 (공유 시크릿/mTLS 등) — 미정.
2. `candidates` 요청 시 `participantPreferences`를 Back이 바디에 포함하는지, AI가 별도 조회를 하는지 — 미정.
3. **L3(시간 교집합) 계산 주체**: AI 파이프라인 노드인지 Back이 계산해서 넘겨주는지 — 미정. 이 저장소는 계산이 끝난 `confirmedSlot`을 받는 것으로 가정하고 L3를 구현하지 않았다.
4. **자동 예약 방식**: Google Calendar 등록(L9)까지만인지, 실제 예약까지 시도하는지 — 미정. L9도 이 저장소의 구현 대상이 아니다(Back이 직접 처리).
5. **N8 재탐색 상태의 영속화 위치**: `revision_history`를 어디에 어떻게 누적할지 — 미정.
6. `UNMAPPED` Preference의 장기 저장 여부 — Back이 결정할 사항, AI는 관여하지 않음.
7. 모임별 개인 선호를 별도로 저장할지 — "구현해보고 결정"으로 남아있음.
