from __future__ import annotations

from graphlib import TopologicalSorter
from typing import TYPE_CHECKING, Generator

from trilium_client.exceptions import NotFoundException
from trilium_client.models.create_note_def import CreateNoteDef
from trilium_client.models.note import Note as EtapiNoteModel
from trilium_client.models.note_with_branch import NoteWithBranch

from ..entity.model import BaseDriver, BaseEntityModel

if TYPE_CHECKING:
    from .note import Note


class NoteDriver(BaseDriver):
    @property
    def note(self) -> Note:
        return self.entity


class EtapiDriver(NoteDriver):
    def fetch(self) -> EtapiNoteModel | None:
        model: EtapiNoteModel | None

        try:
            model = self.session.api.get_note_by_id(self.note.note_id)
        except NotFoundException:
            model = None

        return model

    def flush_create(
        self, sorter: TopologicalSorter
    ) -> Generator[EtapiNoteModel, None, None]:
        # pick first parent branch according to serialization provided by
        # ParentBranches
        parent_branch = self.note.branches.parents[0]

        # ensure parent note exists (should be taken care by sorter)
        assert parent_branch.parent._model.exists

        # get note fields
        model_dict = self.note._model._working.copy()

        model_dict["parent_note_id"] = parent_branch.parent.note_id

        # for simplicity, always init content as empty string and let
        # content extension set content later (handling text/bin)
        # - API generated from openapi does not handle binary content
        model_dict["content"] = ""

        if self.note.note_id is not None:
            model_dict["note_id"] = self.note.note_id

        # assign writeable fields from branch
        for field in parent_branch._model.fields_update:
            model_dict[field] = parent_branch._model.get_field(field)

        model = CreateNoteDef(**model_dict)

        # invoke api
        response: NoteWithBranch = self.session.api.create_note(model)

        # add parent branch to cache before note is loaded
        # (branches will be instantiated)
        if parent_branch.branch_id is None:
            parent_branch._set_entity_id(response.branch.branch_id)
        else:
            assert parent_branch.branch_id == response.branch.branch_id

        # mark parent as clean
        parent_branch._set_clean()

        # if parent was added to sorter, mark it as done
        # (it may not have been part of sorter, even though it's dirty, if e.g.
        # the user called .flush() directly)
        try:
            sorter.done(parent_branch)
        except ValueError:
            pass

        # return note model for processing
        yield response.note

        # load parent branch model
        parent_branch._model.setup(response.branch)

    def flush_update(self, sorter: TopologicalSorter) -> EtapiNoteModel:
        # assemble note model based on needed fields
        model = EtapiNoteModel(**self.note._model.get_fields_changed())

        # invoke api and return new model
        model_new: EtapiNoteModel = self.session.api.patch_note_by_id(
            self.note.note_id, model
        )
        assert model_new is not None

        return model_new

    def flush_delete(self, sorter: TopologicalSorter):
        self.session.api.delete_note_by_id(self.note.note_id)

        # mark attributes as clean
        for attr in self.note.attributes.owned:
            if attr._is_dirty:
                attr._set_clean()
                sorter.done(attr)

        # mark child branches as clean
        for branch in self.note.branches.children:
            if branch._is_dirty:
                branch._set_clean()
                sorter.done(branch)


class FileDriver(NoteDriver):
    pass


class NoteModel(BaseEntityModel):
    etapi_model = EtapiNoteModel

    etapi_driver_cls = EtapiDriver

    file_driver_cls = FileDriver

    field_entity_id = "note_id"

    fields_update = [
        "title",
        "type",
        "mime",
    ]

    # this is where the actual defaults come from; defaults in
    # Note.__init__ are only for documentation
    fields_default = {
        "title": "new note",
        "type": "text",
        "mime": "text/html",
    }
