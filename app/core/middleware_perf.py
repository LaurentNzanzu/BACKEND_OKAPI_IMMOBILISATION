import time
import logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("performance")

class PerformanceLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.perf_counter()
        
        response = await call_next(request)
        
        process_time = (time.perf_counter() - start_time) * 1000
        
        if process_time > 100:
            logger.warning(
                f"⚠️ SLOW ENDPOINT: {request.method} {request.url.path} - "
                f"Total: {process_time:.2f}ms"
            )
        else:
            logger.info(
                f"⚡ {request.method} {request.url.path} - Total: {process_time:.2f}ms"
            )
            
        response.headers["X-Process-Time-Ms"] = f"{process_time:.2f}"
        return response
