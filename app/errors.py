import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError, TimeoutError
from starlette.exceptions import HTTPException

logger = logging.getLogger("dispatch")


class DispatchError(HTTPException):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(status_code=status, detail=message)
        self.code = code


async def validation_error(request: Request, error: RequestValidationError):
    # Omit raw inputs/context: invalid NaN/Infinity and exception objects are not JSON values.
    details = [{key: item[key] for key in ("loc", "msg", "type")} for item in error.errors()]
    return JSONResponse(status_code=422, content={"code": "invalid_request", "detail": details})


async def http_error(request: Request, error: HTTPException):
    return JSONResponse(
        status_code=error.status_code,
        content={"code": getattr(error, "code", "http_error"), "detail": error.detail},
        headers=error.headers,
    )


async def database_unavailable(request: Request, error: Exception):
    logger.warning("Database unavailable on %s", request.url.path)
    return JSONResponse(
        status_code=503,
        content={"code": "database_unavailable", "detail": "Database unavailable; retry later"},
    )


async def internal_error(request: Request, error: Exception):
    logger.error("Unexpected dispatch API error", exc_info=error)
    return JSONResponse(
        status_code=500, content={"code": "internal_error", "detail": "Unexpected server error"}
    )


def install_error_handlers(app):
    app.add_exception_handler(RequestValidationError, validation_error)
    app.add_exception_handler(HTTPException, http_error)
    app.add_exception_handler(OperationalError, database_unavailable)
    app.add_exception_handler(TimeoutError, database_unavailable)
    app.add_exception_handler(Exception, internal_error)
