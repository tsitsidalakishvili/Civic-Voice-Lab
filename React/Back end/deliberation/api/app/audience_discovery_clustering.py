import math
from typing import Dict, List, Optional

import numpy as np
from sklearn.cluster import KMeans

from .audience_discovery_entities import top_entities


def cluster_chunks(
    chunks: List[Dict[str, object]], cluster_count: Optional[int] = None
) -> List[Dict[str, object]]:
    embeddings = [chunk.get("embedding") for chunk in chunks if chunk.get("embedding")]
    if len(embeddings) < 2:
        return []
    matrix = np.array(embeddings, dtype=float)
    if cluster_count is None:
        cluster_count = max(2, min(6, int(math.sqrt(len(embeddings)))))
    cluster_count = max(2, min(cluster_count, len(embeddings)))
    model = KMeans(n_clusters=cluster_count, n_init="auto", random_state=42)
    labels = model.fit_predict(matrix)
    clusters: Dict[int, Dict[str, object]] = {}
    for label, chunk in zip(labels, chunks):
        cluster = clusters.setdefault(
            int(label),
            {
                "clusterId": f"cluster-{int(label)}",
                "clusterSize": 0,
                "chunkIds": [],
                "sampleSnippets": [],
                "label": "",
            },
        )
        cluster["clusterSize"] += 1
        cluster["chunkIds"].append(chunk["chunkId"])
        if len(cluster["sampleSnippets"]) < 3:
            snippet = chunk["text"][:180].strip()
            cluster["sampleSnippets"].append(snippet)
        for entity in chunk.get("entities", []) or []:
            cluster.setdefault("_entity_counts", []).append(entity)
    for cluster in clusters.values():
        top = top_entities(cluster.get("_entity_counts", []), limit=2)
        cluster["label"] = " / ".join(top)
        cluster.pop("_entity_counts", None)
    return list(clusters.values())
