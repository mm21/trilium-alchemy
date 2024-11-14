from __future__ import annotations

from collections.abc import MutableSequence, MutableSet
from typing import TYPE_CHECKING, Iterable, Iterator, cast

from trilium_client.models.note import Note as EtapiNoteModel

from ..branch import Branch
from ..entity.entity import normalize_entities
from ..entity.model import require_setup_prop
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


def normalize_tuple(
    note_spec: Note | tuple[Note, str]
) -> tuple[Note, str | None]:
    """
    Returns a tuple of (Note, prefix) where prefix may be None.
    """

    if type(note_spec) is tuple:
        note, prefix = note_spec
    else:
        note = note_spec
        prefix = None

    return (note, prefix)


class BranchLookup:
    """
    Enables looking up a branch given a related Note, either parent or child.
    """

    def lookup(self, note: Note) -> Branch:
        """
        Lookup a branch given a related {obj}`Note`, either parent or child.

        :raises ValueError: If note is not a parent or child of any branch
        """
        assert note is not None

        for branch in cast(Iterable[Branch], self):
            if note in {branch.parent, branch.child}:
                return branch

        raise ValueError(f"Note {note} not in parents or children of {self}")


class ParentBranches(BaseEntitySet[Branch], BranchLookup):
    """
    Interface to a note's parent branches.
    """

    _child_cls = Branch
    _owner_field = "_child"

    def __contains__(self, val: Branch | Note) -> bool:
        """
        Implement helper:
        note1 in note2.branches.parents
        """

        from .note import Note

        if isinstance(val, Branch):
            return val in self._entity_set
        elif isinstance(val, Note):
            return val in {branch.parent for branch in self._entity_set}
        else:
            raise ValueError(f"Unexpected type: {val}")

    def __getitem__(self, key: int) -> Branch:
        """
        Parent branches are inherently unsorted, but sort set by object id
        so traversal by index is deterministic.
        We can't use parent note_id since it may not be known yet.
        """
        return sorted(self._entity_set, key=lambda branch: id(branch))[key]

    def _setup(self, model: EtapiNoteModel | None):
        if self._entity_set is None:
            self._entity_set = set()

            if model is not None:
                # populate set of parent branches
                for branch_id in model.parent_branch_ids:
                    self._entity_set.add(
                        Branch._from_id(branch_id, session=self._note.session)
                    )

    def _bind_entity(self, parent_branch: Branch):
        """
        When adding a new parent branch, also add to parent's child branches.
        """

        super()._bind_entity(parent_branch)

        assert parent_branch.child is self._note

        if parent_branch not in parent_branch.parent.branches.children:
            parent_branch.parent.branches.children.append(parent_branch)

    def _normalize(self, parent: Note) -> Branch:
        from .note import Note

        parent, prefix = normalize_tuple(parent)

        assert isinstance(
            parent, Note
        ), f"Unexpected type added to ParentBranches: {type(parent)}"

        if parent in self._note.parents:
            # already in parents
            branch_obj = self._note.branches.parents.lookup(parent)
        else:
            # create a new branch
            branch_obj = Branch(
                parent=parent, child=self._note, session=self._note.session
            )

        if prefix is not None:
            branch_obj.prefix = prefix

        return branch_obj


class ChildBranches(BaseEntityList[Branch], BranchLookup):
    """
    Interface to a note's child branches.
    """

    _child_cls = Branch
    _owner_field = "_parent"

    def __contains__(self, val: Branch | Note):
        """
        Implement helper:
        note2 in note1.branches.children
        """
        from .note import Note

        if isinstance(val, Branch):
            return val in self._entity_list
        elif isinstance(val, Note):
            return val in {branch.child for branch in self._entity_list}
        else:
            raise ValueError(f"Unexpected type: {val}")

    def _setup(self, model: EtapiNoteModel | None):
        if self._entity_list is None:
            self._entity_list = []

            if model is not None:
                # populate list of child branches
                for branch_id in model.child_branch_ids:
                    if not branch_id.startswith("root__"):
                        self._entity_list.append(
                            Branch._from_id(
                                branch_id, session=self._note.session
                            )
                        )

            # sort list by position
            self._entity_list.sort(key=lambda x: x._position)

    def _bind_entity(self, child_branch: Branch):
        """
        When adding a new child branch, also add to child's parent branches.
        """

        super()._bind_entity(child_branch)

        assert child_branch.parent is self._note

        if child_branch not in child_branch.child.branches.parents:
            child_branch.child.branches.parents.add(child_branch)

    def _normalize(self, child: Note) -> Branch:
        from .note import Note

        child, prefix = normalize_tuple(child)

        assert isinstance(
            child, Note
        ), f"Unexpected type added to ChildBranches: {child}, {type(child)}"

        if child in self._note.children:
            # already in children
            branch_obj = self._note.branches.children.lookup(child)
        else:
            # create a new branch
            branch_obj = Branch(
                parent=self._note, child=child, session=self._note.session
            )

        if prefix is not None:
            branch_obj.prefix = prefix

        return branch_obj

    def _get_position(self, index: int) -> int:
        if self._note.note_id == "root":
            base = self._note.session._root_position_base
        else:
            base = 0

        return super()._get_position(index, base=base)


