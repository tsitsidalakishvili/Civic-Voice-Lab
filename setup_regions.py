#!/usr/bin/env python3
"""
Script to create Region nodes in Neo4j Aura and link People to them based on addresses.
"""

import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

# Neo4j Aura connection
URI = os.getenv("DELIBERATION_NEO4J_URI", "neo4j+s://1a530eac.databases.neo4j.io")
USER = os.getenv("DELIBERATION_NEO4J_USER", "1a530eac")
PASSWORD = os.getenv("DELIBERATION_NEO4J_PASSWORD", "")
DATABASE = os.getenv("DELIBERATION_NEO4J_DATABASE", "1a530eac")

# Region definitions
REGIONS = [
    # Tbilisi districts
    {"name": "Tbilisi", "type": "city", "country": "Georgia"},
    {"name": "Tbilisi - Vake", "type": "district", "parentCity": "Tbilisi", "keywords": ["ვაკე", "Vake"]},
    {"name": "Tbilisi - Saburtalo", "type": "district", "parentCity": "Tbilisi", "keywords": ["საბურთალო", "Saburtalo"]},
    {"name": "Tbilisi - Dighomi", "type": "district", "parentCity": "Tbilisi", "keywords": ["დიღომი", "Dighomi"]},
    {"name": "Tbilisi - Mukhiani", "type": "district", "parentCity": "Tbilisi", "keywords": ["მუხიანი", "Mukhiani"]},
    {"name": "Tbilisi - Varketili", "type": "district", "parentCity": "Tbilisi", "keywords": ["ვარკეთილი", "Varketili"]},
    {"name": "Tbilisi - Gldani", "type": "district", "parentCity": "Tbilisi", "keywords": ["გლდანი", "Gldani"]},
    {"name": "Tbilisi - Samgori", "type": "district", "parentCity": "Tbilisi", "keywords": ["სამგორი", "Samgori"]},
    {"name": "Tbilisi - Nadzaladevi", "type": "district", "parentCity": "Tbilisi", "keywords": ["ნაძალადევი", "Nadzaladevi"]},
    {"name": "Tbilisi - Isani", "type": "district", "parentCity": "Tbilisi", "keywords": ["ისანი", "Isani"]},
    {"name": "Tbilisi - Krtsanisi", "type": "district", "parentCity": "Tbilisi", "keywords": ["კრწანისი", "Krtsanisi"]},
    {"name": "Tbilisi - Mtatsminda", "type": "district", "parentCity": "Tbilisi", "keywords": ["მთაწმინდა", "Mtatsminda"]},
    {"name": "Tbilisi - Sololaki", "type": "district", "parentCity": "Tbilisi", "keywords": ["სოლოლაკი", "Sololaki"]},
    {"name": "Tbilisi - Vera", "type": "district", "parentCity": "Tbilisi", "keywords": ["ვერა", "Vera"]},
    {"name": "Tbilisi - Didube", "type": "district", "parentCity": "Tbilisi", "keywords": ["დიდუბე", "Didube"]},
    {"name": "Tbilisi - Chugureti", "type": "district", "parentCity": "Tbilisi", "keywords": ["ჩუღურეთი", "Chugureti"]},
    {"name": "Tbilisi - Abanotubani", "type": "district", "parentCity": "Tbilisi", "keywords": ["აბანოთუბანი", "Abanotubani"]},
    {"name": "Tbilisi - Vazisubani", "type": "district", "parentCity": "Tbilisi", "keywords": ["ვაზისუბანი", "Vazisubani"]},
    # Other cities
    {"name": "Batumi", "type": "city", "country": "Georgia", "keywords": ["ბათუმი", "Batumi"]},
    {"name": "Kutaisi", "type": "city", "country": "Georgia", "keywords": ["ქუთაისი", "Kutaisi"]},
    {"name": "Rustavi", "type": "city", "country": "Georgia", "keywords": ["რუსთავი", "Rustavi"]},
    {"name": "Gori", "type": "city", "country": "Georgia", "keywords": ["გორი", "Gori"]},
    {"name": "Zugdidi", "type": "city", "country": "Georgia", "keywords": ["ზუგდიდი", "Zugdidi"]},
    {"name": "Telavi", "type": "city", "country": "Georgia", "keywords": ["თელავი", "Telavi"]},
    {"name": "Akhmeta", "type": "city", "country": "Georgia", "keywords": ["ახმეტა", "Akhmeta"]},
    {"name": "Ozurgeti", "type": "city", "country": "Georgia", "keywords": ["ოზურგეთი", "Ozurgeti"]},
    {"name": "Khashuri", "type": "city", "country": "Georgia", "keywords": ["ხაშური", "Khashuri"]},
    {"name": "Chiatura", "type": "city", "country": "Georgia", "keywords": ["ჭიათურა", "Chiatura"]},
    {"name": "Mtskheta", "type": "city", "country": "Georgia", "keywords": ["მცხეთა", "Mtskheta"]},
    {"name": "Martvili", "type": "city", "country": "Georgia", "keywords": ["მარტვილი", "Martvili"]},
    {"name": "Samtredia", "type": "city", "country": "Georgia", "keywords": ["სამტრედია", "Samtredia"]},
    {"name": "Tedzami", "type": "city", "country": "Georgia", "keywords": ["თეძამი", "Tedzami"]},
    {"name": "Sagarejo", "type": "city", "country": "Georgia", "keywords": ["საგარეჯო", "Sagarejo"]},
    {"name": "Sighnaghi", "type": "city", "country": "Georgia", "keywords": ["სიღნაღი", "Sighnaghi"]},
    {"name": "Kobuleti", "type": "city", "country": "Georgia", "keywords": ["ქობულეთი", "Kobuleti"]},
    {"name": "Poti", "type": "city", "country": "Georgia", "keywords": ["ფოთი", "Poti"]},
    {"name": "Sukhumi", "type": "city", "country": "Georgia", "keywords": ["სოხუმი", "Sukhumi"]},
    # Catch-all regions
    {"name": "Other Regions", "type": "other", "country": "Georgia"},
    {"name": "Unknown", "type": "unknown", "country": "Georgia"},
]


