"""
CRM – event CRUD and registration endpoints.
"""
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from .db import get_driver
from .routes_crm_helpers import (
    EVENT_STATUSES,
    EVENT_REGISTRATION_STATUSES,
    _clean_text,
    _execute_read,
    _execute_write,
    _db_session,
    _query_df,
    _sanitize_neo4j_row,
)

router = APIRouter()

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class EventCreate(BaseModel):
    name: str
    startDate: Optional[str] = ""
    endDate: Optional[str] = ""
    location: Optional[str] = ""
    status: Optional[str] = "Planned"
    capacity: Optional[int] = 0
    notes: Optional[str] = ""


class EventOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    event_id: str = Field(alias="eventId")
    event_key: Optional[str] = Field(alias="eventKey", default=None)
    name: str
    start_date: Optional[str] = Field(alias="startDate", default="")
    end_date: Optional[str] = Field(alias="endDate", default="")
    location: Optional[str] = ""
    status: str
    capacity: int = 0
    registrations: int = 0
    notes: Optional[str] = ""


class EventRegistrationOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    email: str
    first_name: Optional[str] = Field(alias="firstName", default="")
    last_name: Optional[str] = Field(alias="lastName", default="")
    phone: Optional[str] = ""
    group: str
    registration_status: str = Field(alias="registrationStatus")
    notes: Optional[str] = ""
    registered_at: Optional[str] = Field(alias="registeredAt", default=None)
    updated_at: Optional[str] = Field(alias="updatedAt", default=None)


class EventRegisterRequest(BaseModel):
    person: dict
    status: Optional[str] = "Registered"
    notes: Optional[str] = ""


class EventBulkRegisterRequest(BaseModel):
    rows: List[dict]
    status: Optional[str] = "Registered"


class EventCreateWithPeopleRequest(BaseModel):
    event: EventCreate
    rows: List[dict]
    registrationStatus: Optional[str] = "Registered"


class EventStatusCountOut(BaseModel):
    event_id: str = Field(alias="eventId")
    event_name: str = Field(alias="eventName")
    registration_status: str = Field(alias="registrationStatus")
    count: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/events", response_model=List[EventOut])
def list_events(limit: int = Query(200, ge=10, le=1000)):
    df = _query_df(
        """
        MATCH (e:Event)
        OPTIONAL MATCH (p:Person)-[r:REGISTERED_FOR]->(e)
        RETURN
          e.eventId AS eventId,
          e.eventKey AS eventKey,
          e.name AS name,
          e.startDate AS startDate,
          e.endDate AS endDate,
          e.location AS location,
          coalesce(e.status, 'Planned') AS status,
          coalesce(e.capacity, 0) AS capacity,
          count(r) AS registrations,
          coalesce(e.notes, '') AS notes
        ORDER BY e.startDate DESC
        LIMIT $limit
        """,
        {"limit": int(limit)},
    )
    records = df.to_dict(orient="records") if not df.empty else []
    return [EventOut.model_validate(_sanitize_neo4j_row(r)) for r in records]


@router.get("/events/detail", response_model=EventOut)
def get_event_detail(event_id: Optional[str] = None, event_key: Optional[str] = None):
    df = _query_df(
        """
        MATCH (e:Event)
        WHERE ($eventId IS NOT NULL AND e.eventId = $eventId)
           OR ($eventKey IS NOT NULL AND e.eventKey = $eventKey)
        OPTIONAL MATCH (p:Person)-[r:REGISTERED_FOR]->(e)
        RETURN
          e.eventId AS eventId,
          e.eventKey AS eventKey,
          e.name AS name,
          coalesce(e.startDate, '') AS startDate,
          coalesce(e.endDate, '') AS endDate,
          coalesce(e.location, '') AS location,
          coalesce(e.status, 'Planned') AS status,
          coalesce(e.capacity, 0) AS capacity,
          coalesce(e.notes, '') AS notes,
          count(r) AS registrations
        LIMIT 1
        """,
        {"eventId": _clean_text(event_id), "eventKey": _clean_text(event_key)},
    )
    if df.empty:
        raise HTTPException(status_code=404, detail="Event not found")
    return EventOut.model_validate(_sanitize_neo4j_row(df.iloc[0].to_dict()))


