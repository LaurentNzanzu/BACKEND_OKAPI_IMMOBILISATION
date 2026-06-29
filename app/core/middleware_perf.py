import time
import logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

import time
import logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from .config import settings

logger = logging.getLogger("performance")

class PerformanceLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.perf_counter()
        
        response = await call_next(request)
        
        process_time = (time.perf_counter() - start_time) * 1000
        
        if getattr(settings, "DEBUG", False) and process_time > 1000:
            logger.debug(
                f"Slow endpoint: {request.method} {request.url.path} - "
                f"Total: {process_time:.2f}ms"
            )
            
        response.headers["X-Process-Time-Ms"] = f"{process_time:.2f}"
        return response

