from __future__ import annotations

import itertools
from collections.abc import MutableSequence, MutableSet, Sequence
from typing import TYPE_CHECKING, AbstractSet, Any, Iterable, Iterator, overload

from trilium_client.models.note import Note as EtapiNoteModel

from ..branch import Branch
from ..entity.entity import normalize_entities
from .extension import BaseEntityList, BaseEntitySet, NoteExtension

if TYPE_CHECKING:
    from ..note import Note

__all__ = [
    "Branches",
    "ParentBranches",
    "ChildBranches",
    "ParentNotes",
    "ChildNotes",
]


def normalize_tuple(note_spec: Note | tuple[Note, str]) -> tuple[Note, str | None]:
    """
    Returns a tuple of (Note, prefix) where prefix may be None.
    """
    return note_spec if isinstance(note_spec, tuple) else (note_spec, None)


class BranchLookupMixin:
    """
    Enables looking up a branch given a related Note, either parent or child.
    """

    def __iter__(self) -> Iterator[Branch]: ...

    def lookup_branch(self, note: Note) -> Branch | None:
        """
        Lookup a branch given a related {obj}`Note`, either parent or child.
        """
        for branch in self:
            if note in {branch.parent, branch.child}:
                return branch
        return None


class NoteLookupMixin:
    """
    Enables looking up a note given a title, either parent or child.
    """

    def __iter__(self) -> Iterator[Note]: ...

    def lookup_note(self, title: str) -> Note | None:
        """
        Lookup a parent or child note given a title, or `None` if no such note exists.
        """
        for note in self:
            if note.title == title:
                return note
        return None


class ParentBranches(BaseEntitySet[Branch], BranchLookupMixin):
    """
    Interface to a note's parent branches.
    """

    _child_cls = Branch
    _owner_field = "_child"

    def __contains__(self, obj: object) -> bool:
        """
        Implement helper:
        note1 in note2.branches.parents
        """
        assert self._entity_set is not None
        return obj in self._entity_set

    @overload
    def __getitem__(self, i: int) -> Branch: ...

    @overload
    def __getitem__(self, i: slice) -> list[Branch]: ...

    def __getitem__(self, i: int | slice) -> Branch | list[Branch]:
        """
        Parent branches are inherently unsorted, but sort set by object id so traversal
        by index is deterministic.

        We can't use parent note_id since it may not be known yet.
        """
        assert self._entity_set is not None
        return sorted(self._entity_set, key=lambda branch: id(branch))[i]

    def _setup(self, model: EtapiNoteModel | None):
        if self._entity_set is not None:
            return
        self._entity_set = set()

        if model is None:
            return
        assert model.parent_branch_ids is not None

        for branch_id in model.parent_branch_ids:
            self._entity_set.add(Branch._from_id(branch_id, session=self._note.session))

    def _bind_entity(self, parent_branch: Branch):
        """
        When adding a new parent branch, also add to parent's child branches.
        """
        super()._bind_entity(parent_branch)

        assert parent_branch.child is self._note

        if parent_branch not in parent_branch.parent.branches.children:
            parent_branch.parent.branches.children.append(parent_branch)

    def _normalize(self, parent: Note | tuple[Note, str]) -> Branch:
        from .note import Note

        parent_, prefix = normalize_tuple(parent)

        assert isinstance(
            parent_, Note
        ), f"Unexpected type added to ParentBranches: {type(parent_)}"

        if parent_ in self._note.parents:
            # already in parents
            branch_obj = self._note.branches.parents.lookup_branch(parent_)
            assert branch_obj
        else:
            # create a new branch
            branch_obj = Branch(
                parent=parent_, child=self._note, session=self._note.session
            )

        if prefix is not None:
            branch_obj.prefix = prefix

        return branch_obj


