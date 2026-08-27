"""GET /health — liveness + component import check (Contract §7, Phase0-Plan T0.8).

`importable` attempts a real import inside a try/except without failing the
request. This is the fastest possible answer to "has C1/C3 shipped yet?".
"""

import importlib

from fastapi import APIRouter

from api.config.loader import metrics
from api.config.settings import settings

router = APIRouter()


def _is_importable(module_name: str) -> bool:
    try:
        importlib.import_module(module_name)
        return True
    except ImportError:
        return False


@router.get("/health")
def health() -> dict:
    metric_config = metrics()
    sectors = sorted({sector for m in metric_config.values() for sector in m["sector_ids"]})

    return {
        "status": "ok",
        "version": "0.1.0",
        "components": {
            "c1": {
                "mode": "mock" if settings.USE_MOCK_C1 else "real",
                "importable": _is_importable(settings.C1_MODULE_NAME),
            },
            "c3": {
                "mode": "mock" if settings.USE_MOCK_C3 else "real",
                "importable": _is_importable(settings.C3_MODULE_NAME),
            },
        },
        "config": {
            "metrics_loaded": len(metric_config),
            "sectors": sectors,
        },
    }
