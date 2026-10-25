(() => {
    const messages = [...document.querySelectorAll(".ds-message")];

    return {
        count: messages.length,
        messages: messages.map(x => x.innerText)
    };
})()

