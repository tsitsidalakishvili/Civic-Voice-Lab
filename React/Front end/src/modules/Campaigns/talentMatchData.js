// TalentMatch data + pure matching/projection logic for the Campaigns & Audience module.
// Kept framework-free so it can be unit-tested and, later, mirrored by a backend endpoint.

export const NICHES = [
  // Commercial / lifestyle
  'fashion',
  'beauty',
  'lifestyle',
  'entertainment',
  'fitness',
  'food',
  'travel',
  // Creator / culture
  'comedy',
  'music',
  'gaming',
  // Knowledge / economy
  'tech',
  'business',
  'education',
  // Civic
  'news',
  'politics',
  'social',
  'health',
]

// Campaign/content formats and their projection multipliers (industry heuristics).
export const CAMPAIGN_FORMATS = {
  reel: { reach: 1.9, eng: 1.4, click: 0.08, label: 'Reel / TikTok Video' },
  post: { reach: 1.0, eng: 1.0, click: 0.1, label: 'Feed Post (Photo)' },
  story: { reach: 0.5, eng: 0.7, click: 0.15, label: 'Instagram Story' },
  collab: { reach: 2.8, eng: 1.6, click: 0.18, label: 'Full Collaboration' },
}

// Affinity groups — niches whose audiences overlap serve each other's brand
// campaigns well. A brand-niche/creator-niche pair takes the highest group score
// it shares; same-niche is always a direct match (65); lifestyle is a broad
// connector; everything else gets a small awareness-only floor.
const NICHE_AFFINITY_GROUPS = [
  { members: ['fashion', 'beauty', 'lifestyle'], score: 22 },
  { members: ['fitness', 'health', 'food'], score: 18 },
  { members: ['travel', 'lifestyle', 'food'], score: 14 },
  { members: ['entertainment', 'comedy', 'music', 'gaming'], score: 18 },
  { members: ['tech', 'business', 'education', 'gaming'], score: 15 },
  { members: ['news', 'politics', 'social'], score: 22 },
  { members: ['social', 'health', 'education'], score: 14 },
  { members: ['business', 'news', 'politics'], score: 12 },
  { members: ['comedy', 'entertainment', 'social'], score: 10 },
]

// niche-to-niche affinity matrix — how well a creator niche serves a brand niche.
// Generated from NICHE_AFFINITY_GROUPS so the taxonomy can grow without a giant
// hand-maintained NxN literal.
function buildMatchMatrix(niches, groups) {
  const matrix = {}
  for (const brand of niches) {
    matrix[brand] = {}
    for (const creator of niches) {
      if (brand === creator) {
        matrix[brand][creator] = 65
        continue
      }
      let score = 0
      for (const group of groups) {
        if (group.members.includes(brand) && group.members.includes(creator)) {
          score = Math.max(score, group.score)
        }
      }
      if (score === 0) score = brand === 'lifestyle' || creator === 'lifestyle' ? 6 : 3
      matrix[brand][creator] = score
    }
  }
  return matrix
}

export const MATCH_MATRIX = buildMatchMatrix(NICHES, NICHE_AFFINITY_GROUPS)

// Influence tiers by combined reach — how far a messenger's own voice carries a
// campaign message. Neutral civic framing (no commercial partnership value).
export const INFLUENCE_TIERS = [
  { min: 1_000_000, tier: 'National', reach: 'Nationwide voice', tone: 'celebrity' },
  { min: 500_000, tier: 'Major', reach: 'Major public voice', tone: 'vip' },
  { min: 100_000, tier: 'Broad', reach: 'Broad audience', tone: 'mass' },
  { min: 10_000, tier: 'Community', reach: 'Community reach', tone: 'micro' },
  { min: 5_000, tier: 'Grassroots', reach: 'Grassroots reach', tone: 'nano' },
]

