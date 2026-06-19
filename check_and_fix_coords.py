#!/usr/bin/env python3
"""Check actual coordinates in database and fix them."""

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
        # Check current distribution
        print("=" * 60)
        print("CURRENT COORDINATE DISTRIBUTION")
        print("=" * 60)
        
        result = session.run("""
            MATCH (p:Person)-[:LIVES_AT]->(a:Address)
            WHERE a.lat IS NOT NULL AND a.lon IS NOT NULL
            RETURN a.lat as lat, a.lon as lon, count(*) as cnt
            ORDER BY cnt DESC
            LIMIT 20
        """)
        
        print("\nTop 20 locations by count:")
        for record in result:
            lat = record['lat']
            lon = record['lon']
            cnt = record['cnt']
            print(f"  ({lat}, {lon}): {cnt} people")
        
        # Check if all have same coordinates
        result = session.run("""
            MATCH (p:Person)-[:LIVES_AT]->(a:Address)
            WHERE a.lat IS NOT NULL
            WITH count(*) as total, count(DISTINCT [a.lat, a.lon]) as unique_locs
            RETURN total, unique_locs
        """)
        record = result.single()
        print(f"\nTotal with coords: {record['total']}")
        print(f"Unique locations: {record['unique_locs']}")
        
        if record['unique_locs'] == 1:
            print("\n⚠️  ALL PEOPLE HAVE SAME COORDINATES!")
            print("Need to re-geocode with proper city detection...")
            
            # Show sample addresses that should be different cities
            result = session.run("""
                MATCH (p:Person)-[:LIVES_AT]->(a:Address)
                WHERE a.fullAddress CONTAINS 'ბათუმი' 
                   OR a.fullAddress CONTAINS 'Batumi'
                   OR a.fullAddress CONTAINS 'ქუთაისი'
                   OR a.fullAddress CONTAINS 'Kutaisi'
                   OR a.fullAddress CONTAINS 'რუსთავი'
                   OR a.fullAddress CONTAINS 'Rustavi'
                RETURN a.fullAddress as addr, a.lat, a.lon
                LIMIT 10
            """)
            print("\nSample non-Tbilisi addresses:")
            for r in result:
                print(f"  {r['addr'][:50]}... -> ({r['lat']}, {r['lon']})")
        
        # NOW FIX: Reset ALL coordinates and re-assign properly
        print("\n" + "=" * 60)
        print("RE-GEOCODING ALL ADDRESSES")
        print("=" * 60)
        
        # First, reset all to NULL to force re-geocoding
        result = session.run("""
            MATCH (a:Address)
            SET a.lat = NULL, a.lon = NULL
            RETURN count(*) as reset
        """)
        print(f"✓ Reset {result.single()['reset']} addresses")
        
        # City coordinates dictionary
        CITIES = {
            "Tbilisi": (41.7151, 44.8271),
            "Batumi": (41.6168, 41.6367),
            "Kutaisi": (42.2663, 42.6940),
            "Rustavi": (41.5723, 44.9516),
            "Gori": (41.9833, 44.1083),
            "Zugdidi": (42.5088, 41.8709),
            "Telavi": (41.9198, 45.4732),
            "Akhmeta": (42.0411, 45.2061),
            "Ozurgeti": (41.9234, 41.9939),
            "Khashuri": (41.9943, 43.5992),
            "Chiatura": (42.2900, 43.2844),
            "Mtskheta": (41.8453, 44.7188),
            "Martvili": (42.4145, 42.3788),
            "Samtredia": (42.1537, 42.3411),
            "Sagarejo": (41.7339, 45.3286),
            "Sighnaghi": (41.6133, 45.9218),
            "Kobuleti": (41.8200, 41.7754),
            "Poti": (42.1461, 41.6710),
            "Mestia": (43.0442, 42.7206),
            "Vake": (41.7020, 44.7500),
            "Saburtalo": (41.7280, 44.7700),
            "Digomi": (41.7800, 44.7800),
        }
        
        GEORGIAN_NAMES = {
            "თბილისი": "Tbilisi",
            "ბათუმი": "Batumi",
            "ქუთაისი": "Kutaisi",
            "რუსთავი": "Rustavi",
            "გორი": "Gori",
            "ზუგდიდი": "Zugdidi",
            "თელავი": "Telavi",
            "ახმეტა": "Akhmeta",
            "ოზურგეთი": "Ozurgeti",
            "ხაშური": "Khashuri",
            "ჭიათურა": "Chiatura",
            "მცხეთა": "Mtskheta",
            "მარტვილი": "Martvili",
            "სამტრედია": "Samtredia",
            "საგარეჯო": "Sagarejo",
            "სიღნაღი": "Sighnaghi",
            "ქობულეთი": "Kobuleti",
            "ფოთი": "Poti",
            "მესტია": "Mestia",
            "ვაკე": "Vake",
            "საბურთალო": "Saburtalo",
            "დიღომი": "Digomi",
        }
        
        # Get all addresses
        result = session.run("""
            MATCH (p:Person)-[:LIVES_AT]->(a:Address)
            WHERE a.fullAddress IS NOT NULL
            RETURN id(a) as addr_id, a.fullAddress as address
        """)
        
        addresses = [(r["addr_id"], r["address"]) for r in result]
        print(f"\nProcessing {len(addresses)} addresses...")
        
        updated = 0
        for addr_id, address in addresses:
            city_found = None
            
            # Check Georgian names
            for geo_name, eng_name in GEORGIAN_NAMES.items():
                if geo_name in address:
                    city_found = eng_name
                    break
            
            # Check English names
            if not city_found:
                address_lower = address.lower()
                for city_name in CITIES.keys():
                    if city_name.lower() in address_lower:
                        city_found = city_name
                        break
            
            # Default to Tbilisi
            if not city_found:
                city_found = "Tbilisi"
            
            lat, lon = CITIES.get(city_found, CITIES["Tbilisi"])
            
            # Update this specific address
            session.run("""
                MATCH (a:Address)
                WHERE id(a) = $addr_id
                SET a.lat = $lat, a.lon = $lon
            """, addr_id=addr_id, lat=lat, lon=lon)
            
            updated += 1
            if updated % 50 == 0:
                print(f"  ... {updated} done")
        
        print(f"\n✓ Updated {updated} addresses")
        
        # Verify new distribution
        print("\n" + "=" * 60)
        print("NEW COORDINATE DISTRIBUTION")
        print("=" * 60)
        
        result = session.run("""
            MATCH (p:Person)-[:LIVES_AT]->(a:Address)
            WHERE a.lat IS NOT NULL
            RETURN a.lat as lat, a.lon as lon, count(*) as cnt
            ORDER BY cnt DESC
            LIMIT 10
        """)
        
        print("\nTop 10 locations:")
        for record in result:
            lat = record['lat']
            lon = record['lon']
            cnt = record['cnt']
            print(f"  ({lat}, {lon}): {cnt} people")
        
        result = session.run("""
            MATCH (p:Person)-[:LIVES_AT]->(a:Address)
            WHERE a.lat IS NOT NULL
            WITH count(DISTINCT [a.lat, a.lon]) as unique_locs
            RETURN unique_locs
        """)
        unique = result.single()['unique_locs']
        print(f"\nTotal unique locations: {unique}")
        
        if unique > 1:
            print("\n✅ SUCCESS! People are now distributed across multiple cities!")
        else:
            print("\n❌ Still all at one location - check address patterns")
    
    driver.close()

if __name__ == "__main__":
    main()
