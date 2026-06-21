#!/usr/bin/env python3
"""Clear Person.lat/lon so backend uses Address coordinates."""

import os
from neo4j import GraphDatabase

URI = "neo4j+s://1a530eac.databases.neo4j.io"
USER = "1a530eac"
PASSWORD = os.getenv("DELIBERATION_NEO4J_PASSWORD", "")

def main():
    if not PASSWORD:
        print("❌ Set DELIBERATION_NEO4J_PASSWORD")
        return
    
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    
    with driver.session(database="1a530eac") as session:
        print("=" * 60)
        print("CHECKING PERSON VS ADDRESS COORDINATES")
        print("=" * 60)
        
        # Check if Person nodes have coordinates set
        result = session.run("""
            MATCH (p:Person)-[:LIVES_AT]->(a:Address)
            RETURN 
                count(CASE WHEN p.lat IS NOT NULL THEN 1 END) as person_has_lat,
                count(CASE WHEN a.lat IS NOT NULL THEN 1 END) as address_has_lat,
                count(*) as total
        """)
        r = result.single()
        print(f"\nTotal: {r['total']}")
        print(f"Person.lat set: {r['person_has_lat']}")
        print(f"Address.lat set: {r['address_has_lat']}")
        
        # Sample showing the difference
        if r['person_has_lat'] > 0:
            print("\n⚠️  Person nodes have coordinates - these override Address coordinates!")
            print("\nSample showing Person vs Address coordinates:")
            
            result = session.run("""
                MATCH (p:Person)-[:LIVES_AT]->(a:Address)
                WHERE p.lat IS NOT NULL
                RETURN p.lat, p.lon, a.lat, a.lon, a.fullAddress
                LIMIT 5
            """)
            
            for rec in result:
                print(f"\n  Person: ({rec['p.lat']}, {rec['p.lon']})")
                print(f"  Address: ({rec['a.lat']}, {rec['a.lon']})")
                print(f"  Location: {rec['a.fullAddress'][:50]}...")
        
        # Clear Person coordinates so backend uses Address
        print("\n" + "=" * 60)
        print("CLEARING PERSON COORDINATES")
        print("=" * 60)
        
        result = session.run("""
            MATCH (p:Person)
            WHERE p.lat IS NOT NULL OR p.lon IS NOT NULL
            REMOVE p.lat, p.lon
            RETURN count(*) as cleared
        """)
        cleared = result.single()['cleared']
        print(f"✓ Cleared coordinates from {cleared} Person nodes")
        
        # Verify backend will now use Address coordinates
        print("\n" + "=" * 60)
        print("VERIFICATION")
        print("=" * 60)
        
        result = session.run("""
            MATCH (p:Person)-[:LIVES_AT]->(addr:Address)
            WITH p, addr,
                 coalesce(p.lat, addr.lat, addr.latitude) AS lat,
                 coalesce(p.lon, addr.lon, addr.longitude) AS lon
            WHERE lat IS NOT NULL
            RETURN count(DISTINCT [lat, lon]) as unique_locs,
                   count(*) as total
        """)
        r = result.single()
        print(f"Unique locations: {r['unique_locs']}")
        print(f"Total with coords: {r['total']}")
        
        if r['unique_locs'] > 1:
            print(f"\n✅ SUCCESS! Backend will now see {r['unique_locs']} different locations!")
        else:
            print(f"\n❌ Still only 1 unique location")
    
    driver.close()

if __name__ == "__main__":
    main()
