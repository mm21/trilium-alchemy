module.exports = async function formatEvents(div, events) {
    div.empty();

    for (const event of events) {
        let link = await api.createLink(event, 
            {showNoteIcon: true});
        div.append(link);
        div.append($("<br />"));
    }
}