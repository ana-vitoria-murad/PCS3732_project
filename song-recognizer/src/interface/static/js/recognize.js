const statusElement =
    document.getElementById(
        "current-status"
    );

const resultCard =
    document.getElementById(
        "result-card"
    );

const titleElement =
    document.getElementById(
        "song-title"
    );

const artistElement =
    document.getElementById(
        "song-artist"
    );

const votesElement =
    document.getElementById(
        "votes"
    );

const coverElement =
    document.getElementById(
        "cover"
    );

const coverPlaceholder =
    document.getElementById(
        "cover-placeholder"
    );


const statuses = {

    idle: {
        text: "aguardando gravação...",
        className: "status-idle",
    },

    recording: {
        text: "gravando...",
        className: "status-recording",
    },

    processing: {
        text: "processando...",
        className: "status-processing",
    },

    matched: {
        text: "música identificada!",
        className: "status-matched",
    },

    no_match: {
        text: "música não identificada.",
        className: "status-error",
    },

    error: {
        text: "erro durante a execução.",
        className: "status-error",
    },
    ready: {
        text: "gravação concluída — pressione verde para identificar",
        className: "status-processing",
    },
};


async function sendAction(action) {

    try {

        const response = await fetch(
            `/api/action/${action}`,
            {
                method: "POST",
            }
        );

        const data =
            await response.json();

        renderState(data);

    } catch (error) {

        console.error(error);

    }
}


async function refreshState() {

    try {

        const response =
            await fetch(
                "/api/state"
            );

        const data =
            await response.json();

        renderState(data);

    } catch (error) {

        console.error(
            "Unable to retrieve state:",
            error
        );

    }
}


function renderState(data) {

    const status =
        statuses[data.state]
        ?? statuses.error;

    statusElement.textContent =
        status.text;

    statusElement.className =
        `current-status ${status.className}`;


    if (
        data.state === "matched"
        && data.result
    ) {

        const result = data.result;

        resultCard.classList.remove(
            "hidden"
        );

        titleElement.textContent =
            result.title;

        artistElement.textContent =
            result.artist;

        votesElement.textContent =
            `${result.votes} votos`;

        if (result.cover_url) {

            console.log(
                "Cover URL:",
                result.cover_url
            );

            coverElement.src =
                result.cover_url;

            coverElement.classList.remove(
                "hidden"
            );

            coverPlaceholder.classList.add(
                "hidden"
            );

        } else {

            console.log(
                "No cover URL received."
            );

            coverElement.classList.add(
                "hidden"
            );

            coverPlaceholder.classList.remove(
                "hidden"
            );
        }

    } else {

        resultCard.classList.add(
            "hidden"
        );
    }
}


document
    .querySelectorAll(
        "[data-action]"
    )
    .forEach(button => {

        button.addEventListener(
            "click",
            () => {

                sendAction(
                    button.dataset.action
                );

            }
        );

    });


refreshState();

setInterval(
    refreshState,
    500
);
