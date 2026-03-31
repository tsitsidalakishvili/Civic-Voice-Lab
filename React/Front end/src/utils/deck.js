export const parseStoredList = (value) => {
  if (!value) return []
  try {
    const parsed = JSON.parse(value)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

export const parseLocalArray = (value) => {
  if (!value) return []
  try {
    const parsed = JSON.parse(value)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

export const shuffleArray = (items) => {
  const copy = [...items]
  for (let i = copy.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[copy[i], copy[j]] = [copy[j], copy[i]]
  }
  return copy
}

export const buildCommentDeck = (rawComments, votedIds = []) => {
  const votedSet = new Set(votedIds.map((id) => String(id)))
  const seenIds = new Set()
  const normalized = rawComments
    .map((comment, index) => {
      const id =
        comment?.id ||
        comment?.comment_id ||
        comment?.commentId ||
        `comment-${index}`
      const text = String(
        comment?.text || comment?.comment_text || comment?.commentText || '',
      )
        .replace(/\s+/g, ' ')
        .trim()
      if (!text) return null
      const agree = Number(comment?.agree_count || comment?.agreeCount || 0)
      const disagree = Number(comment?.disagree_count || comment?.disagreeCount || 0)
      const pass = Number(comment?.pass_count || comment?.passCount || 0)
      const voteCount = agree + disagree + pass
      const createdAt =
        Date.parse(comment?.created_at || comment?.createdAt || '') || 0
      return { id: String(id), text, voteCount, createdAt }
    })
    .filter(Boolean)
    .filter((comment) => {
      if (votedSet.has(comment.id)) return false
      if (seenIds.has(comment.id)) return false
      seenIds.add(comment.id)
      return true
    })

  if (!normalized.length) return []

  const byVoteCount = normalized.reduce((acc, comment) => {
    const key = comment.voteCount
    if (!acc[key]) acc[key] = []
    acc[key].push(comment)
    return acc
  }, {})

  const orderedCounts = Object.keys(byVoteCount)
    .map(Number)
    .sort((a, b) => a - b)

  const deck = []
  orderedCounts.forEach((count) => {
    deck.push(...shuffleArray(byVoteCount[count] || []))
  })
  return deck
}
