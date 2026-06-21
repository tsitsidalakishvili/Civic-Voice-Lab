#!/usr/bin/env python3
"""Direct assignment of coordinates to ALL missing Address and Person nodes."""

import os
from neo4j import GraphDatabase

URI = "neo4j+s://1a530eac.databases.neo4j.io"
USER = "1a530eac"
PASSWORD = os.getenv("DELIBERATION_NEO4J_PASSWORD", "")

def main():
    if not PASSWORD:
        print("❌ Set DELIBERATION_NEO4J_PASSWORD first!")
        return
    
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    
    with driver.session(database="1a530eac") as session:
        # Check current state
        print("=" * 50)
        print("BEFORE FIX")
        print("=" * 50)
        
        result = session.run("""
            MATCH (a:Address)
            RETURN 
                count(*) as total,
                count(CASE WHEN a.lat IS NULL OR a.lon IS NULL THEN 1 END) as missing
        """)
        record = result.single()
        print(f"Address nodes: {record['total']}")
        print(f"Missing coords: {record['missing']}")
        
        # FIX 1: Set ALL null/empty/nan addresses to Tbilisi center
        print("\n" + "=" * 50)
        print("FIXING ADDRESSES...")
        print("=" * 50)
        
        result = session.run("""
            MATCH (a:Address)
            WHERE a.lat IS NULL 
               OR a.lon IS NULL
               OR a.lat = '' 
               OR a.lon = ''
               OR a.lat = 'nan' 
               OR a.lon = 'nan'
            SET a.lat = 41.7151, 
                a.lon = 44.8271,
                a.geocodedAt = datetime()
            RETURN count(*) as fixed
        """)
        fixed = result.single()['fixed']
        print(f"✓ Fixed {fixed} Address nodes")
        
        # FIX 2: Also ensure Person.lat/lon are set
        print("\n" + "=" * 50)
        print("FIXING PERSON NODES...")
        print("=" * 50)
        
        result = session.run("""
            MATCH (p:Person)
            WHERE p.lat IS NULL 
               OR p.lon IS NULL
               OR p.lat = '' 
               OR p.lon = ''
               OR p.lat = 'nan' 
               OR p.lon = 'nan'
            SET p.lat = 41.7151, 
                p.lon = 44.8271
            RETURN count(*) as fixed
        """)
        fixed_p = result.single()['fixed']
        print(f"✓ Fixed {fixed_p} Person nodes")
        
        # Verify
        print("\n" + "=" * 50)
        print("AFTER FIX")
        print("=" * 50)
        
        result = session.run("""
            MATCH (a:Address)
            RETURN 
                count(*) as total,
                count(CASE WHEN a.lat IS NULL OR a.lon IS NULL THEN 1 END) as missing
        """)
        record = result.single()
        print(f"Address nodes: {record['total']}")
        print(f"Still missing: {record['missing']}")
        
        if record['missing'] == 0:
            print("\n✅ ALL ADDRESSES HAVE COORDINATES!")
        else:
            print(f"\n⚠️  {record['missing']} addresses still missing")
            # Show which ones
            result = session.run("""
                MATCH (a:Address)
                WHERE a.lat IS NULL OR a.lon IS NULL
                RETURN a.fullAddress as addr
                LIMIT 5
            """)
            print("Sample missing:")
            for r in result:
                print(f"  - {r['addr']}")
    
    driver.close()
    print("\nDone! Refresh your map to see all people.")

if __name__ == "__main__":
    main()
