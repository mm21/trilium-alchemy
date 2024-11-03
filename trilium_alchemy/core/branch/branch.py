from __future__ import annotations

import logging
from graphlib import TopologicalSorter
from typing import TYPE_CHECKING

from trilium_client.exceptions import NotFoundException, ServiceException
from trilium_client.models.branch import Branch as EtapiBranchModel

from ..entity.entity import EntityIdDescriptor, OrderedEntity
from ..entity.model import (
    BaseDriver,
    BaseEntityModel,
    FieldDescriptor,
    ReadOnlyDescriptor,
    ReadOnlyFieldDescriptor,
    WriteOnceDescriptor,
)
from ..entity.types import State
from ..exceptions import _assert_validate
from ..session import Session

if TYPE_CHECKING:
    from ..note.note import Note

__all__ = [
    "Branch",
]


class BranchDriver(BaseDriver):
    @property
    def branch(self):
        return self.entity


class EtapiDriver(BranchDriver):
    def fetch(self) -> EtapiBranchModel | None:
        model: EtapiBranchModel | None

        try:
            model = self.branch.session.api.get_branch_by_id(
                self.branch.branch_id
            )

            # Trilium internally sets prefix = null when it's an empty string;
            # null becomes None, so translate None to '' here
            if model.prefix is None:
                model.prefix = ""

        except NotFoundException as e:
            model = None

        return model

    def flush_create(self, sorter: TopologicalSorter):
        assert self.branch.child.note_id is not None

        model = EtapiBranchModel(
            note_id=self.branch.child.note_id,
            parent_note_id=self.branch.parent.note_id,
            **self.branch._model._working,
        )

        model_new = self.session.api.post_branch(model)
        assert model_new is not None

        # if we had a branch_id at this point, make sure it's the same as the
        # one generated by Trilium
        if self.branch.branch_id is not None:
            assert self.branch.branch_id == model_new.branch_id

        return model_new

    def flush_update(self, sorter: TopologicalSorter):
        model = EtapiBranchModel(**self.branch._model.get_fields_changed())

        model_new: EtapiBranchModel = self.session.api.patch_branch_by_id(
            self.branch.branch_id, model
        )
        assert model_new is not None

        return model_new

    def flush_delete(self, sorter: TopologicalSorter):
        try:
            self.session.api.delete_branch_by_id(self.branch.branch_id)
        except ServiceException as e:
            # saw this once but haven't been able to repro
            logging.error(f"Failed to delete branch: {e}")


class FileDriver(BranchDriver):
    pass


class BranchModel(BaseEntityModel):
    etapi_model = EtapiBranchModel

    etapi_driver_cls = EtapiDriver

    file_driver_cls = FileDriver

    field_entity_id = "branch_id"

    fields_update = [
        "prefix",
        "is_expanded",
        "note_position",
    ]

    fields_default = {
        "prefix": "",
        "is_expanded": False,
        "note_position": 0,
    }


