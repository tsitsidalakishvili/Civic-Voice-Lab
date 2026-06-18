// Link Person nodes to Region nodes based on address patterns
// This creates BELONGS_TO_REGION relationships

// 1. Tbilisi districts
MATCH (p:Person), (r:Region {name: 'Tbilisi - Vake'})
WHERE (p.address CONTAINS 'ვაკე' OR p.address CONTAINS 'Vake')
  AND NOT (p)-[:BELONGS_TO_REGION]->()
MERGE (p)-[:BELONGS_TO_REGION]->(r);

MATCH (p:Person), (r:Region {name: 'Tbilisi - Saburtalo'})
WHERE (p.address CONTAINS 'საბურთალო' OR p.address CONTAINS 'Saburtalo')
  AND NOT (p)-[:BELONGS_TO_REGION]->()
MERGE (p)-[:BELONGS_TO_REGION]->(r);

MATCH (p:Person), (r:Region {name: 'Tbilisi - Dighomi'})
WHERE (p.address CONTAINS 'დიღომი' OR p.address CONTAINS 'Dighomi')
  AND NOT (p)-[:BELONGS_TO_REGION]->()
MERGE (p)-[:BELONGS_TO_REGION]->(r);

MATCH (p:Person), (r:Region {name: 'Tbilisi - Mukhiani'})
WHERE (p.address CONTAINS 'მუხიანი' OR p.address CONTAINS 'Mukhiani')
  AND NOT (p)-[:BELONGS_TO_REGION]->()
MERGE (p)-[:BELONGS_TO_REGION]->(r);

MATCH (p:Person), (r:Region {name: 'Tbilisi - Varketili'})
WHERE (p.address CONTAINS 'ვარკეთილი' OR p.address CONTAINS 'Varketili')
  AND NOT (p)-[:BELONGS_TO_REGION]->()
MERGE (p)-[:BELONGS_TO_REGION]->(r);

MATCH (p:Person), (r:Region {name: 'Tbilisi - Gldani'})
WHERE (p.address CONTAINS 'გლდანი' OR p.address CONTAINS 'Gldani')
  AND NOT (p)-[:BELONGS_TO_REGION]->()
MERGE (p)-[:BELONGS_TO_REGION]->(r);

MATCH (p:Person), (r:Region {name: 'Tbilisi - Samgori'})
WHERE (p.address CONTAINS 'სამგორი' OR p.address CONTAINS 'Samgori')
  AND NOT (p)-[:BELONGS_TO_REGION]->()
MERGE (p)-[:BELONGS_TO_REGION]->(r);

MATCH (p:Person), (r:Region {name: 'Tbilisi - Nadzaladevi'})
WHERE (p.address CONTAINS 'ნაძალადევი' OR p.address CONTAINS 'Nadzaladevi')
  AND NOT (p)-[:BELONGS_TO_REGION]->()
MERGE (p)-[:BELONGS_TO_REGION]->(r);

MATCH (p:Person), (r:Region {name: 'Tbilisi - Isani'})
WHERE (p.address CONTAINS 'ისანი' OR p.address CONTAINS 'Isani')
  AND NOT (p)-[:BELONGS_TO_REGION]->()
MERGE (p)-[:BELONGS_TO_REGION]->(r);

MATCH (p:Person), (r:Region {name: 'Tbilisi - Krtsanisi'})
WHERE (p.address CONTAINS 'კრწანისი' OR p.address CONTAINS 'Krtsanisi')
  AND NOT (p)-[:BELONGS_TO_REGION]->()
MERGE (p)-[:BELONGS_TO_REGION]->(r);

MATCH (p:Person), (r:Region {name: 'Tbilisi - Mtatsminda'})
WHERE (p.address CONTAINS 'მთაწმინდა' OR p.address CONTAINS 'Mtatsminda')
  AND NOT (p)-[:BELONGS_TO_REGION]->()
MERGE (p)-[:BELONGS_TO_REGION]->(r);

MATCH (p:Person), (r:Region {name: 'Tbilisi - Sololaki'})
WHERE (p.address CONTAINS 'სოლოლაკი' OR p.address CONTAINS 'Sololaki')
  AND NOT (p)-[:BELONGS_TO_REGION]->()
MERGE (p)-[:BELONGS_TO_REGION]->(r);

MATCH (p:Person), (r:Region {name: 'Tbilisi - Vera'})
WHERE (p.address CONTAINS 'ვერა' OR p.address CONTAINS 'Vera')
  AND NOT (p)-[:BELONGS_TO_REGION]->()
