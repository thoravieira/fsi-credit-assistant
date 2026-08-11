from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"

# The demo has one analyst and no authentication. A real deployment reads this
# from the authenticated session; it is a constant here so that every place
# that stamps an actor or namespaces an analyst memory agrees on one id.
DEMO_ANALYST_ID = "ANALYST-CARLOS"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_REPO_ROOT_ENV, extra="ignore")

    mongodb_uri: str
    mongodb_db: str

    openai_api_key: str
    llm_model: str

    embedding_provider: Literal["voyage", "openai"] = "voyage"
    voyage_api_key: str | None = None
    embedding_dimensions: int = 1024

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    langsmith_tracing: bool = False
    langsmith_api_key: str | None = None
    langsmith_project: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
