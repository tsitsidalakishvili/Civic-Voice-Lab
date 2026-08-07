"""Adapters for the maintained OpenSanctions investigative-data toolchain.

The official FollowTheMoney stack currently depends on PyICU.  It is used
directly when installed (the normal production/Linux case), while the Windows
development environment keeps a deliberately small, strict compatibility
layer so native FtM payloads can still be ingested and tested.
"""

from __future__ import annotations

import re
import unicodedata
from importlib import metadata
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit


try:  # pragma: no cover - exercised in deployments with the official stack.
    from followthemoney import model as _ftm_model
except (ImportError, OSError):
    _ftm_model = None

try:  # pragma: no cover - exercised in deployments with the official stack.
    from rigour.names import normalize_name as _rigour_normalize_name
except (ImportError, OSError):
    _rigour_normalize_name = None

try:  # pragma: no cover - exercised in deployments with the official stack.
    from nomenklatura.matching.logic_v2.model import LogicV2 as _LogicV2
except (ImportError, OSError):
    _LogicV2 = None


FALLBACK_NODE_SCHEMATA = {
    "Thing",
    "Person",
    "Organization",
    "Company",
    "LegalEntity",
    "PublicBody",
    "Asset",
    "RealEstate",
    "Vehicle",
    "Vessel",
    "Airplane",
    "BankAccount",
    "Contract",
    "CourtCase",
    "Address",
    "Document",
    "Article",
    "Passport",
    "Identification",
    "Position",
    "Project",
    "Security",
}

# FollowTheMoney models these as interstitial entities.  The adapter projects
# them to Neo4j edges while preserving the interstitial entity ID and all of
# its literal properties as evidence-bearing statements.
FALLBACK_EDGE_SCHEMATA: Dict[str, Tuple[str, str]] = {
    "Ownership": ("owner", "asset"),
    "Directorship": ("director", "organization"),
    "Membership": ("member", "organization"),
    "Family": ("person", "relative"),
    "Associate": ("person", "associate"),
    "ContractAward": ("contract", "supplier"),
    "Payment": ("payer", "beneficiary"),
    "Documentation": ("document", "entity"),
    "Occupancy": ("holder", "post"),
    "Representation": ("agent", "client"),
    "Employment": ("employee", "employer"),
    "Succession": ("predecessor", "successor"),
}


def _version(package: str) -> Optional[str]:
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return None


def toolkit_capabilities() -> Dict[str, object]:
    schema_count = (
        len(_ftm_model.schemata) if _ftm_model is not None else len(FALLBACK_NODE_SCHEMATA) + len(FALLBACK_EDGE_SCHEMATA)
    )
    return {
        "followTheMoney": {
            "available": _ftm_model is not None,
            "version": _version("followthemoney"),
            "schemaCount": schema_count,
            "mode": "official-library" if _ftm_model is not None else "strict-compatible-fallback",
        },
        "rigour": {
            "available": _rigour_normalize_name is not None,
            "version": _version("rigour"),
            "mode": "official-library" if _rigour_normalize_name is not None else "unicode-fallback",
        },
        "nomenklatura": {
            "available": _LogicV2 is not None,
            "version": _version("nomenklatura"),
            "algorithm": "logic-v2" if _LogicV2 is not None else "evidence-rule-v1",
        },
        "features": {
            "nativeFtmImport": True,
            "statementProvenance": True,
            "interstitialEdgeProjection": True,
            "reifiedMatchValues": True,
            "humanResolutionRequired": True,
        },
    }


