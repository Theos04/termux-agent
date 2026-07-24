(() => {
    const msg = document.querySelector(".ds-message");

    return {
        text: msg.innerText,
        html: msg.innerHTML
    };
})()