// Seed roster — curated Georgian voices/creators. Replaceable via CSV import at runtime.
const SEED = [
  { name: 'Synthetic Creator 01', ig: 'https://example.invalid/synthetic-creator-01', igUser: 'synthetic_creator_01', tt: null, ttUser: null, niche: 'education', igF: 12500, ttF: 0, synthetic: true },
  { name: 'Synthetic Creator 02', ig: null, igUser: null, tt: 'https://example.invalid/synthetic-creator-02', ttUser: 'synthetic_creator_02', niche: 'tech', igF: 0, ttF: 28400, synthetic: true },
  { name: 'Synthetic Creator 03', ig: 'https://example.invalid/synthetic-creator-03', igUser: 'synthetic_creator_03', tt: 'https://example.invalid/synthetic-creator-03-video', ttUser: 'synthetic_creator_03', niche: 'lifestyle', igF: 86700, ttF: 19400, synthetic: true },
  { name: 'Synthetic Creator 04', ig: 'https://example.invalid/synthetic-creator-04', igUser: 'synthetic_creator_04', tt: null, ttUser: null, niche: 'news', igF: 43200, ttF: 0, synthetic: true },
  { name: 'Synthetic Creator 05', ig: null, igUser: null, tt: null, ttUser: null, x: 'https://example.invalid/synthetic-creator-05', xUser: 'synthetic_creator_05', niche: 'social', igF: 0, ttF: 0, xF: 9100, synthetic: true },
  { name: 'Synthetic Creator 06', ig: 'https://example.invalid/synthetic-creator-06', igUser: 'synthetic_creator_06', tt: null, ttUser: null, niche: 'health', igF: 156000, ttF: 0, synthetic: true },
  { name: 'Synthetic Creator 07', ig: 'https://example.invalid/synthetic-creator-07', igUser: 'synthetic_creator_07', tt: 'https://example.invalid/synthetic-creator-07-video', ttUser: 'synthetic_creator_07', niche: 'entertainment', igF: 324000, ttF: 118000, synthetic: true },
  { name: 'Synthetic Creator 08', ig: 'https://example.invalid/synthetic-creator-08', igUser: 'synthetic_creator_08', tt: null, ttUser: null, niche: 'business', igF: 6300, ttF: 0, synthetic: true },
]

// Pure helpers
export function formatCompact(n) {
  const num = Number(n) || 0
  if (num >= 1e6) return `${(num / 1e6).toFixed(1)}M`
  if (num >= 1000) return `${(num / 1000).toFixed(0)}K`
  return String(num)
}

export function initials(name) {
  return String(name || '')
    .split(' ')
    .slice(0, 2)
    .map((w) => w[0])
    .join('')
    .toUpperCase()
}

// Estimated engagement rate by audience size (larger audiences engage at lower rates).
export function estimateEngagement(total) {
  if (total > 500000) return 2.8
  if (total > 300000) return 3.0
  if (total > 200000) return 3.2
  if (total > 100000) return 3.8
  if (total > 50000) return 4.5
  if (total > 20000) return 5.5
  return 6.5
}

// Add derived fields (total reach, avg views, engagement) to a raw roster row.
export function enrichCreator(raw) {
  const igF = Number(raw.igF) || 0
  const ttF = Number(raw.ttF) || 0
  const xF = Number(raw.xF) || 0
  const total = igF + ttF + xF
  const avgViews = Math.round(igF * 0.4 + ttF * 0.62 + xF * 0.25) || Math.round(total * 0.35)
  return {
    ...raw,
    igF,
    ttF,
    xF,
    total,
    avgViews,
    eng: raw.eng != null && raw.eng !== '' ? Number(raw.eng) : estimateEngagement(total),
    real: Boolean(raw.real),
  }
}

export function seedRoster() {
  return SEED.map(enrichCreator)
}

export function influenceTierFor(total) {
  return INFLUENCE_TIERS.find((tier) => total >= tier.min) || null
}

const NICHE_KEYWORDS = {
  fashion: ['fashion', 'cloth', 'wear', 'dress', 'style', 'outfit', 'model', 'boutique', 'apparel', 'collection', 'couture', 'remember', 'garment'],
  beauty: ['beauty', 'makeup', 'skin', 'hair', 'cosmetic', 'salon', 'spa', 'glow', 'serum', 'lotion', 'cream', 'nails', 'perfume', 'fragrance'],
  food: ['food', 'eat', 'drink', 'cafe', 'restaurant', 'candy', 'sweet', 'snack', 'cook', 'chef', 'bakery', 'coffee', 'wine', 'beer', 'chocolate', 'captain', 'sugar', 'juice'],
  fitness: ['fit', 'gym', 'sport', 'workout', 'run', 'athletic', 'protein', 'yoga', 'pilates', 'training', 'crossfit'],
  travel: ['travel', 'hotel', 'tour', 'trip', 'airline', 'resort', 'adventure', 'booking', 'vacation', 'holiday'],
  entertainment: ['event', 'club', 'entertainment', 'show', 'party', 'festival', 'cinema', 'film', 'tv', 'celebrity'],
  comedy: ['comedy', 'humor', 'humour', 'funny', 'meme', 'standup', 'stand-up', 'joke', 'satire', 'prank', 'sketch'],
  music: ['music', 'band', 'song', 'singer', 'musician', 'concert', 'album', 'label', 'records', 'rap', 'hip-hop', 'dj'],
  gaming: ['gaming', 'game', 'esport', 'gamer', 'stream', 'twitch', 'playstation', 'xbox', 'console', 'arcade'],
  tech: ['tech', 'software', 'startup', 'app', ' ai', 'developer', 'gadget', 'saas', 'crypto', 'hardware', 'robot', 'code'],
  business: ['business', 'finance', 'bank', 'invest', 'entrepreneur', 'market', 'corporate', 'trade', 'economy', 'consult', 'fintech', 'startup'],
  education: ['education', 'school', 'university', 'course', 'learn', 'study', 'teacher', 'academy', 'tutor', 'language', 'exam', 'science'],
  news: ['news', 'media', 'press', 'journal', 'report', 'broadcast', 'headline', 'newsroom', 'disinformation', 'propaganda'],
  politics: ['politic', 'government', 'election', 'party', 'policy', 'parliament', 'civic', 'democracy', 'vote', 'reform', 'corruption', 'eu', 'europe', 'accession', 'sovereignty', 'opposition', 'referendum'],
  social: ['social', 'activ', 'ngo', 'charity', 'rights', 'community', 'volunteer', 'equality', 'awareness', 'nonprofit', 'humanitarian', 'protest', 'justice', 'freedom', 'minorit', 'gender', 'diaspora'],
  health: ['health', 'medical', 'doctor', 'clinic', 'nutrition', 'wellness', 'psychology', 'therapy', 'mental', 'pharma', 'dental', 'medicine'],
  lifestyle: ['life', 'home', 'decor', 'digital', 'online', 'service', 'organic', 'vlog'],
}