@router.post("/events", response_model=EventOut)
def create_event(payload: EventCreate):
    name = _clean_text(payload.name)
    if not name:
        raise HTTPException(status_code=400, detail="Event name is required")
    status = _clean_text(payload.status) or "Planned"
    if status not in EVENT_STATUSES:
        status = "Planned"
    event_id = str(uuid4())
    event_key = str(uuid4())
    driver = get_driver()
    query = """
    CREATE (e:Event {
      eventId: $eventId,
      eventKey: $eventKey,
      name: $name,
      startDate: $startDate,
      endDate: $endDate,
      location: $location,
      status: $status,
      capacity: $capacity,
      notes: $notes,
      createdAt: datetime()
    })
    RETURN
      e.eventId AS eventId,
      e.eventKey AS eventKey,
      e.name AS name,
      e.startDate AS startDate,
      e.endDate AS endDate,
      e.location AS location,
      coalesce(e.status, 'Planned') AS status,
      coalesce(e.capacity, 0) AS capacity,
      0 AS registrations,
      coalesce(e.notes, '') AS notes
    """
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            query,
            {
                "eventId": event_id,
                "eventKey": event_key,
                "name": name,
                "startDate": _clean_text(payload.startDate),
                "endDate": _clean_text(payload.endDate),
                "location": _clean_text(payload.location),
                "status": status,
                "capacity": payload.capacity or 0,
                "notes": _clean_text(payload.notes),
            },
        )
    if not records:
        raise HTTPException(status_code=500, detail="Event could not be created")
    return EventOut.model_validate(_sanitize_neo4j_row(records[0].data()))


@router.post("/events/with-people")
def create_event_for_people(payload: EventCreateWithPeopleRequest):
    event = payload.event
    rows = payload.rows or []
    if not _clean_text(event.name):
        raise HTTPException(status_code=400, detail="Event name is required")
    status = _clean_text(event.status) or "Planned"
    if status not in EVENT_STATUSES:
        status = "Planned"
    event_id = str(uuid4())
    event_key = str(uuid4())
    driver = get_driver()
    with _db_session(driver) as session:
        _execute_write(
            session,
            """
            CREATE (e:Event {
              eventId: $eventId,
              eventKey: $eventKey,
              name: $name,
              startDate: $startDate,
              endDate: $endDate,
              location: $location,
              status: $status,
              capacity: $capacity,
              notes: $notes,
              createdAt: datetime()
            })
            """,
            {
                "eventId": event_id,
                "eventKey": event_key,
                "name": _clean_text(event.name),
                "startDate": _clean_text(event.startDate),
                "endDate": _clean_text(event.endDate),
                "location": _clean_text(event.location),
                "status": status,
                "capacity": event.capacity or 0,
                "notes": _clean_text(event.notes),
            },
        )
        _execute_write(
            session,
            """
            UNWIND $rows AS row
            MATCH (e:Event {eventId: $eventId})
            WITH e, row
            WHERE row.email IS NOT NULL AND trim(row.email) <> ""
            MERGE (p:Person {email: row.email})
            ON CREATE SET p.personId = randomUUID(), p.createdAt = datetime()
            SET p.firstName = coalesce(row.firstName, p.firstName),
                p.lastName = coalesce(row.lastName, p.lastName),
                p.phone = coalesce(row.phone, p.phone),
                p.updatedAt = datetime()
            WITH e, p, row
            FOREACH (_ IN CASE
              WHEN row.group IS NULL OR row.group = '' OR NOT row.group IN ['Supporter','Member']
              THEN [] ELSE [1]
            END |
              MERGE (st:SupporterType {name: row.group})
              MERGE (p)-[:CLASSIFIED_AS]->(st)
            )
            MERGE (p)-[r:REGISTERED_FOR]->(e)
            ON CREATE SET r.registeredAt = datetime()
            SET r.status = $status,
                r.updatedAt = datetime()
            """,
            {"eventId": event_id, "rows": rows, "status": payload.registrationStatus},
        )
    return {"eventId": event_id}


@router.post("/events/{event_id}/register")
def register_person_to_event(event_id: str, payload: EventRegisterRequest):
    person = payload.person or {}
    email = _clean_text(person.get("email"))
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    status = _clean_text(payload.status) or "Registered"
    if status not in EVENT_REGISTRATION_STATUSES:
        status = "Registered"
    driver = get_driver()
    with _db_session(driver) as session:
        _execute_write(
            session,
            """
            MATCH (e:Event {eventId: $eventId})
            MERGE (p:Person {email: $email})
            ON CREATE SET p.personId = randomUUID(), p.createdAt = datetime()
            SET p.firstName = coalesce($firstName, p.firstName),
                p.lastName = coalesce($lastName, p.lastName),
                p.phone = coalesce($phone, p.phone),
                p.updatedAt = datetime()
            FOREACH (_ IN CASE
              WHEN $group IS NULL OR $group = '' OR NOT $group IN ['Supporter','Member']
              THEN [] ELSE [1]
            END |
              MERGE (st:SupporterType {name: $group})
              MERGE (p)-[:CLASSIFIED_AS]->(st)
            )
            MERGE (p)-[r:REGISTERED_FOR]->(e)
            ON CREATE SET r.registeredAt = datetime()
            SET r.status = $status,
                r.notes = $notes,
                r.updatedAt = datetime()
            """,
            {
                "eventId": _clean_text(event_id),
                "email": email,
                "firstName": _clean_text(person.get("firstName")),
                "lastName": _clean_text(person.get("lastName")),
                "phone": _clean_text(person.get("phone")),
                "group": _clean_text(person.get("group")),
                "status": status,
                "notes": _clean_text(payload.notes),
            },
        )
    return {"registered": True}


