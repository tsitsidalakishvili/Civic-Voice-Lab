#!/usr/bin/env python3
"""Check what data is actually in the database."""

import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

def check_data():
    driver = GraphDatabase.driver(
        os.getenv("DELIBERATION_NEO4J_AURA_URI"),
        auth=(os.getenv("DELIBERATION_NEO4J_AURA_USER"), os.getenv("DELIBERATION_NEO4J_AURA_PASSWORD"))
    )
    
    with driver.session() as session:
        # Total people
        result = session.run("MATCH (p:Person) RETURN count(*) as c")
        print(f"Total people: {result.single()['c']}")
        
        # People with age
        result = session.run("MATCH (p:Person) WHERE p.age IS NOT NULL RETURN count(*) as c")
        print(f"People with age: {result.single()['c']}")
        
        # Sample ages
        result = session.run("MATCH (p:Person) WHERE p.age IS NOT NULL RETURN p.age as age LIMIT 5")
        ages = [r['age'] for r in result]
        print(f"Sample ages: {ages}")
        
        # People with address
        result = session.run("MATCH (p:Person) WHERE p.address IS NOT NULL AND p.address <> '' RETURN count(*) as c")
        print(f"People with address: {result.single()['c']}")
        
        # Sample addresses
        result = session.run("MATCH (p:Person) WHERE p.address IS NOT NULL RETURN p.address as addr LIMIT 3")
        addrs = [r['addr'] for r in result]
        print(f"Sample addresses: {addrs}")
        
        # People with joinDate
        result = session.run("MATCH (p:Person) WHERE p.joinDate IS NOT NULL RETURN count(*) as c")
        print(f"People with joinDate: {result.single()['c']}")
        
        # Sample joinDates
        result = session.run("MATCH (p:Person) WHERE p.joinDate IS NOT NULL RETURN p.joinDate as jd LIMIT 3")
        jds = [r['jd'] for r in result]
        print(f"Sample joinDates: {jds}")
        
        # Check gender
        result = session.run("MATCH (p:Person) WHERE p.gender IS NOT NULL AND p.gender <> '' RETURN count(*) as c")
        print(f"People with gender: {result.single()['c']}")
        
        # Sample genders
        result = session.run("MATCH (p:Person) WHERE p.gender IS NOT NULL RETURN p.gender as g LIMIT 5")
        genders = [r['g'] for r in result]
        print(f"Sample genders: {genders}")
    
    driver.close()
    print("\nCheck complete!")

if __name__ == "__main__":
    check_data()
