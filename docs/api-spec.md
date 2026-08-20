# API 명세서

> ⚠️ **지난 작업 기록. 현재 계약의 기준이 아니다.**
> 이 문서로 화면 단위 검토를 마쳤고 결론은 전부 [`api-design2-backend.md`](api-design2-backend.md)에 반영됐다.
> 지금 구현·연동의 기준은 그 문서이며, 여기와 내용이 다르면 그 문서가 맞다.
> 이 문서는 "왜 그렇게 결정했는지"의 근거를 되짚을 때만 본다.

프로토타입 화면을 하나씩 보면서, 그 화면이 실제로 필요로 하는 요청/응답 필드를 정확히 확정해나가는 문서다.

- **`api-design.md`와의 관계**: `api-design.md`는 파이프라인(N1~N9) 노드 단위로 설계된 기존 명세다. 이 문서는 반대로 **화면 단위**로 시작해서, 화면이 실제로 뭘 주고받아야 하는지 먼저 정하고 기존 명세와 대조한다. 화면 검토가 끝나면 확정된 내용을 `api-design.md`에 반영해 하나로 합친다.
- **`backend-api-example.md`와의 관계**: 백엔드가 제안한 Front↔Back 계약 초안이다. 여기 나온 Back↔AI 내부 계약(맨 아래 "AI 서비스로 전달할 내부 계약")은 모임 조율 흐름만 다루고, 온보딩 같은 다른 화면의 Back↔AI 계약은 없다. 이 문서에서 화면별로 그 빈자리를 채운다.
- 각 절의 결정 사항 중 "확인 필요"로 표시한 건 코드에 아직 반영 안 한 제안이다.

---

## 화면 1. 온보딩 — 개인 선호 채팅 API를 이용한 초기 선호 수집

가입 후 처음 뜨는 화면. 미리 준비된 문장 중 해당하는 것을 여러 개 고르거나, 하단 입력창에 자유롭게 입력해서 제출(`↑`)한다. "건너뛰기"로 생략할 수도 있다.

### 대응 엔드포인트

새 엔드포인트를 만들지 않고 기존 `POST /ai/preferences/extract`를 그대로 쓴다. 이 화면이 필요로 하는 기능("자연어 → Vocabulary 매핑된 구조화 선호")과 정확히 일치하기 때문이다.

### 화면 → 요청 필드 매핑

| 화면 요소 | 처리 |
| --- | --- |
| 프리셋 문장 여러 개 선택 (예: "나는 활동적인 거 좋아해", "해산물은 별로 안 좋아해") | 선택된 문장들을 각각 원문 그대로 `messages` 배열의 원소로 담는다 |
| 하단 자유 입력 | 선택한 문장이 있으면 배열 맨 뒤에 원소 하나 추가, 없으면 단독 원소로 `messages`에 포함 |
| `↑` 제출 | `POST /ai/preferences/extract` 호출 |
| "건너뛰기" | **AI를 호출하지 않는다.** Back이 `users.onboarding_completed = true`만 처리 |

문장을 합치는 건 Back이 아니라 **AI 쪽 책임**이다 — 라우트 진입부에서 `messages`를 마침표로 조인해 기존 파이프라인(단일 문자열 계약)에 그대로 넣는다. Back은 배열을 원문 그대로 보내기만 하면 된다. 프리셋 문장도 이미 완결된 자연어라 N1이 복합 문장에서 여러 선호를 나눠 뽑는 것과 동일하게 처리된다 — 이건 실제로 검증됐다 ("해산물은 완전 싫어하는데 조개는 진짜 좋아해"에서 두 개를 정확히 분리해낸 테스트, 그리고 백엔드 예시("매운 음식 좋아해", "조용한 분위기가 좋아")를 그대로 실제 Gemini에 넣어 두 선호가 정확히 나뉘어 나온 것까지 확인).

여기서 `messages`는 **전체 대화 이력이 아니라 이번 제출에서 선택하거나 직접 입력한 문장 목록**이다. 과거 입력을 매번 다시 보내면 이전 선호와 최신 선호가 한 응답 안에서 충돌하거나 중복 추출될 수 있으므로 포함하지 않는다.

### Request

```json
{
  "messages": ["나는 활동적인 거 좋아해", "해산물은 별로 안 좋아해", "술 마시는 것도 좋아"]
}
```

`messages`는 최소 1개 이상이어야 하고, 공백뿐인 원소만 있으면 거부한다 (`messages`에 공백이 아닌 문장이 하나 이상 있어야 함).

### Response

```json
{
  "extractedPreferences": [
    {
      "vocabularyCode": "ACTIVE_MEETUP",
      "displayName": "활동적인 모임",
      "domain": "ACTIVITY",
      "rawValue": "활동적인 거",
      "sentiment": "POSITIVE",
      "strength": "MODERATE",
      "mappingType": "EXACT"
    },
    {
      "vocabularyCode": "SEAFOOD",
      "displayName": "해산물",
      "domain": "FOOD",
      "rawValue": "해산물",
      "sentiment": "NEGATIVE",
      "strength": "MODERATE",
      "mappingType": "EXACT"
    },
    {
      "vocabularyCode": "ALCOHOL",
      "displayName": "술",
      "domain": "FOOD",
      "rawValue": "술",
      "sentiment": "POSITIVE",
      "strength": "MODERATE",
      "mappingType": "EXACT"
    }
  ],
  "reply": "말씀해주신 내용을 선호에 반영했어요."
}
```