def create_regions(driver, database):
    """Create Region nodes"""
    create_query = """
    MERGE (r:Region {name: $name})
    ON CREATE SET r.type = $type, r.country = $country
    ON MATCH SET r.type = $type, r.country = $country
    WITH r
    CALL apoc.do.when(
        $parentCity IS NOT NULL,
        'MATCH (parent:Region {name: $parentCity}) MERGE (r)-[:PART_OF]->(parent) RETURN r',
        'RETURN r',
        {r: r, parentCity: $parentCity}
    ) YIELD value
    RETURN r.name as name
    """
    
    with driver.session(database=database) as session:
        created = 0
        for region in REGIONS:
            result = session.run(create_query, {
                "name": region["name"],
                "type": region.get("type", "city"),
                "country": region.get("country", "Georgia"),
                "parentCity": region.get("parentCity")
            })
            if result.single():
                created += 1
                print(f"✓ Region: {region['name']}")
        return created


def link_people_to_regions(driver, database):
    """Link Person nodes to Region nodes based on address patterns"""
    
    with driver.session(database=database) as session:
        # Clear existing relationships first
        print("\nClearing existing BELONGS_TO_REGION relationships...")
        session.run("MATCH ()-[rel:BELONGS_TO_REGION]->() DELETE rel")
        
        linked = 0
        
        # First, link people based on Address nodes (LIVES_AT relationship)
        print("\nProcessing Address nodes...")
        for region in REGIONS:
            if "keywords" not in region or region["type"] in ["other", "unknown"]:
                continue
            
            keywords = region["keywords"]
            for keyword in keywords:
                # Check both Person.address and Address.fullAddress
                link_query = """
                MATCH (p:Person)
                OPTIONAL MATCH (p)-[:LIVES_AT]->(a:Address)
                WITH p, a, 
                  CASE 
                    WHEN a.fullAddress IS NOT NULL AND a.fullAddress <> '' THEN a.fullAddress
                    ELSE p.address
                  END AS addressToCheck
                MATCH (r:Region {name: $regionName})
                WHERE addressToCheck CONTAINS $keyword
                  AND NOT (p)-[:BELONGS_TO_REGION]->()
                MERGE (p)-[:BELONGS_TO_REGION]->(r)
                RETURN count(p) as count
                """
                result = session.run(link_query, {
                    "regionName": region["name"],
                    "keyword": keyword
                })
                count = result.single()["count"]
                if count > 0:
                    linked += count
                    print(f"✓ {region['name']}: +{count} people (keyword: {keyword})")
        
        # Link general Tbilisi (if no district matched) - check both sources
        tbilisi_query = """
        MATCH (p:Person)
        OPTIONAL MATCH (p)-[:LIVES_AT]->(a:Address)
        WITH p, a,
          CASE 
            WHEN a.fullAddress IS NOT NULL AND a.fullAddress <> '' THEN a.fullAddress
            ELSE p.address
          END AS addressToCheck
        MATCH (r:Region {name: 'Tbilisi'})
        WHERE (addressToCheck CONTAINS 'თბილისი' OR addressToCheck CONTAINS 'Tbilisi')
          AND NOT (p)-[:BELONGS_TO_REGION]->()
        MERGE (p)-[:BELONGS_TO_REGION]->(r)
        RETURN count(p) as count
        """
        result = session.run(tbilisi_query)
        count = result.single()["count"]
        if count > 0:
            linked += count
            print(f"✓ Tbilisi (general): +{count} people")
        
        # Link Unknown (no address from either source)
        unknown_query = """
        MATCH (p:Person)
        OPTIONAL MATCH (p)-[:LIVES_AT]->(a:Address)
        WITH p, a
        WHERE (p.address IS NULL OR p.address = '' OR p.address = 'Unspecified')
          AND (a.fullAddress IS NULL OR a.fullAddress = '')
          AND NOT (p)-[:BELONGS_TO_REGION]->()
        MATCH (r:Region {name: 'Unknown'})
        MERGE (p)-[:BELONGS_TO_REGION]->(r)
        RETURN count(p) as count
        """
        result = session.run(unknown_query)
        count = result.single()["count"]
        if count > 0:
            linked += count
            print(f"✓ Unknown: +{count} people")
        
        # Link Other Regions (remaining with addresses but no match)
        other_query = """
        MATCH (p:Person)
        OPTIONAL MATCH (p)-[:LIVES_AT]->(a:Address)
        WITH p, a,
          CASE 
            WHEN a.fullAddress IS NOT NULL AND a.fullAddress <> '' THEN a.fullAddress
            ELSE p.address
          END AS addressToCheck
        WHERE addressToCheck IS NOT NULL 
          AND addressToCheck <> '' 
          AND addressToCheck <> 'Unspecified'
          AND NOT (p)-[:BELONGS_TO_REGION]->()
        MATCH (r:Region {name: 'Other Regions'})
        MERGE (p)-[:BELONGS_TO_REGION]->(r)
        RETURN count(p) as count
        """
        result = session.run(other_query)
        count = result.single()["count"]
        if count > 0:
            linked += count
            print(f"✓ Other Regions: +{count} people")
        
        return linked


