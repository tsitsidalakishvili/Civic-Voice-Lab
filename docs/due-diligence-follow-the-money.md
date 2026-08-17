# Due Diligence as a Follow-the-Money Investigation System

## Product thesis

Civic Voice Lab Due Diligence is not a scorecard that tries to declare a person corrupt. It is a sourced data-integration and investigation workspace that helps an analyst connect public officials, relatives, companies, assets, contracts, payments, jurisdictions, documents, and screening records.

The system produces leads. An investigator verifies or rejects them. A report is a downstream publication of the verified work.

This direction follows the ideas presented in Friedrich Lindenberg's NODES 2023 talk, "Follow the Money: A Graph Ontology for Anti-Corruption Investigations", and the open FollowTheMoney model maintained by OpenSanctions.

## Core workflow

1. **Sources** — Register a dataset, its publisher, coverage, access conditions, and retrieval history.
2. **Normalize** — Map source records into a shared investigative ontology.
3. **Resolve** — Identify records that may refer to the same person or organization without silently merging them.
4. **Explore** — Traverse ownership, family, directorship, procurement, address, payment, and documentation paths.
5. **Review leads** — Accept, reject, or defer name matches and graph-generated hypotheses.
6. **Findings** — Record conclusions separately from the source facts that support them.
7. **Publish** — Generate a report with complete evidence lineage and known limitations.

## Current workspace flow

The authenticated Due Diligence workspace opens on an overview and groups the analyst flow into three destinations:

1. **Evidence** — run baseline collection, inspect source coverage/freshness, review normalized entities, and assess possible identity matches.
2. **Investigation** — explore FollowTheMoney paths and connected evidence.
3. **Outcome** — curate findings, review saved briefs and source audits, record a case decision, and create a publication snapshot when ready.

Baseline collection is automated triage, not a case decision. It distinguishes sources that returned evidence from sources that require operator setup and requires the analyst to review coverage and identity matches before promoting a signal to a finding. The former shell tabs are normalized to these destinations for in-application handoffs; they do not change the API contract.

## Three representations

### 1. Source statements

The durable evidence layer. Each property value or relationship assertion records:

- source entity ID and canonical entity ID;
- schema and property;
- normalized and original value;
- source dataset and processing origin;
- first-seen and last-seen timestamps;
- evidence/document reference;
- whether it is sourced, inferred, or awaiting review.

Contradictory values are retained as separate sourced statements. They are not overwritten.

### 2. Integrated entities

Source-specific fragments can be assigned to a canonical entity after explicit resolution. The integrated profile is assembled from statements, so every displayed name, date, identifier, and jurisdiction remains attributable to its source.

Exact names can generate candidate pairs, but a same-name match is never an automatic merge.

### 3. Investigation projection

Neo4j nodes and relationships provide a fast projection for investigative questions. Relationship-like records such as ownership and directorship retain their own schema, dates, percentages, roles, and evidence even when rendered as visual edges.

## Initial ontology

Entity classes:

- Person, PublicOfficial and Relative
- Organization, Company, PublicBody and Intermediary
- Asset, RealEstate, Vehicle, Vessel and Airplane
- Contract, ContractAward and CallForTenders
- Payment and BankAccount
- Address and Jurisdiction
- Article, Document and ScreeningRecord

Relationship/interstitial classes:

- Family
- Ownership
- Directorship or Membership
- Employment or Occupancy
- ContractAward
- Payment
- Documentation
- Associate
- Identity hypothesis

New source adapters may extend the vocabulary where a practical dataset requires additional precision. They should not create jurisdiction-specific classes when a property is sufficient.

## Required investigative questions

- How is a public official connected to an offshore or otherwise relevant company?
- Is a relative or close associate connected to a government supplier or contract award?
- Which assets or legal entities are owned or controlled by a sanctioned entity?
- Which people and organizations share an address, identifier, phone number, bank account, or intermediary?
- What is the shortest evidence-backed path between two entities?
- Which links are sourced facts, analyst-added assertions, inferred patterns, or unresolved name matches?
- Which source statements disagree about an identity, date, ownership percentage, or jurisdiction?

## Integrity rules

- Never use a graph pattern or a name match as proof of corruption.
- Never discard a contradictory source value merely because another value appears more likely.
- Never merge source records only because their names match.
- Every materialized relationship must resolve to evidence or an auditable analyst review.
- Findings must reference the exact nodes, relationships, statements, and evidence used to support them.
- Sensitive personal data must be minimized; for example, expose a relative's birth year instead of a full birth date unless the exact date is necessary and lawfully handled.

## Backend boundaries

- The source-statement layer is authoritative for provenance.
- Canonical identity assignments are explicit, reviewed decisions.
- The Neo4j investigation graph is a query projection and can be rebuilt from source statements.
- Generated leads are deterministic read models and remain separate from verified findings.
- Reports consume verified findings and evidence; they do not become the source of truth.

## References

- https://neo4j.com/videos/nodes-2023-follow-the-money-a-graph-ontology-for-anti-corruption-investigations/
- https://followthemoney.tech/docs/
- https://followthemoney.tech/docs/statements/
- https://followthemoney.tech/explorer/schemata/
