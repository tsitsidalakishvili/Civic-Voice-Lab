import os
from typing import Dict, List

from fastapi import APIRouter, HTTPException

from .investigation_companyinfo import (
    COMPANYINFO_API_BASE,
    COMPANYINFO_CAVEAT,
    COMPANYINFO_PUBLIC_URL,
    NAPR_SEARCH_URL,
    _companyinfo_config,
)


router = APIRouter()


SOURCE_CONTRACT_VERSION = "1.0"
PARSER_MAPPING_CONTRACT = {
    "artifactChain": [
        "immutable-artifact",
        "parsed-source-record",
        "source-scoped-temporal-statement",
        "resolution-candidate-and-judgement",
        "canonical-entity-view",
    ],
    "requiredRecordMetadata": [
        "sourceRecordId",
        "sourceDocumentId",
        "originalUrl",
        "publishedAt",
        "effectiveFrom",
        "effectiveTo",
        "retrievedAt",
        "evidenceHash",
        "parserVersion",
        "mappingVersion",
        "emittedStatementIds",
    ],
    "resolutionMetadata": [
        "matchMethod",
        "matchScore",
        "matchingEngineVersion",
        "reviewStatus",
        "reviewedBy",
        "reviewedAt",
    ],
    "identifierPolicy": (
        "Identifiers are typed and issuer-scoped. Numeric equality across issuers or "
        "jurisdictions never causes an automatic merge."
    ),
    "temporalPolicy": (
        "Status and relationship changes are effective-dated statements. Contradictions "
        "are retained and competent-source precedence affects only the operational view."
    ),
    "correctionPolicy": (
        "Corrections append snapshots/statements, may supersede prior statements, and "
        "support source tombstones without deleting the evidence audit trail."
    ),
}


def _base_adapter(
    *,
    adapter_id: str,
    name: str,
    owner: str,
    authority_tier: int,
    authority_level: str,
    jurisdiction: str,
    canonical_url: str,
    access_mode: str,
    implementation_status: str,
    permission_state: str,
    kill_switch: str,
) -> Dict[str, object]:
    return {
        "adapterId": adapter_id,
        "name": name,
        "owner": owner,
        "authorityTier": authority_tier,
        "authorityLevel": authority_level,
        "jurisdiction": jurisdiction,
        "canonicalUrl": canonical_url,
        "terms": {"url": "", "version": "unverified"},
        "license": {"name": "unverified", "attribution": "", "commercialUse": "unknown", "redistribution": "unknown"},
        "access": {
            "mode": access_mode,
            "credentialClass": "none",
            "quota": "source-specific",
            "cadence": "source-specific",
            "cursorStrategy": "source-specific",
            "robotsCaptchaAuthPolicy": "Never bypass access controls, CAPTCHA, authentication, or robots restrictions.",
        },
        "governance": {
            "permissionState": permission_state,
            "allowedPurposes": ["documented public-interest due-diligence investigation"],
            "allowedFields": [],
            "lawfulBasisRequired": False,
            "retentionPolicy": "source-specific",
            "redactionPolicy": "personal identifiers omitted by default",
            "dsaExpiresAt": "",
            "killSwitch": kill_switch,
        },
        "ingestion": {
            "implementationStatus": implementation_status,
            "enabled": False,
            "parserVersion": "not-implemented",
            "mappingVersion": "not-implemented",
            "lastAttemptAt": "",
            "lastSuccessAt": "",
            "lastCompleteAt": "",
            "completeness": "unknown",
            "watermark": "",
        },
        "artifactPolicy": {
            "immutableSnapshot": True,
            "contentHash": "sha256",
            "rawStorage": "only when permitted and protected; otherwise sanitized snapshot plus raw hash",
            "corrections": "append-only with supersession",
            "tombstones": True,
        },
    }


