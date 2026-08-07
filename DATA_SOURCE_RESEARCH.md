# Public due-diligence data sources for Georgia and cross-border enrichment

Research date: 2026-08-07. This report excludes the already-assessed Companyinfo.ge internal JSON and NAPR/enreg business-register verification, except when describing join keys and source precedence. “Public” means viewable without privileged access; it does **not** automatically mean licensed for bulk copying or commercial redistribution.

## Executive recommendation

### Phase 1 — quick wins

1. **Georgia State Procurement Agency OCDS / eProcurement** — highest-value Georgian relationship source. Ingest the official machine-readable releases only after confirming that the current feed is updating; retain tender and contract documents as evidence. Historical OCDS coverage was officially described as complete for 2011–2019, with incomplete ongoing updates, so the transactional portal remains the decision source. Value 5, effort M, risk medium.
2. **OpenSanctions** — use `/match` for screening and FollowTheMoney bulk data where the operator’s licence permits. It supplies sanctions, PEPs, enforcement, identifiers and provenance and already matches the target model. Value 5, effort S, risk medium (commercial licence).
3. **GLEIF Golden Copy/API** — free authoritative LEI reference and parent-child relationships, BIC/ISIN mappings and addresses. Value 4, effort S, risk low.
4. **Official UN, OFAC, EU and UK sanctions** — scheduled authoritative list imports with versioned snapshots. Never make an adverse decision from name-only matching. Value 5, effort M, risk low.
5. **ICIJ Offshore Leaks bulk CSV** — graph-native offshore entity/officer/intermediary/address relationships with explicit ODbL/CC BY-SA terms and attribution. Treat inclusion as a lead, not wrongdoing. Value 5, effort S, risk medium.
6. **NBG supervised-entity registries and enforcement** — Georgian company IDs, licence/status and sanctions make high-confidence joins. Public HTML is usable for analyst verification; seek written permission or a data licence before routine bulk extraction. Value 5, effort M, risk medium.

### Phase 2

7. **Georgia political finance (SAO + TI Georgia)** — donor→party/payment links crossed with directors and suppliers. Official SAO is authoritative; TI’s enrichment is an NGO lead layer. Value 5, effort M/L, risk high for personal data and reuse.
8. **Georgia officials’ asset declarations** — official declaration documents connect officials, family, companies, property and income. Ingest only with a documented permission/legal basis and field-level minimisation. Value 5, effort L, risk high.
9. **Georgia environmental decisions + mineral licences/auctions** — companies→projects→sites→permits with coordinates and source documents. Portal documents are excellent evidence, but no bulk licence/API was verified. Value 4, effort M/L, risk medium.
10. **World Bank debarment + TED/OCP procurement** — cross-border supplier risk and contract counterparties; TED has an anonymous API and XML/RDF bulk access. Value 4, effort M, risk low.

## Full comparison matrix — Georgia first

Ingestion codes: **API** documented interface; **bulk** scheduled file import; **verify** analyst lookup/document capture; **permission** obtain written reuse/data-sharing approval first.

