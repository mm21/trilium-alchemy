__all__ = [
    "ReadOnlyError",
    "ValidationError",
]


class ReadOnlyError(Exception):
    """
    Raised when user attempts to write a field which is read-only.
    """

    def __init__(self, field, entity):
        super().__init__(
            self, f"Attempt to set read-only field {field} of {entity}"
        )


class ValidationError(Exception):
    """
    Raised upon flush when changes in unit of work are invalid or incompatible.

    Examples:

    - {obj}`Note` created with no parent
    - {obj}`Label` or {obj}`Relation` created but not assigned to a {obj}`Note`
    - {obj}`Branch` created but parent or child is not set
    """

    errors: list[str]

    def __init__(self, errors: list[str]):
        self.errors = errors
        errors_str = "\n".join([e for e in errors])
        super().__init__(self, f"Errors found during validation: {errors_str}")


class _ValidationError(Exception):
    """
    Raised internally during flush if there are any errors for this
    entity, but aggregated before raising ValidationErrors to user.
    """


def _assert_validate(cond: bool, *args):
    """
    Helper to raise a validation error if the condition is False.
    """
    if cond is not True:
        raise _ValidationError(*args)
