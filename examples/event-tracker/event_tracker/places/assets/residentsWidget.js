const TPL = `<div style="padding: 10px; border-top: 1px solid var(--main-border-color); contain: none;">
    <strong>Residents:</strong>
    <div class="residents"></div>

    <strong>Former residents:</strong>
    <div class="former-residents"></div>
</div>`;

class ResidentsWidget extends api.NoteContextAwareWidget {
    get position() { return 110; } // higher value means position towards the bottom/right

    get parentWidget() { return 'center-pane'; }

    isEnabled() {
        return super.isEnabled()
            && this.note.type === 'text'
            && this.note.hasLabel('residence');
    }

    doRender() {
        this.$widget = $(TPL);
        this.$residents = this.$widget.find('.residents');
        this.$formerResidents = this.$widget.find('.former-residents');
        return this.$widget;
    }

    async refreshWithNote(note) {
        this.$residents.empty();
        this.$formerResidents.empty();

        // lookup current residents
        let residents = await api.searchForNotes(`~livesAt.noteId=${note.noteId}`);

        for (const resident of residents) {
            let link = await api.createLink(resident.noteId, 
                {showNoteIcon: true});

            this.$residents.append(link);
            this.$residents.append($("<br />"));
        }

        // lookup former residents
        let formerResidents = await api.searchForNotes(`~livedAt.noteId=${note.noteId}`);

        for (const formerResident of formerResidents) {
            let link = await api.createLink(formerResident.noteId, 
                {showNoteIcon: true});

            this.$formerResidents.append(link);
            this.$formerResidents.append($("<br />"));
        }
    }

    async entitiesReloadedEvent({loadResults}) {
        if (loadResults.isNoteContentReloaded(this.noteId)) {
            this.refresh();
        }
    }
}

module.exports = new ResidentsWidget();