@router.post("/events/{event_id}/register/bulk")
def bulk_register_people(event_id: str, payload: EventBulkRegisterRequest):
    rows = payload.rows or []
    if not rows:
        raise HTTPException(status_code=400, detail="No rows provided")
    status = _clean_text(payload.status) or "Registered"
    if status not in EVENT_REGISTRATION_STATUSES:
        status = "Registered"
    driver = get_driver()
    with _db_session(driver) as session:
        _execute_write(
            session,
            """
            MATCH (e:Event {eventId: $eventId})
            WITH e
            UNWIND $rows AS row
            WITH e, row
            WHERE row.email IS NOT NULL AND trim(row.email) <> ""
            MERGE (p:Person {email: row.email})
            ON CREATE SET p.personId = randomUUID(), p.createdAt = datetime()
            SET p.firstName = coalesce(row.firstName, p.firstName),
                p.lastName = coalesce(row.lastName, p.lastName),
                p.phone = coalesce(row.phone, p.phone),
                p.updatedAt = datetime()
            WITH e, p, row
            FOREACH (_ IN CASE
              WHEN row.group IS NULL OR row.group = '' OR NOT row.group IN ['Supporter','Member']
              THEN [] ELSE [1]
            END |
              MERGE (st:SupporterType {name: row.group})
              MERGE (p)-[:CLASSIFIED_AS]->(st)
            )
            MERGE (p)-[r:REGISTERED_FOR]->(e)
            ON CREATE SET r.registeredAt = datetime()
            SET r.status = $status,
                r.updatedAt = datetime()
            """,
            {"eventId": _clean_text(event_id), "rows": rows, "status": status},
        )
    return {"registered": len(rows)}


@router.get("/events/{event_id}/registrations", response_model=List[EventRegistrationOut])
def list_event_registrations(event_id: str, limit: int = Query(500, ge=10, le=5000)):
    df = _query_df(
        """
        MATCH (e:Event {eventId: $eventId})<-[r:REGISTERED_FOR]-(p:Person)
        OPTIONAL MATCH (p)-[:CLASSIFIED_AS]->(st:SupporterType)
        WITH p, r, collect(DISTINCT st.name) AS types
        RETURN
          p.email AS email,
          coalesce(p.firstName, '') AS firstName,
          coalesce(p.lastName, '') AS lastName,
          coalesce(p.phone, '') AS phone,
          CASE
            WHEN any(x IN types WHERE toLower(x) CONTAINS 'member') THEN 'Member'
            WHEN size(types) = 0 THEN 'Supporter'
            ELSE head(types)
          END AS group,
          coalesce(r.status, 'Registered') AS registrationStatus,
          coalesce(r.notes, '') AS notes,
          toString(r.registeredAt) AS registeredAt,
          toString(r.updatedAt) AS updatedAt
        ORDER BY r.updatedAt DESC
        LIMIT $limit
        """,
        {"eventId": _clean_text(event_id), "limit": int(limit)},
    )
    recs = df.to_dict(orient="records") if not df.empty else []
    return [EventRegistrationOut.model_validate(_sanitize_neo4j_row(r)) for r in recs]


@router.get("/events/registrations/status-counts", response_model=List[EventStatusCountOut])
def list_registration_status_counts(limit_events: int = Query(20, ge=1, le=100)):
    df = _query_df(
        """
        MATCH (e:Event)
        WITH e
        ORDER BY coalesce(e.startDate, '') DESC
        LIMIT $limitEvents
        OPTIONAL MATCH (:Person)-[r:REGISTERED_FOR]->(e)
        RETURN
          e.eventId AS eventId,
          coalesce(e.name, 'Untitled event') AS eventName,
          coalesce(r.status, 'Registered') AS registrationStatus,
          count(r) AS count
        ORDER BY eventName ASC, registrationStatus ASC
        """,
        {"limitEvents": int(limit_events)},
    )
    recs = df.to_dict(orient="records") if not df.empty else []
    return [EventStatusCountOut.model_validate(_sanitize_neo4j_row(r)) for r in recs]


@router.delete("/events/{event_id}")
def delete_event(event_id: str):
    driver = get_driver()
    with _db_session(driver) as session:
        _execute_write(
            session,
            "MATCH (e:Event {eventId: $eventId}) DETACH DELETE e",
            {"eventId": _clean_text(event_id)},
        )
    return {"deleted": True, "event_id": event_id}