def source_adapter_catalog() -> List[Dict[str, object]]:
    companyinfo_config = _companyinfo_config()
    companyinfo = _base_adapter(
        adapter_id="companyinfo-ge",
        name="Companyinfo.ge corporate registry mirror",
        owner="Transparency International Georgia",
        authority_tier=4,
        authority_level="provenance-rich secondary aggregator",
        jurisdiction="GE",
        canonical_url=COMPANYINFO_PUBLIC_URL,
        access_mode="undocumented-api-low-volume",
        implementation_status="implemented-disabled-pending-permission",
        permission_state="undocumented-public-api-review-required",
        kill_switch="FS_COMPANYINFO_ENABLED",
    )
    companyinfo["terms"] = {"url": "", "version": "unverified"}
    companyinfo["license"] = {
        "name": "unverified",
        "attribution": "Companyinfo.ge / Transparency International Georgia; underlying NAPR records",
        "commercialUse": "unknown",
        "redistribution": "unknown",
    }
    companyinfo["access"].update(
        {
            "baseUrl": COMPANYINFO_API_BASE,
            "quota": {
                "minimumIntervalSeconds": companyinfo_config["minimumIntervalSeconds"],
                "retries": companyinfo_config["retries"],
                "timeoutSeconds": companyinfo_config["timeoutSeconds"],
            },
            "cadence": "monthly source; on-demand identification-code lookup",
            "cursorStrategy": "identification-code conditional refresh",
        }
    )
    companyinfo["governance"].update(
        {
            "permissionAcknowledged": companyinfo_config["permissionAcknowledged"],
            "allowedFields": ["company", "officers", "shareholders", "relationship history", "public-record indicators", "source document links"],
            "lawfulBasisRequired": True,
            "retentionPolicy": "case-scoped sanitized snapshots; no raw personal identifiers",
            "redactionPolicy": "personal IDs excluded from snapshots, logs, and API responses",
        }
    )
    companyinfo["ingestion"].update(
        {
            "enabled": bool(companyinfo_config["enabled"] and companyinfo_config["permissionAcknowledged"]),
            "parserVersion": "companyinfo-ge-v1",
            "mappingVersion": "ftm-companyinfo-v1",
        }
    )
    companyinfo["caveat"] = COMPANYINFO_CAVEAT

    napr = _base_adapter(
        adapter_id="napr-manual-verification",
        name="Georgian National Agency of Public Registry",
        owner="National Agency of Public Registry",
        authority_tier=1,
        authority_level="controlling primary official source",
        jurisdiction="GE",
        canonical_url=NAPR_SEARCH_URL,
        access_mode="analyst-verification",
        implementation_status="implemented-manual-only",
        permission_state="manual-low-volume-only",
        kill_switch="automation-always-disabled",
    )
    napr["access"].update(
        {"cadence": "on demand", "cursorStrategy": "none", "quota": "analyst initiated"}
    )
    napr["governance"].update(
        {
            "allowedFields": ["company registration facts", "application/participant facts", "source document reference"],
            "retentionPolicy": "verification record and permitted document reference",
        }
    )
    napr["ingestion"].update(
        {
            "enabled": True,
            "parserVersion": "manual-verification-v1",
            "mappingVersion": "ftm-napr-verification-v1",
        }
    )

    apify = _base_adapter(
        adapter_id="apify-facebook-public-groups",
        name="Apify public Facebook-group import",
        owner="Apify actor operator / Facebook source publisher",
        authority_tier=6,
        authority_level="discovery source",
        jurisdiction="MULTI",
        canonical_url="https://apify.com/scrapium/facebook-groups-scraper",
        access_mode="existing-run-dataset-or-export-import",
        implementation_status="implemented",
        permission_state="public-content-lawful-basis-required",
        kill_switch="APIFY_API_TOKEN or exported-items-only",
    )
    apify["ingestion"].update(
        {
            "enabled": True,
            "parserVersion": "apify-facebook-v1",
            "mappingVersion": "ftm-social-v1",
        }
    )
    apify["governance"].update(
        {
            "allowedPurposes": ["documented investigation of public group content"],
            "allowedFields": ["public groups", "posts", "top comments", "source-scoped profiles", "engagement snapshot", "attachment OCR"],
            "lawfulBasisRequired": True,
            "retentionPolicy": "7-730 day case setting",
            "redactionPolicy": "no raw actor records; evidence excerpt and checksum only",
        }
    )

    future = [
        ("ge-spa-procurement", "Georgia State Procurement Agency OCDS/eProcurement", "Georgia SPA", 1, "GE", "permission-gated", "permission-or-current-feed-contract-required"),
        ("opensanctions", "OpenSanctions", "OpenSanctions", 4, "MULTI", "license-gated", "appropriate-business-license-required"),
        ("gleif", "GLEIF LEI Golden Copy/API", "GLEIF", 3, "MULTI", "safe-to-implement-after-terms-recorded", "terms-and-attribution-review"),
        ("official-sanctions", "Official UN/OFAC/EU/UK sanctions", "Issuing authorities", 2, "MULTI", "safe-to-implement-source-by-source", "dataset-notice-review"),
        ("icij-offshore-leaks", "ICIJ Offshore Leaks", "ICIJ", 5, "MULTI", "safe-to-implement-with-attribution", "ODbL-and-CC-BY-SA-compliance"),
        ("nbg-regulatory", "National Bank of Georgia registries and enforcement", "NBG", 1, "GE", "permission-gated", "written-permission-or-dsa-required"),
    ]
    planned: List[Dict[str, object]] = []
    for adapter_id, name, owner, tier, jurisdiction, status, permission in future:
        row = _base_adapter(
            adapter_id=adapter_id,
            name=name,
            owner=owner,
            authority_tier=tier,
            authority_level=("official" if tier <= 3 else "aggregator/investigative"),
            jurisdiction=jurisdiction,
            canonical_url="",
            access_mode="not-enabled",
            implementation_status=status,
            permission_state=permission,
            kill_switch=f"FS_SOURCE_{adapter_id.upper().replace('-', '_')}_ENABLED",
        )
        planned.append(row)
    return [companyinfo, napr, apify, *planned]


@router.get("/source-adapters")
def list_source_adapters():
    adapters = source_adapter_catalog()
    return {
        "contractVersion": SOURCE_CONTRACT_VERSION,
        "adapterCount": len(adapters),
        "precedence": [
            {"tier": 1, "label": "Controlling primary official source"},
            {"tier": 2, "label": "Other primary official source"},
            {"tier": 3, "label": "Official international identifier or list"},
            {"tier": 4, "label": "Provenance-rich aggregator"},
            {"tier": 5, "label": "NGO or investigative dataset"},
            {"tier": 6, "label": "Community, media, or discovery source"},
        ],
        "pipeline": PARSER_MAPPING_CONTRACT,
        "adapters": adapters,
    }


@router.get("/source-adapters/{adapter_id}")
def get_source_adapter(adapter_id: str):
    adapter = next(
        (row for row in source_adapter_catalog() if row["adapterId"] == adapter_id),
        None,
    )
    if not adapter:
        raise HTTPException(status_code=404, detail="Source adapter not found")
    return {
        "contractVersion": SOURCE_CONTRACT_VERSION,
        "pipeline": PARSER_MAPPING_CONTRACT,
        "adapter": adapter,
    }
