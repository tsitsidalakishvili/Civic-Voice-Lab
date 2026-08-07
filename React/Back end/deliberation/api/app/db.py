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
        "CREATE CONSTRAINT investigation_entity_id IF NOT EXISTS FOR (n:InvestigationEntity) REQUIRE n.entityId IS UNIQUE",
        "CREATE CONSTRAINT investigation_source_id IF NOT EXISTS FOR (n:InvestigationDataSource) REQUIRE n.sourceId IS UNIQUE",
        "CREATE CONSTRAINT investigation_evidence_id IF NOT EXISTS FOR (n:InvestigationEvidence) REQUIRE n.evidenceId IS UNIQUE",
        "CREATE CONSTRAINT investigation_statement_id IF NOT EXISTS FOR (n:InvestigationStatement) REQUIRE n.statementId IS UNIQUE",
        "CREATE CONSTRAINT investigation_name_normalized IF NOT EXISTS FOR (n:InvestigationName) REQUIRE n.normalizedName IS UNIQUE",
        "CREATE CONSTRAINT investigation_match_value_id IF NOT EXISTS FOR (n:InvestigationMatchValue) REQUIRE n.valueId IS UNIQUE",
        "CREATE CONSTRAINT investigation_resolution_id IF NOT EXISTS FOR (n:EntityResolutionReview) REQUIRE n.candidateId IS UNIQUE",
        "CREATE CONSTRAINT investigation_path_run_id IF NOT EXISTS FOR (n:InvestigationPathRun) REQUIRE n.runId IS UNIQUE",
        "CREATE CONSTRAINT investigation_import_run_id IF NOT EXISTS FOR (n:InvestigationImportRun) REQUIRE n.runId IS UNIQUE",
        "CREATE CONSTRAINT investigation_connector_run_id IF NOT EXISTS FOR (n:InvestigationConnectorRun) REQUIRE n.connectorRunId IS UNIQUE",
        "CREATE CONSTRAINT investigation_webhook_dispatch_id IF NOT EXISTS FOR (n:InvestigationWebhookDispatch) REQUIRE n.dispatchId IS UNIQUE",
        "CREATE CONSTRAINT company_registry_job_id IF NOT EXISTS FOR (n:CompanyRegistryEnrichmentJob) REQUIRE n.jobId IS UNIQUE",
        "CREATE CONSTRAINT company_registry_snapshot_id IF NOT EXISTS FOR (n:CompanyRegistrySnapshot) REQUIRE n.snapshotId IS UNIQUE",
        "CREATE CONSTRAINT investigation_finding_id IF NOT EXISTS FOR (n:InvestigationFinding) REQUIRE n.findingId IS UNIQUE",
        "CREATE CONSTRAINT investigation_publication_id IF NOT EXISTS FOR (n:InvestigationPublication) REQUIRE n.publicationId IS UNIQUE",
        "CREATE CONSTRAINT oidc_transaction_id IF NOT EXISTS FOR (n:OidcLoginTransaction) REQUIRE n.transactionId IS UNIQUE",
        "CREATE CONSTRAINT oidc_state_hash IF NOT EXISTS FOR (n:OidcLoginTransaction) REQUIRE n.stateHash IS UNIQUE",
        "CREATE CONSTRAINT auth_allowlist_id IF NOT EXISTS FOR (n:AuthAllowlistEntry) REQUIRE n.allowlistId IS UNIQUE",
        "CREATE CONSTRAINT auth_allowlist_entry_key IF NOT EXISTS FOR (n:AuthAllowlistEntry) REQUIRE n.entryKey IS UNIQUE",
        "CREATE CONSTRAINT auth_session_hash IF NOT EXISTS FOR (n:AuthSession) REQUIRE n.sessionIdHash IS UNIQUE",
        "CREATE CONSTRAINT auth_audit_event_id IF NOT EXISTS FOR (n:AuthAuditEvent) REQUIRE n.eventId IS UNIQUE",
        "CREATE CONSTRAINT compliance_audit_event_id IF NOT EXISTS FOR (n:ComplianceAuditEvent) REQUIRE n.eventId IS UNIQUE",
        "CREATE CONSTRAINT processing_purpose_version_id IF NOT EXISTS FOR (n:ProcessingPurpose) REQUIRE n.purposeVersionId IS UNIQUE",
        "CREATE CONSTRAINT notice_version_id IF NOT EXISTS FOR (n:NoticeVersion) REQUIRE n.noticeVersionId IS UNIQUE",
        "CREATE CONSTRAINT data_field_policy_id IF NOT EXISTS FOR (n:DataFieldPolicy) REQUIRE n.fieldPolicyId IS UNIQUE",
        "CREATE CONSTRAINT consent_event_id IF NOT EXISTS FOR (n:ConsentEvent) REQUIRE n.consentEventId IS UNIQUE",
        "CREATE CONSTRAINT consent_idempotency_hash IF NOT EXISTS FOR (n:ConsentEvent) REQUIRE n.idempotencyHash IS UNIQUE",
        "CREATE CONSTRAINT withdrawal_event_id IF NOT EXISTS FOR (n:WithdrawalEvent) REQUIRE n.withdrawalEventId IS UNIQUE",
        "CREATE CONSTRAINT withdrawal_idempotency_hash IF NOT EXISTS FOR (n:WithdrawalEvent) REQUIRE n.idempotencyHash IS UNIQUE",
        "CREATE CONSTRAINT suppression_event_id IF NOT EXISTS FOR (n:SuppressionEvent) REQUIRE n.suppressionEventId IS UNIQUE",
        "CREATE CONSTRAINT rights_request_id IF NOT EXISTS FOR (n:DataSubjectRequest) REQUIRE n.requestId IS UNIQUE",
        "CREATE CONSTRAINT rights_request_idempotency_hash IF NOT EXISTS FOR (n:DataSubjectRequest) REQUIRE n.idempotencyHash IS UNIQUE",
        "CREATE CONSTRAINT rights_review_id IF NOT EXISTS FOR (n:DataSubjectRequestReview) REQUIRE n.reviewId IS UNIQUE",
        "CREATE CONSTRAINT retention_job_id IF NOT EXISTS FOR (n:RetentionJob) REQUIRE n.jobId IS UNIQUE",
        "CREATE CONSTRAINT legal_hold_id IF NOT EXISTS FOR (n:LegalHold) REQUIRE n.holdId IS UNIQUE",
        "CREATE CONSTRAINT legal_hold_event_id IF NOT EXISTS FOR (n:LegalHoldEvent) REQUIRE n.eventId IS UNIQUE",
        "CREATE CONSTRAINT investigation_review_event_id IF NOT EXISTS FOR (n:InvestigationReviewEvent) REQUIRE n.reviewEventId IS UNIQUE",
        "CREATE CONSTRAINT investigation_dispute_id IF NOT EXISTS FOR (n:InvestigationDispute) REQUIRE n.disputeId IS UNIQUE",
        "CREATE CONSTRAINT investigation_correction_id IF NOT EXISTS FOR (n:InvestigationCorrection) REQUIRE n.correctionId IS UNIQUE",
        "CREATE CONSTRAINT investigation_appeal_id IF NOT EXISTS FOR (n:InvestigationAppeal) REQUIRE n.appealId IS UNIQUE",
        "CREATE CONSTRAINT investigation_purpose_event_id IF NOT EXISTS FOR (n:InvestigationPurposeEvent) REQUIRE n.eventId IS UNIQUE",
        "CREATE CONSTRAINT investigation_dispute_event_id IF NOT EXISTS FOR (n:InvestigationDisputeEvent) REQUIRE n.eventId IS UNIQUE",
        "CREATE CONSTRAINT investigation_appeal_event_id IF NOT EXISTS FOR (n:InvestigationAppealEvent) REQUIRE n.eventId IS UNIQUE",
    ]
    with driver.session(database=get_active_database()) as session:
        for query in queries:
            _execute_write(session, query)