| Source / authority | Coverage, availability, cadence | Graph fields and stable joins | Access, limits and reuse | Recommended FtM/statement mapping | Effort / value / risk / priority |
|---|---|---|---|---|---|
| [State Procurement Agency](https://procurement.gov.ge/) and [eProcurement](https://tenders.procurement.gov.ge/) — official | Georgian plans, tenders, bids, awards, buyers, suppliers, contracts and procurement documents; live portal. | Georgian company ID/tax ID where present; tender/contract ID, buyer/supplier names, CPV, dates, amounts. | Public portal. Historical [OCDS portal](http://opendata.spa.ge/) and API were officially described in Georgia’s [OGP record](https://ogpgeorgia.gov.ge/en/monitorings/b5b1bb66-a197-4c39-841e-5bd3c26d5b42), but it also says updates were incomplete. No current API contract, rate limit or reuse licence was verified. **Permission** for systematic extraction; no CAPTCHA bypass. | `PublicBody`, `Company`, `Tender`, `Contract`, `Payment`/award event; buyer, bidder, awardedTo, amendment; snapshot JSON and signed contract documents as evidence. | M / 5 / medium / P1 |
| SPA blacklist/warnings and dispute/monitoring publications — official | Supplier exclusions, warnings, procurement disputes and monitoring decisions where published within SPA systems; availability varies by module. | Company ID/name, decision/case and tender IDs, dates, grounds, status. | HTML/PDF/search modules; no documented bulk endpoint verified. **Verify/permission**. | `Company`→`Sanction`/`Debarment`; `LegalDocument`; link affected tender/contract; never infer continuing exclusion after expiry. | M / 5 / medium / P1b |
| [State Audit Office](https://www.sao.ge/) / [political-finance monitoring](https://monitoring.sao.ge/) — official | Party/campaign income, donations, expenditure and declarations; official historic/current availability can vary by election cycle. | Donor name and lawful identifier fields, party, amount/date, declaration/report ID. Company ID and names enable supplier/director joins. | Public search/reports; no documented API/bulk licence verified. Personal-data and political-opinion sensitivity; **permission + DPIA/legal review** before bulk. | `Person`/`Company`→`PoliticalParty` via `Donation`; `Payment`; campaign/report events and original declaration evidence. | L / 5 / high / P2 |
| [TI Georgia political donations](https://transparency.ge/politicaldonations/en) — NGO | Structured donor/party view enriched with donors’ business interests; currently accessible. Not decision-authoritative. | Names, party, date/amount and company interests; join by Georgian company ID where supplied, otherwise resolved name. | Public web UI; licence/API not verified. Seek permission for bulk reuse and attribute. | Lead statements with NGO provenance; donation plus `Directorship`/ownership hypotheses must point back to official register evidence. | M / 4 / medium / P2 |
| [Official asset declarations](https://declaration.gov.ge/) — official | Public officials’ declarations: positions, employment, family, assets, companies, gifts, income/liabilities as required by law. Current public interface; declarations are periodic. | Official name/position, declaration ID/date; company IDs/names, asset addresses/cadastral refs where disclosed; relatives’ names only under lawful purpose. | Search/document-centric access; no documented public API or bulk-reuse licence verified. High personal-data risk. **Written permission/DPIA**, purpose limitation, retention and redaction. | `Person` (`PublicOfficial`), `Position`, `Occupancy`, `Family`, `Ownership`, `Asset`, `Interest`, `Debt`; declaration document and exact page/field as evidence. | L / 5 / high / P2 |
| [Georgia court decisions](https://info.court.ge/Decision) — official judiciary | Published/anonymised common-court judgments; fields exposed include case number, court, category, decision type and date. Completeness and timeliness should not be assumed. | Case number, party names only where not anonymised, company ID rarely, dates, court and cited contracts. | HTML search and downloadable decisions; no bulk/API/reuse licence verified. Respect anonymisation and robots. **Verify/permission**, not automated adverse screening. | `CourtCase`, `LegalDocument`, `Party` relations, judgment/order events; preserve source URL, retrieval date and anonymisation state. | L / 4 / high / P2 |
| [National Bureau of Enforcement debtor registry](https://nbe.gov.ge/service/movaleta-reestridan-amonatseris-gatsema?id=33&locale=en) / [search portal](https://debt.reestri.gov.ge/) — official | Current debtor status; NBE states it is public and constantly changing, and excludes secured claims plus public bodies. | Georgian company/person identifier used by the official lookup; status and extract date. | Interactive lookup/extract service; no bulk API/licence verified and personal-ID queries are sensitive. **Analyst verification only** unless DSA. | Time-bounded `EnforcementCase`/`DebtorStatus`; evidence snapshot with checked-at; do not retain cleared status indefinitely. | S / 4 / high / P2 |
| [NBG licensed banks](https://nbg.gov.ge/licensed-commercial-banks), other supervisory registries and [open-banking registry](https://nbg.gov.ge/en/page/open-banking-registry) — official regulator | Banks, microfinance, payment/VASP, brokerage, funds and other supervised entities; status/licence/date; updated administratively. | Georgian identification code, licence number, BIC/participant identifiers, names/status. | Public HTML tables/pages; no bulk API/licence verified. **Permission** for recurring extraction; verify before decisions. | `Company`→`License`/`RegulatoryStatus`; regulator, effective/revoked dates, licence document. | M / 5 / medium / P1 |
| [NBG AML/CFT sanctions](https://nbg.gov.ge/en/supervision/aml-cft) and [supervisory measures](https://nbg.gov.ge/en/page/certain-supervisory-measures) — official regulator | Published fines/measures since 2020; live search and notices, often including Georgian company identification number. | Company ID, entity type, sanction date/amount/ground and notice URL. | HTML/notices; no bulk API or explicit reuse licence verified. **Permission** for scheduled extraction. | `RegulatoryAction`/`Sanction`, `Company`, `Regulator`; notice is source evidence; distinguish fine, warning and licence action. | M / 5 / medium / P1 |
| Revenue Service taxpayer/VAT/customs portals — official tax/customs authority | Some taxpayer/VAT/status and customs services are publicly searchable, while declarations and most transactional customs data require authentication. | Tax/company ID, VAT status/date, customs identifiers where lawfully public. | [RS portal](https://www.rs.ge/) is service/auth oriented; **no public bulk/API contract verified**. Never automate authenticated or CAPTCHA surfaces. Use analyst verification or DSA. | `TaxStatus`/`Registration`; timestamped official verification; customs event only from explicitly released aggregate/open data. | M / 4 / high / P2 |
| [Environmental Information Portal](https://ei.gov.ge/) — official | Screening, scoping, EIA/SEA procedures, applicants/projects, locations, decisions and downloadable reports; live portal. | Georgian company name/ID in documents, project, municipality/address, coordinates, procedure/decision ID and date. | HTML search and PDFs/attachments; no documented API/licence verified. **Permission** for bulk; document-level analyst import is defensible. | `Project`, `Company`, `Permit`, `Site`, `Address`; application→decision events and PDFs/SHP attachments as evidence. | M/L / 4 / medium / P2 |
| [National Agency of Mineral Resources](https://www.namr.gov.ge/en_GB), [auctions](https://www.namr.gov.ge/en_GB/auction), eAuction — official | Mineral licence applications/auctions, licensees, resource, term, conditions and X/Y coordinates; agency maintains departmental licence/cadastral databases. | Company ID/name, auction/order/licence number, coordinates, dates/resource. | Public HTML/PDF plus eAuction; actual issued-licence bulk register/API not verified. **Permission/FOI or DSA** recommended. | `Company`→`License`→`Site`/`NaturalResource`; auction/bid/award events; order and geoinformation package evidence. | L / 4 / medium / P2 |
| [Matsne](https://matsne.gov.ge/) — official legislative gazette | Laws, decrees and normative acts with version/publication metadata; live and authoritative for legal texts. | Document number, issuer, adoption/publication/effective dates; named companies/persons only when lawfully published. | HTML/PDF search; no documented public bulk API or general redistribution licence verified. Link/cite; seek permission for wholesale corpus. | `LegalDocument`, `PublicBody`, legislative/adoption events; citations govern interpretation rather than entity risk. | S/M / 3 / low / P2 |
| [Georgia open-data portal](https://data.gov.ge/) — official catalogue | Cross-agency datasets; cadence, formats and availability vary by publisher and many records can be stale. | Dataset-specific; prefer official identifiers and spatial codes. | Catalogue/files/APIs only when each dataset explicitly provides them. Licence must be checked per dataset. | Dataset-scoped provenance; never promote catalogue metadata to an authoritative entity statement. | M / 3 / medium / opportunistic |
| Real estate/cadastral/map services (NAPR) — official | Parcels, addresses, extracts and restrictions subject to service/public-access rules; ownership details may be fee/auth restricted. | Cadastral code, address, owner/company ID where lawfully returned. | Public map/search and paid extracts; no permission to bulk harvest verified. **Verification/paid official extracts/DSA only**. | `Land`, `Address`, `Ownership`, `Lien` with validity interval; attach official extract, not map screenshot alone. | L / 5 / high / P2 |
| Municipal portals and Tbilisi open data — official/local | Permits, property, tenders, construction and spatial layers vary by municipality; fragmented and often document-only. | Company ID/name, permit/address/cadastral code, project/date. | Per-portal assessment required; no nationwide API. Prefer published CSV/GIS with an explicit licence; otherwise verify. | `PublicBody`, `Permit`, `Project`, `Site`; municipality-specific source catalogue. | L / 3 / medium / P3 |
| Georgian watchdogs: TI Georgia, IDFI, Social Justice Center and investigative media — NGO/secondary | Investigations, procurement/ownership analyses and curated datasets. Irregular, valuable leads but not authoritative findings. | Names/company IDs, contract/tender IDs, document links. | Public articles/downloads; rights differ. Obtain permission for bulk text/data and preserve attribution. | `Article`/`Investigation` evidence; allegations as qualified claims, never `Sanction`; link corroborating official records. | M / 4 / high / analyst |

## International and cross-border matrix

| Source / authority | Coverage and joins | Access/reuse | FtM use | Effort / value / risk / priority |
|---|---|---|---|---|
| [OpenSanctions documentation](https://www.opensanctions.org/docs/) / [API](https://api.opensanctions.org/) — authoritative aggregator | 400+ watchlist/PEP/enforcement sources; names, aliases, IDs, DOB, countries, company, vessel/aircraft, crypto and provenance; FTm IDs plus original identifiers. Updated multiple times daily/four times daily. | Search/match/entities API, OpenAPI and bulk JSON/CSV. Public download is not a commercial licence: [business use requires a licence](https://www.opensanctions.org/licensing/); trial/API keys and metering apply. | Native FtM nodes and statements; keep dataset/source lineage and match score. | S / 5 / medium / P1 |
| [GLEIF API](https://www.gleif.org/en/lei-data/gleif-api) and Golden Copy — official global LEI authority | LEI, legal name, registry IDs, status, addresses, direct/ultimate parents, BIC/ISIN mappings; global, updated daily. | Free public JSON:API and bulk Golden Copy files; GLEIF terms/licence and attribution apply. Example: search entities by name or LEI through API docs. | `LegalEntity`, `Identifier(LEI)`, `Address`, `Ownership`/parent relations with relationship status/period. | S / 4 / low / P1 |
| [ICIJ Offshore Leaks bulk](https://offshoreleaks.icij.org/pages/database) — NGO investigative dataset | 810k+ offshore entities across 200+ jurisdictions/leaks; entity, officer, intermediary, address and relationship IDs; records through 2020. | ZIP CSV and Neo4j dumps. Database ODbL; contents CC BY-SA; cite ICIJ. Do not imply illegality; not source-document-complete. | `Company`, `Person`, `Intermediary`, `Address`, `Directorship`/`Ownership` leads, leak/source collection. | S / 5 / medium / P1 |
| [OpenCorporates API](https://api.opencorporates.com/documentation/API-Reference) — authoritative aggregator | Company records from registries, officers, addresses, status and source provenance; jurisdiction code + company number are key. Georgian depth must be tested. | JSON/XML API; API key and plan limits. Free only for qualifying open-data projects under share-alike/open conditions; commercial/internal closed use needs a paid agreement. | `Company`, `Officer`, `Address`, identifiers; preserve originating registry and retrieval date. | M / 4 / medium / P2 |
| [UN consolidated list](https://main.un.org/securitycouncil/en/content/un-sc-consolidated-list) — official | UN designations: individuals/entities, aliases, DOB, nationality, address, designation, list date and narrative. | XML/HTML/PDF downloads; poll daily and archive versions. Confirm UN reuse/attribution terms before redistribution. | `Person`/`Organization`→`Sanction`; programme/list, effective dates and original XML. | S / 5 / low / P1 |
| [OFAC Sanctions List Service](https://ofac.treasury.gov/sanctions-list-service) — official | SDN and consolidated/non-SDN lists, entities, persons, vessels/aircraft, addresses, identifiers, programmes and remarks. | Official downloadable XML/CSV and list-search service; U.S. government data generally public-domain, but verify site notices and trademarks. Poll at least daily/change-triggered. | Sanction/designation statements; IMO/aircraft reg/passport/tax IDs; preserve list and publication version. | M / 5 / low / P1 |
| [EU Sanctions Map](https://www.sanctionsmap.eu/) / [EU consolidated financial sanctions](https://data.europa.eu/data/datasets/consolidated-list-of-persons-groups-and-entities-subject-to-eu-financial-sanctions) — official EU | EU restrictive measures and consolidated targets, aliases, identifiers, programme/legal acts. | EU data portal download/API metadata; licence under the relevant dataset notice. Use official downloadable data, not visual-map scraping. | `Sanction`, `LegalDocument`, target entity; EU legal-act evidence. | M / 5 / low / P1 |
| [UK Sanctions List](https://www.gov.uk/government/publications/the-uk-sanctions-list) — official | UK designations, aliases, IDs, addresses, reasons and regimes. OFSI’s former consolidated list closed 2026-01-28; use the UKSL going forward. | CSV/XML and other files; UK Open Government Licence where stated. Daily/change poll. | Sanction nodes/statements with unique designation ID and regime. | S / 5 / low / P1 |
| [World Bank debarred firms](https://www.worldbank.org/en/projects-operations/procurement/debarred-firms) — official MDB | Ineligible/cross-debarred firms and persons, addresses, dates, grounds and sanctions; list says it updates every 3 hours. | Public searchable HTML; no stable documented bulk API/reuse licence verified. Seek permission or consume via an expressly licensed aggregator; analyst checks meanwhile. | `Debarment`/`Sanction`, party, period, grounds and source snapshot. | M / 4 / medium / P2 |
| ADB, EBRD, AfDB and IDB sanctions lists — official MDBs | Institution and cross-debarment risks; names, country/address, grounds/period vary. | Public list/search/PDF formats vary and bulk licences/APIs were not verified. Source-by-source permission; do not scrape protected search. | `Debarment` with issuer, reciprocal/cross-debarment flag and effective period. | M/L / 3 / medium / P2 |
| [TED Search API](https://docs.ted.europa.eu/api/latest/search.html) / [TED Open Data](https://data.ted.europa.eu/) — official EU | EU/EEA procurement notices, buyers, suppliers, lots, awards, values, CPV, places and notice IDs; can reveal Georgian cross-border counterparties. | Anonymous `POST /v3/notices/search`, XML bulk and RDF/SPARQL. Intended for reuse including commercial value-added services; obey EU reuse notice and fair-use constraints. | `Tender`, `Lot`, `Contract`, `PublicBody`, supplier, location; notice/version evidence. | M / 4 / low / P2 |
| [OCP Data Registry](https://data.open-contracting.org/en/search/) — authoritative aggregator | OCDS/converted procurement datasets, including an OpenTender collection covering Georgia and 35 jurisdictions; formats JSON/CSV/Excel, typically six-month retrieval. | Download by dataset under publisher-specific licences; secondary/lagged, not decision-authoritative. | OCDS→FtM contract graph; retain publisher and transformation provenance. | S/M / 4 / medium / P2 |
| [Wikidata Query Service](https://query.wikidata.org/) — community reference | Names/aliases, offices, identifiers, companies, locations, IMO/aircraft IDs and cross-links; uneven and editable. | SPARQL and dumps under CC0; rate/usage policy applies. | Identity aliases and external IDs as low-precedence reference statements; never sole risk evidence. | S / 3 / low / P2 |
| [IMO GISIS](https://gisis.imo.org/) / Equasis — official/cooperative maritime | Vessel identity, IMO number, flag and safety/inspection information; useful for Georgian owners/ports. | Publicly visible interfaces commonly require accounts/acceptance; no unrestricted bulk API/reuse licence verified. **Analyst verification or DSA only**. | `Vessel`, IMO, flag/registration, inspection/detention event; source document. | M / 4 / medium / P2 |
| [OpenSky Network](https://opensky-network.org/data/api) and national aviation registers — research aggregator/official | Aircraft state/flight telemetry and registrations; ICAO24/callsign, time/position. Ownership coverage is not authoritative. | Documented API with authentication/rate limits; research/open licence restrictions vary. Do not use telemetry as ownership proof. | `Aircraft`, `Trip`/observation events; connect ICAO24 to official registration evidence. | M / 3 / medium / P3 |
| [INTERPOL Red Notices](https://www.interpol.int/How-we-work/Notices/Red-Notices/View-Red-Notices) — official law-enforcement publisher | Selected public notices only; names, DOB/nationality, charge and issuing country. Not all notices are public and a notice is not a conviction. | Public search; no bulk API/reuse licence verified. No automated scraping; analyst verification or licensed aggregator. | `Person`→`WantedNotice`, issuing authority, publication/revocation check date; strong UI disclaimer. | S / 4 / high / analyst |
| [OCCRP Aleph](https://aleph.occrp.org/) / OCCRP Data — NGO investigative platform | Documents and structured investigative entities; access varies by collection/account and sources can be sensitive. | No general public bulk API/reuse right should be assumed. Use public collections only under their terms; seek OCCRP agreement for integration. | Lead/document evidence with collection access controls; never re-publish restricted material. | L / 4 / high / permission |

## Join-key and identity-resolution map

```text
Existing Georgian Company
  ├─ company_id / tax_id ── SPA supplier, buyer, NBG licensee, NBG fine,
  │                         political donor, permit/license holder, VAT status
  ├─ registry_number + jurisdiction ── OpenCorporates
  ├─ LEI ── GLEIF entity ── direct/ultimate parent ── global Company
  ├─ legal/previous names + address ── ICIJ, sanctions, courts, watchdog leads
  ├─ tender_id / contract_id ── buyer, bidders, award, amendments, documents
  ├─ cadastral_code / normalized address / coordinates ── Land, EIA, mine/site
  ├─ IMO ── Vessel ── flag, owner/operator, sanction, port/inspection
  └─ aircraft registration / ICAO24 ── Aircraft observations and sanctions

Existing Person
  ├─ lawful national ID (restricted) ── official declaration/donation/debtor check
  ├─ name aliases + DOB + nationality ── sanctions/PEP/INTERPOL matching
  ├─ position + institution + dates ── PEP/official appointment resolution
  └─ declared company/property IDs ── Company, Land, interests, relatives
```

Resolution policy:

* Deterministic exact keys first: Georgian company ID, LEI, jurisdiction+registration number, IMO, aircraft registration, tender/contract/case/licence IDs.
* Composite person matches require at least two independent attributes; transliteration/name-only results remain candidates.
* Store identifiers as typed, issuer-scoped values. Never merge identifiers merely because their numeric text is equal across jurisdictions.
* Preserve aliases as source statements and retain Georgian script plus transliterations. Use address normalization and geocoding as supporting, not decisive, evidence.
* Maintain `sameAs`, `possibleMatch`, `notSameAs`, merge/split history, algorithm/version, score and analyst decision.

## Source precedence and contradiction policy

1. **Controlling primary record:** current official registry/regulator/court/gazette record for the fact it legally controls.
2. **Other primary official records:** procurement notices, declarations, permits and official sanctions; authoritative within their scope and effective dates.
3. **Official international identifiers:** GLEIF and official multilateral/national lists.
4. **Provenance-rich aggregators:** OpenSanctions, OpenCorporates, OCP; valuable normalization but never override their named primary source.
5. **NGO/investigative datasets:** ICIJ, OCCRP, TI/IDFI; lead/evidence layer with explicit qualification.
6. **Community/secondary references:** Wikidata and media; discovery and aliases only.

Contradictions are not overwritten. Store both statements with source, retrieval time, asserted effective interval and source-document hash. Prefer the competent authority and newest effective record for the operational view, while showing conflicts. Status changes (active→revoked, owner A→B) are temporal facts, not conflicts. Material conflicts create an analyst-review task. Negative/risk conclusions require the exact underlying designation/judgment/action, not aggregator membership or fuzzy-name similarity.

## Ingestion architecture and source contract implications

### Modes

* **Scheduled bulk imports:** ICIJ (on release), GLEIF (daily), official sanctions (daily or change-triggered), OpenSanctions bulk (licence-dependent), TED/XML/OCP (weekly/monthly according to source cadence).
* **Direct API:** GLEIF; TED; OpenSanctions matching/search subject to key and plan. Cache source responses only as allowed. Use exponential backoff, conditional requests and source-specific quotas.
* **Permission-gated connector:** SPA current procurement, SAO finance, declarations, NBG pages, debtor registry, courts, environmental/mining systems, OpenCorporates commercial data and MDB HTML lists.
* **Analyst verification only:** debtor/person lookups, court decisions, cadastral extracts, INTERPOL, Aleph restricted collections and any CAPTCHA/authenticated surface.

### Proposed backend source contract

Every source adapter should declare:

* `source_id`, owner, authority tier, canonical URL, jurisdiction and covered datasets;
* access mode, credential class, rate/bulk limits, terms URL/version, licence, attribution, commercial/redistribution permission and personal-data lawful basis;
* allowed fields/purposes, retention/redaction rules, robots/CAPTCHA/auth prohibitions and DSA expiry;
* cursor/watermark strategy, expected cadence, freshness SLA, last successful/complete fetch, checksum and immutable raw snapshot reference;
* parser/schema version, source record/document ID, original URL, published/effective/retrieved timestamps and evidence hash;
* mapping version, emitted statement IDs, confidence, match method/score and review state;
* deletion/correction/tombstone support and an emergency kill switch.

Recommended evidence model: immutable raw artefact → parsed source record → source-scoped statements → resolver candidates/judgements → canonical entity view. Public UI reads canonical views but can open the exact statement and permitted evidence. Sensitive documents require field/document ACLs, audit logs and retention policies.

## Sources rejected or deferred

* **Companyinfo.ge and NAPR business verification:** already assessed baseline; retain NAPR as controlling company record and Companyinfo only under its terms.
* **Any undocumented “internal API” discovered through browser traffic:** rejected until the owner documents or authorizes it. Public reachability is not reuse permission.
* **Authenticated RS/customs declarations, NAPR ownership extracts, GISIS/Equasis account data and Aleph restricted collections:** no bulk reuse authority; analyst lookup or DSA only.
* **CAPTCHA-protected procurement, debtor, court, cadastral or regulatory pages:** never bypass. Request a bulk feed/DSA.
* **Commercial adverse-media/corporate aggregators without a genuinely usable public licence** (Dow Jones, LSEG/World-Check, LexisNexis, Sayari, Orbis, Moody’s/BvD): deferred/paywalled and redistribution generally prohibited.
* **Google/general web search and social-media profiles:** no stable identifiers, poor reproducibility and terms/privacy risk; discovery only, never ingestion.
* **OpenCorporates free API for a closed/commercial product:** rejected unless the project qualifies under its open-data conditions or purchases the appropriate plan.
* **Old OFSI consolidated list:** obsolete since 2026-01-28; use the UK Sanctions List.
* **Stale Georgia OCDS mirrors as sole source:** useful historical/analytics layer but not authoritative for current tender status until update completeness is demonstrated.
* **Name-only PEP or “adverse media” lists assembled from Wikipedia/LLMs:** rejected for decisioning; insufficient provenance and unacceptable false-positive risk.

## Permissions/data-sharing agreements required

Written permission or a DSA is recommended before automated ingestion from SPA transactional modules, SAO monitoring, asset declarations, NBG HTML registries/actions, NBE debtor registry, courts, cadastral/property services, environmental/mineral portals, RS/customs services, MDB HTML debarment lists, INTERPOL, GISIS/Equasis and OCCRP/Aleph collections. The request should specify endpoints/files, frequency, commercial and redistribution use, retention, corrections/deletions, attribution, personal-data lawful basis and security controls.

## UI/graph implications

* Display source authority, freshness and evidence on every fact; distinguish **official status**, **aggregator match**, **investigative lead** and **analyst conclusion**.
* Model time explicitly for ownership, positions, licences, sanctions, debtor status and contracts.
* Show fuzzy matches as unresolved candidates with score/reasons; never silently merge or label a person sanctioned from a name hit.
* Add warning components for ICIJ inclusion, INTERPOL notices, court anonymisation and stale/secondary procurement data.
* Support document-level access controls and redaction; relatives/personal IDs must not be exposed by default.
* Procurement should have buyer→tender/lot→bidder/awardee→contract/amendment paths; permits should have company→project→site→decision; declarations should expose only lawful, field-level relationships.

