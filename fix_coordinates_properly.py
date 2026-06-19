#!/usr/bin/env python3
"""Properly fix ALL coordinates by detecting cities from addresses."""

import os
from neo4j import GraphDatabase

URI = "neo4j+s://1a530eac.databases.neo4j.io"
USER = "1a530eac"
PASSWORD = os.getenv("DELIBERATION_NEO4J_PASSWORD", "")

# City coordinates - both Georgian and English names
CITY_PATTERNS = [
    # (pattern, lat, lon, city_name)
    ("თბილისი", 41.7151, 44.8271, "Tbilisi"),
    ("tbilisi", 41.7151, 44.8271, "Tbilisi"),
    ("ბათუმი", 41.6168, 41.6367, "Batumi"),
    ("batumi", 41.6168, 41.6367, "Batumi"),
    ("ქუთაისი", 42.2663, 42.6940, "Kutaisi"),
    ("kutaisi", 42.2663, 42.6940, "Kutaisi"),
    ("რუსთავი", 41.5723, 44.9516, "Rustavi"),
    ("rustavi", 41.5723, 44.9516, "Rustavi"),
    ("გორი", 41.9833, 44.1083, "Gori"),
    ("gori", 41.9833, 44.1083, "Gori"),
    ("ზუგდიდი", 42.5088, 41.8709, "Zugdidi"),
    ("zugdidi", 42.5088, 41.8709, "Zugdidi"),
    ("თელავი", 41.9198, 45.4732, "Telavi"),
    ("telavi", 41.9198, 45.4732, "Telavi"),
    ("ახმეტა", 42.0411, 45.2061, "Akhmeta"),
    ("akhmeta", 42.0411, 45.2061, "Akhmeta"),
    ("ოზურგეთი", 41.9234, 41.9939, "Ozurgeti"),
    ("ozurgeti", 41.9234, 41.9939, "Ozurgeti"),
    ("ხაშური", 41.9943, 43.5992, "Khashuri"),
    ("khashuri", 41.9943, 43.5992, "Khashuri"),
    ("ჭიათურა", 42.2900, 43.2844, "Chiatura"),
    ("chiatura", 42.2900, 43.2844, "Chiatura"),
    ("მცხეთა", 41.8453, 44.7188, "Mtskheta"),
    ("mtskheta", 41.8453, 44.7188, "Mtskheta"),
    ("მარტვილი", 42.4145, 42.3788, "Martvili"),
    ("martvili", 42.4145, 42.3788, "Martvili"),
    ("სამტრედია", 42.1537, 42.3411, "Samtredia"),
    ("samtredia", 42.1537, 42.3411, "Samtredia"),
    ("საგარეჯო", 41.7339, 45.3286, "Sagarejo"),
    ("sagarejo", 41.7339, 45.3286, "Sagarejo"),
    ("სიღნაღი", 41.6133, 45.9218, "Sighnaghi"),
    ("sighnaghi", 41.6133, 45.9218, "Sighnaghi"),
    ("ქობულეთი", 41.8200, 41.7754, "Kobuleti"),
    ("kobuleti", 41.8200, 41.7754, "Kobuleti"),
    ("ფოთი", 42.1461, 41.6710, "Poti"),
    ("poti", 42.1461, 41.6710, "Poti"),
    ("მესტია", 43.0442, 42.7206, "Mestia"),
    ("mestia", 43.0442, 42.7206, "Mestia"),
    ("ვაკე", 41.7020, 44.7500, "Vake"),
    ("vake", 41.7020, 44.7500, "Vake"),
    ("საბურთალო", 41.7280, 44.7700, "Saburtalo"),
    ("saburtalo", 41.7280, 44.7700, "Saburtalo"),
    ("დიღომი", 41.7800, 44.7800, "Digomi"),
    ("digomi", 41.7800, 44.7800, "Digomi"),
    ("დიდი დიღომი", 41.7850, 44.7750, "Didi Digomi"),
    ("დიდუბე", 41.7250, 44.8050, "Didube"),
    ("didube", 41.7250, 44.8050, "Didube"),
    ("ვაზისუბანი", 41.7200, 44.8150, "Vazisubani"),
    ("vazisubani", 41.7200, 44.8150, "Vazisubani"),
    ("ვარკეთილი", 41.7350, 44.8250, "Varketili"),
    ("varketili", 41.7350, 44.8250, "Varketili"),
    ("მუხიანი", 41.7650, 44.8400, "Mukhiani"),
    ("mukhiani", 41.7650, 44.8400, "Mukhiani"),
    ("გლდანი", 41.7700, 44.8200, "Gldani"),
    ("gldani", 41.7700, 44.8200, "Gldani"),
    ("ისანი", 41.6870, 44.8550, "Isani"),
    ("isani", 41.6870, 44.8550, "Isani"),
    ("სამგორი", 41.6800, 44.8400, "Samgori"),
    ("samgori", 41.6800, 44.8400, "Samgori"),
    ("კრწანისი", 41.6650, 44.8800, "Krtsanisi"),
    ("krtsanisi", 41.6650, 44.8800, "Krtsanisi"),
    ("ჩუღურეთი", 41.7080, 44.7950, "Chugureti"),
    ("chugureti", 41.7080, 44.7950, "Chugureti"),
    ("ზესტაფონი", 42.1056, 43.0370, "Zestafoni"),
    ("zestafoni", 42.1056, 43.0370, "Zestafoni"),
    ("გურჯაანი", 41.7425, 45.8026, "Gurjaani"),
    ("gurjaani", 41.7425, 45.8026, "Gurjaani"),
    ("ყაზბეგი", 42.6628, 44.6417, "Kazbegi"),
    ("kazbegi", 42.6628, 44.6417, "Kazbegi"),
    ("ლაგოდეხი", 41.8219, 46.2757, "Lagodekhi"),
    ("lagodekhi", 41.8219, 46.2757, "Lagodekhi"),
]

