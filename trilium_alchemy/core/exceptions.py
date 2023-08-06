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

    def __init__(self, errors: list[Exception]):
        errors = "\n".join([str(e) for e in errors])
        super().__init__(self, f"Errors found during validation: {errors}")
