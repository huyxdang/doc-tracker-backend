"""
Diff engine service.
Compares two documents and identifies changes at block and word level.
"""

from typing import List
from difflib import SequenceMatcher

from app.models import ContentBlock, Change, WordChange, ChangeType


def diff_documents(blocks_v1: List[ContentBlock], blocks_v2: List[ContentBlock]) -> List[Change]:
    """
    Compare two parsed documents and identify changes.
    
    Uses SequenceMatcher to align blocks, then categorizes:
    - ADDED: Block exists in v2 but not v1
    - DELETED: Block exists in v1 but not v2
    - MODIFIED: Block exists in both but content changed
    
    Args:
        blocks_v1: Content blocks from original document
        blocks_v2: Content blocks from modified document
        
    Returns:
        List of Change objects describing all differences
    """
    contents_v1 = [b.content for b in blocks_v1]
    contents_v2 = [b.content for b in blocks_v2]
    
    matcher = SequenceMatcher(None, contents_v1, contents_v2)
    
    changes = []
    change_id = 1
    
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        
        if tag == 'equal':
            continue
            
        elif tag == 'delete':
            # Blocks in v1 that were removed
            for i in range(i1, i2):
                block = blocks_v1[i]
                changes.append(Change(
                    change_id=change_id,
                    change_type=ChangeType.DELETED,
                    block_type=block.block_type,
                    location=f"Block {block.index + 1}",
                    original=block.content,
                    modified=None,
                    similarity=None,
                    diff_text=f"[-{block.content}-]",
                    word_changes=[WordChange(
                        change_type="deleted",
                        old_text=block.content,
                        new_text="",
                        context="Entire block deleted"
                    )]
                ))
                change_id += 1
                
        elif tag == 'insert':
            # Blocks in v2 that were added
            for j in range(j1, j2):
                block = blocks_v2[j]
                changes.append(Change(
                    change_id=change_id,
                    change_type=ChangeType.ADDED,
                    block_type=block.block_type,
                    location=f"Block {block.index + 1}",
                    original=None,
                    modified=block.content,
                    similarity=None,
                    diff_text=f"[+{block.content}+]",
                    word_changes=[WordChange(
                        change_type="added",
                        old_text="",
                        new_text=block.content,
                        context="Entire block added"
                    )]
                ))
                change_id += 1
                
        elif tag == 'replace':
            # Blocks that were modified (or replaced)
            v1_blocks = [blocks_v1[i] for i in range(i1, i2)]
            v2_blocks = [blocks_v2[j] for j in range(j1, j2)]
            
            matched = _match_similar_blocks(v1_blocks, v2_blocks)
            
            for match in matched:
                if match['type'] == 'modified':
                    changes.append(Change(
                        change_id=change_id,
                        change_type=ChangeType.MODIFIED,
                        block_type=match['v1'].block_type,
                        location=f"Block {match['v1'].index + 1}",
                        original=match['v1'].content,
                        modified=match['v2'].content,
                        similarity=match['similarity'],
                        diff_text=match['diff_text'],
                        word_changes=match['word_changes']
                    ))
                elif match['type'] == 'deleted':
                    changes.append(Change(
                        change_id=change_id,
                        change_type=ChangeType.DELETED,
                        block_type=match['v1'].block_type,
                        location=f"Block {match['v1'].index + 1}",
                        original=match['v1'].content,
                        modified=None,
                        similarity=None,
                        diff_text=match['diff_text'],
                        word_changes=match['word_changes']
                    ))
                elif match['type'] == 'added':
                    changes.append(Change(
                        change_id=change_id,
                        change_type=ChangeType.ADDED,
                        block_type=match['v2'].block_type,
                        location=f"Block {match['v2'].index + 1}",
                        original=None,
                        modified=match['v2'].content,
                        similarity=None,
                        diff_text=match['diff_text'],
                        word_changes=match['word_changes']
                    ))
                change_id += 1
    
    return changes


