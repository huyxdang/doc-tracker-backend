"""
Classification service.
Hybrid approach: rule-based for numbers, LLM for semantic analysis.
"""

import re
import json
import time
from typing import List, Tuple
from dataclasses import dataclass

from openai import OpenAI

from app.config import settings
from app.models import Change, ClassifiedChange, ImpactLevel, ChangeType


@dataclass
class ClassificationResult:
    """Result of classification including timing info."""
    classified_changes: List[ClassifiedChange]
    llm_time_ms: int  # Time spent on LLM API calls
    llm_calls: int    # Number of LLM API calls made


# ============================================================
# RULE-BASED PATTERNS (Numbers only)
# ============================================================

CRITICAL_PATTERNS = [
    # Percentages
    (r'\d+[.,]?\d*\s*%', "Giá trị phần trăm thay đổi"),
    
    # Currency - USD
    (r'\$\s*[\d,]+\.?\d*', "Giá trị tiền tệ thay đổi (USD)"),
    
    # Currency - VND (various formats)
    (r'[\d.,]+\s*(VND|đồng|vnđ|VNĐ)', "Giá trị tiền tệ thay đổi (VND)"),
    (r'[\d.,]+\s*(triệu|tỷ|nghìn|ngàn)', "Giá trị tiền tệ thay đổi (VND)"),
    
    # General numbers (integers and decimals)
    (r'\b\d{1,3}([.,]\d{3})+\b', "Giá trị số thay đổi"),
    (r'\b\d+[.,]\d+\b', "Giá trị số thay đổi"),
]

RISK_STATEMENTS = {
    "Giá trị phần trăm thay đổi": "Có thể ảnh hưởng đến các tính toán tài chính - cần xác minh",
    "Giá trị tiền tệ thay đổi (USD)": "Sai lệch giá trị tiền tệ - có thể ảnh hưởng tài chính",
    "Giá trị tiền tệ thay đổi (VND)": "Sai lệch giá trị tiền tệ - có thể ảnh hưởng tài chính",
    "Giá trị số thay đổi": "Thay đổi dữ liệu số - cần kiểm tra với nguồn gốc",
}


# ============================================================
# RULE-BASED CLASSIFIER
# ============================================================

def classify_by_rules(change: Change) -> tuple[ImpactLevel | None, str, str]:
    """
    Apply rule-based classification for numerical changes.
    
    Returns:
        (impact_level, reasoning, risk_analysis) or (None, "", "") if no rule matches
    """
    # Get text to analyze
    if change.word_changes:
        texts_to_check = []
        for wc in change.word_changes:
            if wc.old_text:
                texts_to_check.append(wc.old_text)
            if wc.new_text:
                texts_to_check.append(wc.new_text)
        text_to_analyze = ' '.join(texts_to_check)
    else:
        text_to_analyze = change.diff_text or ""
    
    # Check for trivial changes
    if _is_trivial_change(change):
        return (
            ImpactLevel.LOW,
            "Thay đổi không đáng kể",
            "Không ảnh hưởng đến nghiệp vụ - chỉ thay đổi định dạng"
        )
    
    # Check for CRITICAL patterns (numbers)
    for pattern, reason in CRITICAL_PATTERNS:
        if re.search(pattern, text_to_analyze, re.IGNORECASE):
            risk = RISK_STATEMENTS.get(reason, "Phát hiện thay đổi - cần xem xét")
            return (ImpactLevel.CRITICAL, reason, risk)
    
    # No rule matched - needs LLM
    return (None, "", "")


def _is_trivial_change(change: Change) -> bool:
    """Check if change is trivial (whitespace, punctuation only)."""
    if not change.word_changes:
        return False
    
    for wc in change.word_changes:
        old = wc.old_text.strip()
        new = wc.new_text.strip()
        
        old_alpha = re.sub(r'[^\w]', '', old)
        new_alpha = re.sub(r'[^\w]', '', new)
        
        if old_alpha.lower() != new_alpha.lower():
            return False
    
    return True


# ============================================================
# LLM CLASSIFIER (OpenAI GPT-4o)
# ============================================================

