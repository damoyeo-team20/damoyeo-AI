# 문서 안내

**API 연동하러 왔다면 → [`api-design2-backend.md`](api-design2-backend.md) 하나만 보면 된다.**

Back↔AI 요청/응답 형태에 대해 다른 문서와 내용이 다르면 항상 그 문서가 맞다.

## 현재 유효한 문서

| 문서 | 언제 보는가 |
| --- | --- |
| [`api-design2-backend.md`](api-design2-backend.md) | **Back↔AI 계약의 단일 기준.** 엔드포인트, 요청/응답 필드, 에러 코드, 구현 상태 |
| [`db_schema.md`](db_schema.md) | 필드명·타입·enum 값의 최종 근거 (백엔드 확정본) |
| [`ai-part-proposal.md`](ai-part-proposal.md) | "왜 이런 파이프라인인가" 배경 설명. API 형태의 근거는 아님 |
| [`backend-api-example.md`](backend-api-example.md) | 백엔드가 제안한 Front↔Back 예시. 참고용이며 그대로 따르지 않음 |

## 지난 기록 (참고만)

아래는 결론이 이미 `api-design2-backend.md`에 반영된 과거 산출물이다. 현재 계약의 근거로 쓰지 않는다 — 내용이 다르면 `api-design2-backend.md`가 맞다. 각 문서 상단에도 같은 안내가 붙어 있다.

- [`api-spec.md`](api-spec.md) — 화면 단위로 필드를 확정하던 작업 기록
- [`api-design.md`](api-design.md) — 초기 API 초안 (`/context` 2단계 분리, `/revise` 제거 이전)
- [`ai-pipeline-design.md`](ai-pipeline-design.md), [`backend-ai-contract.md`](backend-ai-contract.md) — 기획 단계 설계 문서
- [`service-proposal.md`](service-proposal.md), [`topic-development.md`](topic-development.md) — 기획안·브레인스토밍 히스토리
