from __future__ import annotations

from uuid import uuid4

from fastapi.responses import JSONResponse

CONTRACT_VERSION = "fs-compliance.v1"


def error_response(
    status_code: int,
    code: str,
    message: str,
    *,
    request_id: str = "",
    retryable: bool = False,
    details: dict | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    safe_request_id = str(request_id or uuid4())
    return JSONResponse(
        status_code=status_code,
        headers=headers,
        content={
            "detail": message,
            "error": {
                "contractVersion": CONTRACT_VERSION,
                "code": code,
                "message": message,
                "requestId": safe_request_id,
                "retryable": bool(retryable),
                "details": details or {},
            },
        },
    )

