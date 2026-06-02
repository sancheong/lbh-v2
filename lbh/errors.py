class LBHError(Exception):
    """Base LBH V2 error."""


class ValidationError(LBHError):
    """Raised when an input contract is invalid."""


class TaskStateError(LBHError):
    """Raised when the task state blocks the requested operation."""