class Branch(OrderedEntity[BranchModel]):
    """
    Encapsulates a branch, a parent-child association between notes.

    Implicitly created by operations documented in {obj}`Note` and
    {obj}`Branches`. Can also be explicitly created and added to a note
    using its `+=`{l=python} operator:

    ```
    # add child note with prefix
    note += Branch(child=Note(title="Child note"), prefix="Child branch prefix")

    # add parent note (cloning the note) with prefix
    note += Branch(parent=session.root, prefix="Parent branch prefix")
    ```
    """

    branch_id: str = EntityIdDescriptor()
    """
    Read-only access to `branchId`.
    """

    parent: Note = WriteOnceDescriptor("_parent", validator="_validate")
    """
    Parent note.
    """

    child: Note = WriteOnceDescriptor("_child", validator="_validate")
    """
    Child note.
    """

    prefix: str = FieldDescriptor("prefix")
    """
    Branch prefix.
    """

    expanded: bool = FieldDescriptor("is_expanded")
    """
    Whether child note (as a folder) appears expanded in UI.
    """

    utc_date_modified: str = ReadOnlyFieldDescriptor("utc_date_modified")
    """
    UTC modified datetime, e.g. `2021-12-31 19:18:11.939Z`.
    """

    position: int = ReadOnlyDescriptor("_position")
    """
    Read-only access to position of this branch.

    ```{note}
    This is maintained automatically based on the order of this branch
    in the parent note's {obj}`Note.branches.children <Note.branches>` list.
    ```
    """

    _model_cls = BranchModel

    _parent: Note = None
    _child: Note = None
    _position: int = FieldDescriptor("note_position")

    def __new__(cls, *_, **kwargs) -> Branch:
        return super().__new__(
            cls,
            entity_id=kwargs.get("branch_id"),
            session=kwargs.get("session"),
            create=kwargs.get("create"),
        )

    def __init__(
        self,
        parent: Note = None,
        child: Note = None,
        prefix: str = "",
        expanded: bool = False,
        session: Session = None,
        **kwargs,
    ):
        """
        :param parent: Parent note
        :param child: Child note
        :param prefix: Branch specific title prefix for child note
        :param expanded: `True`{l=python} if child note (as a folder) appears expanded in UI
        :param kwargs: Internal only
        """

        branch_id = kwargs.pop("branch_id", None)
        create = kwargs.pop("create", None)

        assert len(kwargs) == 0, f"Unexpected kwargs: {kwargs}"

        super().__init__(
            entity_id=branch_id,
            session=session,
            create=create,
        )

        self._set_attrs(
            parent=parent,
            child=child,
        )

        """
        create can be True/False/None:
            True: when branch_id not provided (created by user)
            False: when loaded by branch_id
            None: when loaded by declarative note definition
                (don't care if it exists or not)
        """
        if create is not False:
            # set model fields for newly created or declarative definition
            self._set_attrs(prefix=prefix, expanded=expanded)

    @property
    def _str_short(self):
        return f"Branch(parent={self.parent}, child={self.child}, prefix={self.prefix}, expanded={self.expanded}, position={self._position}, branch_id={self.branch_id})"

    @property
    def _str_safe(self):
        str_parent = self._parent._str_safe if self._parent else None
        str_child = self._child._str_safe if self._child else None
        return f"Branch(parent={str_parent}, child={str_child}, branch_id={self._entity_id}, id={id(self)})"

    @classmethod
    def _from_id(self, branch_id: str, session: Session = None):
        """
        Constructor to create instance of existing Branch given branch_id.

        The default is for Branch() to create a new branch; use this to load an
        existing one.
        """

        # This is different than attributes since when getting a note from the
        # server, an Attribute model is returned for each attribute. Branches,
        # however, are returned by id only.

        return Branch(
            branch_id=branch_id,
            session=session,
            create=False,
        )

    # TODO: only use case for this right now is test code, so not
    # not high priority
    @classmethod
    def _from_model(self, model: EtapiBranchModel):
        ...

    @classmethod
    def _gen_branch_id(cls, parent: Note, child: Note) -> str:
        from ..note.note import Note

        assert isinstance(parent, Note)
        assert isinstance(child, Note)

        assert parent.note_id is not None
        assert child.note_id is not None

        return f"{parent.note_id}_{child.note_id}"

    def _setup(self, model: EtapiBranchModel):
        from ..note.note import Note

        # in Trilium, root note has a parent branch to a
        # non-existent note with id 'none'; handle this case here
        if model.parent_note_id == "none":
            assert self._parent is None
            assert model.note_id == "root"
        else:
            self.parent = Note(
                note_id=model.parent_note_id, session=self._session
            )

        self.child = Note(note_id=model.note_id, session=self._session)

    def _flush_check(self):
        _assert_validate(self.child is not None, "No child set")

        if self.child.note_id != "root":
            _assert_validate(self.parent is not None, "No parent set")

        if self.state is not State.DELETE:
            # make sure this branch was added to parents of child
            _assert_validate(
                self in self.child.branches.parents,
                f"Not added to parents of child {self.child}",
            )

            # make sure this branch was added to children of parents
            if self.child.note_id != "root":
                _assert_validate(
                    self in self.parent.branches.children,
                    f"Not added to children of parent {self.parent}",
                )

    @property
    def _dependencies(self):
        deps = set()

        # branch depends on both parent and child
        deps |= {self.child}

        if self.parent is None:
            assert self.child.note_id == "root"
        else:
            deps |= {self.parent}

            if self._state is not State.DELETE:
                # get index of this branch
                index = self.parent.branches.children.index(self)

                # add dependency on branches before this one to flush
                # them in order and enable more deterministic sequence
                # (e.g. to make failures more reproducible)
                # they can still be created out of order since notes create
                # a parent branch when they're created, but this at least
                # flushes clones in a predictable order
                if index != 0:
                    for i in range(index):
                        deps.add(self.parent.branches.children[i])

                        # corresponding child note
                        deps.add(self.parent.branches.children[i].child)

        return deps

    def _validate(self):
        """
        Ensure there isn't already a Branch between parent and child.
        """

        if self._parent and self._child:
            # collect cached and newly created branches
            branches = {
                entity
                for entity_id, entity in self._session._cache.entity_map.items()
                if isinstance(entity, Branch)
            }

            branches |= {
                entity
                for entity in self._session._cache.dirty_set
                if isinstance(entity, Branch)
            }

            # traverse branches
            for branch in branches:
                if branch is self:
                    continue

                assert not (
                    branch._parent is self._parent
                    and branch._child is self._child
                ), f"Multiple branches mapping parent {self._parent._str_safe} to child {self._child._str_safe}: {self._str_safe}, {branch._str_safe}"
