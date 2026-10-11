from fastapi import HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.database import SessionLocal
from app.models.user import User
from app.utils.security import decode_access_token
from app.utils.usage import PLAN_LIMITS, reset_daily_usage_if_needed


class PlanLimitMiddleware(BaseHTTPMiddleware):
    """Ensure users hitting protected endpoints haven't exceeded their plan limits."""

    def __init__(self, app, protected_paths: list[str] | None = None):
        super().__init__(app)
        self.protected_paths = protected_paths or ["/upload", "/campaigns", "/dashboard"]

    async def dispatch(self, request, call_next):
        if not any(request.url.path.startswith(prefix) for prefix in self.protected_paths):
            return await call_next(request)

        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.lower().startswith("bearer "):
            return JSONResponse(status_code=401, content={"detail": "Authorization header missing"})

        token = auth_header.split(" ", 1)[1]
        try:
            payload = decode_access_token(token)
        except HTTPException as exc:  # re-wrap for middleware response
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

        user_id = payload.get("user_id")
        if not user_id:
            return JSONResponse(status_code=401, content={"detail": "Invalid token payload"})

        db = SessionLocal()
        try:
            user = db.get(User, user_id)
            if not user:
                return JSONResponse(status_code=404, content={"detail": "User not found"})

            reset_daily_usage_if_needed(user)
            limit = PLAN_LIMITS.get(user.plan, PLAN_LIMITS["Free"])
            if user.plan != "Enterprise" and user.daily_usage_count >= limit:
                return JSONResponse(status_code=429, content={"detail": "Daily messaging limit reached"})

            db.commit()
        finally:
            db.close()

        response = await call_next(request)
        return response
