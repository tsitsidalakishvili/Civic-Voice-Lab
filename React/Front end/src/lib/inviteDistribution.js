/** Shared helpers for Network / Survey & Consensus “distribution” invite flows. */

/** Bcc count cap for mailto: URLs (long lists hit browser limits; rest via clipboard). */
export const MAILTO_SEGMENT_BCC_LIMIT = 25

export function openExternalShareLink(url) {
  if (!url || typeof window === 'undefined') return
  const popup = window.open(url, '_blank', 'noopener,noreferrer')
  if (!popup) {
    window.location.href = url
  }
}

export function getInviteAudienceLabel(audience) {
  if (audience === 'everyone') return 'Everyone'
  if (audience === 'segment') return 'Selected segment'
  if (audience === 'verified') return 'Verified users'
  if (audience === 'registered') return 'Registered users'
  return 'Single recipient'
}

export function getInviteAudienceGroupEmail(audience, groupsConfig = {}) {
  if (audience === 'everyone') return String(groupsConfig.everyoneGroupEmail || '').trim()
  if (audience === 'segment') return ''
  if (audience === 'verified') return String(groupsConfig.verifiedGroupEmail || '').trim()
  if (audience === 'registered') return String(groupsConfig.registeredGroupEmail || '').trim()
  return ''
}
