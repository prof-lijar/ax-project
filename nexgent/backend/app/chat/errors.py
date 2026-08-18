from app.chat.models import ChatErrorDetail


class ChatRequestError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        filename: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = ChatErrorDetail(
            code=code,
            message=message,
            filename=filename,
        )
