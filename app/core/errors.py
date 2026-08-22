class AIServiceError(Exception):
    """공통 에러 응답 포맷(`{"error": {"code","message","retryable","requestId"}}`)으로 직렬화되는 예외.

    포맷은 docs/api-design-backend.md 1장 "공통 오류 형식"을 따른다.
    """

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 500,
        retryable: bool = False,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
        self.request_id = request_id
