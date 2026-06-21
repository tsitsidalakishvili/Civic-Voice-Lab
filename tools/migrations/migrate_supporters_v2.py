#!/usr/bin/env python3
"""
One-time migration script for Georgian supporters data - VERSION 2.
Imports ALL records, including those without emails (uses phone as fallback).
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

CSV_FILE = r"C:\Users\Tsitsi\Desktop\FS\members_supporters_FS - მხარდამჭერები.csv"


def _parse_date_to_age(date_val) -> Optional[int]:
    """Parse Georgian date format and calculate age."""
    if pd.isna(date_val) or date_val is None or date_val == "":
        return None
    
    date_str = str(date_val).strip()
    if not date_str:
        return None
    
    # Georgian date formats: DD/MM/YYYY, DD.MM.YYYY, or ISO YYYY-MM-DD
    for fmt in ("%d/%m/%Y", "%d.%m.%Y", "%Y-%m-%d", "%Y/%m/%d"):
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


def _generate_id_from_row(row_num: int, first_name: str, last_name: str, phone: str) -> str:
    """Generate a unique ID for people without email."""
    # Use phone if available, otherwise generate from names + row number
    if phone and phone.strip():
        clean_phone = re.sub(r'\D', '', phone)
        return f"phone_{clean_phone}"
    else:
        # Generate from names
        clean_first = re.sub(r'[^\w]', '', str(first_name).lower())
        clean_last = re.sub(r'[^\w]', '', str(last_name).lower())
        return f"row{row_num}_{clean_first}_{clean_last}"


def _build_import_rows(df: pd.DataFrame, default_type: str) -> List[dict]:
    """Build import rows from Georgian CSV data."""
    if df.empty:
        return []
    
    # Georgian column mappings
    col_email = _get_column(df, ["email", "primary_email", "e_mail", "e-mail", "email_address", "ელ.ფოსტა"])
    col_last_name = _get_column(df, ["last_name", "lastname", "surname", "family_name", "გვარი"])
    col_first_name = _get_column(df, ["first_name", "firstname", "given_name", "name", "სახელი"])
    col_dob = _get_column(df, ["date_of_birth", "dob", "birthdate", "birth_date", "დაბ. თარიღი"])
    col_gender = _get_column(df, ["gender", "sex", "სქესი", "gender"])
    col_phone = _get_column(df, ["phone", "telephone", "mobile", "cell", "ტელ"])
    col_address = _get_column(df, ["address", "location", "მისამართი"])
    col_profession = _get_column(df, ["profession", "occupation", "workplace", "job", "პროფესია/სამუშაო ადგილი"])
    col_social_media = _get_column(df, ["social_media", "facebook", "instagram", "linkedin", "social", "სოც ქსელები"])
    col_was_party_member = _get_column(df, ["was_party_member", "former_party_member", "party_history", "ყოფილხართ თუ არა რომელიმე პარტიის წევრი?"])
    col_party_details = _get_column(df, ["party_details", "party_name", "party_history_details", "გთხოვთ, მიუთითოთ კონკრეტულად"])
    col_about = _get_column(df, ["about", "bio", "description", "background", "მოგვიყევით თქვენს შესახებ და გვითხარით, რატომ გსურთ შემოგვიერთდეთ."])
    col_time_availability = _get_column(df, ["time_availability", "availability", "hours", "რა დროს დაუთმობთ ჩვენს საქმიანობას ?"])
    col_topics_of_interest = _get_column(df, ["topics_of_interest", "interests", "topics", "გთხოვთ, მონიშნოთ თქვენთვის საინტერესო თემები"])
    col_involvement_areas = _get_column(df, ["involvement_areas", "involvement", "areas", "რა მიმართულებით გირჩევნიათ ჩაერთოთ \"თავისუფლების მოედნის\"  საქმიანობაში?"])
    col_how_to_help = _get_column(df, ["how_to_help", "help", "contribution", "როგორ დაეხმარებით \"თავისუფლების მოედანს\"?"])
    col_additional_comments = _get_column(df, ["additional_comments", "comments", "notes", "სივრცე დამატებითი კომენტარისთვის"])
    col_agrees_with_manifesto = _get_column(df, ["agrees_with_manifesto", "manifesto", "agreement", "გავეცანი თავისუფლების მოედნის მანიფესტს და სრულად ვიზიარებ მასში გაცხადებულ იდეებს."])
    col_interested_in_membership = _get_column(df, ["interested_in_membership", "membership_interest", "wants_membership", "გსურთ თუ არა ჩვენი პარტიის წევრობა მომავალში?"])
    col_personal_id = _get_column(df, ["personal_id", "id_number", "national_id", "pid", "პ/ნ"])
    
    rows = []
    skipped = 0
    imported = 0
    
    for idx, raw in df.iterrows():
        row_num = idx + 1
        
        # Try email first
        email = ""
        if col_email:
            email = str(raw.get(col_email, "")).strip().lower()
            if email in ("nan", "none", "null", ""):
                email = ""
        
        # Get other fields
        first_name = str(raw.get(col_first_name, "")).strip() if col_first_name else ""
        last_name = str(raw.get(col_last_name, "")).strip() if col_last_name else ""
        phone = str(raw.get(col_phone, "")).strip() if col_phone else ""
        
        # Generate identifier
        if email:
            identifier = email
            id_type = "email"
        else:
            identifier = _generate_id_from_row(row_num, first_name, last_name, phone)
            id_type = "generated"
        
        # Skip only if NO identifying info at all
        if not identifier or identifier.startswith("row") and not first_name and not last_name:
            skipped += 1
            continue
        
        # Calculate age from date of birth
        age = _parse_date_to_age(raw.get(col_dob)) if col_dob else None
        
        # Parse boolean fields
        was_party_member = _parse_georgian_boolean(raw.get(col_was_party_member)) if col_was_party_member else False
        agrees_with_manifesto = _parse_georgian_boolean(raw.get(col_agrees_with_manifesto)) if col_agrees_with_manifesto else False
        interested_in_membership = _parse_georgian_boolean(raw.get(col_interested_in_membership)) if col_interested_in_membership else False
        
        row = {
            "identifier": identifier,
            "idType": id_type,
            "email": email,
            "firstName": first_name,
            "lastName": last_name,
            "gender": str(raw.get(col_gender, "")).strip() if col_gender else "",
            "age": age,
            "phone": phone,
            "address": str(raw.get(col_address, "")).strip() if col_address else "",
            "lat": None,
            "lon": None,
            "profession": str(raw.get(col_profession, "")).strip() if col_profession else "",
            "socialMedia": str(raw.get(col_social_media, "")).strip() if col_social_media else "",
            "wasPartyMember": was_party_member,
            "partyDetails": str(raw.get(col_party_details, "")).strip() if col_party_details else "",
            "about": str(raw.get(col_about, "")).strip() if col_about else "",
            "timeAvailability": str(raw.get(col_time_availability, "")).strip() if col_time_availability else "",
            "topicsOfInterest": _split_list(raw.get(col_topics_of_interest)) if col_topics_of_interest else [],
            "involvementAreas": _split_list(raw.get(col_involvement_areas)) if col_involvement_areas else [],
            "howToHelp": str(raw.get(col_how_to_help, "")).strip() if col_how_to_help else "",
            "additionalComments": str(raw.get(col_additional_comments, "")).strip() if col_additional_comments else "",
            "agreesWithManifesto": agrees_with_manifesto,
            "interestedInMembership": interested_in_membership,
            "personalId": str(raw.get(col_personal_id, "")).strip() if col_personal_id else "",
            "dateOfBirth": str(raw.get(col_dob, "")).strip() if col_dob else "",
            "supporterType": default_type,
        }
        rows.append(row)
        imported += 1
    
    print(f"  CSV rows: {len(df)}")
    print(f"  To import: {imported}")
    print(f"  Skipped (no ID): {skipped}")
    
    return rows


def get_neo4j_driver():
    """Create Neo4j driver from environment variables."""
    uri = os.getenv("DELIBERATION_NEO4J_AURA_URI") or os.getenv("DELIBERATION_NEO4J_URI") or os.getenv("NEO4J_URI")
    user = os.getenv("DELIBERATION_NEO4J_AURA_USER") or os.getenv("DELIBERATION_NEO4J_USER") or os.getenv("NEO4J_USER")
    password = os.getenv("DELIBERATION_NEO4J_AURA_PASSWORD") or os.getenv("DELIBERATION_NEO4J_PASSWORD") or os.getenv("NEO4J_PASSWORD")
    
    if not all([uri, user, password]):
        raise ValueError("Neo4j credentials not found")
    
    return GraphDatabase.driver(uri, auth=(user, password))


def migrate_supporters():
    """Read CSV and import to Neo4j."""
    
    if not os.path.exists(CSV_FILE):
        print(f"ERROR: File not found: {CSV_FILE}")
        return False
    
    print(f"Reading CSV file: {CSV_FILE}")
    
    try:
        df = pd.read_csv(CSV_FILE, encoding='utf-8')
        print(f"Loaded {len(df)} rows from CSV")
    except Exception as e:
        print(f"ERROR: Could not read CSV: {e}")
        return False
    
    print("\nProcessing rows...")
    rows = _build_import_rows(df, "Supporter")
    
    if not rows:
        print("ERROR: No valid rows found.")
        return False
    
    print(f"\nPrepared {len(rows)} rows for import")
    
    # Auto-confirm - importing ALL records including those without emails
    print(f"\nAuto-importing ALL {len(rows)} supporters to Neo4j...")
    
    print("\nClearing existing supporter data...")
    
    try:
        driver = get_neo4j_driver()
    except Exception as e:
        print(f"ERROR: Could not connect to Neo4j: {e}")
        return False
    
    # Clear existing data
    with driver.session() as session:
        result = session.run("MATCH (p:Person)-[:CLASSIFIED_AS]->(st:SupporterType {name: 'Supporter'}) RETURN count(*) as c")
        existing = result.single()['c']
        print(f"  Found {existing} existing supporters to replace")
        
        # Delete existing supporters (keep members)
        session.run("""
            MATCH (p:Person)-[r:CLASSIFIED_AS]->(st:SupporterType {name: 'Supporter'})
            OPTIONAL MATCH (p)-[r2:LIVES_AT]->(a:Address)
            DELETE r, r2
            WITH p, a
            WHERE NOT EXISTS((p)-[:CLASSIFIED_AS]->(:SupporterType {name: 'Member'}))
            DETACH DELETE p
        """)
        print("  Existing supporters cleared")
    
    print("\nImporting to Neo4j...")
    
    imported_count = 0
    batch_size = 50
    
    try:
        with driver.session() as session:
            for i in range(0, len(rows), batch_size):
                batch = rows[i:i+batch_size]
                
                result = session.run(
                    """
                    UNWIND $rows AS row
                    WITH row
                    MERGE (p:Person {personId: row.identifier})
                    ON CREATE SET p.createdAt = datetime()
                    SET p.email = CASE WHEN row.idType = 'email' THEN row.identifier ELSE p.email END,
                        p.generatedId = CASE WHEN row.idType = 'generated' THEN row.identifier ELSE p.generatedId END,
                        p.firstName = row.firstName,
                        p.lastName = row.lastName,
                        p.gender = row.gender,
                        p.age = row.age,
                        p.phone = row.phone,
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
                        p.dateOfBirth = row.dateOfBirth,
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
                    MERGE (st:SupporterType {name: coalesce(row.supporterType, 'Supporter')})
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
        import traceback
        traceback.print_exc()
        return False
    finally:
        driver.close()
    
    print(f"\nSUCCESS: Imported {imported_count} supporters into Neo4j!")
    print(f"  - With email: {sum(1 for r in rows if r['idType'] == 'email')}")
    print(f"  - With generated ID: {sum(1 for r in rows if r['idType'] == 'generated')}")
    return True


if __name__ == "__main__":
    success = migrate_supporters()
    sys.exit(0 if success else 1)
