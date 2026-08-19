from __future__ import annotations

import threading

import pigpio


BLUE_PIN = 20
GREEN_PIN = 16
RED_PIN = 21

# 200 ms debounce, same idea as your old project
GLITCH_FILTER_US = 200_000


class GPIOController:

    def __init__(self, service):
        self.service = service

        self.pi: pigpio.pi | None = None
        self.callbacks = []

    def start(self):

        print("[GPIO] Connecting to pigpio daemon...")

        self.pi = pigpio.pi()

        if not self.pi.connected:
            raise RuntimeError(
                "Could not connect to pigpio daemon. "
                "Start it with: sudo pigpiod"
            )

        print("[GPIO] Connected to pigpio.")

        buttons = [
            BLUE_PIN,
            GREEN_PIN,
            RED_PIN,
        ]

        for pin in buttons:

            self.pi.set_mode(
                pin,
                pigpio.INPUT,
            )

            self.pi.set_pull_up_down(
                pin,
                pigpio.PUD_UP,
            )

            self.pi.set_glitch_filter(
                pin,
                GLITCH_FILTER_US,
            )

        self.callbacks = [
            self.pi.callback(
                BLUE_PIN,
                pigpio.FALLING_EDGE,
                self._button_callback,
            ),

            self.pi.callback(
                GREEN_PIN,
                pigpio.FALLING_EDGE,
                self._button_callback,
            ),

            self.pi.callback(
                RED_PIN,
                pigpio.FALLING_EDGE,
                self._button_callback,
            ),
        ]

        print("[GPIO] Buttons ready:")
        print(f"       BLUE   -> GPIO {BLUE_PIN}")
        print(f"       GREEN  -> GPIO {GREEN_PIN}")
        print(f"       RED    -> GPIO {RED_PIN}")

    def _button_callback(
        self,
        gpio,
        level,
        tick,
    ):
        """
        Called by pigpio whenever one of the buttons
        generates a falling edge.
        """

        if gpio == BLUE_PIN:

            print(
                "[GPIO] BLUE pressed "
                "-> start"
            )

            action = (
                self.service.start_or_resume
            )

        elif gpio == GREEN_PIN:

            print(
                "[GPIO] GREEN pressed "
                "-> submit"
            )

            action = self.service.submit

        elif gpio == RED_PIN:

            print(
                "[GPIO] RED pressed "
                "-> cancel"
            )

            action = self.service.cancel

        else:
            return

        # Do not perform potentially slow operations inside
        # pigpio's callback thread.
        threading.Thread(
            target=self._safe_action,
            args=(action,),
            daemon=True,
        ).start()

    @staticmethod
    def _safe_action(action):

        try:
            action()

        except Exception as exc:
            print(
                "[GPIO] Action failed:",
                exc,
            )

    def stop(self):

        print("[GPIO] Cleaning up...")

        for callback in self.callbacks:
            callback.cancel()

        self.callbacks.clear()

        if self.pi is not None:

            for pin in [
                BLUE_PIN,
                GREEN_PIN,
                RED_PIN,
            ]:
                self.pi.set_glitch_filter(
                    pin,
                    0,
                )

                self.pi.set_pull_up_down(
                    pin,
                    pigpio.PUD_OFF,
                )

            self.pi.stop()
            self.pi = None

        print("[GPIO] Stopped.")
