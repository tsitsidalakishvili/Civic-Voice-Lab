// Find all properties that exist on Person nodes
MATCH (p:Person)
UNWIND keys(p) AS key
RETURN DISTINCT key
ORDER BY key
