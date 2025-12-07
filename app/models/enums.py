"""
Enums for document change tracking.
"""

from enum import Enum


class ChangeType(str, Enum):
    """Type of change detected between documents."""
    ADDED = "added"
    DELETED = "deleted"
    MODIFIED = "modified"


class ImpactLevel(str, Enum):
    """Business impact level of a change."""
    CRITICAL = "critical"
    MEDIUM = "medium"
    LOW = "low"
