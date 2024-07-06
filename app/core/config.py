import os
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    FAUNA_SECRET: Optional[str] = os.getenv("FAUNA_SECRET")
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    API_V1_STR: str = "/api/v1"
    ALLOWED_HOSTS: str = "*"

    class Config:
        env_file = ".env"

    def is_fauna_configured(self) -> bool:
        return self.FAUNA_SECRET is not None

settings = Settings()