def init_compliance_backfill():
    """Classify legacy records without inventing consent, purpose, or values."""
    driver = get_driver()
    queries = [
        """
        MATCH (record:Person)
        WHERE record.legacyConsentStatus IS NULL
        SET record.legacyConsentStatus = 'unknown',
            record.dataClassificationVersion = 1,
            record.complianceBackfilledAt = datetime()
        """,
        """
        MATCH (record:SupporterSignupSubmission)
        WHERE record.legacyConsentStatus IS NULL
        SET record.legacyConsentStatus = 'unknown',
            record.dataClassificationVersion = 1,
            record.complianceBackfilledAt = datetime()
        """,
        """
        MATCH (record:CampaignContribution)
        WHERE record.legacyConsentStatus IS NULL
        SET record.legacyConsentStatus = 'unknown',
            record.dataClassificationVersion = 1,
            record.complianceBackfilledAt = datetime()
        """,
        """
        MATCH (record:InvestigationStatement)
        WHERE record.statementNature IS NULL
        SET record.statementNature = CASE
              WHEN record.assertionKind = 'inferred' THEN 'inference'
              WHEN record.assertionKind = 'hypothesis' THEN 'analyst-assessment'
              ELSE 'source-assertion'
            END,
            record.provenanceSchemaVersion = coalesce(record.provenanceSchemaVersion, 1),
            record.complianceBackfilledAt = datetime()
        """,
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