class ChildBranches(BaseEntityList[Branch], BranchLookupMixin):
    """
    Interface to a note's child branches.
    """

    _child_cls = Branch
    _owner_field = "_parent"

    def _setup(self, model: EtapiNoteModel | None):
        if self._entity_list is not None:
            return
        self._entity_list = []

        if model is None:
            return
        assert model.child_branch_ids is not None

        # populate list of child branches
        for branch_id in model.child_branch_ids:
            if not branch_id.startswith("root__"):
                self._entity_list.append(
                    Branch._from_id(branch_id, session=self._note.session)
                )

        self._entity_list.sort(key=lambda x: x._position)

    def _bind_entity(self, child_branch: Branch):
        """
        When adding a new child branch, also add to child's parent branches.
        """
        super()._bind_entity(child_branch)

        assert child_branch.parent is self._note

        if child_branch not in child_branch.child.branches.parents:
            child_branch.child.branches.parents.add(child_branch)

    def _normalize(self, child: Note | tuple[Note, str]) -> Branch:
        from .note import Note

        child_, prefix = normalize_tuple(child)

        assert isinstance(
            child_, Note
        ), f"Unexpected type added to ChildBranches: {child_}, {type(child_)}"

        if child_ in self._note.children:
            # already in children
            branch_obj = self._note.branches.children.lookup_branch(child_)
            assert branch_obj
        else:
            # create a new branch
            branch_obj = Branch(
                parent=self._note, child=child_, session=self._note.session
            )

        if prefix is not None:
            branch_obj.prefix = prefix

        return branch_obj

    def _setattr(self, obj: Sequence[Branch | Note | tuple[Note, str]]):
        if self is obj:
            return
        normalized_list = [self._invoke_normalize(e) for e in obj]
        super()._setattr(normalized_list)


class Branches(NoteExtension, BranchLookupMixin):
    """
    Interface to a note's parent and child branches.

    This object is stateless; `Note.branches.parents` and `Note.branches.children` are
    the sources of truth for parent and child branches respectively.
    """

    _parents: ParentBranches
    _children: ChildBranches

    def __init__(self, note):
        super().__init__(note)
        self._parents = ParentBranches(note)
        self._children = ChildBranches(note)

    def __iter__(self) -> Iterator[Branch]:
        return iter(itertools.chain(self.parents, self.children))

    @overload
    def __getitem__(self, i: int) -> Branch: ...

    @overload
    def __getitem__(self, i: slice) -> list[Branch]: ...

    def __getitem__(self, i: int | slice) -> Branch | list[Branch]:
        return list(self)[i]

    @property
    def parents(self) -> ParentBranches:
        """
        Getter/setter for parent branches, modeled as a set.
        """
        self._model.setup_check()
        return self._parents

    @parents.setter
    def parents(self, val: AbstractSet[Branch]):
        self._parents._setattr(val)

    @property
    def children(self) -> ChildBranches:
        """
        Getter/setter for child branches, modeled as a list.
        """
        self._model.setup_check()
        return self._children

    @children.setter
    def children(self, val: Sequence[Branch]):
        self._children._setattr(val)

    def _setattr(self, obj: Any):
        _ = obj
        raise AttributeError(
            "Ambiguous assignment: must specify branches.parents or branches.children"
        )


