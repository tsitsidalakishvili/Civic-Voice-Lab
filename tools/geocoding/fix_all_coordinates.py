#!/usr/bin/env python3
"""Force-assign coordinates to ALL addresses - no exceptions."""

import os
from neo4j import GraphDatabase

def get_db_driver():
    uri = os.getenv("DELIBERATION_NEO4J_AURA_URI")
    user = os.getenv("DELIBERATION_NEO4J_AURA_USER")
    password = os.getenv("DELIBERATION_NEO4J_AURA_PASSWORD")
    return GraphDatabase.driver(uri, auth=(user, password))


def fix_all_coordinates():
    driver = get_db_driver()
    
    with driver.session() as session:
        # Step 1: Count current state
        print("=" * 60)
        print("BEFORE FIX:")
        print("=" * 60)
        
        # Total people
        result = session.run("MATCH (p:Person) RETURN count(*) as total")
        total_people = result.single()["total"]
        print(f"Total Person nodes: {total_people}")
        
        # People with coordinates
        result = session.run("""
            MATCH (p:Person)
            WHERE p.lat IS NOT NULL AND p.lon IS NOT NULL
               OR EXISTS((p)-[:LIVES_AT]->(:Address {lat: $lat}))
            RETURN count(*) as with_coords
        """, lat=41.7151)
        with_coords = result.single()["with_coords"]
        print(f"With coordinates: {with_coords}")
        print(f"Missing coordinates: {total_people - with_coords}")
        
        # Address nodes status
        result = session.run("""
            MATCH (a:Address)
            RETURN 
                count(*) as total_addresses,
                count(CASE WHEN a.lat IS NOT NULL AND a.lon IS NOT NULL THEN 1 END) as with_coords,
                count(CASE WHEN a.lat IS NULL OR a.lon IS NULL THEN 1 END) as without_coords
        """)
        addr_stats = result.single()
        print(f"\nAddress nodes: {addr_stats['total_addresses']}")
        print(f"  With coords: {addr_stats['with_coords']}")
        print(f"  Without coords: {addr_stats['without_coords']}")
        
        # Step 2: Fix ALL Address nodes - assign Tbilisi center to any missing
        print("\n" + "=" * 60)
        print("FIXING ADDRESSES...")
        print("=" * 60)
        
        result = session.run("""
            MATCH (a:Address)
            WHERE a.lat IS NULL OR a.lon IS NULL 
               OR a.lat = '' OR a.lon = ''
               OR a.lat = 'nan' OR a.lon = 'nan'
            SET a.lat = 41.7151, a.lon = 44.8271
            RETURN count(*) as fixed
        """)
        fixed_addresses = result.single()["fixed"]
        print(f"✓ Fixed {fixed_addresses} Address nodes")
        
        # Step 3: Fix ALL Person nodes - assign coordinates directly to people
        print("\n" + "=" * 60)
        print("FIXING PERSON NODES...")
        print("=" * 60)
        
        result = session.run("""
            MATCH (p:Person)
            WHERE p.lat IS NULL OR p.lon IS NULL
               OR p.lat = '' OR p.lon = ''
               OR p.lat = 'nan' OR p.lon = 'nan'
            SET p.lat = 41.7151, p.lon = 44.8271
            RETURN count(*) as fixed
        """)
        fixed_people = result.single()["fixed"]
        print(f"✓ Fixed {fixed_people} Person nodes")
        
        # Step 4: Verify final state
        print("\n" + "=" * 60)
        print("AFTER FIX:")
        print("=" * 60)
        
        result = session.run("""
            MATCH (p:Person)
            WHERE p.lat IS NOT NULL AND p.lon IS NOT NULL
               OR EXISTS((p)-[:LIVES_AT]->(a:Address))
                  AND a.lat IS NOT NULL AND a.lon IS NOT NULL
            RETURN count(*) as with_coords
        """)
        final_with_coords = result.single()["with_coords"]
        print(f"People with coordinates: {final_with_coords}")
        print(f"Still missing: {total_people - final_with_coords}")
        
        # Check for any remaining NULLs
        result = session.run("""
            MATCH (a:Address)
            WHERE a.lat IS NULL OR a.lon IS NULL
            RETURN count(*) as null_count
        """)
        remaining_nulls = result.single()["null_count"]
        print(f"\nAddress nodes still without coords: {remaining_nulls}")
        
        if remaining_nulls == 0 and (total_people - final_with_coords) == 0:
            print("\n✅ SUCCESS! All people now have coordinates!")
        else:
            print(f"\n⚠️  Warning: Still missing some coordinates")
    
    driver.close()


if __name__ == "__main__":
    fix_all_coordinates()