class LLMClassifier:
    """Classifies changes using OpenAI GPT-4o based on business impact."""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.client = OpenAI(api_key=self.api_key) if self.api_key else None
        self.model = settings.OPENAI_MODEL
    
    def classify_batch(
        self, 
        changes: List[Change], 
        document_type: str = "general"
    ) -> Tuple[dict[int, tuple[ImpactLevel, str, str]], int]:
        """
        Classify changes using LLM based on business impact.
        
        Returns:
            Tuple of (Dict mapping change_id -> (impact, reasoning, risk_analysis), llm_time_ms)
        """
        if not changes:
            return {}, 0
        
        if not self.client:
            return {
                c.change_id: (
                    ImpactLevel.MEDIUM,
                    "LLM không khả dụng - mặc định mức trung bình",
                    "Cần xem xét thủ công"
                )
                for c in changes
            }, 0
        
        prompt = self._build_prompt(changes, document_type)
        system_prompt = self._get_system_prompt()
        
        try:
            # Track LLM API call time
            llm_start = time.time()
            
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=500,
                temperature=0,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ]
            )
            
            llm_time_ms = int((time.time() - llm_start) * 1000)
            
            response_text = response.choices[0].message.content
            print(f"LLM response received in {llm_time_ms}ms: {response_text[:200]}...")
            parsed_results = self._parse_response(response_text, changes)
            print(f"Parsed {len(parsed_results)} classifications from LLM")
            return parsed_results, llm_time_ms
            
        except Exception as e:
            print(f"LLM classification failed: {e}")
            return {
                c.change_id: (
                    ImpactLevel.MEDIUM,
                    f"Lỗi LLM: {str(e)[:50]}",
                    "Cần xem xét thủ công"
                )
                for c in changes
            }, 0
    
    def _get_system_prompt(self) -> str:
        """System prompt for classification."""
        return """Bạn là hệ thống phân tích rủi ro tài liệu cho ngân hàng. 
Nhiệm vụ của bạn là phân loại các thay đổi trong tài liệu dựa trên MỨC ĐỘ ẢNH HƯỞNG ĐẾN NGHIỆP VỤ.

TIÊU CHÍ PHÂN LOẠI (dựa trên tác động kinh doanh):

CRITICAL (Nghiêm trọng):
- Thay đổi ảnh hưởng trực tiếp đến tài chính, nghĩa vụ hợp đồng, hoặc có thể gây ra vấn đề pháp lý/tiền tệ
- Thay đổi ngày tháng quan trọng (deadline, ngày hiệu lực, ngày thanh toán)
- Thay đổi tên tổ chức, cá nhân trong hợp đồng
- Thay đổi điều khoản ràng buộc pháp lý
- Thêm/xóa từ phủ định làm đảo ngược ý nghĩa

MEDIUM (Trung bình):
- Thay đổi nội dung có ảnh hưởng đến hiểu biết nhưng không trực tiếp tác động tài chính/pháp lý
- Thêm/xóa đoạn văn giải thích
- Thay đổi từ ngữ làm thay đổi sắc thái ý nghĩa
- Thay đổi cấu trúc câu ảnh hưởng đến cách hiểu

LOW (Thấp):
- Thay đổi không ảnh hưởng đến nghiệp vụ
- Sửa lỗi chính tả
- Thay đổi định dạng
- Thay từ đồng nghĩa có cùng ý nghĩa

CHỈ TRẢ VỀ JSON ARRAY với format: [{"id": 1, "impact": "critical"}, {"id": 2, "impact": "low"}]
KHÔNG cần reasoning hay risk - chỉ cần id và impact."""
    
    def _build_prompt(self, changes: List[Change], document_type: str) -> str:
        """Build the user prompt with change details."""
        doc_type_vn = {
            "general": "tài liệu chung",
            "contract": "hợp đồng",
            "policy": "chính sách",
            "report": "báo cáo",
            "research_paper": "bài nghiên cứu"
        }.get(document_type, document_type)
        
        change_lines = []
        for c in changes:
            if c.word_changes:
                parts = []
                for wc in c.word_changes:
                    if wc.change_type == "replaced":
                        parts.append(f"THAY ĐỔI: '{wc.old_text}' → '{wc.new_text}'")
                    elif wc.change_type == "added":
                        parts.append(f"THÊM: '{wc.new_text}'")
                    elif wc.change_type == "deleted":
                        parts.append(f"XÓA: '{wc.old_text}'")
                diff_summary = "; ".join(parts)
            else:
                diff_summary = c.diff_text or "Thay đổi không xác định"
            
            context_info = ""
            if c.original and len(c.original) < 500:
                context_info += f"\nNội dung gốc: {c.original[:300]}"
            if c.modified and len(c.modified) < 500:
                context_info += f"\nNội dung mới: {c.modified[:300]}"
            
            change_lines.append(
                f"#{c.change_id} [{c.block_type}, {c.location}]:\n{diff_summary}{context_info}"
            )
        
        changes_block = "\n\n".join(change_lines)
        
        return f"""Loại tài liệu: {doc_type_vn}

CÁC THAY ĐỔI CẦN PHÂN LOẠI:

{changes_block}

Trả về JSON array CHỈ với id và impact (không cần reasoning/risk):
[{{"id": 1, "impact": "critical"}}, {{"id": 2, "impact": "medium"}}]

JSON array:"""
    
    def _parse_response(
        self, 
        response_text: str, 
        changes: List[Change]
    ) -> dict[int, tuple[ImpactLevel, str, str]]:
        """Parse LLM response - just impact levels."""
        text = response_text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as e:
            print(f"JSON parse error: {e}")
            print(f"Raw LLM response: {response_text}")
            return {}
        
        impact_map = {
            "critical": ImpactLevel.CRITICAL,
            "medium": ImpactLevel.MEDIUM,
            "low": ImpactLevel.LOW,
            "high": ImpactLevel.CRITICAL
        }
        
        results = {}
        for item in parsed:
            # Handle both string and integer IDs from LLM
            change_id = item.get("id")
            if change_id is not None:
                change_id = int(change_id)  # Ensure integer for matching
            impact_str = item.get("impact", "medium").lower()
            impact = impact_map.get(impact_str, ImpactLevel.MEDIUM)
            
            # Default reasoning based on impact level
            default_reasons = {
                ImpactLevel.CRITICAL: ("Thay đổi quan trọng", "Cần xem xét kỹ"),
                ImpactLevel.MEDIUM: ("Thay đổi có ý nghĩa", "Cần xem xét"),
                ImpactLevel.LOW: ("Thay đổi nhỏ", "Ảnh hưởng thấp")
            }
            reasoning, risk = default_reasons.get(impact, ("", ""))
            
            results[change_id] = (impact, reasoning, risk)
        
        return results


