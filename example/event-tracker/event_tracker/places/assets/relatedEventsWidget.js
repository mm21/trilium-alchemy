const TPL = `<div style="padding: 10px; border-top: 1px solid var(--main-border-color); contain: none;">
    <strong>Related events:</strong>
    <div class="related-events"></div>
</div>`;

class RelatedEventsWidget extends api.NoteContextAwareWidget {
    get position() { return 100; } // higher value means position towards the bottom/right

    get parentWidget() { return 'center-pane'; }

    isEnabled() {
        return super.isEnabled()
            && this.note.type === 'text'
            && this.note.hasLabel('place');
    }

    doRender() {
        this.$widget = $(TPL);
        this.$relatedEvents = this.$widget.find('.related-events');
        return this.$widget;
    }

    async refreshWithNote(note) {
        formatEvents(this.$relatedEvents, await getEventsByPlace(note));
    }

    async entitiesReloadedEvent({loadResults}) {
        if (loadResults.isNoteContentReloaded(this.noteId)) {
            this.refresh();
        }
    }
}

module.exports = new RelatedEventsWidget();