"""Manual E-stop latch: a false signal never resumes motion implicitly."""


class EstopLatch:
    def __init__(self) -> None:
        self.latched = False

    def update(self, pressed: bool) -> None:
        self.latched = self.latched or pressed
