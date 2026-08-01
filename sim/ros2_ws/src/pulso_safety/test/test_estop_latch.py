from pulso_safety.estop_latch import EstopLatch


def test_estop_remains_latched_after_signal_releases():
    latch = EstopLatch()
    latch.update(True)
    latch.update(False)
    assert latch.latched