# ============================================================
# HYBRID PIPELINE
# ============================================================

def classify_changes(
    changes: List[Change],
    document_type: str = "general",
    api_key: str = None
) -> ClassificationResult:
    """
    Classify all changes using hybrid approach:
    1. Rule-based for numerical changes (fast, free)
    2. LLM for semantic analysis (smart, costly)
    
    Returns:
        ClassificationResult with classified changes and timing info
    """
    classified = []
    needs_llm = []
    llm_time_ms = 0
    llm_calls = 0
    
    # Layer 1: Rule-based classification
    for change in changes:
        impact, reasoning, risk = classify_by_rules(change)
        
        if impact is not None:
            classified.append(ClassifiedChange(
                change_id=change.change_id,
                change_type=change.change_type,
                block_type=change.block_type,
                location=change.location,
                original=change.original,
                modified=change.modified,
                similarity=change.similarity,
                diff_text=change.diff_text,
                word_changes=change.word_changes,
                impact=impact,
                reasoning=reasoning,
                risk_analysis=risk,
                classification_source="rule-based"
            ))
        else:
            needs_llm.append(change)
    
    # Layer 2: LLM classification for ambiguous cases
    if needs_llm:
        llm = LLMClassifier(api_key=api_key)
        print(f"Sending {len(needs_llm)} changes to LLM ({llm.model})...")
        llm_results, llm_time_ms = llm.classify_batch(needs_llm, document_type)
        llm_calls = 1 if needs_llm else 0  # Currently batches all in one call
        
        for change in needs_llm:
            if change.change_id in llm_results:
                impact, reasoning, risk = llm_results[change.change_id]
            else:
                print(f"Warning: change_id {change.change_id} not found in LLM results. Available: {list(llm_results.keys())}")
                impact = ImpactLevel.MEDIUM
                reasoning = "Không thể phân loại"
                risk = "Cần xem xét thủ công"
            
            classified.append(ClassifiedChange(
                change_id=change.change_id,
                change_type=change.change_type,
                block_type=change.block_type,
                location=change.location,
                original=change.original,
                modified=change.modified,
                similarity=change.similarity,
                diff_text=change.diff_text,
                word_changes=change.word_changes,
                impact=impact,
                reasoning=reasoning,
                risk_analysis=risk,
                classification_source="llm"
            ))
    
    classified.sort(key=lambda c: c.change_id)
    
    return ClassificationResult(
        classified_changes=classified,
        llm_time_ms=llm_time_ms,
        llm_calls=llm_calls
    )
