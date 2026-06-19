#!/usr/bin/env python3
"""Comprehensive geocoding for ALL Georgian cities."""

import os
from neo4j import GraphDatabase

# City coordinates (lat, lon)
CITIES = {
    # Major cities
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
    # Tbilisi districts (use Tbilisi center with slight offsets)
    "Avlabari": (41.6950, 44.8100),
    "Vake": (41.7020, 44.7500),
    "Saburtalo": (41.7280, 44.7700),
    "Digomi": (41.7800, 44.7800),
    "Didi Digomi": (41.7850, 44.7750),
    "Didube": (41.7250, 44.8050),
    "Vazisubani": (41.7200, 44.8150),
    "Varketili": (41.7350, 44.8250),
    "Vera": (41.7100, 44.7600),
    "Mtatsminda": (41.7000, 44.7900),
    "Isani": (41.6870, 44.8550),
    "Samgori": (41.6800, 44.8400),
    "Nadzaladevi": (41.7450, 44.7850),
    "Chugureti": (41.7080, 44.7950),
    "Krtsanisi": (41.6650, 44.8800),
    "Sololaki": (41.6920, 44.8050),
    "Abanotubani": (41.6880, 44.8100),
    "Gldani": (41.7700, 44.8200),
    "Mukhiani": (41.7650, 44.8400),
    # Other towns
    "Aspindza": (41.5739, 43.2553),
    "Gurjaani": (41.7425, 45.8026),
    "Dmanisi": (41.4503, 44.2334),
    "Zestafoni": (42.1056, 43.0370),
    "Zugdidi": (42.5088, 41.8709),
    "Tsalka": (41.5947, 44.0894),
    "Tsibanobalka": (41.8650, 44.7450),
    "Tskneti": (41.7300, 44.7350),
    "Tskaltubo": (42.3417, 42.5960),
    "Tbilisi Sea": (41.7580, 44.8180),
    "Abkhazia": (43.0015, 41.0234),
    "Ambrolauri": (42.5211, 43.1463),
    "Adigeni": (41.6731, 42.7380),
    "Akhalkalaki": (41.4052, 43.4895),
    "Akhaltsikhe": (41.6396, 42.9829),
    "Akhmeta": (42.0411, 45.2061),
    "Dedoplistsqaro": (41.4611, 46.1115),
    "Kazbegi": (42.6628, 44.6417),
    "Kvareli": (41.9487, 45.8017),
    "Lagodekhi": (41.8219, 46.2757),
    "Marneuli": (41.4689, 44.8086),
    "Racha": (42.6395, 43.3832),
    "Senaki": (42.2703, 42.0650),
    "Sukhumi": (43.0015, 41.0234),
    "Tianeti": (42.1075, 44.9691),
    "Tkibuli": (42.3458, 42.9967),
    "Khon": (42.3223, 42.4133),
    "Chokhatauri": (42.1851, 42.4001),
    "Jvari": (42.7186, 42.0486),
    "Pankisi": (42.1776, 45.1998),
    "Poti": (42.1461, 41.6710),
    "Satskheni": (41.6150, 44.0450),
    "Surami": (42.0191, 43.5549),
    "Ujarma": (41.9469, 45.2263),
    "Bolnisi": (41.4594, 44.5381),
    "Borjomi": (41.8389, 43.3794),
    "Gardabani": (41.4586, 45.0786),
    "Kaspi": (41.9250, 44.4216),
    "Kareli": (42.2247, 43.9167),
    "Khoni": (42.3154, 42.4202),
    "Lanchkhuti": (42.0889, 42.0358),
    "Ninotsminda": (41.2646, 43.5911),
    "Oni": (42.5803, 43.4410),
    "Qvareli": (41.9487, 45.8017),
    "Sachkhere": (42.3452, 43.4164),
    "Samtredia": (42.1537, 42.3411),
    "Shuakhevi": (41.6300, 42.1900),
    "Tetritsqaro": (41.5420, 44.4637),
    "Tsageri": (42.6505, 42.7710),
    "Vani": (42.0842, 42.5087),
    "Yerevan": (40.1792, 44.4991),  # Armenia
    "Lausanne": (46.5197, 6.6323),  # Switzerland
}

