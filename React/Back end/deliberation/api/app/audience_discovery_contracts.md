Audience Discovery Engine - Data Contracts

ProductPage
- pageId (string)
- url (string)
- title (string)
- rawHtml (string)
- cleanedText (string)
- crawlStatus (string: success | failed | skipped)
- metaDescription (string)
- canonicalUrl (string)
- headings (string[])
- breadcrumbs (string[])

ContentChunk
- chunkId (string)
- pageId (string)
- url (string)
- text (string)
- startOffset (number)
- endOffset (number)
- sectionHeading (string)
- embedding (number[])
- embeddingModel (string)
- embeddingTimestamp (number)
- textHash (string)

Cluster
- clusterId (string)
- clusterSize (number)
- chunkIds (string[])
- sampleSnippets (string[])
- label (string)

Segment
- segmentId (string)
- name (string)
- rationale (string)
- confidence (number)
- evidence (EvidenceSnippet[])
- confirmed (boolean)
- verified (boolean)
- pageId (string)
- pageUrl (string)
- rejectedEvidence (string[])

EvidenceSnippet
- quote (string)
- url (string)
- chunkId (string)
- startOffset (number)
- endOffset (number)
- isSample (boolean)

MessagingRecommendation
- segmentId (string)
- name (string)
- headlines (string[])
- tone (string)
- ctas (string[])

MetricsSummary
- coverage (number)
- explainability (number)
- evidencePassRate (number)
- runtimeSeconds (number)
- p95RuntimeSeconds (number)
- pagesCrawled (number)
- segmentsGenerated (number)
- verifiedSegments (number)
- chunksCreated (number)
- clustersCreated (number)
