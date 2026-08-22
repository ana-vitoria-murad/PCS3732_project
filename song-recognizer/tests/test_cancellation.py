"""Regression tests for immediate execution cancellation."""

from __future__ import annotations

import sys
import threading
import time
import unittest

from tests.audio_test_utils import SRC_DIR


if str(SRC_DIR.parent) not in sys.path:
    sys.path.insert(0, str(SRC_DIR.parent))

from src.interface.recognition_service import (  # noqa: E402
    ExecutionCancelled,
    RecognitionService,
    State,
)


class CancellationTests(unittest.TestCase):

    def test_cancel_stops_an_active_subprocess(self):

        service = RecognitionService()

        with service._lock:
            service._run_id = 1
            service.state = State.PROCESSING

        errors = []

        def run_slow_process():
            try:
                service._run(
                    [
                        sys.executable,
                        "-c",
                        "import time; time.sleep(30)",
                    ],
                    run_id=1,
                )
            except Exception as exc:
                errors.append(exc)

        worker = threading.Thread(
            target=run_slow_process,
            daemon=True,
        )
        worker.start()

        deadline = time.monotonic() + 2.0

        while (
            service._active_process is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.01)

        self.assertIsNotNone(service._active_process)

        started = time.monotonic()
        service.cancel()
        elapsed = time.monotonic() - started

        worker.join(timeout=2.0)

        self.assertFalse(worker.is_alive())
        self.assertEqual(State.IDLE.value, service.get_state()["state"])
        self.assertLess(elapsed, 1.0)
        self.assertEqual(1, len(errors))
        self.assertIsInstance(errors[0], ExecutionCancelled)


if __name__ == "__main__":
    unittest.main()