class ParentNotes(NoteExtension, MutableSet, NoteLookupMixin):
    """
    Interface to a note's parent notes.

    This object is stateless; `Note.branches.parents` is the source of truth for parent
    branches.
    """

    def __iadd__(
        self,
        parent: Note | Iterable[Note],
    ) -> ParentNotes:
        """
        Implement helper:

        note.parents += parent_note
        """
        parents = normalize_entities(parent)
        self._note.branches.parents |= {self._normalize_branch(n) for n in parents}
        return self

    def __contains__(self, obj: object) -> bool:
        """
        Implement helper:

        parent_note in note.parents
        """
        return any(obj is b.parent for b in self._note.branches.parents)

    def __iter__(self) -> Iterator[Note]:
        return iter(b._parent for b in self._note.branches.parents if b._parent)

    def __len__(self):
        return len(self._note.branches.parents)

    @overload
    def __getitem__(self, i: int) -> Note: ...

    @overload
    def __getitem__(self, i: slice) -> list[Note]: ...

    def __getitem__(self, i: int | slice) -> Note | list[Note]:
        """
        Return parent Note of Branch given by index.

        Not required for a set, but used to access the provided index of the serialized
        parent branches.
        """
        parent_branches = self._note.branches.parents[i]
        if isinstance(i, int):
            assert isinstance(parent_branches, Branch)
            return parent_branches.parent
        else:
            assert isinstance(parent_branches, list)
            return [b.parent for b in parent_branches]

    def add(self, value: Note):
        self._note.branches.parents.add(self._normalize_branch(value))

    def discard(self, value: Note):
        self._note.branches.parents.discard(self._normalize_branch(value))

    def _setattr(self, obj: AbstractSet[Note]):
        self._note.branches.parents = {self._normalize_branch(n) for n in obj}

    def _normalize_branch(self, parent: Note) -> Branch:
        return normalize_parent_branch(self._note, parent)


class ChildNotes(NoteExtension, MutableSequence, NoteLookupMixin):
    """
    Interface to a note's child notes.

    This object is stateless; `Note.branches.children` is the source of truth for child
    branches.
    """

    def __iadd__(
        self,
        child: Note | Iterable[Note],
    ) -> ChildNotes:
        """
        Implement helper:

        note.children += branch_spec
        """
        children = normalize_entities(child)
        child_branches = [self._note.branches.children._normalize(c) for c in children]
        self._note.branches.children += child_branches
        return self

    def __iter__(self) -> Iterator[Note]:
        return iter([b._child for b in self._note.branches.children if b._child])

    def __contains__(self, obj: object) -> bool:
        """
        Implement helper:

        note2 in note1.children
        """
        return any(obj is b.child for b in self._note.branches.children)

    @overload
    def __getitem__(self, i: int) -> Note: ...

    @overload
    def __getitem__(self, i: slice) -> list[Note]: ...

    def __getitem__(self, i: int | slice) -> Note | list[Note]:
        assert isinstance(i, (int, slice))

        if isinstance(i, int):
            return self._note.branches.children[i].child
        else:
            return [b.child for b in self._note.branches.children[i]]

    @overload
    def __setitem__(self, i: int, value: Note): ...

    @overload
    def __setitem__(self, i: slice, value: Iterable[Note]): ...

    def __setitem__(self, i: int | slice, value: Note | Iterable[Note]):
        if isinstance(i, int):
            assert isinstance(value, Note)
            self._note.branches.children[i] = self._normalize_branch(value)
        else:
            assert isinstance(value, Iterable)
            self._note.branches.children[i] = [self._normalize_branch(n) for n in value]

    @overload
    def __delitem__(self, i: int): ...

    @overload
    def __delitem__(self, i: slice): ...

    def __delitem__(self, i: int | slice):
        del self._note.branches.children[i]

    def __len__(self):
        return len(self._note.branches.children)

    def insert(self, index: int, value: Note):
        self._note.branches.children.insert(index, self._normalize_branch(value))

    def _setattr(self, obj: Sequence[Note]):
        self._note.branches.children = [self._normalize_branch(n) for n in obj]

    def _normalize_branch(self, child: Note) -> Branch:
        return normalize_child_branch(self._note, child)


def normalize_parent_branch(note: Note, parent: Branch | Note) -> Branch:
    if isinstance(parent, Branch):
        return parent
    for branch in note.branches.parents:
        if branch.parent is parent:
            return branch
    return Branch(parent=parent, child=note, session=note.session)


def normalize_child_branch(note: Note, child: Branch | Note) -> Branch:
    if isinstance(child, Branch):
        return child
    for branch in note.branches.children:
        if branch.child is child:
            return branch
    return Branch(parent=note, child=child, session=note.session)
