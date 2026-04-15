from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_OPTICS_SIM_KRAKEN_URL = "http://optics-sim-kraken:8000"
DEFAULT_OPTICS_SIM_SIMPLE_URL = "http://optics-sim-simple:8000"
DEFAULT_POSITION_SERVICE_URL = "http://position-service:8004"
DEFAULT_BOLT_SERVICE_URL = "http://bolt-service:8005"
DEFAULT_DOWNSTREAM_TIMEOUT_SEC = 30.0
DEFAULT_DATA_DIR = "/app/data"


@dataclass(frozen=True)
class Settings:
    optics_sim_kraken_url: str = DEFAULT_OPTICS_SIM_KRAKEN_URL
    optics_sim_simple_url: str = DEFAULT_OPTICS_SIM_SIMPLE_URL
    position_service_url: str = DEFAULT_POSITION_SERVICE_URL
    bolt_service_url: str = DEFAULT_BOLT_SERVICE_URL
    downstream_timeout_sec: float = DEFAULT_DOWNSTREAM_TIMEOUT_SEC
    data_dir: Path = Path(DEFAULT_DATA_DIR)

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            optics_sim_kraken_url=os.getenv("OPTICS_SIM_KRAKEN_URL", DEFAULT_OPTICS_SIM_KRAKEN_URL),
            optics_sim_simple_url=os.getenv("OPTICS_SIM_SIMPLE_URL", DEFAULT_OPTICS_SIM_SIMPLE_URL),
            position_service_url=os.getenv(
                "POSITION_SERVICE_URL", DEFAULT_POSITION_SERVICE_URL
            ),
            bolt_service_url=os.getenv("BOLT_SERVICE_URL", DEFAULT_BOLT_SERVICE_URL),
            downstream_timeout_sec=float(
                os.getenv(
                    "DOWNSTREAM_TIMEOUT_SEC",
                    str(DEFAULT_DOWNSTREAM_TIMEOUT_SEC),
                )
            ),
            data_dir=Path(os.getenv("DATA_DIR", DEFAULT_DATA_DIR)),
        )
