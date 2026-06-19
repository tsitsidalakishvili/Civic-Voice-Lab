// Diagnostic: what does WANTS_TO_HELP_WITH connect to?
MATCH (p:Person)-[:WANTS_TO_HELP_WITH]->(n)
RETURN labels(n) AS node_labels, count(*) AS count
ORDER BY count DESC
