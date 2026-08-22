from __future__ import annotations

import os
import re
import atexit

from flask import (
    Flask,
    jsonify,
    render_template,
    url_for,
)

from src.interface.gpio_controller import (
    GPIOController,
)
from src.interface.recognition_service import (
    RecognitionService,
)


app = Flask(__name__)


service = RecognitionService(
    device=os.getenv(
        "MELODY_AUDIO_DEVICE",
        "default",
    ),
    channels=int(
        os.getenv(
            "MELODY_AUDIO_CHANNELS",
            "1",
        )
    ),
)


def slugify(text):

    text = text.lower()

    text = re.sub(
        r"[^a-z0-9]+",
        "_",
        text,
    )

    return text.strip("_")


def public_state():

    data = service.get_state()

    result = data.get("result")

    if result:

        cover_file = result.get(
            "cover_file"
        )

        if cover_file:

            result["cover_url"] = url_for(
                "static",
                filename=f"covers/{cover_file}",
            )

        else:

            result["cover_url"] = None

    return data


@app.get("/")
def home():
    return render_template(
        "home.html"
    )


@app.get("/recognize")
def recognize_page():
    return render_template(
        "recognize.html"
    )


@app.get("/api/state")
def api_state():

    return jsonify(
        public_state()
    )


@app.post("/api/action/start")
def start():

    service.start_or_resume()

    return jsonify(
        public_state()
    )


@app.post("/api/action/submit")
def submit():

    service.submit()

    return jsonify(
        public_state()
    )


@app.post("/api/action/cancel")
def cancel():

    service.cancel()

    return jsonify(
        public_state()
    )


# Physical GPIO
gpio_controller = None


if os.getenv(
    "MELODY_ENABLE_GPIO",
    "0",
) == "1":

    try:

        gpio_controller = GPIOController(
            service
        )

        gpio_controller.start()

        atexit.register(
            gpio_controller.stop
        )

    except Exception as exc:

        print(
            "[GPIO] Disabled:",
            exc,
        )

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
        use_reloader=False,
    )
