# 다모여 AI — 진행 중인 작업

## 지금 하고 있는 작업

화면 단위로 API 명세를 확정하는 작업은 끝났다. 지금은 확정된 명세(`docs/api-design2-backend.md`)에 맞게 **실제 코드를 엔드포인트 단위로 하나씩** 고치는 단계다.

1. 명세서(`api-design2-backend.md`)와 현재 코드(`app/schemas/`, `app/graph/`, `app/api/routes/`)를 비교해 격차를 짚는다.
2. 한 번에 한 엔드포인트만 고친다 — 스키마 → 그래프/노드 → 라우트 순. 여러 엔드포인트를 동시에 고치지 않는다 — diff가 커지면 리뷰도 버그 추적도 어려워지기 때문이다.
3. 테스트로 검증한다 (pytest, 필요하면 실제 Gemini 호출로 확인).
4. 명세와 다르게 구현해야 할 이유가 생기면 코드부터 고치지 않는다 — 명세서를 먼저 갱신하고 사용자 확인을 받은 뒤 코드에 반영한다.

진행 순서: **① `/context` 2단계 분리 (`/context/messages` 신규 + `/context` 재정의, 완료) → ② `/candidates`**

`/revise`는 목표 계약과 코드 양쪽에서 제거했다 — 제품 흐름상 "재생성"이 "뒤로가기"로 단순화되면서 전용 엔드포인트 없이 `/context/messages`+`/context`+`/candidates`를 재사용하기로 했다 (`api-design2-backend.md` 7장 참고).

## 문서별 역할 (참고 우선순위)

| 문서 | 역할 |
| --- | --- |
| `docs/api-design2-backend.md` | **Back↔AI 계약의 단일 기준 문서.** 요청/응답/에러코드가 다른 문서와 다르면 항상 이 문서가 맞다. 명세를 새로 쓰거나 고칠 땐 이 문서의 형식(엔드포인트별 Request/Response 예시 → 필드 표 → 규칙 → 에러 표)을 따른다. |
| `docs/db_schema.md` | DB 스키마 확정본. 필드명·타입·enum 값의 최종 근거. |
| `docs/ai-part-proposal.md` | AI 파트 전체 기획서. 파이프라인 구조·노드 역할·설계 배경. API 형태의 근거가 아니라 "왜 이런 파이프라인인가"의 배경용. |
| `docs/backend-api-example.md` | 백엔드가 임시로 작성해준 Front↔Back API 예시. **참고만 한다 — 그대로 따르지 않는다.** |

아래는 이미 최신 계약에 반영이 끝난 과거 산출물이다. 히스토리로만 남아 있고 현재 계약의 근거로 쓰지 않는다 — 내용이 최신 문서와 다르면 최신 문서가 맞다.

`docs/api-spec.md`(화면 단위 명세 작업), `docs/api-design.md`(초기 API 초안), `docs/ai-pipeline-design.md`, `docs/backend-ai-contract.md`, `docs/service-proposal.md`, `docs/topic-development.md`(기획 단계 문서)

## 판단 기준

- 코드를 고치기 전에 반드시 `api-design2-backend.md`와 현재 코드를 대조해서 격차를 먼저 짚는다.
- 엔드포인트 하나를 끝까지(스키마 → 노드/그래프 → 라우트 → 테스트) 마치고 나서 다음 엔드포인트로 넘어간다.
- 새 필드를 구현할 땐 LLM이 만드는 값인지 서버가 코드로 파생시키는 값인지 구분한다 (예: `AVAILABLE_AT_MEETING_TIME`은 LLM이 고르지 않고 서버가 `businessHoursVerified`/`openAtMeetingTime`에서 파생시킨다).
- 명세와 다른 설계가 필요하면 문서를 먼저 고치고, 실제 코드 변경은 사용자 확인 후 진행한다.
- 명세는 `api-design2-backend.md` **한 곳에만** 쓴다. 같은 내용을 다른 문서에 복제하지 않는다 — 두 벌이 되면 곧바로 어긋나서 팀원이 어느 쪽이 맞는지 알 수 없게 된다.
- 커밋은 사용자가 요청할 때만 한다. 작업이 끝났다고 자동으로 커밋하지 않는다.
