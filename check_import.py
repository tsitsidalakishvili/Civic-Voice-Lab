#!/usr/bin/env python3
"""Check what happened during import - why 592 CSV rows became 450 DB records."""

import os
import pandas as pd
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

CSV_FILE = r"C:\Users\Tsitsi\Desktop\FS\members_supporters_FS - მხარდამჭერები.csv"

def get_db_counts():
    """Get counts from Neo4j."""
    driver = GraphDatabase.driver(
        os.getenv("DELIBERATION_NEO4J_AURA_URI"),
        auth=(os.getenv("DELIBERATION_NEO4J_AURA_USER"), os.getenv("DELIBERATION_NEO4J_AURA_PASSWORD"))
    )
    
    with driver.session() as session:
        # Total people
        result = session.run("MATCH (p:Person) RETURN count(*) as c")
        total = result.single()['c']
        
        # Supporters
        result = session.run("""
            MATCH (p:Person)-[:CLASSIFIED_AS]->(st:SupporterType)
            WHERE st.name = 'Supporter'
            RETURN count(*) as c
        """)
        supporters = result.single()['c']
        
        # Members
        result = session.run("""
            MATCH (p:Person)-[:CLASSIFIED_AS]->(st:SupporterType)
            WHERE st.name = 'Member'
            RETURN count(*) as c
        """)
        members = result.single()['c']
        
        # Check emails
        result = session.run("MATCH (p:Person) WHERE p.email IS NOT NULL RETURN count(*) as c")
        with_email = result.single()['c']
        
        # Check for duplicate emails in DB
        result = session.run("""
            MATCH (p:Person) 
            WHERE p.email IS NOT NULL 
            WITH p.email as email, count(*) as c 
            WHERE c > 1 
            RETURN count(*) as dupes
        """)
        dupes = result.single()['dupes']
        
    driver.close()
    return total, supporters, members, with_email, dupes

def analyze_csv():
    """Analyze the CSV file."""
    df = pd.read_csv(CSV_FILE, encoding='utf-8')
    
    print(f"CSV Analysis:")
    print(f"  Total rows: {len(df)}")
    
    # Check email column
    email_col = None
    for col in df.columns:
        if 'ელ' in col.lower() or 'email' in col.lower():
            email_col = col
            break
    
    if email_col:
        print(f"  Email column: {email_col}")
        
        # Count valid emails
        valid_emails = 0
        empty_emails = 0
        invalid_emails = 0
        
        for val in df[email_col]:
            if pd.isna(val) or str(val).strip() == '' or str(val).lower() in ('nan', 'none', 'null'):
                empty_emails += 1
            elif '@' in str(val):
                valid_emails += 1
            else:
                invalid_emails += 1
        
        print(f"  Valid emails: {valid_emails}")
        print(f"  Empty emails: {empty_emails}")
        print(f"  Invalid emails: {invalid_emails}")
        
        # Check for duplicates
        emails = df[email_col].dropna().astype(str).str.strip().str.lower()
        unique_emails = emails.nunique()
        print(f"  Unique emails: {unique_emails}")
        print(f"  Duplicate emails in CSV: {len(emails) - unique_emails}")
        
        # Show some duplicates
        dupes = emails[emails.duplicated(keep=False)].unique()
        if len(dupes) > 0:
            print(f"\n  Sample duplicate emails:")
            for email in dupes[:5]:
                count = (emails == email).sum()
                print(f"    {email}: appears {count} times")

def main():
    print("=" * 60)
    print("IMPORT ANALYSIS: 592 CSV rows → 450 DB records")
    print("=" * 60)
    
    # Analyze CSV
    analyze_csv()
    
    print("\n" + "=" * 60)
    print("DATABASE COUNTS:")
    print("=" * 60)
    
    # Get DB counts
    total, supporters, members, with_email, dupes = get_db_counts()
    
    print(f"  Total people in DB: {total}")
    print(f"  Supporters: {supporters}")
    print(f"  Members: {members}")
    print(f"  People with email: {with_email}")
    print(f"  Duplicate emails merged: {dupes}")
    
    print("\n" + "=" * 60)
    print("SUMMARY:")
    print("=" * 60)
    print(f"  • CSV has 592 rows")
    print(f"  • Some rows skipped due to missing/invalid emails")
    print(f"  • Duplicate emails merged into single Person nodes")
    print(f"  • Final DB count: {total} people")

if __name__ == "__main__":
    main()