class Branches(NoteExtension, BranchLookup):
    """
    Interface to a note's parent and child branches.

    This object is stateless; `Note.branches.parents` and
    `Note.branches.children` are the sources of truth
    for parent and child branches respectively.
    """

    _parents: ParentBranches
    _children: ChildBranches

    def __init__(self, note):
        super().__init__(note)

        self._parents = ParentBranches(note)
        self._children = ChildBranches(note)

    def __iter__(self) -> Iterator[Branch]:
        return iter(list(self.parents) + list(self.children))

    def __getitem__(self, key: int) -> Branch:
        return list(self)[key]

    @require_setup_prop
    @property
    def parents(self) -> ParentBranches:
        """
        Getter/setter for parent branches, modeled as a set.
        """
        return self._parents

    @parents.setter
    def parents(self, val: set[Branch]):
        self._parents._setattr(val)

    @require_setup_prop
    @property
    def children(self) -> ChildBranches:
        """
        Getter/setter for child branches, modeled as a list.
        """
        return self._children

    @children.setter
    def children(self, val: list[Branch]):
        self._children._setattr(val)

    def _setattr(self, val: list[Branch]):
        raise Exception(
            "Ambiguous assignment: must specify branches.parents or branches.children"
        )


class ParentNotes(NoteExtension, MutableSet):
    """
    Interface to a note's parent notes.

    This object is stateless; `Note.branches.parents` is the source of
    truth for parent branches.
    """

    def __iadd__(
        self,
        parent: Note | tuple[Note, str] | Iterable[Note | tuple[Note, str]],
    ) -> ParentNotes:
        """
        Implement helper:

        note.parents += branch_spec
        """
        self._note.branches.parents |= normalize_entities(
            parent, collection_cls=set
        )
        return self

    def __contains__(self, val: Note):
        """
        Implement helper:

        note2 in note1.parents
        """
        return val in self._note.branches.parents

    def __iter__(self) -> Iterator[Note]:
        return iter([b.parent for b in self._note.branches.parents if b.parent])

    def __len__(self):
        return len(self._note.branches.parents)

    def __getitem__(self, key: int) -> Note:
        """
        Return parent Note of Branch given by index.
        """
        return self._note.branches.parents[key].parent

    def add(self, value: Note):
        self._note.branches.parents.add(value)

    def discard(self, value: Note):
        for branch in self._note.branches.parents:
            if value is branch.parent:
                self._note.branches.parents.discard(branch)
                break

    def _setattr(self, val: set[Note]) -> None:
        self._note.branches.parents = val


class ChildNotes(NoteExtension, MutableSequence):
    """
    Interface to a note's child notes.

    This object is stateless; `Note.branches.children` is the source of
    truth for child branches.
    """

    def __iadd__(
        self,
        child: Note | tuple[Note, str] | Iterable[Note | tuple[Note, str]],
    ) -> ChildNotes:
        """
        Implement helper:

        note.children += branch_spec
        """
        self._note.branches.children += normalize_entities(child)
        return self

    def __iter__(self) -> Iterator[Note]:
        return iter([b.child for b in self._note.branches.children if b.child])

    def __contains__(self, val: Note) -> bool:
        """
        Implement helper:
        note2 in note1.children
        """
        return val in self._note.branches.children

    def __getitem__(self, i: int) -> Note:
        """
        Accessor for child note.
        """
        return self._note.branches.children[i].child

    def __setitem__(self, i: int, value: Note):
        self._note.branches.children[i] = value

    def __delitem__(self, i: int):
        del self._note.branches.children[i].child

    def __len__(self):
        return len(self._note.branches.children)

    def insert(
        self,
        i: int,
        val: Note,
    ):
        self._note.branches.children.insert(i, val)

    def _setattr(self, val: list[Note]) -> None:
        self._note.branches.children = val
