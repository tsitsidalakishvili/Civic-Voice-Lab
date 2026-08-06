"""
Data chat: answer natural-language questions from the Neo4j graph.

Uses a Text2Cypher (GraphRAG) flow for accuracy:
1. Load the live graph schema (labels, relationship types, property keys).
2. Ask the LLM to write a single read-only Cypher query for the question.
3. Execute it in a read transaction with row caps.
4. Ask the LLM to answer strictly from the returned rows.

The generated Cypher and the rows are returned to the client so every
answer is auditable.
"""

import json
import os
import re
import time
from typing import Any, List, Optional

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .db import get_active_database, get_driver

router = APIRouter()

SCHEMA_CACHE_TTL_S = 300
MAX_RESULT_ROWS = 50
MAX_CELL_CHARS = 400
CYPHER_RETRY_ATTEMPTS = 2

# Base64 blobs and vectors would flood the prompt without adding meaning.
EXCLUDED_PROPERTY_KEYS = {
    "screenshot",
    "embedding",
    "vector",
    "raw_html",
    "cleaned_text",
}

FORBIDDEN_CYPHER = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|LOAD\s+CSV|FOREACH|CALL\s+\{|"
    r"apoc\.(create|merge|refactor|periodic|load)|db\.index\.fulltext\.createNode)\b",
    re.IGNORECASE,
)

_schema_cache: dict = {"schema": "", "loaded_at": 0.0}


class ChatAskIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    language: Optional[str] = ""
    api_key: Optional[str] = Field(alias="apiKey", default="")

    class Config:
        populate_by_name = True


class ChatAskOut(BaseModel):
    answer: str
    cypher: str
    rows: List[dict]
    row_count: int = Field(alias="rowCount")
    model: str

    class Config:
        populate_by_name = True


def _execute_read(session, query: str, params: Optional[dict] = None):
    if hasattr(session, "execute_read"):
        return session.execute_read(lambda tx: list(tx.run(query, params or {})))
    return session.read_transaction(lambda tx: list(tx.run(query, params or {})))


def _db_session(driver):
    return driver.session(database=get_active_database())


def _llm_config(override_key: str = ""):
    api_key = str(override_key or "").strip() or os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail=(
                "Data chat is not configured: add your OpenAI API key in the chat panel "
                "or set OPENAI_API_KEY on the server."
            ),
        )
    api_url = (
        os.getenv("OPENAI_CHAT_COMPLETIONS_URL", "").strip()
        or "https://api.openai.com/v1/chat/completions"
    )
    model = os.getenv("DATA_CHAT_MODEL", "").strip() or os.getenv(
        "OPENAI_MODEL", ""
    ).strip() or "gpt-4.1-mini"
    return api_url, api_key, model


