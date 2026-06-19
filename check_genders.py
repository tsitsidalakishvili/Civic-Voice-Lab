#!/usr/bin/env python3
"""Check what gender values exist in the database"""
import os
from neo4j import GraphDatabase

URI = "neo4j+s://1a530eac.databases.neo4j.io"
USER = "1a530eac"
PASSWORD = os.getenv("DELIBERATION_NEO4J_PASSWORD", "")

driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))

with driver.session(database="1a530eac") as session:
    # Get all distinct gender values
    result = session.run("""
        MATCH (p:Person)
        WHERE p.gender IS NOT NULL AND p.gender <> ''
        RETURN p.gender as gender, count(*) as count
        ORDER BY count DESC
    """)
    
    print("Raw gender values in database:")
    print("-" * 40)
    for record in result:
        g = record["gender"]
        count = record["count"]
        # Show the raw value with type info
        print(f"'{g}' (type: {type(g).__name__}) = {count}")
    
    # Check how normalization works
    print("\n\nAfter normalization:")
    print("-" * 40)
    result2 = session.run("""
        MATCH (p:Person)
        WITH p,
          CASE 
            WHEN p.gender IS NULL OR p.gender = '' OR p.gender = 'nan' THEN 'U'
            WHEN toLower(toString(p.gender)) CONTAINS 'female' OR toString(p.gender) IN ['1', '1.0', 'Female', 'F'] THEN 'F'
            WHEN toLower(toString(p.gender)) CONTAINS 'male' OR toString(p.gender) IN ['2', '2.0', 'Male', 'M'] THEN 'M'
            WHEN toLower(toString(p.gender)) CONTAINS 'other' OR toString(p.gender) IN ['3', '3.0', 'Other', 'O'] THEN 'O'
            ELSE 'U'
          END AS normalizedGender
        RETURN normalizedGender, count(*) as cnt
        ORDER BY cnt DESC
    """)
    for record in result2:
        print(f"{record['normalizedGender']}: {record['cnt']}")

driver.close()
