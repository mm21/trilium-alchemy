from __future__ import annotations

from abc import abstractmethod
from collections.abc import MutableSequence, Sequence
from typing import (
    TYPE_CHECKING,
    Any,
    Iterator,
    TypeVar,
    get_args,
    get_origin,
    overload,
)

from ...attribute.attribute import BaseAttribute

if TYPE_CHECKING:
    from ..note import Note


class AttributeListMixin[AttributeT: BaseAttribute]:
    _value_name: str
    """
    Name of attribute containing the value, i.e. "value" or "target".
    """

    def __contains__(self, obj: Any) -> bool:
        if isinstance(obj, str):
            return self.get(obj) is not None
        return super().__contains__(obj)

    def get(self, name: str) -> AttributeT | None:
        """
        Get first attribute with provided name, or `None` if none exist.
        """
        for a in self._attr_list:
            if a.name == name:
                return a
        return None

    def get_all(self, name: str) -> list[AttributeT]:
        """
        Get all attributes with provided name.
        """
        return [a for a in self._attr_list if a.name == name]

    @property
    def _writeable_attr_list(self) -> list[AttributeT]:
        """
        Attribute list which can be written to, i.e. owned attributes.
        """
        return self._attr_list

    def _get_writeable(self, name: str) -> AttributeT | None:
        """
        Get first writeable attribute with provided name.
        """
        for a in self._writeable_attr_list:
            if a.name == name:
                return a
        return None

    def _get_all_writeable(self, name: str) -> list[AttributeT]:
        """
        Get all writeable attributes with provided name.
        """
        return [a for a in self._writeable_attr_list if a.name == name]

    def _set_value(self, name: str, val: Any, inheritable: bool):
        attr = self._get_writeable(name)

        if attr is None:
            attr = self._create_attr(name)

        setattr(attr, self._value_name, val)
        attr.inheritable = inheritable

    def _set_values(
        self, name: str, vals: list[Any], inheritable: bool = False
    ):
        attrs = self._get_all_writeable(name)

        if len(vals) > len(attrs):
            # need to create new attributes
            for _ in range(len(vals) - len(attrs)):
                attrs.append(self._create_attr(name))

        elif len(attrs) > len(vals):
            # need to delete attributes
            for _ in range(len(attrs) - len(vals)):
                # pop from end
                attr = attrs.pop()
                attr.delete()

        for attr, val in zip(attrs, vals):
            setattr(attr, self._value_name, val)
            attr.inheritable = inheritable

    def _append_value(self, name: str, val: Any, inheritable: bool):
        attr = self._create_attr(name)
        setattr(attr, self._value_name, val)
        attr.inheritable = inheritable

    @property
    @abstractmethod
    def _attr_list(self) -> list[AttributeT]:
        """
        Overridden by subclass.
        """
        ...

    @property
    @abstractmethod
    def _note_getter(self) -> Note:
        """
        Overridden by subclass.
        """
        ...

    @abstractmethod
    def _create_attr(self, name: str) -> AttributeT:
        """
        Overridden by subclass to create an attribute of the respective type,
        already bound to this note.
        """
        ...


class BaseFilteredAttributes[AttributeT: BaseAttribute](
    AttributeListMixin[AttributeT]
):
    """
    Base class to represent attributes filtered by type, with capability to
    further filter by name.
    """

    _filter_cls: type[AttributeT]

    def __init_subclass__(cls: type[BaseFilteredAttributes]):
        """
        Set _filter_cls based on the type parameter.
        """

        def get_filter_cls() -> type[AttributeT] | None:
            for base in cls.__orig_bases__:
                origin = get_origin(base)

                if origin is None:
                    continue

                assert issubclass(origin, BaseFilteredAttributes)

                args = get_args(base)
                assert len(args) > 0

                for arg in args:
                    if isinstance(arg, TypeVar):
                        # have a TypeVar, look up its bound
                        if issubclass(arg.__bound__, BaseAttribute):
                            return arg.__bound__

                    elif issubclass(arg, BaseAttribute):
                        return arg

        filter_cls = get_filter_cls()
        assert filter_cls is not None

        cls._filter_cls = filter_cls

    def __iter__(self) -> Iterator[AttributeT]:
        return iter(self._attr_list)

    def __len__(self) -> int:
        return len(self._attr_list)

    @overload
    def __getitem__(self, i: int) -> AttributeT:
        ...

    @overload
    def __getitem__(self, i: slice) -> list[AttributeT]:
        ...

    def __getitem__(self, i: int | slice) -> AttributeT | list[AttributeT]:
        return self._attr_list[i]

    def _filter_list(self, attrs: list[BaseAttribute]) -> list[AttributeT]:
        return [a for a in attrs if isinstance(a, self._filter_cls)]


class BaseDerivedFilteredAttributes[AttributeT: BaseAttribute](
    BaseFilteredAttributes[AttributeT]
):
    _note_obj: Note

    def __init__(self, note: Note):
        self._note_obj = note

    @property
    def _note_getter(self) -> Note:
        return self._note_obj


class BaseOwnedFilteredAttributes[AttributeT: BaseAttribute](
    BaseDerivedFilteredAttributes[AttributeT],
    MutableSequence[AttributeT],
):
    @property
    def _attr_list(self) -> list[AttributeT]:
        return self._filter_list(list(self._note_getter.attributes.owned))

    def __setitem__(self, i: int, val: AttributeT):
        self._note_getter.attributes.owned[i] = val

    def __delitem__(self, i: int):
        del self._note_getter.attributes.owned[i]

    def insert(self, i: int, val: AttributeT):
        self._note_getter.attributes.owned.insert(i, val)


class BaseInheritedFilteredAttributes[AttributeT: BaseAttribute](
    BaseDerivedFilteredAttributes[AttributeT],
    Sequence[AttributeT],
):
    @property
    def _attr_list(self) -> list[AttributeT]:
        return self._filter_list(list(self._note_getter.attributes.inherited))


class BaseCombinedFilteredAttributes[AttributeT: BaseAttribute](
    BaseDerivedFilteredAttributes[AttributeT], Sequence[AttributeT]
):
    @property
    def _attr_list(self) -> list[AttributeT]:
        return self._filter_list(
            list(self._note_getter.attributes.owned)
            + list(self._note_getter.attributes.inherited)
        )

    @property
    def _writeable_attr_list(self) -> list[AttributeT]:
        return self._filter_list(list(self._note_getter.attributes.owned))