def normalize_investigation_name(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if _rigour_normalize_name is not None:
        normalized = _rigour_normalize_name(text)
        return str(normalized or "")
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(re.sub(r"[^\w]+", " ", normalized).split())


def name_blocking_keys(value: object) -> List[str]:
    primary = normalize_investigation_name(value)
    if not primary:
        return []
    keys = [primary]
    # This adds a useful accent-insensitive key without pretending to be the
    # cross-script matching supplied by rigour/nomenklatura.
    decomposed = unicodedata.normalize("NFKD", primary)
    accentless = "".join(char for char in decomposed if not unicodedata.combining(char))
    accentless = " ".join(re.sub(r"[^\w]+", " ", accentless).split())
    if accentless and accentless not in keys:
        keys.append(accentless)
    return keys


def normalize_match_value(value_type: str, value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    value_type = value_type.casefold()
    if value_type == "identifier":
        normalized = "".join(char for char in text.casefold() if char.isalnum())
        return normalized if len(normalized) >= 7 else ""
    if value_type == "phone":
        digits = "".join(char for char in text if char.isdigit())
        return digits if len(digits) >= 5 else ""
    if value_type == "email":
        value = text.casefold()
        return value if "@" in value and "." in value.rsplit("@", 1)[-1] else ""
    if value_type == "url":
        candidate = text if "://" in text else f"https://{text}"
        parsed = urlsplit(candidate)
        host = (parsed.hostname or "").casefold()
        path = parsed.path.rstrip("/").casefold()
        return f"{host}{path}" if host else ""
    if value_type in {"address", "name"}:
        normalized = normalize_investigation_name(text)
        return normalized if len(normalized) >= 5 else ""
    return ""


def ftm_schema_metadata(schema_name: str) -> Optional[Dict[str, object]]:
    if _ftm_model is not None:
        schema = _ftm_model.get(schema_name)
        if schema is None:
            return None
        source_prop = schema.source_prop.name if schema.source_prop is not None else None
        target_prop = schema.target_prop.name if schema.target_prop is not None else None
        return {
            "name": schema.name,
            "edge": bool(schema.edge),
            "sourceProp": source_prop,
            "targetProp": target_prop,
            "propertyTypes": {
                prop.name: prop.type.name for prop in schema.properties.values()
            },
        }
    if schema_name in FALLBACK_NODE_SCHEMATA:
        return {
            "name": schema_name,
            "edge": False,
            "sourceProp": None,
            "targetProp": None,
            "propertyTypes": {},
        }
    endpoints = FALLBACK_EDGE_SCHEMATA.get(schema_name)
    if endpoints is not None:
        return {
            "name": schema_name,
            "edge": True,
            "sourceProp": endpoints[0],
            "targetProp": endpoints[1],
            "propertyTypes": {
                endpoints[0]: "entity",
                endpoints[1]: "entity",
            },
        }
    return None


def infer_ftm_property_type(property_name: str) -> str:
    value = property_name.casefold()
    if value in {
        "owner",
        "asset",
        "director",
        "organization",
        "member",
        "person",
        "relative",
        "associate",
        "contract",
        "supplier",
        "payer",
        "beneficiary",
        "document",
        "entity",
        "holder",
        "post",
        "agent",
        "client",
        "employee",
        "employer",
        "predecessor",
        "successor",
    }:
        return "entity"
    if "date" in value or value.endswith("at") or value in {"modified", "published"}:
        return "date"
    if value in {"amount", "sharescount", "percentage"} or value.endswith("amount"):
        return "number"
    if value in {"country", "nationality", "jurisdiction", "birthcountry"}:
        return "country"
    if "address" in value:
        return "address"
    if value in {"name", "alias", "weakalias", "previousname", "firstname", "lastname"}:
        return "name"
    if value.endswith("url") or value == "website":
        return "url"
    if value in {"email", "phone"}:
        return value
    if "id" in value or "number" in value or value in {"leicode", "imonumber", "taxnumber"}:
        return "identifier"
    return "string"


def validate_ftm_entity(data: Dict[str, object]) -> Tuple[Dict[str, object], List[str]]:
    entity_id = str(data.get("id") or "").strip()
    schema_name = str(data.get("schema") or "").strip()
    if not entity_id:
        raise ValueError("FollowTheMoney entity id is required")
    schema_meta = ftm_schema_metadata(schema_name)
    if schema_meta is None:
        raise ValueError(f"Unsupported FollowTheMoney schema: {schema_name}")
    raw_properties = data.get("properties") or {}
    if not isinstance(raw_properties, dict):
        raise ValueError(f"FollowTheMoney entity {entity_id} properties must be an object")

    warnings: List[str] = []
    clean_properties: Dict[str, List[str]] = {}
    for raw_name, raw_values in raw_properties.items():
        prop_name = str(raw_name or "").strip()
        if not prop_name:
            continue
        values = raw_values if isinstance(raw_values, list) else [raw_values]
        cleaned: List[str] = []
        for raw_value in values:
            if not isinstance(raw_value, (str, int, float, bool)):
                warnings.append(f"{entity_id}.{prop_name}: discarded non-scalar value")
                continue
            value = str(raw_value).strip()
            if value and value not in cleaned:
                cleaned.append(value)
        if cleaned:
            clean_properties[prop_name] = cleaned

    if _ftm_model is not None:
        proxy = _ftm_model.get_proxy(
            {"id": entity_id, "schema": schema_name, "properties": clean_properties},
            cleaned=False,
        )
        normalized = proxy.to_dict()
        normalized_properties = normalized.get("properties") or {}
        dropped = sum(len(values) for values in clean_properties.values()) - sum(
            len(values) for values in normalized_properties.values()
        )
        if dropped:
            warnings.append(f"{entity_id}: {dropped} invalid value(s) rejected by FollowTheMoney")
        clean_properties = {
            str(key): [str(value) for value in values]
            for key, values in normalized_properties.items()
        }

    return {
        "id": entity_id,
        "schema": schema_name,
        "properties": clean_properties,
        "datasets": [str(value) for value in data.get("datasets") or [] if str(value).strip()],
        "referents": [str(value) for value in data.get("referents") or [] if str(value).strip()],
        "firstSeen": str(data.get("firstSeen") or data.get("first_seen") or ""),
        "lastSeen": str(data.get("lastSeen") or data.get("last_seen") or ""),
        "lastChange": str(data.get("lastChange") or data.get("last_change") or ""),
    }, warnings


def official_ftm_model():
    return _ftm_model


def official_logic_v2():
    return _LogicV2
