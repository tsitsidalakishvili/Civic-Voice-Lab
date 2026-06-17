from uuid import uuid4

from crm.db.neo4j import run_query, run_write
from crm.utils.text import clean_text

EVENT_STATUSES = ["Planned", "Scheduled", "Completed", "Cancelled"]
EVENT_REGISTRATION_STATUSES = ["Registered", "Attended", "Cancelled", "No Show"]


def list_events(limit=200):
    try:
        limit = int(limit)
    except Exception:
        limit = 200
    limit = max(10, min(1000, limit))
    return run_query(
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
        {"limit": limit},
        silent=True,
    )


def get_event(event_id=None, event_key=None):
    event_id = clean_text(event_id)
    event_key = clean_text(event_key)
    if not event_id and not event_key:
        return None
    df = run_query(
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
        {"eventId": event_id, "eventKey": event_key},
        silent=True,
    )
    if df.empty:
        return None
    row = df.iloc[0]
    return {
        "eventId": row.get("eventId"),
        "eventKey": row.get("eventKey"),
        "name": row.get("name"),
        "startDate": row.get("startDate"),
        "endDate": row.get("endDate"),
        "location": row.get("location"),
        "status": row.get("status"),
        "capacity": row.get("capacity"),
        "notes": row.get("notes"),
        "registrations": row.get("registrations"),
    }


def create_event(payload):
    name = clean_text(payload.get("name"))
    if not name:
        return False
    event_key = clean_text(payload.get("eventKey")) or str(uuid4())
    status = clean_text(payload.get("status")) or "Planned"
    if status not in EVENT_STATUSES:
        status = "Planned"
    return run_write(
        """
        CREATE (e:Event {
          eventId: randomUUID(),
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
            "eventKey": event_key,
            "name": name,
            "startDate": clean_text(payload.get("startDate")),
            "endDate": clean_text(payload.get("endDate")),
            "location": clean_text(payload.get("location")),
            "status": status,
            "capacity": payload.get("capacity") if payload.get("capacity") is not None else 0,
            "notes": clean_text(payload.get("notes")),
        },
    )


def delete_event(event_id):
    event_id = clean_text(event_id)
    if not event_id:
        return False
    exists = run_query(
        """
        MATCH (e:Event {eventId: $eventId})
        RETURN e.eventId AS eventId
        LIMIT 1
        """,
        {"eventId": event_id},
        silent=True,
    )
    if exists.empty:
        return False
    return run_write(
        """
        MATCH (e:Event {eventId: $eventId})
        DETACH DELETE e
        """,
        {"eventId": event_id},
    )


def _clean_people_rows(rows):
    cleaned = []
    for row in rows or []:
        email = clean_text(row.get("email"))
        if not email:
            continue
        cleaned.append(
            {
                "email": email,
                "firstName": clean_text(row.get("firstName")),
                "lastName": clean_text(row.get("lastName")),
                "phone": clean_text(row.get("phone")),
                "group": clean_text(row.get("group")),
            }
        )
    return cleaned


def bulk_register_people_for_event(event_id, rows, status="Registered"):
    event_id = clean_text(event_id)
    if not event_id:
        return 0
    cleaned = _clean_people_rows(rows)
    if not cleaned:
        return 0
    reg_status = clean_text(status) or "Registered"
    if reg_status not in EVENT_REGISTRATION_STATUSES:
        reg_status = "Registered"

    ok = run_write(
        """
        MATCH (e:Event {eventId: $eventId})
        WITH e
        UNWIND $rows AS row
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
        {"eventId": event_id, "rows": cleaned, "status": reg_status},
    )
    return len(cleaned) if ok else 0


def create_event_for_people(payload, rows, registration_status="Registered"):
    name = clean_text(payload.get("name"))
    if not name:
        return None
    status = clean_text(payload.get("status")) or "Planned"
    if status not in EVENT_STATUSES:
        status = "Planned"

    event_id = str(uuid4())
    event_key = clean_text(payload.get("eventKey")) or str(uuid4())
    created = run_write(
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
            "name": name,
            "startDate": clean_text(payload.get("startDate")),
            "endDate": clean_text(payload.get("endDate")),
            "location": clean_text(payload.get("location")),
            "status": status,
            "capacity": payload.get("capacity") if payload.get("capacity") is not None else 0,
            "notes": clean_text(payload.get("notes")),
        },
    )
    if not created:
        return None

    bulk_register_people_for_event(event_id, rows, status=registration_status)
    return event_id


def register_person_to_event(event_id, person, status="Registered", notes=""):
    event_id = clean_text(event_id)
    email = clean_text((person or {}).get("email"))
    if not event_id or not email:
        return False
    reg_status = clean_text(status) or "Registered"
    if reg_status not in EVENT_REGISTRATION_STATUSES:
        reg_status = "Registered"
    first_name = clean_text((person or {}).get("firstName"))
    last_name = clean_text((person or {}).get("lastName"))
    phone = clean_text((person or {}).get("phone"))
    group = clean_text((person or {}).get("group"))
    reg_notes = clean_text(notes)

    return run_write(
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
            "eventId": event_id,
            "email": email,
            "firstName": first_name,
            "lastName": last_name,
            "phone": phone,
            "group": group,
            "status": reg_status,
            "notes": reg_notes,
        },
    )


def list_event_registrations(event_id, limit=500):
    event_id = clean_text(event_id)
    if not event_id:
        return run_query("RETURN 1 AS _ WHERE false", silent=True)
    try:
        limit = int(limit)
    except Exception:
        limit = 500
    limit = max(10, min(5000, limit))
    return run_query(
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
        {"eventId": event_id, "limit": limit},
        silent=True,
    )


def list_registration_status_counts(limit_events=20):
    try:
        limit_events = int(limit_events)
    except Exception:
        limit_events = 20
    limit_events = max(1, min(100, limit_events))
    return run_query(
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
        {"limitEvents": limit_events},
        silent=True,
    )
