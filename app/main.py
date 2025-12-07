"""
Document Change Tracker API
FastAPI application entry point.
"""

import time
import hashlib

from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from app.config import settings
from app.models import (
    ChangeSummary,
    ChangeDetail,
    TimingBreakdown,
    CompareResponse,
    ImpactLevel,
)
from app.services import (
    parse_document,
    diff_documents,
    classify_changes,
    create_annotated_document,
)
from app.utils import document_storage

app = FastAPI(
    title=settings.APP_NAME,
    description="Compare two Word documents and classify change impacts for banking compliance",
    version=settings.APP_VERSION,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }


@app.get("/health")
async def health():
    """Health check for deployment."""
    return {"status": "ok"}


@app.post("/api/compare", response_model=CompareResponse)
async def compare_documents(
    file_v1: UploadFile = File(..., description="Original document (.docx)"),
    file_v2: UploadFile = File(..., description="Modified document (.docx)"),
    document_type: str = Form(
        default="general",
        description="Document type: general, contract, policy, report"
    ),
):
    """
    Compare two Word documents and classify the impact of changes.
    
    Returns:
    - Summary of changes by impact level
    - Detailed list of all changes with classifications
    - Risk analysis for each change
    - ID to download annotated document with highlights
    """
    start_time = time.time()
    
    # Validate file types
    if not file_v1.filename.endswith('.docx'):
        raise HTTPException(400, f"File 1 must be .docx, got: {file_v1.filename}")
    if not file_v2.filename.endswith('.docx'):
        raise HTTPException(400, f"File 2 must be .docx, got: {file_v2.filename}")
    
    try:
        # Read file contents
        bytes_v1 = await file_v1.read()
        bytes_v2 = await file_v2.read()
        
        # Step 1: Parse documents
        parse_start = time.time()
        blocks_v1 = parse_document(bytes_v1)
        blocks_v2 = parse_document(bytes_v2)
        parsing_ms = int((time.time() - parse_start) * 1000)
        
        # Step 2: Detect changes
        diff_start = time.time()
        changes = diff_documents(blocks_v1, blocks_v2)
        diffing_ms = int((time.time() - diff_start) * 1000)
        
        # Step 3: Classify changes (hybrid approach)
        classify_start = time.time()
        classification_result = classify_changes(
            changes,
            document_type=document_type,
            api_key=settings.OPENAI_API_KEY
        )
        classified = classification_result.classified_changes
        llm_ms = classification_result.llm_time_ms
        classification_ms = int((time.time() - classify_start) * 1000)
        
        # Step 4: Generate annotated document
        annotate_start = time.time()
        annotated_doc_id = None
        if classified:
            try:
                annotated_bytes = create_annotated_document(bytes_v2, classified)
                doc_id = hashlib.md5(
                    f"{file_v1.filename}{file_v2.filename}{time.time()}".encode()
                ).hexdigest()[:12]
                document_storage.store(
                    doc_id=doc_id,
                    doc_bytes=annotated_bytes,
                    filename=f"annotated_{file_v2.filename}"
                )
                annotated_doc_id = doc_id
            except Exception as e:
                print(f"Warning: Could not create annotated document: {e}")
        annotation_ms = int((time.time() - annotate_start) * 1000)
        
        # Build response
        total_time_ms = int((time.time() - start_time) * 1000)
        
        timing = TimingBreakdown(
            total_ms=total_time_ms,
            parsing_ms=parsing_ms,
            diffing_ms=diffing_ms,
            classification_ms=classification_ms,
            llm_ms=llm_ms,
            annotation_ms=annotation_ms
        )
        
        summary = ChangeSummary(
            total=len(classified),
            critical=sum(1 for c in classified if c.impact == ImpactLevel.CRITICAL),
            medium=sum(1 for c in classified if c.impact == ImpactLevel.MEDIUM),
            low=sum(1 for c in classified if c.impact == ImpactLevel.LOW),
        )
        
        change_details = [
            ChangeDetail(
                change_id=c.change_id,
                change_type=c.change_type.value,
                block_type=c.block_type,
                location=c.location,
                original=c.original,
                modified=c.modified,
                diff_text=c.diff_text,
                impact=c.impact.value,
                reasoning=c.reasoning,
                risk_analysis=c.risk_analysis,
                classification_source=c.classification_source
            )
            for c in classified
        ]
        
        return CompareResponse(
            success=True,
            summary=summary,
            changes=change_details,
            processing_time_ms=total_time_ms,
            timing=timing,
            metadata={
                "file_v1": file_v1.filename,
                "file_v2": file_v2.filename,
                "blocks_v1": len(blocks_v1),
                "blocks_v2": len(blocks_v2),
                "document_type": document_type,
                "llm_available": bool(settings.OPENAI_API_KEY),
                "llm_calls": classification_result.llm_calls,
            },
            annotated_doc_id=annotated_doc_id
        )
        
    except Exception as e:
        raise HTTPException(500, f"Processing error: {str(e)}")


@app.get("/api/download/{doc_id}")
async def download_annotated_document(doc_id: str):
    """Download the annotated document with highlights and comments."""
    doc_info = document_storage.get(doc_id)
    
    if not doc_info:
        raise HTTPException(404, "Document not found. It may have expired.")
    
    return Response(
        content=doc_info['bytes'],
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f"attachment; filename={doc_info['filename']}"
        }
    )
    

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
