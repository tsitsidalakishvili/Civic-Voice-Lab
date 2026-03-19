import json
import uuid
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError

from .audience_discovery_examples import FEW_SHOT_EXAMPLES
from .audience_discovery_keywords import keyword_segments
from .audience_discovery_llm import generate_segments_llm


class SegmentDraft(BaseModel):
    segment_name: str = Field(alias="segmentName")
    rationale: str
    candidate_evidence_quotes: List[str] = Field(alias="candidateEvidenceQuotes")
    confidence: Optional[float] = None


class SegmentDraftResponse(BaseModel):
    segments: List[SegmentDraft]




def _keyword_segments(text: str, limit: int = 4) -> List[Dict[str, object]]:
    return keyword_segments(text, limit=limit)


def generate_segment_drafts(
    text: str, description: str, locale: Optional[str] = None
) -> Dict[str, object]:
    return generate_segments_llm(text=text, description=description, locale=locale)


def validate_segments(raw_payload: Dict[str, object]) -> SegmentDraftResponse:
    try:
        return SegmentDraftResponse(**raw_payload)
    except ValidationError:
        cleaned = {"segments": []}
        for item in raw_payload.get("segments", []):
            cleaned["segments"].append(
                {
                    "segmentName": item.get("segmentName") or item.get("segment_name") or "Segment",
                    "rationale": item.get("rationale") or "No rationale provided.",
                    "candidateEvidenceQuotes": item.get("candidateEvidenceQuotes")
                    or item.get("candidate_evidence_quotes")
                    or [],
                    "confidence": item.get("confidence"),
                }
            )
        return SegmentDraftResponse(**cleaned)


def attach_segment_ids(
    drafts: SegmentDraftResponse,
    page_id: Optional[str] = None,
    page_url: Optional[str] = None,
) -> List[Dict[str, object]]:
    segments: List[Dict[str, object]] = []
    for draft in drafts.segments:
        segments.append(
            {
                "segmentId": str(uuid.uuid4()),
                "name": draft.segment_name,
                "rationale": draft.rationale,
                "candidateEvidenceQuotes": draft.candidate_evidence_quotes,
                "confidence": draft.confidence or 0.65,
                "pageId": page_id or "",
                "pageUrl": page_url or "",
            }
        )
    return segments