`displayName`과 `domain`은 LLM이 생성하지 않는다. AI 서버가 이미 캐시한 Vocabulary에서 `vocabularyCode`로 조회해 붙인다. `UNMAPPED`는 조회할 코드가 없으므로 `vocabularyCode`, `displayName`, `domain`이 모두 `null`이다.

### 에러 및 계층별 책임

백엔드 예시의 에러 코드는 Front↔Back 계약이다.

| 구간 | HTTP / code | 상황 |
| --- | --- | --- |
| Front↔Back | `400 INVALID_CHAT_MESSAGES` | `messages`가 비었거나 유효한 문장이 없음 |
| Front↔Back | `502 AI_RESPONSE_INVALID` | AI 응답 파싱 또는 Vocabulary 검증 실패 |
| Back↔AI | `422` FastAPI validation error | `messages` 누락, 빈 배열 또는 공백뿐인 배열 |
| Back↔AI | `503 VOCABULARY_UNAVAILABLE` | Vocabulary 조회 실패 |

LLM 호출 또는 structured output 파싱 실패에 대한 Back↔AI 공통 에러 코드는 아직 없다. 이 경우 어떤 코드로 표준화할지는 **확인 필요**이며, Back은 최종적으로 Front에 `502 AI_RESPONSE_INVALID`를 반환한다.

### 백엔드 초안과 다른 점

**1.** ~~`messages: string[]` vs `message: string`~~ → **반영 완료.** `PreferenceExtractRequest.messages: list[str]`로 변경했다 (`min_length=1`, 공백뿐인 배열 거부). 조인은 라우트 핸들러에서 처리하고 그래프/노드는 기존 단일 문자열 계약 그대로 둔다. 백엔드 예시 payload(`["매운 음식 좋아해", "조용한 분위기가 좋아"]`)를 실제로 넣어 두 선호가 정확히 분리되는 것까지 확인했다.

**2.** ~~응답에 `displayName`, `domain`이 없다~~ → **반영 완료.** AI 서버가 캐시된 Vocabulary에서 `vocabularyCode`로 조회해 두 값을 붙인다. LLM 출력 항목에는 추가하지 않았으므로 토큰 비용이나 새 환각 위험은 없다.

**3.** ~~필드명 `reply` vs `assistantReply`~~ → **`reply`로 통일 완료.** 의미가 같은 필드에 굳이 다른 이름을 쓰지 않고 백엔드 예시와 맞췄다 — Back이 가공 없이 그대로 Front에 전달(passthrough)하는 구조라 이름이 다르면 그대로 Front까지 노출되기 때문이다.

**3-1.** ~~선호 배열명 `preferences` vs `extractedPreferences`~~ → **`extractedPreferences`로 통일 완료** (`ExtractedPreference` 응답 모델에 반영). Back↔AI와 Front↔Back 양쪽 모두 같은 이름을 쓴다.

**4.** ~~`reply`가 잡담이 섞였을 때만 채워진다~~ → **반영 완료.** 처음엔 "스몰톡 핸들러를 잡담 없어도 돌리자"로 접근했는데, 다시 보니 완료 통보와 스몰톡 반응은 생성 경로가 달라야 했다.

- 백엔드의 `reply`("말씀해주신 내용을 선호에 반영했어요.")는 대화 유지 목적이 아니라 **처리 완료 통보**다. 잡담에 반응하지도, 다음 발화를 유도하지도 않는다.
- 우리 스몰톡 핸들러는 잡담 내용에 실제로 반응하고 Vocabulary 실제 항목으로 다음 발화를 유도하는, 훨씬 무거운 별개 기능이다.

그래서 스몰톡 핸들러를 잡담 없을 때도 억지로 돌리는 대신 **경로를 분리**했다. 응답의 `reply`는 항상 채워지지만 내부 생성 경로는 다음과 같다.
- 잡담이 있으면: 기존 스몰톡 핸들러(LLM)가 그대로 반응
- 선호만 있으면: `acknowledge_preferences_only`가 **LLM 호출 없이** 고정 문구(백엔드 예시와 동일한 문장)로 통보만

`app/graph/nodes/n1_smalltalk_handler.py`의 `acknowledge_preferences_only`, `app/graph/build_preference_graph.py`의 라우팅 분기 참고. 실제 테스트로 두 경로 모두 확인했다.

**5.** ~~`userId`, `conversationId`가 요청에 포함된다~~ → **제거 완료.** AI는 이 엔드포인트에서 저장이나 사용자별 대화 상태를 관리하지 않고 이번 제출의 문장만 추출한다. 로그인 사용자 식별과 `(user_id, vocabulary_code)` UPSERT는 Back의 책임이다. 향후 AI가 사용자별 맥락을 직접 관리해야 한다는 요구가 생기면 별도 계약으로 다시 추가한다. 이는 아직 두 필드를 포함하는 `api-design.md`와 다르며, 화면 검토 종료 후 통합 시 반영한다.

**6. `UNMAPPED` 처리.** 백엔드 초안은 "`UNMAPPED`는 디버깅 목적으로만 보관하고 일반 선호 목록에는 노출하지 않는다"고 명시했다. 이건 이전에 미정이었던 사항이 백엔드 쪽에서 결정된 것으로 보인다 — `ai-part-proposal.md` 12장 오픈 이슈에 반영해두는 게 좋겠다.

### 다루지 않는 것

- "건너뛰기": AI 호출 자체가 없으므로 이 문서의 범위 밖.
- 밸런스 게임 형식 온보딩: 이전 기획 단계에서 MVP 제외로 이미 결정됨 — 지금 화면(문장 선택 + 자유 입력)이 그 대체 방식.

---

*다음 화면 검토 시 이 문서에 절을 추가한다.*