def _match_similar_blocks(
    v1_blocks: List[ContentBlock], 
    v2_blocks: List[ContentBlock],
    threshold: float = 0.5
) -> List[dict]:
    """
    Match blocks between v1 and v2 based on similarity.
    Blocks with similarity > threshold are considered MODIFIED.
    Unmatched blocks are ADDED or DELETED.
    """
    results = []
    used_v2 = set()
    
    for b1 in v1_blocks:
        best_match = None
        best_sim = 0
        
        for idx, b2 in enumerate(v2_blocks):
            if idx in used_v2:
                continue
            sim = SequenceMatcher(None, b1.content, b2.content).ratio()
            if sim > best_sim:
                best_sim = sim
                best_match = (idx, b2)
        
        if best_match and best_sim >= threshold:
            used_v2.add(best_match[0])
            diff_text, word_changes = get_word_level_diff(b1.content, best_match[1].content)
            results.append({
                'type': 'modified',
                'v1': b1,
                'v2': best_match[1],
                'similarity': best_sim,
                'diff_text': diff_text,
                'word_changes': word_changes
            })
        else:
            results.append({
                'type': 'deleted',
                'v1': b1,
                'v2': None,
                'similarity': None,
                'diff_text': f"[-{b1.content}-]",
                'word_changes': [WordChange(
                    change_type="deleted",
                    old_text=b1.content,
                    new_text="",
                    context="Entire block deleted"
                )]
            })
    
    # Unmatched v2 blocks are additions
    for idx, b2 in enumerate(v2_blocks):
        if idx not in used_v2:
            results.append({
                'type': 'added',
                'v1': None,
                'v2': b2,
                'similarity': None,
                'diff_text': f"[+{b2.content}+]",
                'word_changes': [WordChange(
                    change_type="added",
                    old_text="",
                    new_text=b2.content,
                    context="Entire block added"
                )]
            })
    
    return results


def get_word_level_diff(original: str, modified: str) -> tuple[str, List[WordChange]]:
    """
    Compare two texts and return:
    1. Human-readable diff string: "word [-deleted-] [+added+] word"
    2. List of specific word changes
    """
    orig_words = original.split()
    mod_words = modified.split()
    
    matcher = SequenceMatcher(None, orig_words, mod_words)
    
    diff_parts = []
    word_changes = []
    
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            diff_parts.extend(orig_words[i1:i2])
            
        elif tag == 'delete':
            deleted = orig_words[i1:i2]
            diff_parts.append(f"[-{' '.join(deleted)}-]")
            
            context_before = ' '.join(orig_words[max(0, i1-2):i1])
            context_after = ' '.join(orig_words[i2:i2+2])
            context = f"{context_before} [DELETED] {context_after}".strip()
            
            word_changes.append(WordChange(
                change_type="deleted",
                old_text=' '.join(deleted),
                new_text="",
                context=context
            ))
            
        elif tag == 'insert':
            added = mod_words[j1:j2]
            diff_parts.append(f"[+{' '.join(added)}+]")
            
            context_before = ' '.join(mod_words[max(0, j1-2):j1])
            context_after = ' '.join(mod_words[j2:j2+2])
            context = f"{context_before} [ADDED] {context_after}".strip()
            
            word_changes.append(WordChange(
                change_type="added",
                old_text="",
                new_text=' '.join(added),
                context=context
            ))
            
        elif tag == 'replace':
            old = orig_words[i1:i2]
            new = mod_words[j1:j2]
            diff_parts.append(f"[-{' '.join(old)}-]")
            diff_parts.append(f"[+{' '.join(new)}+]")
            
            context_before = ' '.join(orig_words[max(0, i1-2):i1])
            context_after = ' '.join(orig_words[i2:i2+2])
            context = f"{context_before} [REPLACED] {context_after}".strip()
            
            word_changes.append(WordChange(
                change_type="replaced",
                old_text=' '.join(old),
                new_text=' '.join(new),
                context=context
            ))
    
    diff_text = ' '.join(diff_parts)
    return diff_text, word_changes
