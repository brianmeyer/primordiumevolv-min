import time
from typing import Dict
from fastapi import Request
from fastapi.responses import JSONResponse

class TokenBucket:
    def __init__(self, rate_per_min: int, capacity: int | None = None):
        self.rate = rate_per_min / 60.0
        self.capacity = capacity or rate_per_min
        self.tokens = self.capacity
        self.timestamp = time.monotonic()

    def allow(self) -> bool:
        now = time.monotonic()
        elapsed = now - self.timestamp
        self.timestamp = now
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False

class RateLimiter:
    def __init__(self, per_min: int = 30):
        self.buckets: Dict[str, TokenBucket] = {}
        self.per_min = per_min

    async def __call__(self, request: Request, call_next):
        # Skip rate limiting for static files
        if request.url.path.startswith("/static"):
            return await call_next(request)
            
        ip = request.client.host if request.client else "unknown"
        bucket = self.buckets.setdefault(ip, TokenBucket(self.per_min))
        
        if not bucket.allow():
            return JSONResponse(
                {"error": "rate_limited", "detail": "Too many requests"}, 
                status_code=429
            )
        
        # Cleanup old buckets occasionally (memory leak prevention)
        if len(self.buckets) > 1000:
            self._cleanup_old_buckets()
            
        return await call_next(request)
    
    def _cleanup_old_buckets(self):
        now = time.monotonic()
        to_remove = []
        for ip, bucket in self.buckets.items():
            # Remove buckets inactive for more than 1 hour
            if now - bucket.timestamp > 3600:
                to_remove.append(ip)
        for ip in to_remove:
            del self.buckets[ip]