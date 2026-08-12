class GPIOController:

    def __init__(self, service):

        self.service = service
        self.buttons = []

    def start(self):

        try:
            from gpiozero import Button

            blue = Button(
                17,
                pull_up=True,
                bounce_time=0.05,
            )

            yellow = Button(
                27,
                pull_up=True,
                bounce_time=0.05,
            )

            green = Button(
                22,
                pull_up=True,
                bounce_time=0.05,
            )

            red = Button(
                23,
                pull_up=True,
                bounce_time=0.05,
            )

        except Exception as exc:

            print(
                "GPIO disabled:",
                exc,
            )

            return

        blue.when_pressed = self._start
        yellow.when_pressed = self._pause
        green.when_pressed = self._submit
        red.when_pressed = self._cancel

        self.buttons = [
            blue,
            yellow,
            green,
            red,
        ]

        print("GPIO controls enabled.")

    def _safe(self, callback):

        try:
            callback()

        except Exception as exc:
            print(
                "GPIO action failed:",
                exc,
            )

    def _start(self):
        self._safe(
            self.service.start_or_resume
        )

    def _pause(self):
        self._safe(
            self.service.pause
        )

    def _submit(self):
        self._safe(
            self.service.submit
        )

    def _cancel(self):
        self._safe(
            self.service.cancel
        )

