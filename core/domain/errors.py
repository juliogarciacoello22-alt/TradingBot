"""Errors raised only when domain contracts or transitions are invalid."""


class DomainContractError(ValueError):
    """Base class for invalid domain data."""


class InvalidIdentifierError(DomainContractError):
    """A caller supplied a malformed explicit identifier."""


class InvalidTimestampError(DomainContractError):
    """A timestamp is naive or otherwise unsuitable for UTC storage."""


class InvalidStateTransitionError(DomainContractError):
    """A requested transition violates a contract state machine."""


class InvariantViolationError(DomainContractError):
    """Related fields violate a domain invariant."""


class SerializationError(DomainContractError):
    """A value cannot be represented by canonical in-memory JSON."""
