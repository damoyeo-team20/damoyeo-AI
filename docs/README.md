# 문서 안내

**API 연동하러 왔다면 → [`api-design2-backend.md`](api-design2-backend.md) 하나만 보면 된다.**

Back↔AI 요청/응답 형태에 대해 다른 문서와 내용이 다르면 항상 그 문서가 맞다.

## 현재 유효한 문서

| 문서 | 언제 보는가 |
| --- | --- |
| [`api-design2-backend.md`](api-design2-backend.md) | **Back↔AI 계약의 단일 기준.** 엔드포인트, 요청/응답 필드, 에러 코드, 구현 상태 |
| [`db_schema.md`](db_schema.md) | 필드명·타입·enum 값의 최종 근거 (백엔드 확정본) |
| [`ai-part-proposal.md`](ai-part-proposal.md) | "왜 이런 파이프라인인가" 배경 설명. API 형태의 근거는 아님 |
| [`ai-pipeline-walkthrough.md`](ai-pipeline-walkthrough.md) | 각 노드가 어떤 필드를 받아 어떤 프롬프트/계산으로 무엇을 내는지 (내부 동작 상세) |
| [`backend-api-example.md`](backend-api-example.md) | 백엔드가 제안한 Front↔Back 예시. 참고용이며 그대로 따르지 않음 |
| [`troubleshooting.md`](troubleshooting.md) | 개발·배포 과정에서 실제로 겪은 문제와 해결 기록 |

기획 단계 산출물(초기 API 초안, 브레인스토밍 등)은 결론이 전부 위 문서들에 반영된 뒤 삭제했다.
