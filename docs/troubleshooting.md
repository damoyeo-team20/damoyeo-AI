# 트러블슈팅

개발·배포 과정에서 실제로 겪고 해결한 문제들을 정리한 문서입니다.

## 인프라 · 배포

1. **이미지 아키텍처 불일치 (`no matching manifest for linux/arm64/v8`)** — Mac(arm64)에서 backend 이미지를 pull하지 못함. 해당 이미지가 `amd64`로만 빌드돼 있었던 게 원인. 같은 문제를 반복하지 않도록 이 저장소의 이미지는 처음부터 GitHub Actions에서 `amd64`/`arm64` 멀티 아키텍처로 빌드하도록 구성.
2. **EC2 `docker compose build requires buildx 0.17.0 or later`** — EC2에 설치된 buildx가 구버전. GitHub Releases의 `latest/download/` 별칭 URL로 받으면 실제 파일명과 안 맞아 9바이트짜리 에러 페이지만 받아짐 → Releases API로 정확한 버전 파일명(`buildx-v0.36.1.linux-amd64`)을 조회해 직접 받는 방식으로 해결.
3. **`docker compose down --remove-orphans`가 컨테이너를 삭제** — 정지가 아니라 완전 삭제라는 걸 모르고 실행해 `backend`/`postgres` 컨테이너가 사라짐. `docker run`으로 임시 복구했다가, 실제 운영 백엔드(`api.damoyeo.kro.kr`)가 이미 별도 서버로 떠 있다는 걸 확인하고 로컬 컨테이너는 정리 대상으로 정리.
4. **배포 스크립트가 파일을 엉뚱한 경로에 복사** — `scp file1 file2 user@host:~/app/`처럼 서로 다른 하위 경로의 파일 여러 개를 한 디렉터리로 복사하면 원래 경로 구조가 무시되고 flat하게 복사됨. 빌드는 성공했는데 버그가 그대로인 걸 보고 `grep`으로 배포된 파일 내용을 직접 확인해 발견 → 파일별로 목적지 전체 경로를 지정해서 재배포.
5. **`host.docker.internal`이 예상과 다른 게이트웨이로 풀림** — 컨테이너 간 통신 실패를 DNS 문제로 의심(기본 브리지 게이트웨이 `172.17.0.1` vs 실제 네트워크 게이트웨이 `172.20.0.1`). `getent hosts`/`docker inspect`로 직접 확인한 결과 DNS는 정상이었고, 실제 원인은 3번 사고로 컨테이너 자체가 삭제된 것이었음 — 겉보기 증상만으로 원인을 단정하지 않고 직접 확인해 잘못된 진단을 피한 사례.

## 인증 · 외부 연동

6. **AI → Back 인증 완전 누락** — Vocabulary 조회가 계속 실패. `.env`의 `INTERNAL_API_KEY`가 플레이스홀더 값 그대로였고, 애초에 헤더 자체를 코드에서 안 보내고 있었음. 실제 키를 생성(`openssl rand -hex 32`)하고 `X-Internal-Api-Key` 헤더를 추가했으며, 헤더 이름은 Back 컨테이너에 직접 curl로 여러 개 테스트해 확정(다른 이름은 401, 이 이름만 200).
7. **로컬 `BACKEND_API_BASE_URL`에 스킴 누락** — `httpx.UnsupportedProtocol` 에러. `.env`에 프로토콜 없이 IP만 적혀 있던 게 원인. `https://api.damoyeo.kro.kr`로 수정.
8. **Kakao Local API 403** — Kakao Developers 콘솔에서 "카카오맵" 서비스가 활성화돼 있지 않았던 게 원인. 서비스 활성화 후 정상화.
9. **Candidate Place Verifier에서 Gemini `google_search` 429** — 후보 생성 마지막 단계(영업시간 검증)에서 자주 할당량 초과. `google_search` grounding 도구 호출이 일반 텍스트 생성과 별도의, 더 빡빡한 할당량을 갖는다는 걸 A/B 테스트(도구 바인딩 호출 vs 순수 텍스트 호출 격리)로 확인. 테스트를 막지 않도록 `SKIP_BUSINESS_HOURS_VERIFICATION` 플래그로 임시 우회 — 할당량 자체는 아직 미해결.

## 프로덕션 버그

10. **`/schedule`에서 `OutputParserException`** — 날짜 선택 API가 실제 운영 트래픽에서 파싱 에러로 실패. 프롬프트가 후보 날짜를 `"2026-08-28 (Friday)"`처럼 요일을 붙여서 보여줬는데, 모델이 그 문자열 전체를 답으로 냈고 응답 스키마는 순수 ISO 날짜만 허용하는 `Literal`이라 거부됨. 요일 표기를 프롬프트에서 제거하고 "후보 목록과 정확히 같은 문자열이어야 한다"는 규칙을 명시해 해결.

## 관측성(디버깅 기능) 관련

임시 디버깅 기능(`# TEMP DEBUG` 태그, 정식 배포 전 제거 예정)을 만들면서 겪은 문제들입니다.

11. **디버그 응답 설계를 두 번 갈아엎음** — 처음엔 새 최상위 키(`_debug`)를 응답에 추가하는 방식으로 구현했으나, Jackson처럼 엄격한 파서를 쓰는 백엔드가 모르는 필드를 만나면 파싱이 깨질 수 있다는 우려로 전면 재설계. 최종적으로 새 필드를 추가하지 않고 기존 `reply`/`reason`/`summary`/`message` 문자열 값 뒤에 `[DEBUG: ...]`를 그대로 이어붙이는 방식으로 바꾸고, 여러 엔드포인트에서 응답 키 구성이 이전과 100% 동일함을 직접 검증.
12. **디버그 트레이스 기록이 테스트에서 크래시** — `record_debug`가 `AttributeError: 'SimpleNamespace' object has no attribute 'model_dump'`로 실패. 테스트가 LLM 응답을 `SimpleNamespace`로 스텁하는데 무조건 `.model_dump()`를 호출하고 있었던 게 원인. `hasattr` 체크 후 없으면 `repr()`로 폴백하도록 방어적으로 수정.
13. **검증 에러 직렬화 실패** — 요청 검증 실패 응답에 상세 내용을 넣는 과정에서 `TypeError: Object of type ValueError is not JSON serializable`. Pydantic 검증 에러 중 일부가 `ValueError` 인스턴스를 그대로 담고 있던 게 원인. `json.dumps(..., default=str)`로 안전하게 직렬화해 해결.
