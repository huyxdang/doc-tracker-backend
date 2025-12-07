"""
Document storage utility.
In-memory storage for annotated documents (can be swapped for S3/Redis later).
"""

import time
from typing import Optional


class DocumentStorage:
    """
    In-memory storage for annotated documents.
    
    For production with multiple instances, replace with:
    - Redis for temporary storage
    - S3 for persistent storage
    """
    
    def __init__(self):
        self._storage: dict = {}
    
    def store(self, doc_id: str, doc_bytes: bytes, filename: str) -> None:
        """Store a document with metadata."""
        self._storage[doc_id] = {
            'bytes': doc_bytes,
            'filename': filename,
            'created': time.time()
        }
    
    def get(self, doc_id: str) -> Optional[dict]:
        """Retrieve a document by ID."""
        return self._storage.get(doc_id)
    
    def delete(self, doc_id: str) -> bool:
        """Delete a document by ID."""
        if doc_id in self._storage:
            del self._storage[doc_id]
            return True
        return False
    
    def cleanup(self, max_age_seconds: int = 3600) -> int:
        """Remove documents older than max_age_seconds. Returns count removed."""
        now = time.time()
        to_remove = [
            doc_id for doc_id, data in self._storage.items()
            if now - data['created'] > max_age_seconds
        ]
        for doc_id in to_remove:
            del self._storage[doc_id]
        return len(to_remove)


# Singleton instance
document_storage = DocumentStorage()
