#!/usr/bin/env python3
"""Initialize subscription tiers for all existing Person nodes."""

import os
from neo4j import GraphDatabase
from datetime import datetime

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
        print("INITIALIZING SUBSCRIPTION TIERS")
        print("=" * 60)
        
        # Check current state
        result = session.run("""
            MATCH (p:Person)
            RETURN count(*) as total,
                   count(CASE WHEN p.subscriptionTier IS NOT NULL THEN 1 END) as has_tier
        """)
        r = result.single()
        print(f"\nTotal people: {r['total']}")
        print(f"Already have tier: {r['has_tier']}")
        
        # Set default 'free' tier for everyone without one
        now = datetime.utcnow().isoformat()
        
        result = session.run("""
            MATCH (p:Person)
            WHERE p.subscriptionTier IS NULL
            SET p.subscriptionTier = 'free',
                p.subscriptionSince = $now
            RETURN count(*) as updated
        """, now=now)
        
        updated = result.single()['updated']
        print(f"\n✓ Set {updated} people to 'free' tier")
        
        # Verify
        result = session.run("""
            MATCH (p:Person)
            RETURN p.subscriptionTier as tier, count(*) as cnt
            ORDER BY cnt DESC
        """)
        
        print("\nSubscription tier distribution:")
        for r in result:
            tier = r['tier'] or 'null'
            print(f"  {tier}: {r['cnt']}")
        
        print("\n✅ Subscription tiers initialized!")
    
    driver.close()

if __name__ == "__main__":
    main()
