import os
from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError


def _normalize_neo4j_uri(uri: str | None) -> str | None:
    text = str(uri or "").strip()
    if not text:
        return None
    if ".bolt.neo4jsandbox.com" in text:
        text = text.replace(".bolt.neo4jsandbox.com:443", ".neo4jsandbox.com:7687")
        text = text.replace(".bolt.neo4jsandbox.com", ".neo4jsandbox.com:7687")
    return text


def _first(*keys: str, default: str | None = None) -> str | None:
    for key in keys:
        value = os.getenv(key)
        if value is not None and str(value).strip() != "":
            return value
    return default


def _build_db_candidates() -> list[dict[str, str]]:
    mode = str(os.getenv("DELIBERATION_DB_MODE", "local") or "local").lower()
    candidates: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()

    def add_candidate(source: str, uri: str | None, user: str | None, password: str | None, database: str | None):
        normalized_uri = _normalize_neo4j_uri(uri)
        text_password = str(password or "").strip()
        text_user = str(user or "neo4j").strip() or "neo4j"
        text_db = str(database or "neo4j").strip() or "neo4j"
        if not normalized_uri or not text_password:
            return
        key = (normalized_uri, text_user, text_password, text_db)
        if key in seen:
            return
        seen.add(key)
        candidates.append(
            {
                "source": source,
                "uri": normalized_uri,
                "user": text_user,
                "password": text_password,
                "database": text_db,
            }
        )

    add_candidate(
        "DELIBERATION_*",
        _first("DELIBERATION_NEO4J_URI"),
        _first("DELIBERATION_NEO4J_USER", "DELIBERATION_NEO4J_USERNAME"),
        _first("DELIBERATION_NEO4J_PASSWORD"),
        _first("DELIBERATION_NEO4J_DATABASE", default="neo4j"),
    )
    if mode == "sandbox":
        add_candidate(
            "NEO4J_SANDBOX_*",
            _first("NEO4J_SANDBOX_URI"),
            _first("NEO4J_SANDBOX_USER", "NEO4J_SANDBOX_USERNAME", default="neo4j"),
            _first("NEO4J_SANDBOX_PASSWORD"),
            _first("NEO4J_SANDBOX_DATABASE", default="neo4j"),
        )
    add_candidate(
        "NEO4J_*",
        _first("NEO4J_URI"),
        _first("NEO4J_USER", "NEO4J_USERNAME", default="neo4j"),
        _first("NEO4J_PASSWORD", "NEO4J_PASS"),
        _first("NEO4J_DATABASE", default="neo4j"),
    )
    if mode != "sandbox":
        add_candidate(
            "NEO4J_SANDBOX_*",
            _first("NEO4J_SANDBOX_URI"),
            _first("NEO4J_SANDBOX_USER", "NEO4J_SANDBOX_USERNAME", default="neo4j"),
            _first("NEO4J_SANDBOX_PASSWORD"),
            _first("NEO4J_SANDBOX_DATABASE", default="neo4j"),
        )

    if not candidates:
        add_candidate(
            "defaults",
            "bolt://localhost:7687",
            "neo4j",
            "change-this",
            "neo4j",
        )
    return candidates


_first_candidate = _build_db_candidates()[0]
NEO4J_URI = _first_candidate["uri"]
NEO4J_USER = _first_candidate["user"]
NEO4J_PASSWORD = _first_candidate["password"]
NEO4J_DATABASE = _first_candidate["database"]

_driver = None
_active_target: dict[str, str] | None = None


def get_active_database() -> str:
    active = _active_target or {}
    return str(active.get("database") or NEO4J_DATABASE or "neo4j")


def get_driver():
    global _driver, _active_target
    if _driver is None:
        errors: list[str] = []
        for target in _build_db_candidates():
            candidate_driver = None
            try:
                candidate_driver = GraphDatabase.driver(
                    target["uri"],
                    auth=(target["user"], target["password"]),
                    connection_timeout=12,
                    connection_acquisition_timeout=12,
                )
                candidate_driver.verify_connectivity()
                with candidate_driver.session(database=target["database"]) as session:
                    session.run("RETURN 1 AS ok").consume()
                _driver = candidate_driver
                _active_target = target
                break
            except Exception as exc:
                errors.append(
                    f"{target['source']}[{target['uri']}|{target['database']}] => {exc}"
                )
                try:
                    if candidate_driver is not None:
                        candidate_driver.close()
                except Exception:
                    pass
        if _driver is None:
            raise RuntimeError("No working Neo4j configuration. " + " ; ".join(errors))
    return _driver


def close_driver():
    global _driver, _active_target
    if _driver is not None:
        _driver.close()
        _driver = None
    _active_target = None


def _execute_write(session, query):
    if hasattr(session, "execute_write"):
        session.execute_write(lambda tx: tx.run(query))
    else:
        session.write_transaction(lambda tx: tx.run(query))


def init_constraints():
    driver = get_driver()
    queries = [
        "CREATE CONSTRAINT conversation_id IF NOT EXISTS FOR (c:Conversation) REQUIRE c.id IS UNIQUE",
        "CREATE CONSTRAINT comment_id IF NOT EXISTS FOR (c:Comment) REQUIRE c.id IS UNIQUE",
        "CREATE CONSTRAINT participant_id IF NOT EXISTS FOR (p:Participant) REQUIRE p.id IS UNIQUE",
        "CREATE CONSTRAINT cluster_id IF NOT EXISTS FOR (c:Cluster) REQUIRE c.id IS UNIQUE",
        "CREATE CONSTRAINT analysis_run_id IF NOT EXISTS FOR (a:AnalysisRun) REQUIRE a.id IS UNIQUE",
    ]
    with driver.session(database=get_active_database()) as session:
        for query in queries:
            _execute_write(session, query)


def db_health() -> dict:
    try:
        driver = get_driver()
        driver.verify_connectivity()
        active = _active_target or {}
        active_db = get_active_database()
        with driver.session(database=active_db) as session:
            records = session.run("RETURN 1 AS ok").data()
        return {
            "ok": bool(records),
            "target_source": active.get("source"),
            "target_uri": active.get("uri"),
            "target_database": active_db,
        }
    except Neo4jError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
