// Regional Skills Distribution - diagnostic query
// Matches what the chart should display: top skills per major Georgian city

MATCH (p:Person)-[:CAN_CONTRIBUTE_WITH]->(s:Skill)
OPTIONAL MATCH (p)-[:LIVES_AT]->(a:Address)
WITH p, s,
  CASE 
    WHEN toLower(coalesce(p.address, a.fullAddress, '')) CONTAINS 'თბილისი' OR toLower(coalesce(p.address, a.fullAddress, '')) CONTAINS 'tbilisi' THEN 'Tbilisi'
    WHEN toLower(coalesce(p.address, a.fullAddress, '')) CONTAINS 'ბათუმი' OR toLower(coalesce(p.address, a.fullAddress, '')) CONTAINS 'batumi' THEN 'Batumi'
    WHEN toLower(coalesce(p.address, a.fullAddress, '')) CONTAINS 'ქუთაისი' OR toLower(coalesce(p.address, a.fullAddress, '')) CONTAINS 'kutaisi' THEN 'Kutaisi'
    WHEN toLower(coalesce(p.address, a.fullAddress, '')) CONTAINS 'რუსთავი' OR toLower(coalesce(p.address, a.fullAddress, '')) CONTAINS 'rustavi' THEN 'Rustavi'
    WHEN toLower(coalesce(p.address, a.fullAddress, '')) CONTAINS 'გორი' OR toLower(coalesce(p.address, a.fullAddress, '')) CONTAINS 'gori' THEN 'Gori'
    WHEN toLower(coalesce(p.address, a.fullAddress, '')) CONTAINS 'ზუგდიდი' OR toLower(coalesce(p.address, a.fullAddress, '')) CONTAINS 'zugdidi' THEN 'Zugdidi'
    WHEN toLower(coalesce(p.address, a.fullAddress, '')) CONTAINS 'თელავი' OR toLower(coalesce(p.address, a.fullAddress, '')) CONTAINS 'telavi' THEN 'Telavi'
    ELSE 'Other'
  END AS region
WHERE region <> 'Other'
RETURN region, s.name AS skill, count(*) AS count
ORDER BY region, count DESC
LIMIT 20
