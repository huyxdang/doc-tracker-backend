"""
Services package - business logic.
"""

from app.services.parser import parse_document
from app.services.differ import diff_documents, get_word_level_diff
from app.services.classifier import classify_changes, classify_by_rules, LLMClassifier, ClassificationResult
from app.services.annotator import create_annotated_document

__all__ = [
    "parse_document",
    "diff_documents",
    "get_word_level_diff",
    "classify_changes",
    "classify_by_rules",
    "LLMClassifier",
    "ClassificationResult",
    "create_annotated_document",
]
