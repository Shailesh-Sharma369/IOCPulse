from typing import Any, Optional, Dict
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder

def success_response(
    data: Any,
    message: Optional[str] = None,
    pagination: Optional[Dict[str, int]] = None
) -> JSONResponse:
    payload = {"status": "success", "data": jsonable_encoder(data)}
    if message:
        payload["message"] = message
    if pagination:
        payload["pagination"] = jsonable_encoder(pagination)
    return JSONResponse(status_code=200, content=payload)

def error_response(message: str, status_code: int = 400, details: Any = None) -> JSONResponse:
    payload = {"status": "error", "message": message}
    if details:
        payload["details"] = jsonable_encoder(details)
    return JSONResponse(status_code=status_code, content=payload)