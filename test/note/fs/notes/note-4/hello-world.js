const TPL = `<div style="padding: 10px; border-top: 1px solid var(--main-border-color); contain: none;">
    <strong>Hello, world!</strong>
</div>`;

class HelloWorldWidget extends api.NoteContextAwareWidget {
    get position() { return 100; } // higher value means position towards the bottom/right

    get parentWidget() { return 'center-pane'; }

    isEnabled() {
        return super.isEnabled()
            && this.note.type === 'text';
    }

    doRender() {
        this.$widget = $(TPL);
        return this.$widget;
    }

    async refreshWithNote(note) {}

    async entitiesReloadedEvent({loadResults}) {
        if (loadResults.isNoteContentReloaded(this.noteId)) {
            this.refresh();
        }
    }
}

module.exports = new HelloWorldWidget();