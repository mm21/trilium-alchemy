/*
This is a simple example illustrating how a component can use a script 
by adding it as a child.
*/
module.exports = async function getEventsByPerson(person) {
    let results = await api.searchForNotes(`#event ~person.noteId=${person.noteId} orderBy #date`);
    return results.map(event => event.noteId);
}