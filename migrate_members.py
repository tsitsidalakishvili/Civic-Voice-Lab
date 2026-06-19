#!/usr/bin/env python3
"""
One-time migration script for Georgian MEMBERS data.
Reads local CSV file and imports directly into Neo4j as "Member" type.
"""

import os
import sys
import re
import uuid
from datetime import datetime
from typing import Optional, List
import pandas as pd
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

CSV_FILE = r"C:\Users\Tsitsi\Desktop\FS\members - წევრები.csv"


def _parse_date_to_age(date_val) -> Optional[int]:
    """Parse date format (MM/DD/YYYY or DD/MM/YYYY) and calculate age."""
    if pd.isna(date_val) or date_val is None or date_val == "":
        return None
    
    date_str = str(date_val).strip()
    if not date_str:
        return None
    
    # Try multiple formats
    for fmt in ("%m/%d/%Y", "%d/%m/%Y", "%m/%d/%y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            dob = datetime.strptime(date_str, fmt)
            today = datetime.today()
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            return max(0, age)
        except ValueError:
            continue
    
    return None


def _parse_georgian_boolean(val) -> bool:
    """Parse Georgian boolean values."""
    if pd.isna(val):
        return False
    val_str = str(val).strip().lower()
    return val_str in ("დიახ", "კი", "yes", "true", "1", "თანხმები", "თანხმები მასზე")


def _get_column(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    """Find first matching column name (case-insensitive)."""
    cols = {c.lower().strip(): c for c in df.columns}
    for cand in candidates:
        key = cand.lower().strip()
        if key in cols:
            return cols[key]
    return None


def _split_list(val) -> List[str]:
    """Split comma/newline separated values into list."""
    if pd.isna(val) or val is None or str(val).strip() == "":
        return []
    items = re.split(r"[,;\n]", str(val))
    return [i.strip() for i in items if i.strip()]


def _build_import_rows(df: pd.DataFrame, default_type: str) -> List[dict]:
    """Build import rows from Georgian members CSV data."""
    if df.empty:
        return []
    
    # Skip header row if it contains "ეროვნული საბჭო" (National Council)
    if len(df) > 0:
        first_row = df.iloc[0]
        first_whatsapp = str(first_row.get(df.columns[0], "")).lower()
        if "ეროვნული" in first_whatsapp or "საბჭო" in first_whatsapp:
            df = df.iloc[1:].reset_index(drop=True)
            print("  Skipped header row (ეროვნული საბჭო)")
    
    # Member column mappings
    col_whatsapp = _get_column(df, ["whatsapp", "whatsApp", "WhatsApp ჩატი", "whatsapp_chat"])
    col_join_date = _get_column(df, ["გაწევრიანების თარიღი", "join_date", "membership_date"])
    col_first_name = _get_column(df, ["სახელი", "first_name", "firstname", "name"])
    col_last_name = _get_column(df, ["გვარი", "last_name", "lastname", "surname"])
    col_gender = _get_column(df, ["სქესი", "gender", "sex"])
    col_dob = _get_column(df, ["დაბ.თარიღი", "date_of_birth", "dob", "birthdate", "birth_date"])
    col_phone = _get_column(df, ["ტელ", "phone", "telephone", "mobile"])
    col_email = _get_column(df, ["ელ.ფოსტა", "email", "e_mail", "e-mail"])
    col_address = _get_column(df, ["მისამართი", "address", "location"])
    col_profession = _get_column(df, ["პროფესია / სამუშაო მიმართულება მოედანში", "profession", "occupation", "workplace"])
    col_social_media = _get_column(df, ["სოც.ქსელები", "social_media", "facebook", "instagram", "social"])
    col_was_party_member = _get_column(df, ["ყოფილხართ თუ არა რომელიმე პარტიის წევრი?", "was_party_member", "former_party"])
    col_party_details = _get_column(df, ["გთხოვთ, მიუთითოთ კონკრეტულად", "party_details"])
    col_about = _get_column(df, ["მოგვიყევით თქვენს შესახებ და გვითხარით, რატომ გსურთ შემოგვიერთდეთ.", "about", "bio"])
    col_time_availability = _get_column(df, ["რა დროს დაუთმობთ ჩვენს საქმიანობას ?", "time_availability"])
    col_topics = _get_column(df, ["გთხოვთ, მონიშნოთ თქვენთვის საინტერესო თემები", "topics", "interests"])
    col_involvement = _get_column(df, ["რა მიმართულებით გირჩევნიათ ჩაერთოთ \"თავისუფლების მოედნის\"  საქმიანობაში?", "involvement"])
    col_how_to_help = _get_column(df, ["როგორ დაეხმარებით \"თავისუფლების მოედანს\"?", "how_to_help"])
    col_comments = _get_column(df, ["სივრცე დამატებითი კომენტარისთვის", "comments", "notes"])
    
    if not col_email:
        print("ERROR: No email column found!")
        print(f"Available columns: {list(df.columns)}")
        return []
    
    print(f"  Email column: {col_email}")
    print(f"  WhatsApp column: {col_whatsapp}")
    
    rows = []
    for _, raw in df.iterrows():
        email = str(raw.get(col_email, "")).strip().lower()
        if not email or email in ("nan", "none", "null", ""):
            continue
        
        # Parse gender - 1 might be Female, blank might be Male
        gender_val = str(raw.get(col_gender, "")).strip() if col_gender else ""
        if gender_val == "1":
            gender = "Female"
        elif gender_val == "2":
            gender = "Male"
        else:
            gender = gender_val
        
        # Calculate age from date of birth
        age = _parse_date_to_age(raw.get(col_dob)) if col_dob else None
        
        # Parse boolean fields
        was_party_member = _parse_georgian_boolean(raw.get(col_was_party_member)) if col_was_party_member else False
        
        # WhatsApp value
        whatsapp = str(raw.get(col_whatsapp, "")).strip() if col_whatsapp else ""
        if whatsapp.lower() in ("nan", "none", "null"):
            whatsapp = ""
        
        # Join date
        join_date = str(raw.get(col_join_date, "")).strip() if col_join_date else ""
        
        row = {
            "email": email,
            "firstName": str(raw.get(col_first_name, "")).strip() if col_first_name else "",
            "lastName": str(raw.get(col_last_name, "")).strip() if col_last_name else "",
            "gender": gender,
            "age": age,
            "phone": str(raw.get(col_phone, "")).strip() if col_phone else "",
            "address": str(raw.get(col_address, "")).strip() if col_address else "",
            "lat": None,
            "lon": None,
            "profession": str(raw.get(col_profession, "")).strip() if col_profession else "",
            "socialMedia": str(raw.get(col_social_media, "")).strip() if col_social_media else "",
            "wasPartyMember": was_party_member,
            "partyDetails": str(raw.get(col_party_details, "")).strip() if col_party_details else "",
            "about": str(raw.get(col_about, "")).strip() if col_about else "",
            "timeAvailability": str(raw.get(col_time_availability, "")).strip() if col_time_availability else "",
            "topicsOfInterest": _split_list(raw.get(col_topics)) if col_topics else [],
            "involvementAreas": _split_list(raw.get(col_involvement)) if col_involvement else [],
            "howToHelp": str(raw.get(col_how_to_help, "")).strip() if col_how_to_help else "",
            "additionalComments": str(raw.get(col_comments, "")).strip() if col_comments else "",
            "agreesWithManifesto": True,  # Assume members agree
            "interestedInMembership": True,  # They are already members
            "personalId": "",  # Not in this file
            "whatsappChat": whatsapp,
            "dateOfBirth": str(raw.get(col_dob, "")).strip() if col_dob else "",
            "joinDate": join_date,
            "supporterType": default_type,
        }
        rows.append(row)
    
    return rows


def get_neo4j_driver():
    """Create Neo4j driver from environment variables."""
    uri = os.getenv("DELIBERATION_NEO4J_AURA_URI") or os.getenv("DELIBERATION_NEO4J_URI") or os.getenv("NEO4J_URI")
    user = os.getenv("DELIBERATION_NEO4J_AURA_USER") or os.getenv("DELIBERATION_NEO4J_USER") or os.getenv("NEO4J_USER")
    password = os.getenv("DELIBERATION_NEO4J_AURA_PASSWORD") or os.getenv("DELIBERATION_NEO4J_PASSWORD") or os.getenv("NEO4J_PASSWORD")
    
    if not all([uri, user, password]):
        raise ValueError("Neo4j credentials not found")
    
    return GraphDatabase.driver(uri, auth=(user, password))


def migrate_members():
    """Read CSV and import to Neo4j."""
    
    if not os.path.exists(CSV_FILE):
        print(f"ERROR: File not found: {CSV_FILE}")
        return False
    
    print(f"Reading members CSV file: {CSV_FILE}")
    
    try:
        df = pd.read_csv(CSV_FILE, encoding='utf-8')
        print(f"Loaded {len(df)} rows from CSV")
        print(f"Columns: {list(df.columns)}")
    except Exception as e:
        print(f"ERROR: Could not read CSV: {e}")
        return False
    
    print("Processing rows...")
    rows = _build_import_rows(df, "Member")
    
    if not rows:
        print("ERROR: No valid rows found. Check email column exists.")
        return False
    
    print(f"Prepared {len(rows)} rows for import (skipped {len(df) - len(rows)})")
    print(f"\nFirst row sample: {rows[0] if rows else 'None'}")
    
    # Auto-confirm
    print(f"\nAuto-importing {len(rows)} members to Neo4j...")
    
    try:
        driver = get_neo4j_driver()
    except Exception as e:
        print(f"ERROR: Could not connect to Neo4j: {e}")
        return False
    
    imported_count = 0
    batch_size = 100
    
    try:
        with driver.session() as session:
            for i in range(0, len(rows), batch_size):
                batch = rows[i:i+batch_size]
                
                result = session.run(
                    """
                    UNWIND $rows AS row
                    WITH row
                    WHERE row.email IS NOT NULL AND trim(row.email) <> ""
                    MERGE (p:Person {email: row.email})
                    ON CREATE SET p.personId = randomUUID(), p.createdAt = datetime()
                    SET p.firstName    = row.firstName,
                        p.lastName     = row.lastName,
                        p.gender       = row.gender,
                        p.age          = row.age,
                        p.phone        = row.phone,
                        p.profession = row.profession,
                        p.socialMedia = row.socialMedia,
                        p.wasPartyMember = row.wasPartyMember,
                        p.partyDetails = row.partyDetails,
                        p.about = row.about,
                        p.howToHelp = row.howToHelp,
                        p.additionalComments = row.additionalComments,
                        p.agreesWithManifesto = row.agreesWithManifesto,
                        p.interestedInMembership = row.interestedInMembership,
                        p.personalId = row.personalId,
                        p.whatsappChat = row.whatsappChat,
                        p.dateOfBirth = row.dateOfBirth,
                        p.joinDate = row.joinDate,
                        p.timeAvailability = row.timeAvailability
                    WITH p, row
                    FOREACH (topic IN coalesce(row.topicsOfInterest, []) |
                        MERGE (t:Topic {name: topic})
                        MERGE (p)-[:INTERESTED_IN]->(t)
                    )
                    FOREACH (area IN coalesce(row.involvementAreas, []) |
                        MERGE (ia:InvolvementArea {name: area})
                        MERGE (p)-[:WANTS_TO_HELP_WITH]->(ia)
                    )
                    MERGE (st:SupporterType {name: coalesce(row.supporterType, 'Member')})
                    MERGE (p)-[:CLASSIFIED_AS]->(st)
                    WITH p, row
                    FOREACH (_ IN CASE WHEN row.address IS NULL OR row.address = '' THEN [] ELSE [1] END |
                        MERGE (a:Address {fullAddress: row.address})
                        MERGE (p)-[:LIVES_AT]->(a)
                    )
                    RETURN count(*) as count
                    """,
                    rows=batch
                )
                
                imported_count += len(batch)
                print(f"  Imported batch {i//batch_size + 1}/{(len(rows)-1)//batch_size + 1}: {len(batch)} rows")
    
    except Exception as e:
        print(f"ERROR during import: {e}")
        return False
    finally:
        driver.close()
    
    print(f"\nSUCCESS: Imported {imported_count} members into Neo4j!")
    return True


if __name__ == "__main__":
    success = migrate_members()
    sys.exit(0 if success else 1)
