/*
This is more involved than getEventsByPerson() since it "rolls up" events
for each child place. It's somewhat inefficient since it performs a separate
search for each child place, but at least it's done on the backend.
*/

function getChildEvents(noteId) {
    place = api.getNote(noteId);

    /* return all children of provided note */
    function getChildPlaces(place) {
        var label = null;
        if (place.hasLabel('land')) {
            label = 'land';
        } else if (place.hasLabel('city')) {
            label = 'city';
        }

        if (label != null) {
            results = api.searchForNotes(`~${label}.noteId=${place.noteId}`);
        } else {
            results = [];
        }

        return results;
    }

    places = getChildPlaces(place)
    places.push(place);
    var events = [];

    // traverse and get events for each place
    for (place of places) {
        results = api.searchForNotes(`#event ~place.noteId=${place.noteId} orderBy #date`);

        for (result of results) {
            if (!events.includes(result)) {
                events.push(result);
            }
        }
    }

    // sort events by date
    events.sort((a, b) => {
        const aValue = a.getLabelValue("date") !== null ? a.getLabelValue("date") : a.title;
        const bValue = b.getLabelValue("date") !== null ? b.getLabelValue("date") : b.title;
        if (aValue < bValue) {
          return -1;
        } else if (aValue > bValue) {
          return 1;
        } else {
          return 0;
        }
    });

    return events.map(event => event.noteId);
}

module.exports = async function getEventsByPlace(place) {
    // invoke search functions on backend
    return await api.runOnBackend(getChildEvents, [place.noteId]);
}