# Georgian name mappings
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
    "ავლაბარი": "Avlabari",
    "ვაკე": "Vake",
    "საბურთალო": "Saburtalo",
    "დიღომი": "Digomi",
    "დიდი დიღომი": "Didi Digomi",
    "დიდუბე": "Didube",
    "ვაზისუბანი": "Vazisubani",
    "ვარკეთილი": "Varketili",
    "ვერა": "Vera",
    "მთაწმინდა": "Mtatsminda",
    "ისანი": "Isani",
    "სამგორი": "Samgori",
    "ნაძალადევი": "Nadzaladevi",
    "ჩუღურეთი": "Chugureti",
    "კრწანისი": "Krtsanisi",
    "სოლოლაკი": "Sololaki",
    "აბანოთუბანი": "Abanotubani",
    "გლდანი": "Gldani",
    "მუხიანი": "Mukhiani",
    "ასპინძა": "Aspindza",
    "გურჯაანი": "Gurjaani",
    "დმანისი": "Dmanisi",
    "ზესტაფონი": "Zestafoni",
    "წალკა": "Tsalka",
    "წყნეთი": "Tskneti",
    "ჯიხაიში": "Zestafoni",
    "წყალტუბო": "Tskaltubo",
    "აფხაზეთი": "Abkhazia",
    "ამბროლაური": "Ambrolauri",
    "ადიგენი": "Adigeni",
    "ახალქალაქი": "Akhalkalaki",
    "ახალციხე": "Akhaltsikhe",
    "დედოფლისწყარო": "Dedoplistsqaro",
    "ყაზბეგი": "Kazbegi",
    "ყვარლ": "Kvareli",
    "ლაგოდეხი": "Lagodekhi",
    "მარნეული": "Marneuli",
    "რაჭა": "Racha",
    "სენაკი": "Senaki",
    "სოხუმი": "Sukhumi",
    "თიანეთი": "Tianeti",
    "ტყიბული": "Tkibuli",
    "ხონი": "Khon",
    "ჩოხატაური": "Chokhatauri",
    "ჯვარი": "Jvari",
    "პანკისი": "Pankisi",
    "ფოთი": "Poti",
    "საწახნი": "Satskheni",
    "სურამი": "Surami",
    "უჯარმა": "Ujarma",
    "ბოლნისი": "Bolnisi",
    "ბორჯომი": "Borjomi",
    "გარდაბანი": "Gardabani",
    "კასპი": "Kaspi",
    "ქარელი": "Kareli",
    "ნინოწმინდა": "Ninotsminda",
    "ონი": "Oni",
    "საჩხერე": "Sachkhere",
    "შუახევი": "Shuakhevi",
    "თეთრიწყარო": "Tetritsqaro",
    "წაღვერი": "Tsageri",
    "ვანი": "Vani",
}


def get_db_driver():
    uri = os.getenv("DELIBERATION_NEO4J_AURA_URI")
    user = os.getenv("DELIBERATION_NEO4J_AURA_USER")
    password = os.getenv("DELIBERATION_NEO4J_AURA_PASSWORD")
    return GraphDatabase.driver(uri, auth=(user, password))


def assign_city_coordinates():
    driver = get_db_driver()
    
    with driver.session() as session:
        # Get all addresses without coordinates
        result = session.run("""
            MATCH (p:Person)-[:LIVES_AT]->(a:Address)
            WHERE (a.lat IS NULL OR a.lon IS NULL 
                   OR a.lat = '' OR a.lon = '' 
                   OR a.lat = 'nan' OR a.lon = 'nan')
              AND a.fullAddress IS NOT NULL
            RETURN a.fullAddress as address, id(a) as address_id
        """)
        
        addresses = [(r["address"], r["address_id"]) for r in result]
        print(f"Found {len(addresses)} addresses needing coordinates")
        
        if not addresses:
            print("All addresses already have coordinates!")
            driver.close()
            return
        
        assigned_count = 0
        
        for address, addr_id in addresses:
            city_found = None
            address_lower = address.lower()
            
            # Check for Georgian names first (exact match priority)
            for geo_name, eng_name in GEORGIAN_NAMES.items():
                if geo_name in address:
                    city_found = eng_name
                    break
            
            # If no Georgian match, check English/other names
            if not city_found:
                for city_name in CITIES.keys():
                    if city_name.lower() in address_lower:
                        city_found = city_name
                        break
            
            # Assign coordinates if city found
            if city_found and city_found in CITIES:
                lat, lon = CITIES[city_found]
                session.run("""
                    MATCH (a:Address)
                    WHERE id(a) = $addr_id
                    SET a.lat = $lat, a.lon = $lon
                """, addr_id=addr_id, lat=lat, lon=lon)
                assigned_count += 1
                print(f"✓ {city_found}: {address[:50]}...")
            else:
                # Assign default Tbilisi coordinates
                lat, lon = CITIES["Tbilisi"]
                session.run("""
                    MATCH (a:Address)
                    WHERE id(a) = $addr_id
                    SET a.lat = $lat, a.lon = $lon
                """, addr_id=addr_id, lat=lat, lon=lon)
                print(f"? Default (Tbilisi): {address[:50]}...")
        
        print(f"\n✓ Assigned coordinates to {assigned_count} addresses")
        
        # Also update Person nodes directly
        result = session.run("""
            MATCH (p:Person)
            WHERE p.lat IS NULL 
              AND p.address IS NOT NULL 
              AND p.address <> ''
            SET p.lat = $lat, p.lon = $lon
            RETURN count(*) as c
        """, lat=41.7151, lon=44.8271)
        person_count = result.single()["c"]
        print(f"✓ Updated {person_count} Person nodes")
        
        # Final count
        result = session.run("""
            MATCH (p:Person)
            WHERE p.lat IS NOT NULL 
               OR EXISTS((p)-[:LIVES_AT]->(:Address))
            RETURN count(*) as c
        """)
        total = result.single()["c"]
        print(f"\n✓ Total people with coordinates: {total}")
    
    driver.close()
    print("\nGeocoding complete!")


if __name__ == "__main__":
    assign_city_coordinates()
