from typing import Dict, List


def compute_metrics(run: Dict[str, object]) -> Dict[str, object]:
    pages = run.get("pages", [])
    chunks = run.get("chunks", [])
    segments = run.get("segments", [])
    verified_segments = [segment for segment in segments if segment.get("verified")]

    coverage = 0.0
    if pages:
        coverage = min(1.0, len(segments) / max(1, len(pages)))

    explainability = 0.0
    if segments:
        explainability = len(verified_segments) / max(1, len(segments))

    return {
        "coverage": round(coverage, 2),
        "explainability": round(explainability, 2),
        "evidencePassRate": round(explainability, 2),
        "runtimeSeconds": run.get("runtimeSeconds", 0),
        "p95RuntimeSeconds": run.get("p95RuntimeSeconds", run.get("runtimeSeconds", 0)),
        "pagesCrawled": len(pages),
        "segmentsGenerated": len(segments),
        "verifiedSegments": len(verified_segments),
        "chunksCreated": len(chunks),
        "clustersCreated": len(run.get("clusters", [])),
    }
