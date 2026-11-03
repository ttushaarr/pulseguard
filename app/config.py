import os
from pydantic import BaseModel


class Settings(BaseModel):
    APP_NAME: str = "PulseGuard"
    VERSION: str = "1.0.0"
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./pulseguard.db")
    DEFAULT_CHECK_INTERVAL: int = int(os.getenv("DEFAULT_CHECK_INTERVAL", "30"))
    REQUEST_TIMEOUT: int = int(os.getenv("REQUEST_TIMEOUT", "10"))
    MAX_HISTORY_PER_SERVICE: int = int(os.getenv("MAX_HISTORY_PER_SERVICE", "100"))


settings = Settings()
