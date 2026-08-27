"""Component resolver (Phase1-Plan T1.1). This single abstraction is what
makes Phase 4 an import swap instead of a refactor.

Critical rule: never import the real modules at module level. They may not
exist on disk yet, and a top-level `import ml_engine` would break /health,
the tests, and everything else. Import lazily inside the getter, inside a
try/except, and fall back to the mock with a loud warning log if the real
module is missing.
"""

import importlib
import logging
from typing import Callable

from api.config.settings import settings
from api.mocks.mock_c3 import MockC3
from api.mocks.mock_ml import MockMLEngine
from api.models.shared import AnomalyReport, CompanyInput, EnrichedReport

logger = logging.getLogger(__name__)


def _mock_c1() -> Callable[[CompanyInput], AnomalyReport]:
    engine = MockMLEngine(
        scenario=settings.MOCK_SCENARIO,
        raise_on_call=settings.MOCK_C1_RAISE_ON_CALL,
        sleep_s=settings.MOCK_C1_SLEEP_S,
    )
    return engine.analyze_company


def _mock_c3() -> Callable[[AnomalyReport], EnrichedReport]:
    c3 = MockC3(
        fail_llm=settings.MOCK_C3_FAIL_LLM,
        raise_on_call=settings.MOCK_C3_RAISE_ON_CALL,
        sleep_s=settings.MOCK_C3_SLEEP_S,
    )
    return c3.enrich_report


def get_c1() -> Callable[[CompanyInput], AnomalyReport]:
    if settings.USE_MOCK_C1:
        return _mock_c1()

    try:
        module = importlib.import_module(settings.C1_MODULE_NAME)
        return getattr(module, settings.C1_ENTRYPOINT_NAME)
    except (ImportError, AttributeError):
        logger.warning(
            "C1 real module %r (entrypoint %r) unavailable — falling back to mock",
            settings.C1_MODULE_NAME,
            settings.C1_ENTRYPOINT_NAME,
        )
        return _mock_c1()


def get_c3() -> Callable[[AnomalyReport], EnrichedReport]:
    if settings.USE_MOCK_C3:
        return _mock_c3()

    try:
        module = importlib.import_module(settings.C3_MODULE_NAME)
        return getattr(module, settings.C3_ENTRYPOINT_NAME)
    except (ImportError, AttributeError):
        logger.warning(
            "C3 real module %r (entrypoint %r) unavailable — falling back to mock",
            settings.C3_MODULE_NAME,
            settings.C3_ENTRYPOINT_NAME,
        )
        return _mock_c3()
