Audience Discovery Engine - QA Checklist

Input validation
- Invalid sitemap URL
- Empty seed URL list
- Invalid URL format

Crawling
- robots.txt disallows crawling
- 404 and 500 responses
- Mixed HTTP/HTTPS redirects
- Large sites with max pages limit

Content extraction
- Pages with no headings
- Pages with only images or scripts
- Non-English content

Chunking
- Empty chunks rejected
- Offsets match cleaned text
- Chunk overlap applied

Embeddings
- External API rate limit
- Embeddings API failure fallback

Clustering
- No embeddings available
- Single chunk input

Segments
- LLM invalid JSON response
- No evidence quotes

Evidence verification
- Quotes not found in chunks
- Quotes with mismatched offsets

Messaging
- Only confirmed segments included
- Evidence-based recommendations

Exports
- JSON includes pages, segments, evidence, messaging, metrics
- CSV includes messaging fields