MERGE (p)-[:BELONGS_TO_REGION]->(r);

MATCH (p:Person), (r:Region {name: 'Tbilisi - Didube'})
WHERE (p.address CONTAINS 'დიდუბე' OR p.address CONTAINS 'Didube')
  AND NOT (p)-[:BELONGS_TO_REGION]->()
MERGE (p)-[:BELONGS_TO_REGION]->(r);

MATCH (p:Person), (r:Region {name: 'Tbilisi - Chugureti'})
WHERE (p.address CONTAINS 'ჩუღურეთი' OR p.address CONTAINS 'Chugureti')
  AND NOT (p)-[:BELONGS_TO_REGION]->()
MERGE (p)-[:BELONGS_TO_REGION]->(r);

MATCH (p:Person), (r:Region {name: 'Tbilisi - Abanotubani'})
WHERE (p.address CONTAINS 'აბანოთუბანი' OR p.address CONTAINS 'Abanotubani')
  AND NOT (p)-[:BELONGS_TO_REGION]->()
MERGE (p)-[:BELONGS_TO_REGION]->(r);

MATCH (p:Person), (r:Region {name: 'Tbilisi - Vazisubani'})
WHERE (p.address CONTAINS 'ვაზისუბანი' OR p.address CONTAINS 'Vazisubani')
  AND NOT (p)-[:BELONGS_TO_REGION]->()
MERGE (p)-[:BELONGS_TO_REGION]->(r);

// 2. General Tbilisi (if no district matched)
MATCH (p:Person), (r:Region {name: 'Tbilisi'})
WHERE (p.address CONTAINS 'თბილისი' OR p.address CONTAINS 'Tbilisi')
  AND NOT (p)-[:BELONGS_TO_REGION]->()
MERGE (p)-[:BELONGS_TO_REGION]->(r);

// 3. Other major cities
MATCH (p:Person), (r:Region {name: 'Batumi'})
WHERE (p.address CONTAINS 'ბათუმი' OR p.address CONTAINS 'Batumi')
  AND NOT (p)-[:BELONGS_TO_REGION]->()
MERGE (p)-[:BELONGS_TO_REGION]->(r);

MATCH (p:Person), (r:Region {name: 'Kutaisi'})
WHERE (p.address CONTAINS 'ქუთაისი' OR p.address CONTAINS 'Kutaisi')
  AND NOT (p)-[:BELONGS_TO_REGION]->()
MERGE (p)-[:BELONGS_TO_REGION]->(r);

MATCH (p:Person), (r:Region {name: 'Rustavi'})
WHERE (p.address CONTAINS 'რუსთავი' OR p.address CONTAINS 'Rustavi')
  AND NOT (p)-[:BELONGS_TO_REGION]->()
MERGE (p)-[:BELONGS_TO_REGION]->(r);

MATCH (p:Person), (r:Region {name: 'Gori'})
WHERE (p.address CONTAINS 'გორი' OR p.address CONTAINS 'Gori')
  AND NOT (p)-[:BELONGS_TO_REGION]->()
MERGE (p)-[:BELONGS_TO_REGION]->(r);

MATCH (p:Person), (r:Region {name: 'Zugdidi'})
WHERE (p.address CONTAINS 'ზუგდიდი' OR p.address CONTAINS 'Zugdidi')
  AND NOT (p)-[:BELONGS_TO_REGION]->()
MERGE (p)-[:BELONGS_TO_REGION]->(r);

MATCH (p:Person), (r:Region {name: 'Telavi'})
WHERE (p.address CONTAINS 'თელავი' OR p.address CONTAINS 'Telavi')
  AND NOT (p)-[:BELONGS_TO_REGION]->()
MERGE (p)-[:BELONGS_TO_REGION]->(r);

MATCH (p:Person), (r:Region {name: 'Akhmeta'})
WHERE (p.address CONTAINS 'ახმეტა' OR p.address CONTAINS 'Akhmeta')
  AND NOT (p)-[:BELONGS_TO_REGION]->()
MERGE (p)-[:BELONGS_TO_REGION]->(r);

MATCH (p:Person), (r:Region {name: 'Ozurgeti'})
WHERE (p.address CONTAINS 'ოზურგეთი' OR p.address CONTAINS 'Ozurgeti')
  AND NOT (p)-[:BELONGS_TO_REGION]->()
MERGE (p)-[:BELONGS_TO_REGION]->(r);