// Infer a campaign's issue/topic area from its name or description by keyword hits.
export function inferNiche(input) {
  const s = String(input || '').toLowerCase()
  let best = 'lifestyle'
  let bestScore = 0
  for (const [niche, words] of Object.entries(NICHE_KEYWORDS)) {
    const score = words.filter((w) => s.includes(w)).length
    if (score > bestScore) {
      bestScore = score
      best = niche
    }
  }
  return best
}

export function buildReason(campaignTopic, campaignName, creator) {
  const nicheScore = (MATCH_MATRIX[campaignTopic] || MATCH_MATRIX.lifestyle)[creator.niche] || 0
  const followers = formatCompact(creator.total)
  if (nicheScore >= 60) {
    return `${creator.name} is a ${creator.niche} voice with ${followers} followers — directly aligned with "${campaignName}". Their ${creator.eng}% engagement means the message reaches a highly active, on-topic audience.`
  }
  if (nicheScore >= 20) {
    return `${creator.name}'s ${creator.niche} audience overlaps strongly with the audience for "${campaignName}". With ${followers} followers and ${creator.eng}% engagement, they can carry the message to adjacent, receptive communities.`
  }
  return `${creator.name} brings broad reach (${followers} followers) across their platforms. Their ${creator.niche} focus is not a direct topic match, but their scale makes them valuable for widening awareness of "${campaignName}".`
}

// Score every messenger against a campaign topic and return the top N matches.
export function matchCreators(roster, campaignTopic, campaignName, count) {
  const scored = roster.map((creator) => {
    const ns = (MATCH_MATRIX[campaignTopic] || MATCH_MATRIX.lifestyle)[creator.niche] || 0
    const es = Math.min(creator.eng * 1.2, 12)
    const rs = Math.min(creator.total / 30000, 8)
    const raw = ns + es + rs
    const score =
      ns >= 60
        ? Math.min(Math.round(55 + raw * 0.52), 99)
        : Math.min(Math.round(15 + raw * 0.38), 57)
    return { ...creator, score, reason: buildReason(campaignTopic, campaignName, creator) }
  })
  return scored.sort((a, b) => b.score - a.score).slice(0, count)
}

// Aggregate reach / engagement / clicks projection for a set of matches + format.
export function projectCampaign(matches, formatKey) {
  const format = CAMPAIGN_FORMATS[formatKey] || CAMPAIGN_FORMATS.post
  const reach = Math.round(matches.reduce((sum, m) => sum + m.avgViews * format.reach, 0))
  const eng = Math.round(matches.reduce((sum, m) => sum + m.total * (m.eng / 100) * format.eng, 0))
  const clicks = Math.round(eng * format.click)
  const engRate = reach > 0 ? ((eng / reach) * 100).toFixed(1) : '0.0'
  return { reach, eng, clicks, engRate, format }
}

// Roster-wide summary for the header pulse stats.
export function rosterSummary(roster) {
  const total = roster.reduce((s, r) => s + r.total, 0)
  const withTikTok = roster.filter((r) => r.ttF > 0).length
  const withX = roster.filter((r) => (r.xF || 0) > 0).length
  const avgEng = roster.length
    ? (roster.reduce((s, r) => s + Number(r.eng || 0), 0) / roster.length).toFixed(1)
    : '0.0'
  return { count: roster.length, totalReach: total, withTikTok, withX, avgEng }
}

