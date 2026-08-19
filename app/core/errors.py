class AIServiceError(Exception):
    """공통 에러 응답 포맷(`{"error": {"code", "message"}}`)으로 직렬화되는 예외."""

    def __init__(self, code: str, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
