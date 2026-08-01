"""Server-side rover safety proxy; credentials never enter browser JavaScript."""

from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class RoverControlError(RuntimeError):
    pass


class RoverControlProxy:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    @classmethod
    def from_env(cls) -> "RoverControlProxy":
        return cls(
            os.getenv("PULSO_ROVER_URL", "http://10.245.145.36:8765"),
            os.getenv("PULSO_ROVER_TOKEN", ""),
        )

    def emergency_stop(self) -> dict[str, str]:
        if not self.token:
            raise RoverControlError("Mission Control has no provisioned rover credential")
        request = Request(
            self.base_url + "/v1/estop/engage",
            data=json.dumps({"reason": "Mission Control PARAR TODO"}).encode(),
            method="POST",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=2.5) as response:
                if response.status != 204:
                    raise RoverControlError(f"gateway returned HTTP {response.status}")
        except HTTPError as failure:
            raise RoverControlError(f"gateway rejected e-stop with HTTP {failure.code}") from failure
        except (URLError, TimeoutError) as failure:
            raise RoverControlError("gateway e-stop could not be confirmed") from failure
        return {"status": "ESTOP_LATCHED", "physical_achievement": "UNVERIFIED"}