// ── follower-trend (stock-style arrows) ───────────────────────
// Genuine ▲/▼ arrows require two data points over time. We keep a local history
// of dated follower snapshots; the arrow shows the real change between a
// creator's current total and their most recent earlier snapshot. No fabricated
// deltas — until a second snapshot exists a creator reads as "new".

// Stable identity for matching a creator across snapshots (handles rename of
// display name but keeps the same social handle).
export function creatorKey(creator) {
  return (creator.igUser || creator.ttUser || creator.name || '').toLowerCase()
}

// Build a snapshot of the current roster: { date, totals: { key: total } }.
export function buildSnapshot(roster, nowMs) {
  const totals = {}
  for (const creator of roster) {
    totals[creatorKey(creator)] = Number(creator.total) || 0
  }
  return { date: new Date(nowMs ?? Date.now()).toISOString(), totals }
}

// Compare a creator's live total against the most recent earlier snapshot that
// contains them. Returns null when there is no prior data point.
export function computeTrend(creator, history, nowMs) {
  if (!Array.isArray(history) || history.length === 0) return null
  const key = creatorKey(creator)
  const now = nowMs ?? Date.now()
  for (let i = history.length - 1; i >= 0; i -= 1) {
    const prev = history[i]?.totals?.[key]
    if (prev != null && prev > 0) {
      const pct = ((Number(creator.total) - prev) / prev) * 100
      const days = Math.max(1, Math.round((now - new Date(history[i].date).getTime()) / 86_400_000))
      const dir = pct > 0.2 ? 'up' : pct < -0.2 ? 'down' : 'flat'
      return { dir, pct: Number(pct.toFixed(1)), days, prev }
    }
  }
  return null
}

const FOLLOWER_RE = /^([\d.]+)\s*([km])?$/i

export function parseFollowerCount(value) {
  if (value == null) return 0
  const s = String(value).trim().replace(/[,\s]/g, '')
  if (!s) return 0
  const m = s.match(FOLLOWER_RE)
  if (!m) return parseInt(s, 10) || 0
  const n = parseFloat(m[1])
  const suffix = (m[2] || '').toLowerCase()
  if (suffix === 'k') return Math.round(n * 1000)
  if (suffix === 'm') return Math.round(n * 1e6)
  return Math.round(n)
}

function usernameFromUrl(url) {
  if (!url) return null
  return (
    String(url)
      .split('/')
      .filter(Boolean)
      .pop()
      ?.replace('@', '') || null
  )
}

// Map parsed CSV rows (array-of-arrays, first row = header) into enriched creators.
// Expected columns: Name, Instagram, IG Followers, TikTok, TT Followers,
// X/Twitter, X Followers, Eng%, Niche
export function rowsToRoster(rows) {
  const out = []
  for (let i = 1; i < rows.length; i += 1) {
    const r = rows[i]
    if (!r || !r[0]) continue
    const name = String(r[0]).trim()
    if (!name || name.length < 2) continue
    const ig = r[1] ? String(r[1]).trim() : null
    const tt = r[3] ? String(r[3]).trim() : null
    const x = r[5] ? String(r[5]).trim() : null
    out.push(
      enrichCreator({
        name,
        ig: ig || null,
        igUser: usernameFromUrl(ig),
        tt: tt || null,
        ttUser: usernameFromUrl(tt),
        x: x || null,
        xUser: usernameFromUrl(x),
        niche: r[8] ? String(r[8]).trim().toLowerCase() : inferNiche(name),
        igF: parseFollowerCount(r[2]),
        ttF: parseFollowerCount(r[4]),
        xF: parseFollowerCount(r[6]),
        eng: r[7] !== undefined && r[7] !== '' ? parseFloat(r[7]) : undefined,
        real: false,
      }),
    )
  }
  return out
}

// Serialize the roster back to CSV rows for export.
export function rosterToRows(roster) {
  const header = ['Name', 'Instagram', 'IG Followers', 'TikTok', 'TT Followers', 'X/Twitter', 'X Followers', 'Eng%', 'Niche', 'Total', 'Data']
  const body = roster.map((r) => [
    r.name,
    r.ig || '',
    r.igF || 0,
    r.tt || '',
    r.ttF || 0,
    r.x || '',
    r.xF || 0,
    r.eng,
    r.niche,
    r.total,
    r.real ? 'real' : 'estimated',
  ])
  return [header, ...body]
}
