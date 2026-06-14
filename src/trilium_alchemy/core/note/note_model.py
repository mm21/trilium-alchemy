from __future__ import annotations

from graphlib import TopologicalSorter
from typing import TYPE_CHECKING, Generator

from trilium_client.exceptions import NotFoundException
from trilium_client.models.create_note_def import CreateNoteDef
from trilium_client.models.note import Note as EtapiNoteModel

from ..entity.model import BaseDriver, BaseEntityModel

if TYPE_CHECKING:
    from .note import Note


class NoteDriver(BaseDriver[EtapiNoteModel]):
    @property
    def note(self) -> Note:
        from .note import Note

        assert isinstance(self.entity, Note)
        return self.entity

    def fetch(self) -> EtapiNoteModel | None:
        assert self.note.note_id
        model: EtapiNoteModel | None = None
        try:
            model = self.session.api.get_note_by_id(self.note.note_id)
        except NotFoundException:
            pass
        return model

    def flush_create(
        self, sorter: TopologicalSorter
    ) -> Generator[EtapiNoteModel, None, None]:
        # pick first parent branch according to serialization provided by
        # ParentBranches
        parent_branch = self.note.branches.parents[0]

        # ensure parent note exists (should be taken care by sorter)
        assert parent_branch.parent._model.exists
        assert self.note._model.working_data

        # get note fields
        model_dict = self.note._model.working_data.copy()

        model_dict["parent_note_id"] = parent_branch.parent.note_id

        # for simplicity, always init content as empty string and let
        # content extension set content later (handling text/bin)
        # - API generated from openapi does not handle binary content
        model_dict["content"] = ""

        if self.note.note_id is not None:
            model_dict["note_id"] = self.note.note_id

        # assign writeable fields from branch
        for field in parent_branch._model.update_fields:
            model_dict[field] = parent_branch._model.get_field(field, object)

        model = CreateNoteDef(**model_dict)

        # invoke api
        response = self.session.api.create_note(model)
        assert response.note
        assert response.branch
        assert response.branch.branch_id

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
        _ = sorter
        assert self.note.note_id

        # assemble note model based on needed fields
        model = EtapiNoteModel(**self.note._model.get_changed_fields())

        # invoke api and return new model
        new_model = self.session.api.patch_note_by_id(self.note.note_id, model)
        return new_model

    def flush_delete(self, sorter: TopologicalSorter):
        assert self.note.note_id

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


class NoteModel(BaseEntityModel):
    @property
    def etapi_model(self) -> type[EtapiNoteModel]:
        return EtapiNoteModel

    @property
    def driver_cls(self) -> type[NoteDriver]:
        return NoteDriver

    @property
    def entity_id_field(self) -> str:
        return "note_id"

    @property
    def update_fields(self) -> list[str]:
        return ["title", "type", "mime"]

    @property
    def default_fields(self) -> dict:
        # this is where the actual defaults come from; defaults in
        # Note.__init__ are only for documentation
        return {"title": "new note", "type": "text", "mime": "text/html"}
