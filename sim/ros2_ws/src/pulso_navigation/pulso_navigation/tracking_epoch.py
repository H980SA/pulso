"""Track localization resets from the normalized VIO diagnostic stream."""

from diagnostic_msgs.msg import DiagnosticArray


class TrackingEpoch:
    def __init__(self) -> None:
        self.value = 0
        self._previous_state = "LOST"

    def update(self, message: DiagnosticArray) -> bool:
        if not message.status:
            return False
        status = message.status[0]
        values = {item.key: item.value for item in status.values}
        state = values.get("state", status.message or "LOST").upper()
        changed = self._previous_state == "LOST" and state == "TRACKING"
        if changed:
            self.value += 1
        self._previous_state = state
        return changed
