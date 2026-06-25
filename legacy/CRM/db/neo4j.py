import pandas as pd
import streamlit as st
from neo4j import GraphDatabase, basic_auth

from crm.config import NEO4J_DATABASE, NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER

driver = None
_auth_rate_limited = False
_active_database = NEO4J_DATABASE
_active_uri = None
_active_user = None


def _normalize_neo4j_uri(uri: str | None) -> str | None:
    text = str(uri or "").strip()
    if not text:
        return None
    # Neo4j sandbox "websocket bolt" endpoint on 443 is not a direct Bolt
    # endpoint for the Python driver; normalize to the TLS Bolt endpoint.
    if ".bolt.neo4jsandbox.com" in text:
        # Handles:
        # - bolt+s://<id>.bolt.neo4jsandbox.com:443
        # - bolt+s://<id>.bolt.neo4jsandbox.com
        text = text.replace(".bolt.neo4jsandbox.com:443", ".neo4jsandbox.com:7687")
        text = text.replace(".bolt.neo4jsandbox.com", ".neo4jsandbox.com:7687")
    return text


def _session_execute_read(session, func, *args):
    if hasattr(session, "execute_read"):
        return session.execute_read(func, *args)
    return session.read_transaction(func, *args)


def _session_execute_write(session, func, *args):
    if hasattr(session, "execute_write"):
        return session.execute_write(func, *args)
    return session.write_transaction(func, *args)


def init_driver(uri=None, user=None, password=None, database=None):
    global driver, _auth_rate_limited, _active_database, _active_uri, _active_user
    if _auth_rate_limited:
        return False
    uri = _normalize_neo4j_uri(uri or NEO4J_URI)
    user = user or NEO4J_USER
    password = password or NEO4J_PASSWORD
    database = database or NEO4J_DATABASE
    if not uri or not password:
        driver = None
        return False
    if _active_uri != uri or _active_user != user or _active_database != database:
        if driver is not None:
            try:
                driver.close()
            except Exception:
                pass
        _auth_rate_limited = False
    try:
        driver = GraphDatabase.driver(
            uri,
            auth=basic_auth(user, password),
            connection_timeout=8,
            connection_acquisition_timeout=8,
            max_transaction_retry_time=4,
        )
        _active_uri = uri
        _active_user = user
        _active_database = database
        with driver.session(database=_active_database) as session:
            _session_execute_read(session, lambda tx: list(tx.run("RETURN 1")))
        return True
    except Exception as exc:
        error_str = str(exc)
        if "AuthenticationRateLimit" in error_str or "authentication details too many times" in error_str:
            _auth_rate_limited = True
            st.error("Neo4j authentication rate limit reached. Please wait a few minutes.")
        elif "looks like HTTP" in error_str:
            st.error(
                "Neo4j URI looks like a WebSocket/HTTP endpoint. "
                "Use Bolt endpoint, e.g. "
                "`bolt+s://<sandbox-id>.neo4jsandbox.com:7687`."
            )
        else:
            st.error(f"Could not initialize Neo4j driver: {exc}")
        driver = None
        return False


def _run_read(tx, query, params):
    result = tx.run(query, params or {})
    return [r.data() for r in result]


def run_query(query, params=None, silent=False):
    if driver is None:
        if not silent:
            st.warning("Neo4j driver not available. Check connection settings.")
        return pd.DataFrame()
    if _auth_rate_limited:
        if not silent:
            st.error("Neo4j authentication rate limit active. Please wait before retrying.")
        return pd.DataFrame()
    try:
        with driver.session(database=_active_database) as session:
            data = _session_execute_read(session, _run_read, query, params)
            return pd.DataFrame(data)
    except Exception as exc:
        if not silent:
            st.error(f"Neo4j query failed: {exc}")
        return pd.DataFrame()


def _run_write(tx, query, params):
    tx.run(query, params or {})


def run_write(query, params=None):
    if driver is None:
        st.warning("Neo4j driver not available. Check connection settings.")
        return False
    if _auth_rate_limited:
        st.error("Neo4j authentication rate limit active. Please wait before retrying.")
        return False
    try:
        with driver.session(database=_active_database) as session:
            _session_execute_write(session, _run_write, query, params)
        return True
    except Exception as exc:
        st.error(f"Neo4j write failed: {exc}")
        return False
