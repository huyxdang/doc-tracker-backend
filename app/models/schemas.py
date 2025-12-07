"""
Data models and schemas for document change tracking.
"""

from dataclasses import dataclass
from typing import List
from pydantic import BaseModel

from app.models.enums import ChangeType, ImpactLevel

@dataclass
class ContentBlock:
    """A single unit of document content."""
    index: int          # Position in document
    block_type: str     # "paragraph" or "table"
    content: str        # The actual text


@dataclass
class WordChange:
    """A single word-level change within a block."""
    change_type: str    # "added", "deleted", "replaced"
    old_text: str       # What was removed (empty if added)
    new_text: str       # What was added (empty if deleted)
    context: str        # Surrounding words for context


@dataclass
class Change:
    """A detected change between two documents."""
    change_id: int
    change_type: ChangeType
    block_type: str             # "paragraph" or "table"
    location: str               # Human-readable location
    original: str | None        # None if ADDED
    modified: str | None        # None if DELETED
    similarity: float | None    # For MODIFIED, how similar (0-1)
    diff_text: str | None       # Human-readable diff
    word_changes: List[WordChange] | None


@dataclass
class ClassifiedChange:
    """A change with impact classification."""
    # Original Change fields
    change_id: int
    change_type: ChangeType
    block_type: str
    location: str
    original: str | None
    modified: str | None
    similarity: float | None
    diff_text: str | None
    word_changes: List[WordChange] | None
    # Classification fields
    impact: ImpactLevel
    reasoning: str
    risk_analysis: str
    classification_source: str  # "rule-based" or "llm"


class ChangeSummary(BaseModel):
    """Summary of changes by impact level."""
    total: int
    critical: int
    medium: int
    low: int


class ChangeDetail(BaseModel):
    """Detailed information about a single change."""
    change_id: int
    change_type: str
    block_type: str
    location: str
    original: str | None
    modified: str | None
    diff_text: str | None
    impact: str
    reasoning: str
    risk_analysis: str
    classification_source: str


class TimingBreakdown(BaseModel):
    """Breakdown of processing time by component."""
    total_ms: int
    parsing_ms: int
    diffing_ms: int
    classification_ms: int
    llm_ms: int  # Subset of classification_ms spent on LLM calls
    annotation_ms: int
    

class CompareResponse(BaseModel):
    """Response from the compare endpoint."""
    success: bool
    summary: ChangeSummary
    changes: List[ChangeDetail]
    processing_time_ms: int
    timing: TimingBreakdown | None = None  # Detailed timing breakdown
    metadata: dict
    annotated_doc_id: str | None = None
