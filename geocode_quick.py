#!/usr/bin/env python3
"""Quick geocoding for Georgian addresses - assign Tbilisi center to most addresses."""

import os
import re
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

# Tbilisi center coordinates
TBILISI_LAT = 41.7151
TBILISI_LON = 44.8271

# Batumi coordinates  
BATUMI_LAT = 41.6168
BATUMI_LON = 41.6367

# Kutaisi coordinates
KUTAISI_LAT = 42.2663
KUTAISI_LON = 42.6940

def get_db_driver():
    uri = os.getenv("DELIBERATION_NEO4J_AURA_URI")
    user = os.getenv("DELIBERATION_NEO4J_AURA_USER")
    password = os.getenv("DELIBERATION_NEO4J_AURA_PASSWORD")
    return GraphDatabase.driver(uri, auth=(user, password))

def assign_default_coordinates():
    """Assign approximate coordinates based on address text."""
    driver = get_db_driver()
    
    with driver.session() as session:
        # Count people with addresses but no coordinates
        result = session.run("""
            MATCH (p:Person)-[:LIVES_AT]->(a:Address)
            WHERE a.lat IS NULL AND a.fullAddress IS NOT NULL
            RETURN count(*) as c
        """)
        to_geocode = result.single()['c']
        print(f"People needing coordinates: {to_geocode}")
        
        if to_geocode == 0:
            print("No addresses to geocode!")
            driver.close()
            return
        
        # Assign Tbilisi coordinates to Tbilisi addresses
        result = session.run("""
            MATCH (p:Person)-[:LIVES_AT]->(a:Address)
            WHERE a.lat IS NULL 
              AND a.fullAddress IS NOT NULL
              AND (toLower(a.fullAddress) CONTAINS 'tbilisi' 
                   OR toLower(a.fullAddress) CONTAINS 'თბილისი'
                   OR toLower(a.fullAddress) CONTAINS 'digomi'
                   OR toLower(a.fullAddress) CONTAINS 'dighomi'
                   OR toLower(a.fullAddress) CONTAINS 'didube'
                   OR toLower(a.fullAddress) CONTAINS 'digomi'
                   OR toLower(a.fullAddress) CONTAINS 'saburtalo'
                   OR toLower(a.fullAddress) CONTAINS 'vera'
                   OR toLower(a.fullAddress) CONTAINS 'vake'
                   OR toLower(a.fullAddress) CONTAINS 'mtatsminda'
                   OR toLower(a.fullAddress) CONTAINS 'chughureti'
                   OR toLower(a.fullAddress) CONTAINS 'isani'
                   OR toLower(a.fullAddress) CONTAINS 'samgori'
                   OR toLower(a.fullAddress) CONTAINS 'nadzaladevi')
            SET a.lat = $lat, a.lon = $lon
            RETURN count(*) as c
        """, lat=TBILISI_LAT, lon=TBILISI_LON)
        tbilisi_count = result.single()['c']
        print(f"Assigned Tbilisi coordinates: {tbilisi_count}")
        
        # Assign Batumi coordinates
        result = session.run("""
            MATCH (p:Person)-[:LIVES_AT]->(a:Address)
            WHERE a.lat IS NULL 
              AND a.fullAddress IS NOT NULL
              AND (toLower(a.fullAddress) CONTAINS 'batumi' 
                   OR toLower(a.fullAddress) CONTAINS 'ბათუმი')
            SET a.lat = $lat, a.lon = $lon
            RETURN count(*) as c
        """, lat=BATUMI_LAT, lon=BATUMI_LON)
        batumi_count = result.single()['c']
        print(f"Assigned Batumi coordinates: {batumi_count}")
        
        # Assign Kutaisi coordinates
        result = session.run("""
            MATCH (p:Person)-[:LIVES_AT]->(a:Address)
            WHERE a.lat IS NULL 
              AND a.fullAddress IS NOT NULL
              AND (toLower(a.fullAddress) CONTAINS 'kutaisi' 
                   OR toLower(a.fullAddress) CONTAINS 'ქუთაისი')
            SET a.lat = $lat, a.lon = $lon
            RETURN count(*) as c
        """, lat=KUTAISI_LAT, lon=KUTAISI_LON)
        kutaisi_count = result.single()['c']
        print(f"Assigned Kutaisi coordinates: {kutaisi_count}")
        
        # Assign default Tbilisi to remaining addresses
        result = session.run("""
            MATCH (p:Person)-[:LIVES_AT]->(a:Address)
            WHERE a.lat IS NULL 
              AND a.fullAddress IS NOT NULL
              AND a.fullAddress <> ''
            SET a.lat = $lat, a.lon = $lon
            RETURN count(*) as c
        """, lat=TBILISI_LAT, lon=TBILISI_LON)
        remaining_count = result.single()['c']
        print(f"Assigned default Tbilisi to remaining: {remaining_count}")
        
        # Also update Person nodes directly (for those without Address nodes)
        result = session.run("""
            MATCH (p:Person)
            WHERE p.lat IS NULL 
              AND p.address IS NOT NULL 
              AND p.address <> ''
            SET p.lat = $lat, p.lon = $lon
            RETURN count(*) as c
        """, lat=TBILISI_LAT, lon=TBILISI_LON)
        person_count = result.single()['c']
        print(f"Updated Person nodes: {person_count}")
        
        # Total with coordinates now
        result = session.run("""
            MATCH (p:Person)
            WHERE p.lat IS NOT NULL 
               OR EXISTS((p)-[:LIVES_AT]->(:Address {lat: $lat}))
            RETURN count(*) as c
        """, lat=TBILISI_LAT)
        total_with_coords = result.single()['c']
        print(f"\nTotal people with coordinates now: {total_with_coords}")
    
    driver.close()
    print("\nGeocoding complete!")

if __name__ == "__main__":
    assign_default_coordinates()
