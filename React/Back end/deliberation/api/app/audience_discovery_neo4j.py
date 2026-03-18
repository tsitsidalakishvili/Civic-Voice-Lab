from typing import Dict, List

from neo4j.exceptions import Neo4jError

from .db import get_active_database, get_driver


VECTOR_INDEX_NAME = "ade_contentchunk_embedding_index"


def _execute_write(query: str, params: Dict[str, object]):
    driver = get_driver()
    with driver.session(database=get_active_database()) as session:
        return session.run(query, params).consume()


def _execute_read(query: str, params: Dict[str, object]):
    driver = get_driver()
    with driver.session(database=get_active_database()) as session:
        return list(session.run(query, params))


def ensure_schema(dimensions: int):
    queries = [
        "CREATE CONSTRAINT ade_page_id IF NOT EXISTS FOR (p:ProductPage) REQUIRE p.page_id IS UNIQUE",
        "CREATE CONSTRAINT ade_chunk_id IF NOT EXISTS FOR (c:ContentChunk) REQUIRE c.chunk_id IS UNIQUE",
        "CREATE CONSTRAINT ade_cluster_id IF NOT EXISTS FOR (c:Cluster) REQUIRE c.cluster_id IS UNIQUE",
        "CREATE CONSTRAINT ade_run_id IF NOT EXISTS FOR (r:AnalysisRun) REQUIRE r.run_id IS UNIQUE",
    ]
    for query in queries:
        _execute_write(query, {})

    try:
        _execute_write(
            "CREATE VECTOR INDEX "
            + VECTOR_INDEX_NAME
            + " IF NOT EXISTS FOR (c:ContentChunk) ON (c.embedding) "
            + "OPTIONS {indexConfig: {`vector.dimensions`: $dims, `vector.similarity_function`: 'cosine'}}",
            {"dims": dimensions},
        )
    except Neo4jError:
        # Vector index not supported in this environment.
        pass


def upsert_pages(run_id: str, pages: List[Dict[str, object]]):
    for page in pages:
        _execute_write(
            """
            MERGE (p:ProductPage {page_id: $page_id})
            SET p.url = $url,
                p.title = $title,
                p.raw_html = $raw_html,
                p.cleaned_text = $cleaned_text,
                p.crawl_status = $crawl_status
            WITH p
            MERGE (r:AnalysisRun {run_id: $run_id})
            MERGE (r)-[:ANALYZED]->(p)
            """,
            {
                "run_id": run_id,
                "page_id": page["page_id"],
                "url": page["url"],
                "title": page["title"],
                "raw_html": page["raw_html"],
                "cleaned_text": page["cleaned_text"],
                "crawl_status": page["crawl_status"],
            },
        )


def upsert_chunks(chunks: List[Dict[str, object]]):
    for chunk in chunks:
        _execute_write(
            """
            MERGE (c:ContentChunk {chunk_id: $chunk_id})
            SET c.page_id = $page_id,
                c.url = $url,
                c.text = $text,
                c.start_offset = $start_offset,
                c.end_offset = $end_offset,
                c.embedding = $embedding
            WITH c
            MATCH (p:ProductPage {page_id: $page_id})
            MERGE (p)-[:HAS_CHUNK]->(c)
            """,
            chunk,
        )


def upsert_clusters(run_id: str, clusters: List[Dict[str, object]]):
    for cluster in clusters:
        _execute_write(
            """
            MERGE (cl:Cluster {cluster_id: $cluster_id})
            SET cl.run_id = $run_id,
                cl.cluster_size = $cluster_size,
                cl.label = $label
            """,
            {
                "cluster_id": cluster["clusterId"],
                "run_id": run_id,
                "cluster_size": cluster["clusterSize"],
                "label": cluster.get("label") or "",
            },
        )
        for chunk_id in cluster.get("chunkIds", []):
            _execute_write(
                """
                MATCH (c:ContentChunk {chunk_id: $chunk_id})
                MATCH (cl:Cluster {cluster_id: $cluster_id})
                MERGE (c)-[:BELONGS_TO_CLUSTER]->(cl)
                """,
                {"chunk_id": chunk_id, "cluster_id": cluster["clusterId"]},
            )


def get_chunks_by_page(page_id: str) -> List[Dict[str, object]]:
    rows = _execute_read(
        """
        MATCH (p:ProductPage {page_id: $page_id})-[:HAS_CHUNK]->(c:ContentChunk)
        RETURN c.chunk_id AS chunkId, c.text AS text, c.start_offset AS startOffset,
               c.end_offset AS endOffset, c.url AS url
        ORDER BY c.start_offset ASC
        """,
        {"page_id": page_id},
    )
    return [dict(row) for row in rows]


def knn_search(embedding: List[float], k: int = 5) -> List[Dict[str, object]]:
    rows = _execute_read(
        """
        CALL db.index.vector.queryNodes($index, $k, $embedding)
        YIELD node, score
        RETURN node.chunk_id AS chunkId, node.text AS text, node.url AS url, score
        """,
        {"index": VECTOR_INDEX_NAME, "k": k, "embedding": embedding},
    )
    return [dict(row) for row in rows]


def get_cluster_members(cluster_id: str) -> List[Dict[str, object]]:
    rows = _execute_read(
        """
        MATCH (c:ContentChunk)-[:BELONGS_TO_CLUSTER]->(cl:Cluster {cluster_id: $cluster_id})
        RETURN c.chunk_id AS chunkId, c.text AS text, c.url AS url
        """,
        {"cluster_id": cluster_id},
    )
    return [dict(row) for row in rows]
