import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { getJson, requestJson } from '../services/api'
import { LanguageSelect, StatusMessage } from '../ui'
import { parseLocalArray } from '../utils/deck'

export function DeliberationQuestionnaire({
  conversationId,
  t,
  language,
  languages,
  onLanguageChange,
}) {
  const translate = t || ((key, vars) => key)
  const [error, setError] = useState('')
  const [comments, setComments] = useState([])
  const [statementDiscussionById, setStatementDiscussionById] = useState({})
  const [statementDiscussionDraftById, setStatementDiscussionDraftById] = useState({})
  const [statementDiscussionLoadingById, setStatementDiscussionLoadingById] = useState({})
  const [statementDiscussionSavingById, setStatementDiscussionSavingById] = useState({})
  const [statementDiscussionErrorById, setStatementDiscussionErrorById] = useState({})
  const [statementDiscussionReactionBusyById, setStatementDiscussionReactionBusyById] = useState(
    {},
  )
  const [loading, setLoading] = useState(false)
  const [queueLoading, setQueueLoading] = useState(false)
  const [currentIndex, setCurrentIndex] = useState(0)
  const [pendingVote, setPendingVote] = useState(false)
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 })
  const [isDragging, setIsDragging] = useState(false)
  const [conversation, setConversation] = useState(null)
  const [votedIds, setVotedIds] = useState([])
  const [importantFlag, setImportantFlag] = useState(false)
  const [completedSent, setCompletedSent] = useState(false)
  const votedIdsRef = useRef([])
  const dragStartRef = useRef(null)
  const dragTypeRef = useRef(null)
  const dragPointerIdRef = useRef(null)
  const supportsPointerEvents =
    typeof window !== 'undefined' && typeof window.PointerEvent !== 'undefined'

  const params = new URLSearchParams(window.location.search)
  const sid = params.get('sid') || ''
  const inviteCode = params.get('invite') || ''
  const xid = params.get('xid') || params.get('participant_id') || ''
  const viewMode = params.get('view') || ''
  const isEmbed = viewMode === 'embed'
  const participantStorageKey = `delib_anon_id_${conversationId || 'default'}_${sid || 'default'}`
  const participantRef = useRef(
    xid || localStorage.getItem(participantStorageKey) || `${Date.now()}_${Math.random()}`,
  )
  const participantId = participantRef.current
  const emitEmbedEventRef = useRef(null)
  const voteStorageKey = useMemo(
    () => `delib_votes_${conversationId || 'default'}_${participantId}`,
    [conversationId, participantId],
  )
  const votedSet = useMemo(
    () => new Set(votedIds.map((id) => String(id))),
    [votedIds],
  )
  const availableComments = useMemo(
    () => comments.filter((comment) => !votedSet.has(String(comment.id))),
    [comments, votedSet],
  )
  const requestHeaders = useMemo(
    () => ({
      'X-Participant-Id': participantId,
      'X-Invite-Code': inviteCode,
    }),
    [inviteCode, participantId],
  )

  useEffect(() => {
    votedIdsRef.current = votedIds
  }, [votedIds])

  const missingConversationId = !conversationId

  const emitEmbedEvent = useCallback(
    (event, payload = {}) => {
      if (typeof window === 'undefined') return
      if (window.parent && window.parent !== window) {
        window.parent.postMessage(
          {
            type: 'fs_survey_event',
            event,
            conversation_id: conversationId,
            participant_id: participantId,
            ...payload,
          },
          '*',
        )
      }
    },
    [conversationId, participantId],
  )

  useEffect(() => {
    emitEmbedEventRef.current = emitEmbedEvent
  }, [emitEmbedEvent])

  const loadQueue = useCallback(
    async ({ reset = false, extraVotedIds = [] } = {}) => {
      if (!conversationId) return
      setQueueLoading(true)
      setError('')
      try {
        const currentVoted = votedIdsRef.current
        const payload = {
          seen_ids: [],
          voted_ids: [...currentVoted, ...extraVotedIds],
          limit: 50,
        }
        const response = await requestJson(`/conversations/${conversationId}/queue`, {
          method: 'POST',
          payload,
          headers: requestHeaders,
        })
        const items = Array.isArray(response?.items) ? response.items : []
        const votedSetSnapshot = new Set(votedIdsRef.current.map((id) => String(id)))
        const freshItems = items.filter((item) => !votedSetSnapshot.has(String(item.id)))
        setComments((prev) => {
          if (reset) return items
          const existing = new Set(prev.map((comment) => comment.id))
          const merged = [...prev]
          freshItems.forEach((item) => {
            if (!existing.has(item.id)) merged.push(item)
          })
          return merged
        })
        if (reset) setCurrentIndex(0)
      } catch (err) {
        setError(err.message || translate('questionnaire.loadingBody'))
      } finally {
        setQueueLoading(false)
      }
    },
    [conversationId, requestHeaders, translate],
  )

  useEffect(() => {
    if (!conversationId) return
    setLoading(true)
    setError('')
    localStorage.setItem(participantStorageKey, participantId)
    const storedVotes = parseLocalArray(localStorage.getItem(voteStorageKey))
    setVotedIds(storedVotes)
    Promise.all([getJson(`/conversations/${conversationId}`)])
      .then(([convoPayload]) => {
        setConversation(convoPayload)
        setCurrentIndex(0)
        setDragOffset({ x: 0, y: 0 })
        setIsDragging(false)
        setCompletedSent(false)
        loadQueue({ reset: true })
        requestJson(`/conversations/${conversationId}/view`, {
          method: 'POST',
          headers: requestHeaders,
        }).catch(() => null)
      })
      .catch((err) => setError(err.message || 'Unable to load conversation comments.'))
      .finally(() => setLoading(false))
  }, [conversationId, participantId, participantStorageKey, voteStorageKey, loadQueue, requestHeaders])

  useEffect(() => {
    if (!conversationId) return
    localStorage.setItem(voteStorageKey, JSON.stringify(votedIds))
  }, [conversationId, voteStorageKey, votedIds])

  useEffect(() => {
    if (!conversationId) return
    setStatementDiscussionById({})
    setStatementDiscussionDraftById({})
    setStatementDiscussionLoadingById({})
    setStatementDiscussionSavingById({})
    setStatementDiscussionErrorById({})
    setStatementDiscussionReactionBusyById({})
  }, [conversationId])

  const currentComment = availableComments[currentIndex]
  const currentCommentId = currentComment?.id
  const currentText = currentComment?.text || ''
  const currentStatementDiscussion = currentCommentId
    ? statementDiscussionById[currentCommentId] || []
    : []
  const currentStatementDiscussionDraft = currentCommentId
    ? statementDiscussionDraftById[currentCommentId] || ''
    : ''
  const currentStatementDiscussionLoading = currentCommentId
    ? Boolean(statementDiscussionLoadingById[currentCommentId])
    : false
  const currentStatementDiscussionSaving = currentCommentId
    ? Boolean(statementDiscussionSavingById[currentCommentId])
    : false
  const currentStatementDiscussionError = currentCommentId
    ? statementDiscussionErrorById[currentCommentId] || ''
    : ''
  const identityRequired = conversation?.identity_mode === 'xid_required' && !xid
  const votingDisabled =
    (conversation && conversation.allow_voting === false) || identityRequired
  const totalComments = availableComments.length + votedIds.length
  const progressCount = votedIds.length
  const progress = totalComments
    ? Math.min(100, Math.round((progressCount / totalComments) * 100))
    : 0
  const swipeHintThreshold = 40
  const swipeIntent =
    dragOffset.x > swipeHintThreshold
      ? 'agree'
      : dragOffset.x < -swipeHintThreshold
        ? 'disagree'
        : dragOffset.y > swipeHintThreshold
          ? 'pass'
          : ''

  const handleVote = useCallback(
    async (commentId, choice) => {
      if (!commentId || pendingVote || votingDisabled) return
      setPendingVote(true)
      setError('')
      try {
        await requestJson('/vote', {
          method: 'POST',
          payload: {
            conversation_id: conversationId,
            comment_id: commentId,
            choice,
            important: importantFlag,
          },
          headers: requestHeaders,
        })
        setVotedIds((prev) => {
          if (prev.includes(commentId)) return prev
          return [...prev, commentId]
        })
        setCurrentIndex((prev) => prev)
        setImportantFlag(false)
        emitEmbedEventRef.current?.('vote_cast', {
          comment_id: commentId,
          choice,
          important: importantFlag,
        })
        const remainingAfterVote = Math.max(0, availableComments.length - 1)
        if (remainingAfterVote <= 3) {
          loadQueue({ extraVotedIds: [commentId] })
        }
      } catch (err) {
        setError(err.message || translate('questionnaire.voteFailed'))
      } finally {
        setPendingVote(false)
      }
    },
    [
      availableComments.length,
      conversationId,
      importantFlag,
      loadQueue,
      pendingVote,
      requestHeaders,
      translate,
      votingDisabled,
    ],
  )

  const loadStatementDiscussion = useCallback(
    async (statementId) => {
      if (!conversationId || !statementId) return
      setStatementDiscussionLoadingById((prev) => ({ ...prev, [statementId]: true }))
      setStatementDiscussionErrorById((prev) => ({ ...prev, [statementId]: '' }))
      try {
        const payload = await requestJson(
          `/conversations/${conversationId}/statements/${statementId}/discussion-comments`,
          {
            method: 'GET',
            headers: requestHeaders,
          },
        )
        setStatementDiscussionById((prev) => ({
          ...prev,
          [statementId]: Array.isArray(payload) ? payload : [],
        }))
      } catch (err) {
        setStatementDiscussionErrorById((prev) => ({
          ...prev,
          [statementId]: err.message || 'Unable to load statement comments.',
        }))
      } finally {
        setStatementDiscussionLoadingById((prev) => ({ ...prev, [statementId]: false }))
      }
    },
    [conversationId, requestHeaders],
  )

  const handleSubmitStatementDiscussion = async () => {
    if (!conversationId || !currentCommentId) return
    const draft = String(statementDiscussionDraftById[currentCommentId] || '').trim()
    if (!draft) {
      setStatementDiscussionErrorById((prev) => ({
        ...prev,
        [currentCommentId]: 'Comment text is required.',
      }))
      return
    }
    setStatementDiscussionSavingById((prev) => ({ ...prev, [currentCommentId]: true }))
    setStatementDiscussionErrorById((prev) => ({ ...prev, [currentCommentId]: '' }))
    try {
      await requestJson(
        `/conversations/${conversationId}/statements/${currentCommentId}/discussion-comments`,
        {
          method: 'POST',
          payload: { text: draft, author_id: participantId },
          headers: requestHeaders,
        },
      )
      setStatementDiscussionDraftById((prev) => ({ ...prev, [currentCommentId]: '' }))
      await loadStatementDiscussion(currentCommentId)
    } catch (err) {
      setStatementDiscussionErrorById((prev) => ({
        ...prev,
        [currentCommentId]: err.message || 'Unable to post statement comment.',
      }))
    } finally {
      setStatementDiscussionSavingById((prev) => ({ ...prev, [currentCommentId]: false }))
    }
  }

  const handleReactToStatementDiscussionComment = async (discussionCommentId, reaction) => {
    if (!conversationId || !currentCommentId || !discussionCommentId) return
    setStatementDiscussionReactionBusyById((prev) => ({ ...prev, [discussionCommentId]: true }))
    setStatementDiscussionErrorById((prev) => ({ ...prev, [currentCommentId]: '' }))
    try {
      const updated = await requestJson(
        `/conversations/${conversationId}/statements/${currentCommentId}/discussion-comments/${discussionCommentId}/reactions`,
        {
          method: 'POST',
          payload: { reaction, author_id: participantId },
          headers: requestHeaders,
        },
      )
      setStatementDiscussionById((prev) => ({
        ...prev,
        [currentCommentId]: (prev[currentCommentId] || []).map((item) =>
          item.id === discussionCommentId ? { ...item, ...(updated || {}) } : item,
        ),
      }))
    } catch (err) {
      setStatementDiscussionErrorById((prev) => ({
        ...prev,
        [currentCommentId]: err.message || 'Unable to save reaction.',
      }))
    } finally {
      setStatementDiscussionReactionBusyById((prev) => ({ ...prev, [discussionCommentId]: false }))
    }
  }

  useEffect(() => {
    if (!conversationId) return
    emitEmbedEventRef.current?.('view', { invite: inviteCode || null })
  }, [conversationId, inviteCode])

  useEffect(() => {
    if (!availableComments.length) return
    if (currentIndex >= availableComments.length) {
      setCurrentIndex(Math.max(availableComments.length - 1, 0))
    }
  }, [availableComments.length, currentIndex])

  useEffect(() => {
    if (completedSent) return
    if (!currentCommentId && !loading && !queueLoading) {
      emitEmbedEventRef.current?.('completed_all')
      setCompletedSent(true)
    }
  }, [completedSent, currentCommentId, loading, queueLoading])

  const resetDrag = () => {
    setDragOffset({ x: 0, y: 0 })
    setIsDragging(false)
    dragStartRef.current = null
    dragTypeRef.current = null
    dragPointerIdRef.current = null
  }

  useEffect(() => {
    resetDrag()
  }, [currentCommentId])

  useEffect(() => {
    if (!currentCommentId) return
    const handleKeyDown = (event) => {
      if (pendingVote) return
      const target = event.target
      const tagName = String(target?.tagName || '').toLowerCase()
      const isTypingField =
        tagName === 'input' ||
        tagName === 'textarea' ||
        tagName === 'select' ||
        target?.isContentEditable
      if (isTypingField) return
      const key = event.key
      if (key === 'ArrowRight' || key === 'd' || key === 'D') {
        event.preventDefault()
        handleVote(currentCommentId, 1)
      } else if (key === 'ArrowLeft' || key === 'a' || key === 'A') {
        event.preventDefault()
        handleVote(currentCommentId, -1)
      } else if (key === 'ArrowDown' || key === 's' || key === 'S') {
        event.preventDefault()
        handleVote(currentCommentId, 0)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [currentCommentId, handleVote, pendingVote])

  useEffect(() => {
    if (!currentCommentId) return
    if (statementDiscussionById[currentCommentId]) return
    loadStatementDiscussion(currentCommentId)
  }, [currentCommentId, loadStatementDiscussion, statementDiscussionById])

  const beginDrag = useCallback(
    (clientX, clientY, type, pointerId = null) => {
      if (pendingVote || !currentCommentId) return
      dragStartRef.current = { x: clientX, y: clientY }
      dragTypeRef.current = type
      dragPointerIdRef.current = pointerId
      setDragOffset({ x: 0, y: 0 })
      setIsDragging(true)
    },
    [currentCommentId, pendingVote],
  )

  const updateDrag = useCallback((clientX, clientY, type, pointerId = null) => {
    if (!dragStartRef.current || dragTypeRef.current !== type) return
    if (type === 'pointer' && dragPointerIdRef.current !== pointerId) return
    setDragOffset({
      x: clientX - dragStartRef.current.x,
      y: clientY - dragStartRef.current.y,
    })
  }, [])

  const endDrag = useCallback(
    (clientX, clientY, type, pointerId = null) => {
      if (!dragStartRef.current || dragTypeRef.current !== type) return
      if (type === 'pointer' && dragPointerIdRef.current !== pointerId) return
      const start = dragStartRef.current
      const endX = typeof clientX === 'number' ? clientX : start.x + dragOffset.x
      const endY = typeof clientY === 'number' ? clientY : start.y + dragOffset.y
      const x = endX - start.x
      const y = endY - start.y
      const threshold = 70
      const choice = x > threshold ? 1 : x < -threshold ? -1 : y > threshold ? 0 : null
      resetDrag()
      if (choice !== null) handleVote(currentCommentId, choice)
    },
    [currentCommentId, dragOffset.x, dragOffset.y, handleVote],
  )

  const handlePointerDown = (event) => {
    if (votingDisabled) return
    if (event.button !== undefined && event.button !== 0) return
    event.preventDefault()
    beginDrag(event.clientX, event.clientY, 'pointer', event.pointerId)
    try {
      event.currentTarget.setPointerCapture(event.pointerId)
    } catch {
      // Pointer capture isn't supported in all environments.
    }
  }
  const handlePointerMove = (event) => updateDrag(event.clientX, event.clientY, 'pointer', event.pointerId)
  const handlePointerEnd = (event) => endDrag(event?.clientX, event?.clientY, 'pointer', event?.pointerId)

  const handleTouchStart = (event) => {
    if (supportsPointerEvents) return
    if (votingDisabled) return
    const touch = event.touches?.[0]
    if (!touch) return
    event.preventDefault()
    beginDrag(touch.clientX, touch.clientY, 'touch')
  }
  const handleTouchMove = (event) => {
    if (supportsPointerEvents) return
    const touch = event.touches?.[0]
    if (!touch) return
    if (dragTypeRef.current === 'touch') event.preventDefault()
    updateDrag(touch.clientX, touch.clientY, 'touch')
  }
  const handleTouchEnd = (event) => {
    if (supportsPointerEvents) return
    const touch = event.changedTouches?.[0]
    endDrag(touch?.clientX, touch?.clientY, 'touch')
  }

  const handleMouseDown = (event) => {
    if (supportsPointerEvents) return
    if (votingDisabled) return
    if (event.button !== 0) return
    event.preventDefault()
    beginDrag(event.clientX, event.clientY, 'mouse')
  }
  const handleMouseMove = (event) => {
    if (supportsPointerEvents) return
    updateDrag(event.clientX, event.clientY, 'mouse')
  }
  const handleMouseUp = (event) => {
    if (supportsPointerEvents) return
    endDrag(event.clientX, event.clientY, 'mouse')
  }

  useEffect(() => {
    if (supportsPointerEvents) {
      const onMove = (e) => updateDrag(e.clientX, e.clientY, 'pointer', e.pointerId)
      const onEnd = (e) => endDrag(e.clientX, e.clientY, 'pointer', e.pointerId)
      window.addEventListener('pointermove', onMove)
      window.addEventListener('pointerup', onEnd)
      window.addEventListener('pointercancel', onEnd)
      return () => {
        window.removeEventListener('pointermove', onMove)
        window.removeEventListener('pointerup', onEnd)
        window.removeEventListener('pointercancel', onEnd)
      }
    }
    const onMouseMove = (e) => updateDrag(e.clientX, e.clientY, 'mouse')
    const onMouseUp = (e) => endDrag(e.clientX, e.clientY, 'mouse')
    const onTouchMove = (e) => {
      const touch = e.touches?.[0]
      if (!touch) return
      if (dragTypeRef.current === 'touch') e.preventDefault()
      updateDrag(touch.clientX, touch.clientY, 'touch')
    }
    const onTouchEnd = (e) => {
      const touch = e.changedTouches?.[0]
      endDrag(touch?.clientX, touch?.clientY, 'touch')
    }
    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', onMouseUp)
    window.addEventListener('touchmove', onTouchMove, { passive: false })
    window.addEventListener('touchend', onTouchEnd)
    window.addEventListener('touchcancel', onTouchEnd)
    return () => {
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('mouseup', onMouseUp)
      window.removeEventListener('touchmove', onTouchMove)
      window.removeEventListener('touchend', onTouchEnd)
      window.removeEventListener('touchcancel', onTouchEnd)
    }
  }, [endDrag, supportsPointerEvents, updateDrag])

  return (
    <section className={`delib-questionnaire ${isEmbed ? 'delib-questionnaire--embed' : ''}`}>
      {!isEmbed ? (
        <div className="page-language page-language--questionnaire">
          <LanguageSelect
            language={language}
            languages={languages}
            onLanguageChange={onLanguageChange}
            label={translate('language.label')}
          />
        </div>
      ) : null}
      {!isEmbed ? (
        <header className="delib-questionnaire__header">
          <span className="pill">{translate('module.deliberation')}</span>
          <h2>{translate('questionnaire.title')}</h2>
          <p>{translate('questionnaire.subtitle')}</p>
        </header>
      ) : null}
      {missingConversationId ? (
        <div className="module-alert">
          Missing conversation id. Please open a valid participant link.
        </div>
      ) : (
        <>
          {error ? <div className="module-alert">{error}</div> : null}
          <div className="questionnaire-progress">
            <div className="questionnaire-progress__track">
              <div className="questionnaire-progress__bar" style={{ width: `${progress}%` }} />
            </div>
            <span className="questionnaire-progress__label">
              {progressCount}/{totalComments || 0}
            </span>
          </div>
          <div className="questionnaire-deck">
            <div className="questionnaire-card-stack">
              {currentIndex + 1 < totalComments && (
                <div className="questionnaire-card questionnaire-card--back" aria-hidden="true" />
              )}
              {loading || queueLoading ? (
                <div className="questionnaire-card questionnaire-card--empty">
                  <h3>{translate('questionnaire.loadingTitle')}</h3>
                  <p className="muted">{translate('questionnaire.loadingBody')}</p>
                </div>
              ) : currentComment ? (
                <div
                  className={`questionnaire-card ${isDragging ? 'is-dragging' : ''}`}
                  style={{
                    transform: `translate(${dragOffset.x}px, ${dragOffset.y}px) rotate(${dragOffset.x / 18}deg)`,
                  }}
                  onPointerDown={handlePointerDown}
                  onPointerMove={handlePointerMove}
                  onPointerUp={handlePointerEnd}
                  onPointerCancel={handlePointerEnd}
                  onTouchStart={handleTouchStart}
                  onTouchMove={handleTouchMove}
                  onTouchEnd={handleTouchEnd}
                  onTouchCancel={handleTouchEnd}
                  onMouseDown={handleMouseDown}
                  onMouseMove={handleMouseMove}
                  onMouseUp={handleMouseUp}
                  onMouseLeave={handleMouseUp}
                >
                  <div className="questionnaire-card__title">
                    {translate('questionnaire.questionLabel', {
                      current: progressCount + 1,
                      total: totalComments,
                    })}
                  </div>
                  <div className="questionnaire-card__text">{currentText}</div>
                  <div className="questionnaire-card__footer">
                    {translate('questionnaire.footer')}
                  </div>
                  {swipeIntent ? (
                    <div className={`questionnaire-swipe-hint questionnaire-swipe-hint--${swipeIntent}`}>
                      {swipeIntent === 'agree'
                        ? `✅ ${translate('questionnaire.agree')}`
                        : swipeIntent === 'disagree'
                          ? `❌ ${translate('questionnaire.disagree')}`
                          : translate('questionnaire.pass')}
                    </div>
                  ) : null}
                </div>
              ) : (
                <div className="questionnaire-card questionnaire-card--empty">
                  <h3>{translate('questionnaire.doneTitle')}</h3>
                  <p className="muted">{translate('questionnaire.doneBody')}</p>
                </div>
              )}
            </div>
          </div>
          {identityRequired ? (
            <p className="muted">Login is required to vote in this conversation.</p>
          ) : null}
          <div className="questionnaire-importance">
            <label className="checkbox">
              <input
                type="checkbox"
                checked={importantFlag}
                onChange={(event) => setImportantFlag(event.target.checked)}
                disabled={!currentCommentId || pendingVote || votingDisabled}
              />
              This is important to me
            </label>
          </div>
          <div className="questionnaire-controls">
            <button
              className="swipe-button swipe-button--disagree"
              type="button"
              onClick={() => handleVote(currentCommentId, -1)}
              disabled={!currentCommentId || pendingVote || votingDisabled}
            >
              {translate('questionnaire.disagree')}
            </button>
            <button
              className="swipe-button swipe-button--pass"
              type="button"
              onClick={() => handleVote(currentCommentId, 0)}
              disabled={!currentCommentId || pendingVote || votingDisabled}
            >
              {translate('questionnaire.pass')}
            </button>
            <button
              className="swipe-button swipe-button--agree"
              type="button"
              onClick={() => handleVote(currentCommentId, 1)}
              disabled={!currentCommentId || pendingVote || votingDisabled}
            >
              {translate('questionnaire.agree')}
            </button>
          </div>
          {currentCommentId ? (
            <div className="questionnaire-add">
              <div className="card-divider">
                <h4>Comments on this statement</h4>
              </div>
              {currentStatementDiscussionError ? (
                <div className="module-alert">{currentStatementDiscussionError}</div>
              ) : null}
              {currentStatementDiscussionLoading ? (
                <p className="muted">Loading comments...</p>
              ) : currentStatementDiscussion.length === 0 ? (
                <p className="muted">No comments yet for this statement.</p>
              ) : (
                <div className="stack">
                  {currentStatementDiscussion.map((item) => (
                    <div className="module-card" key={item.id}>
                      <p>{item.text}</p>
                      <div className="module-footer">
                        <span className="muted">{item.created_at || 'Live'}</span>
                        <span>
                          <strong>Like</strong> {item.like_count || 0}
                        </span>
                        <span>
                          <strong>Dislike</strong> {item.disagree_count || 0}
                        </span>
                        {item.my_reaction ? (
                          <span>
                            <strong>Your reaction</strong> {item.my_reaction === 'disagree' ? 'dislike' : item.my_reaction}
                          </span>
                        ) : null}
                      </div>
                      <div className="filter-row">
                        <button
                          className="button-secondary button-secondary--small"
                          type="button"
                          onClick={() => handleReactToStatementDiscussionComment(item.id, 'like')}
                          disabled={Boolean(statementDiscussionReactionBusyById[item.id])}
                        >
                          👍 Like
                        </button>
                        <button
                          className="button-secondary button-secondary--small"
                          type="button"
                          onClick={() => handleReactToStatementDiscussionComment(item.id, 'disagree')}
                          disabled={Boolean(statementDiscussionReactionBusyById[item.id])}
                        >
                          👎 Dislike
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              <textarea
                className="textarea"
                value={currentStatementDiscussionDraft}
                onChange={(event) =>
                  setStatementDiscussionDraftById((prev) => ({
                    ...prev,
                    [currentCommentId]: event.target.value,
                  }))
                }
                placeholder="Add your comment on this statement"
              />
              <div className="filter-row">
                <button
                  className="button-secondary"
                  type="button"
                  onClick={() => loadStatementDiscussion(currentCommentId)}
                  disabled={currentStatementDiscussionLoading}
                >
                  {currentStatementDiscussionLoading ? 'Refreshing...' : 'Refresh comments'}
                </button>
                <button
                  className="button"
                  type="button"
                  onClick={handleSubmitStatementDiscussion}
                  disabled={currentStatementDiscussionSaving}
                >
                  {currentStatementDiscussionSaving ? 'Posting...' : 'Post statement comment'}
                </button>
              </div>
            </div>
          ) : null}
        </>
      )}
    </section>
  )
}
