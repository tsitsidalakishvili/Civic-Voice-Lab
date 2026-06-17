from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA


def build_vote_matrix(votes: List[Dict]) -> Tuple[pd.DataFrame, List[str], List[str]]:
    if not votes:
        return pd.DataFrame(), [], []
    df = pd.DataFrame(votes)
    matrix = df.pivot_table(
        index="participant_id",
        columns="comment_id",
        values="choice",
        fill_value=0,
        aggfunc="max",
    )
    return matrix, list(matrix.index), list(matrix.columns)


def run_clustering(votes: List[Dict], n_clusters: int = 3) -> Tuple[List[Dict], Dict[str, str]]:
    matrix, participant_ids, _ = build_vote_matrix(votes)
    if matrix.empty or len(participant_ids) < 2:
        return [], {}

    X = matrix.values
    n_clusters = max(2, min(n_clusters, len(participant_ids)))
    pca = PCA(n_components=2, random_state=42)
    coords = pca.fit_transform(X)

    kmeans = KMeans(n_clusters=n_clusters, n_init="auto", random_state=42)
    labels = kmeans.fit_predict(X)

    points = []
    label_map = {}
    for idx, participant_id in enumerate(participant_ids):
        cluster_id = f"cluster-{labels[idx]}"
        label_map[participant_id] = cluster_id
        points.append(
            {
                "participant_id": participant_id,
                "x": float(coords[idx, 0]),
                "y": float(coords[idx, 1]),
                "cluster_id": cluster_id,
            }
        )
    return points, label_map


def _vote_counts(votes: List[Dict]) -> Dict[str, Dict[str, int]]:
    counts: Dict[str, Dict[str, int]] = {}
    for vote in votes:
        comment_id = vote["comment_id"]
        counts.setdefault(comment_id, {"agree": 0, "disagree": 0, "pass": 0})
        if vote["choice"] == 1:
            counts[comment_id]["agree"] += 1
        elif vote["choice"] == -1:
            counts[comment_id]["disagree"] += 1
        else:
            counts[comment_id]["pass"] += 1
    return counts


def _cluster_variance(matrix: pd.DataFrame, label_map: Dict[str, str]) -> Dict[str, float]:
    if matrix.empty or not label_map:
        return {col: 0.0 for col in matrix.columns} if not matrix.empty else {}
    variance = {}
    for comment_id in matrix.columns:
        ratios = []
        for cluster_id in set(label_map.values()):
            cluster_rows = matrix.loc[
                [pid for pid, cid in label_map.items() if cid == cluster_id], comment_id
            ]
            agree = int((cluster_rows == 1).sum())
            disagree = int((cluster_rows == -1).sum())
            if agree + disagree == 0:
                continue
            ratios.append(agree / (agree + disagree))
        variance[comment_id] = float(np.var(ratios)) if ratios else 0.0
    return variance


def compute_cluster_insights(
    comments: List[Dict],
    votes: List[Dict],
    label_map: Dict[str, str],
) -> Tuple[List[Dict], List[Dict]]:
    matrix, _, comment_ids = build_vote_matrix(votes)
    if matrix.empty or not label_map:
        return [], []

    comment_text = {comment["id"]: comment["text"] for comment in comments}
    cluster_ids = sorted(set(label_map.values()))
    cluster_vectors = {}
    summaries = []

    for cluster_id in cluster_ids:
        members = [pid for pid, cid in label_map.items() if cid == cluster_id and pid in matrix.index]
        if not members:
            continue
        subset = matrix.loc[members]
        cluster_vectors[cluster_id] = subset.mean(axis=0).to_numpy()

        stats = []
        for comment_id in comment_ids:
            col = subset[comment_id]
            agree = int((col == 1).sum())
            disagree = int((col == -1).sum())
            passed = int((col == 0).sum())
            participation = agree + disagree + passed
            if participation < 3:
                continue
            ratio = agree / (agree + disagree) if (agree + disagree) > 0 else 0.0
            stats.append((comment_id, ratio, participation))

        top_agree = [
            comment_text[comment_id]
            for comment_id, ratio, participation in sorted(stats, key=lambda x: (-x[1], -x[2]))
            if ratio >= 0.7
        ][:3]
        top_disagree = [
            comment_text[comment_id]
            for comment_id, ratio, participation in sorted(stats, key=lambda x: (x[1], -x[2]))
            if ratio <= 0.3
        ][:3]

        summaries.append(
            {
                "cluster_id": cluster_id,
                "size": len(members),
                "top_agree": top_agree,
                "top_disagree": top_disagree,
            }
        )

    similarities = []
    for i, cluster_a in enumerate(cluster_ids):
        for cluster_b in cluster_ids[i + 1 :]:
            vec_a = cluster_vectors.get(cluster_a)
            vec_b = cluster_vectors.get(cluster_b)
            if vec_a is None or vec_b is None:
                continue
            denom = float(np.linalg.norm(vec_a) * np.linalg.norm(vec_b))
            similarity = float(np.dot(vec_a, vec_b) / denom) if denom else 0.0
            similarities.append(
                {"cluster_a": cluster_a, "cluster_b": cluster_b, "similarity": similarity}
            )

    similarities = sorted(similarities, key=lambda item: item["similarity"], reverse=True)
    return summaries, similarities


def compute_metrics(
    comments: List[Dict],
    votes: List[Dict],
    label_map: Dict[str, str],
) -> Tuple[List[Dict], List[Dict]]:
    vote_counts = _vote_counts(votes)
    matrix, _, _ = build_vote_matrix(votes)
    cluster_variance = _cluster_variance(matrix, label_map)

    metrics = []
    for comment in comments:
        comment_id = comment["id"]
        counts = vote_counts.get(comment_id, {"agree": 0, "disagree": 0, "pass": 0})
        agree = counts["agree"]
        disagree = counts["disagree"]
        passed = counts["pass"]
        participation = agree + disagree + passed
        agreement_ratio = agree / (agree + disagree) if (agree + disagree) > 0 else 0.0
        variance = cluster_variance.get(comment_id, 0.0)
        participation_factor = min(participation / 10.0, 1.0)
        consensus_score = agreement_ratio * (1.0 - variance) * participation_factor
        polarity_score = (1.0 - abs(agreement_ratio - 0.5) * 2.0) * variance * participation_factor
        metrics.append(
            {
                "id": comment_id,
                "text": comment["text"],
                "status": comment.get("status", "approved"),
                "participation": participation,
                "agreement_ratio": agreement_ratio,
                "consensus_score": consensus_score,
                "polarity_score": polarity_score,
                "agree_count": agree,
                "disagree_count": disagree,
                "pass_count": passed,
            }
        )

    consensus = [
        m for m in metrics if m["participation"] >= 3 and m["consensus_score"] >= 0.35
    ]
    polarizing = [
        m for m in metrics if m["participation"] >= 3 and m["polarity_score"] >= 0.15
    ]
    consensus = sorted(consensus, key=lambda m: (-m["consensus_score"], -m["participation"]))[:20]
    polarizing = sorted(polarizing, key=lambda m: (-m["polarity_score"], -m["participation"]))[:20]
    return consensus, polarizing
