#!/usr/bin/env python3
"""Verify what coordinates are actually in the database."""

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
        print("COORDINATE DISTRIBUTION IN DATABASE")
        print("=" * 60)
        
        # Check unique coordinate pairs
        result = session.run("""
            MATCH (p:Person)-[:LIVES_AT]->(a:Address)
            WHERE a.lat IS NOT NULL
            RETURN a.lat, a.lon, count(*) as cnt
            ORDER BY cnt DESC
            LIMIT 20
        """)
        
        print("\nTop 20 coordinate pairs:")
        for r in result:
            print(f"  ({r['a.lat']}, {r['a.lon']}): {r['cnt']} people")
        
        # Count unique locations
        result = session.run("""
            MATCH (p:Person)-[:LIVES_AT]->(a:Address)
            WHERE a.lat IS NOT NULL
            RETURN count(DISTINCT [a.lat, a.lon]) as unique_locs,
                   count(*) as total_with_coords
        """)
        r = result.single()
        print(f"\nUnique locations: {r['unique_locs']}")
        print(f"Total with coords: {r['total_with_coords']}")
        
        # Show sample addresses for each major location
        if r['unique_locs'] <= 5:
            print("\n⚠️  WARNING: Too few unique locations!")
            print("\nSample addresses that should be different cities:")
            
            result = session.run("""
                MATCH (p:Person)-[:LIVES_AT]->(a:Address)
                WHERE a.fullAddress CONTAINS 'ბათუმი' 
                   OR a.fullAddress CONTAINS 'ქუთაისი'
                   OR a.fullAddress CONTAINS 'რუსთავი'
                   OR a.fullAddress CONTAINS 'გორი'
                RETURN a.fullAddress as addr, a.lat, a.lon
                LIMIT 10
            """)
            
            for rec in result:
                print(f"  {rec['addr'][:40]}... -> ({rec['a.lat']}, {rec['a.lon']})")
    
    driver.close()

if __name__ == "__main__":
    main()