MATCH (p:Person), (r:Region {name: 'Khashuri'})
WHERE (p.address CONTAINS 'ხაშური' OR p.address CONTAINS 'Khashuri')
  AND NOT (p)-[:BELONGS_TO_REGION]->()
MERGE (p)-[:BELONGS_TO_REGION]->(r);

MATCH (p:Person), (r:Region {name: 'Chiatura'})
WHERE (p.address CONTAINS 'ჭიათურა' OR p.address CONTAINS 'Chiatura')
  AND NOT (p)-[:BELONGS_TO_REGION]->()
MERGE (p)-[:BELONGS_TO_REGION]->(r);

MATCH (p:Person), (r:Region {name: 'Mtskheta'})
WHERE (p.address CONTAINS 'მცხეთა' OR p.address CONTAINS 'Mtskheta')
  AND NOT (p)-[:BELONGS_TO_REGION]->()
MERGE (p)-[:BELONGS_TO_REGION]->(r);

MATCH (p:Person), (r:Region {name: 'Martvili'})
WHERE (p.address CONTAINS 'მარტვილი' OR p.address CONTAINS 'Martvili')
  AND NOT (p)-[:BELONGS_TO_REGION]->()
MERGE (p)-[:BELONGS_TO_REGION]->(r);

MATCH (p:Person), (r:Region {name: 'Samtredia'})
WHERE (p.address CONTAINS 'სამტრედია' OR p.address CONTAINS 'Samtredia')
  AND NOT (p)-[:BELONGS_TO_REGION]->()
MERGE (p)-[:BELONGS_TO_REGION]->(r);

MATCH (p:Person), (r:Region {name: 'Tedzami'})
WHERE (p.address CONTAINS 'თეძამი' OR p.address CONTAINS 'Tedzami')
  AND NOT (p)-[:BELONGS_TO_REGION]->()
MERGE (p)-[:BELONGS_TO_REGION]->(r);

MATCH (p:Person), (r:Region {name: 'Sagarejo'})
WHERE (p.address CONTAINS 'საგარეჯო' OR p.address CONTAINS 'Sagarejo')
  AND NOT (p)-[:BELONGS_TO_REGION]->()
MERGE (p)-[:BELONGS_TO_REGION]->(r);

MATCH (p:Person), (r:Region {name: 'Sighnaghi'})
WHERE (p.address CONTAINS 'სიღნაღი' OR p.address CONTAINS 'Sighnaghi')
  AND NOT (p)-[:BELONGS_TO_REGION]->()
MERGE (p)-[:BELONGS_TO_REGION]->(r);

MATCH (p:Person), (r:Region {name: 'Kobuleti'})
WHERE (p.address CONTAINS 'ქობულეთი' OR p.address CONTAINS 'Kobuleti')
  AND NOT (p)-[:BELONGS_TO_REGION]->()
MERGE (p)-[:BELONGS_TO_REGION]->(r);

MATCH (p:Person), (r:Region {name: 'Poti'})
WHERE (p.address CONTAINS 'ფოთი' OR p.address CONTAINS 'Poti')
  AND NOT (p)-[:BELONGS_TO_REGION]->()
MERGE (p)-[:BELONGS_TO_REGION]->(r);

MATCH (p:Person), (r:Region {name: 'Sukhumi'})
WHERE (p.address CONTAINS 'სოხუმი' OR p.address CONTAINS 'Sukhumi')
  AND NOT (p)-[:BELONGS_TO_REGION]->()
MERGE (p)-[:BELONGS_TO_REGION]->(r);

// 4. Unknown (no address or empty address)
MATCH (p:Person), (r:Region {name: 'Unknown'})
WHERE (p.address IS NULL OR p.address = '' OR p.address = 'Unspecified')
  AND NOT (p)-[:BELONGS_TO_REGION]->()
MERGE (p)-[:BELONGS_TO_REGION]->(r);

// 5. Other Regions (catch-all for any remaining unassigned people)
MATCH (p:Person), (r:Region {name: 'Other Regions'})
WHERE p.address IS NOT NULL 
  AND p.address <> '' 
  AND p.address <> 'Unspecified'
  AND NOT (p)-[:BELONGS_TO_REGION]->()
MERGE (p)-[:BELONGS_TO_REGION]->(r);

// Return statistics
MATCH (p:Person)-[rel:BELONGS_TO_REGION]->(r:Region)
RETURN r.name as region, count(p) as peopleCount
ORDER BY peopleCount DESC;