def main():
    if not PASSWORD:
        print("❌ Set DELIBERATION_NEO4J_PASSWORD first!")
        return
    
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    
    with driver.session(database="1a530eac") as session:
        # First, check current state
        print("=" * 60)
        print("BEFORE FIX")
        print("=" * 60)
        
        result = session.run("""
            MATCH (p:Person)-[:LIVES_AT]->(a:Address)
            RETURN 
                count(*) as total,
                count(CASE WHEN a.lat IS NULL THEN 1 END) as missing_lat,
                count(CASE WHEN a.lon IS NULL THEN 1 END) as missing_lon
        """)
        record = result.single()
        print(f"Total addresses: {record['total']}")
        print(f"Missing lat: {record['missing_lat']}")
        print(f"Missing lon: {record['missing_lon']}")
        
        # Get all addresses that need coordinates
        print("\n" + "=" * 60)
        print("ASSIGNING COORDINATES")
        print("=" * 60)
        
        result = session.run("""
            MATCH (p:Person)-[:LIVES_AT]->(a:Address)
            WHERE a.lat IS NULL OR a.lon IS NULL
            RETURN id(a) as addr_id, a.fullAddress as address
        """)
        
        addresses = [(r["addr_id"], r["address"]) for r in result]
        print(f"Found {len(addresses)} addresses needing coordinates\n")
        
        # Track stats
        city_counts = {}
        updated = 0
        
        for addr_id, address in addresses:
            address_lower = address.lower() if address else ""
            
            # Find matching city
            lat, lon, city_name = 41.7151, 44.8271, "Tbilisi"  # Default
            
            for pattern, city_lat, city_lon, city in CITY_PATTERNS:
                if pattern in address_lower:
                    lat, lon, city_name = city_lat, city_lon, city
                    break
            
            # Update this address
            session.run("""
                MATCH (a:Address)
                WHERE id(a) = $addr_id
                SET a.lat = $lat, a.lon = $lon
            """, addr_id=addr_id, lat=lat, lon=lon)
            
            city_counts[city_name] = city_counts.get(city_name, 0) + 1
            updated += 1
            
            if updated % 100 == 0:
                print(f"  ... {updated} addresses updated")
        
        print(f"\n✓ Updated {updated} addresses")
        
        # Show distribution
        print("\n" + "=" * 60)
        print("CITY DISTRIBUTION")
        print("=" * 60)
        
        for city, count in sorted(city_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"  {city}: {count}")
        
        # Verify fix
        print("\n" + "=" * 60)
        print("VERIFICATION")
        print("=" * 60)
        
        result = session.run("""
            MATCH (p:Person)-[:LIVES_AT]->(a:Address)
            RETURN 
                count(*) as total,
                count(CASE WHEN a.lat IS NULL THEN 1 END) as missing_lat,
                count(DISTINCT [a.lat, a.lon]) as unique_locations
        """)
        record = result.single()
        print(f"Total: {record['total']}")
        print(f"Still missing lat: {record['missing_lat']}")
        print(f"Unique locations: {record['unique_locations']}")
        
        if record['missing_lat'] == 0 and record['unique_locations'] > 1:
            print("\n✅ SUCCESS! Coordinates properly assigned!")
        elif record['missing_lat'] > 0:
            print(f"\n⚠️  {record['missing_lat']} addresses still missing coordinates")
        else:
            print("\n⚠️  All addresses still at same location")
    
    driver.close()

if __name__ == "__main__":
    main()