def _call_llm(messages: List[dict], api_url: str, api_key: str, model: str) -> str:
    try:
        response = requests.post(
            api_url,
            json={"model": model, "messages": messages, "temperature": 0},
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=60,
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"LLM request failed: {exc}")
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"LLM rejected request ({response.status_code}): {response.text[:300]}",
        )
    payload = response.json()
    try:
        return str(payload["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError):
        raise HTTPException(status_code=502, detail="LLM returned an unexpected payload.")


def _load_schema_text(session) -> str:
    label_rows = _execute_read(session, "CALL db.labels() YIELD label RETURN label")
    rel_rows = _execute_read(
        session, "CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType"
    )
    labels = [row.get("label") for row in label_rows if row.get("label")]
    rel_types = [row.get("relationshipType") for row in rel_rows if row.get("relationshipType")]

    lines = []
    for label in labels[:60]:
        try:
            prop_rows = _execute_read(
                session,
                f"MATCH (n:`{label}`) WITH n LIMIT 50 "
                "UNWIND keys(n) AS key RETURN DISTINCT key",
            )
        except Exception:
            prop_rows = []
        keys = sorted(
            {
                row.get("key")
                for row in prop_rows
                if row.get("key") and row.get("key") not in EXCLUDED_PROPERTY_KEYS
            }
        )
        lines.append(f"(:{label}) properties: {', '.join(keys) if keys else '(none seen)'}")

    pattern_rows = _execute_read(
        session,
        """
        MATCH (a)-[r]->(b)
        WITH labels(a) AS la, type(r) AS rel, labels(b) AS lb, count(*) AS c
        ORDER BY c DESC
        RETURN la, rel, lb
        LIMIT 80
        """,
    )
    patterns = []
    seen = set()
    for row in pattern_rows:
        la = (row.get("la") or ["?"])[0] if row.get("la") else "?"
        lb = (row.get("lb") or ["?"])[0] if row.get("lb") else "?"
        rel = row.get("rel") or "?"
        key = (la, rel, lb)
        if key in seen:
            continue
        seen.add(key)
        patterns.append(f"(:{la})-[:{rel}]->(:{lb})")

    return "\n".join(
        [
            "Node labels and their observed properties:",
            *lines,
            "",
            "Relationship patterns:",
            *patterns,
            "",
            f"Other relationship types: {', '.join(rel_types)}",
        ]
    )


def _get_schema(session) -> str:
    now = time.time()
    if _schema_cache["schema"] and now - _schema_cache["loaded_at"] < SCHEMA_CACHE_TTL_S:
        return _schema_cache["schema"]
    schema = _load_schema_text(session)
    _schema_cache["schema"] = schema
    _schema_cache["loaded_at"] = now
    return schema


def _extract_cypher(text: str) -> str:
    fenced = re.search(r"```(?:cypher)?\s*(.+?)```", text, re.DOTALL | re.IGNORECASE)
    query = (fenced.group(1) if fenced else text).strip().rstrip(";").strip()
    return query


def _validate_cypher(query: str) -> None:
    if not query:
        raise ValueError("Empty Cypher query.")
    if FORBIDDEN_CYPHER.search(query):
        raise ValueError("Only read-only Cypher is allowed.")


def _serialize_cell(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:MAX_CELL_CHARS]
    if isinstance(value, (list, tuple)):
        return [_serialize_cell(item) for item in value[:20]]
    if isinstance(value, dict):
        return {
            key: _serialize_cell(item)
            for key, item in value.items()
            if key not in EXCLUDED_PROPERTY_KEYS
        }
    if hasattr(value, "items"):  # neo4j Node/Relationship
        return {
            key: _serialize_cell(item)
            for key, item in dict(value).items()
            if key not in EXCLUDED_PROPERTY_KEYS
        }
    return str(value)[:MAX_CELL_CHARS]


def _run_cypher(session, query: str) -> List[dict]:
    records = _execute_read(session, query)
    rows = []
    for record in records[:MAX_RESULT_ROWS]:
        rows.append({key: _serialize_cell(value) for key, value in record.items()})
    return rows


CYPHER_SYSTEM_PROMPT = """You translate user questions into a single read-only Neo4j Cypher query.

Rules:
- Output ONLY the Cypher query, nothing else. No explanations, no markdown fences.
- Read-only: never use CREATE, MERGE, SET, DELETE, REMOVE, DROP, LOAD CSV or FOREACH.
- Always add LIMIT {max_rows} unless the query aggregates to a few rows.
- Use case-insensitive matching for user-provided text values:
  toLower(n.prop) CONTAINS toLower('value').
- Prefer counting/aggregating in Cypher instead of returning long lists.
- People: the group is derived from (:Person)-[:CLASSIFIED_AS]->(:SupporterType);
  a person is a Member when any linked SupporterType name contains 'member',
  otherwise they are a Supporter.
- Return clear column aliases (AS name).

Graph schema:
{schema}"""

ANSWER_SYSTEM_PROMPT = """You answer questions about an organization's database.
You are given the user's question, the Cypher query that was executed, and the rows it returned.

Rules:
- Answer ONLY from the returned rows. Never invent numbers or names.
- If the rows are empty, say that no matching data was found.
- Be concise: one short paragraph, plus a short list or numbers when helpful.
- Answer in the same language as the user's question.
- Do not mention Cypher or SQL unless the user asked about the query."""


@router.post("/ask", response_model=ChatAskOut)
def ask_database(payload: ChatAskIn):
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is empty.")
    api_url, api_key, model = _llm_config(payload.api_key or "")

    driver = get_driver()
    with _db_session(driver) as session:
        schema = _get_schema(session)

        cypher_messages = [
            {
                "role": "system",
                "content": CYPHER_SYSTEM_PROMPT.replace("{schema}", schema).replace(
                    "{max_rows}", str(MAX_RESULT_ROWS)
                ),
            },
            {"role": "user", "content": question},
        ]

        query = ""
        rows: List[dict] = []
        last_error = ""
        for _ in range(CYPHER_RETRY_ATTEMPTS):
            raw = _call_llm(cypher_messages, api_url, api_key, model)
            query = _extract_cypher(raw)
            try:
                _validate_cypher(query)
                rows = _run_cypher(session, query)
                last_error = ""
                break
            except Exception as exc:
                last_error = str(exc)
                cypher_messages.append({"role": "assistant", "content": query})
                cypher_messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"That query failed with: {last_error}. "
                            "Return a corrected read-only Cypher query only."
                        ),
                    }
                )

        if last_error:
            raise HTTPException(
                status_code=502,
                detail=f"Could not build a working query for this question: {last_error}",
            )

    answer_messages = [
        {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "question": question,
                    "cypher": query,
                    "rowCount": len(rows),
                    "rows": rows,
                },
                ensure_ascii=False,
            ),
        },
    ]
    answer = _call_llm(answer_messages, api_url, api_key, model)

    return ChatAskOut(
        answer=answer,
        cypher=query,
        rows=rows,
        rowCount=len(rows),
        model=model,
    )