def get_region_statistics(driver, database):
    """Get statistics of people by region"""
    query = """
    MATCH (p:Person)-[:BELONGS_TO_REGION]->(r:Region)
    RETURN r.name as region, r.type as type, count(p) as peopleCount
    ORDER BY peopleCount DESC
    """
    
    with driver.session(database=database) as session:
        result = session.run(query)
        stats = [record.data() for record in result]
        return stats


def main():
    if not PASSWORD:
        print("❌ Error: DELIBERATION_NEO4J_PASSWORD environment variable not set")
        print("Please set it with: $env:DELIBERATION_NEO4J_PASSWORD='your-password'")
        return
    
    print(f"🚀 Connecting to Neo4j Aura at {URI}...")
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    
    try:
        # Verify connection
        driver.verify_connectivity()
        print(f"✓ Connected to database: {DATABASE}\n")
        
        # Step 1: Create Region nodes
        print("=" * 60)
        print("STEP 1: Creating Region nodes")
        print("=" * 60)
        created = create_regions(driver, DATABASE)
        print(f"\n✓ Created/updated {created} Region nodes\n")
        
        # Step 2: Link people to regions
        print("=" * 60)
        print("STEP 2: Linking People to Regions")
        print("=" * 60)
        linked = link_people_to_regions(driver, DATABASE)
        print(f"\n✓ Linked {linked} people to regions\n")
        
        # Step 3: Get statistics
        print("=" * 60)
        print("STEP 3: Region Statistics")
        print("=" * 60)
        stats = get_region_statistics(driver, DATABASE)
        
        print(f"\n{'Region':<30} {'Type':<12} {'People':<10}")
        print("-" * 60)
        for stat in stats:
            print(f"{stat['region']:<30} {stat['type']:<12} {stat['peopleCount']:<10}")
        
        total_people = sum(s['peopleCount'] for s in stats)
        print("-" * 60)
        print(f"{'TOTAL':<30} {'':<12} {total_people:<10}")
        
        print("\n✅ Region setup complete!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        driver.close()


if __name__ == "__main__":
    main()
