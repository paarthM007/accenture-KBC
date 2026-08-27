"""Env-overridable settings (Phase0-Plan T0.5).

Two independent mock flags, not one: C1 will almost certainly land before C3,
and we want to run real detection against a mocked C3 without a code change.
"""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    USE_MOCK_C1: bool = True
    USE_MOCK_C3: bool = True
    MOCK_SCENARIO: Literal["healthy", "critical", "refusal", "degraded"] = "critical"
    C1_TIMEOUT_S: float = 10
    C3_TIMEOUT_S: float = 30
    LLM_TIMEOUT_S: int = 20
    MAX_UPLOAD_MB: int = 10
    FEEDBACK_LOG_PATH: str = "./feedback.jsonl"

    # Real C1's module is confirmed (Contract §5, §9 item 10). C3's is not —
    # single constants so confirmation is a one-line change, not a grep-and-pray
    # (Phase1-Plan T1.1).
    C1_MODULE_NAME: str = "ml_engine"
    C1_ENTRYPOINT_NAME: str = "analyze_company"
    C3_MODULE_NAME: str = "c3_engine"  # UNVERIFIED — ask C3 this week
    C3_ENTRYPOINT_NAME: str = "enrich_report"  # UNVERIFIED — ask C3 this week

    # Mock failure/latency injection, read by orchestration/resolver.py so
    # get_c1()/get_c3() stay zero-argument. Tests override these directly on
    # the settings instance (not via env) to exercise each degradation path.
    MOCK_C1_RAISE_ON_CALL: bool = False
    MOCK_C1_SLEEP_S: float = 0.2
    MOCK_C3_RAISE_ON_CALL: bool = False
    MOCK_C3_FAIL_LLM: bool = False
    MOCK_C3_SLEEP_S: float = 1.5


settings = Settings()
