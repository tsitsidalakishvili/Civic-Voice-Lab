/** Shared helpers for Network / Survey & Consensus “distribution” invite flows. */

export function openExternalShareLink(url) {
  if (!url || typeof window === 'undefined') return
  const popup = window.open(url, '_blank', 'noopener,noreferrer')
  if (!popup) {
    window.location.href = url
  }
}

export function getInviteAudienceLabel(audience) {
  if (audience === 'everyone') return 'Everyone'
  if (audience === 'verified') return 'Verified users'
  if (audience === 'registered') return 'Registered users'
  return 'Single recipient'
}

export function getInviteAudienceGroupEmail(audience, groupsConfig = {}) {
  if (audience === 'everyone') return String(groupsConfig.everyoneGroupEmail || '').trim()
  if (audience === 'verified') return String(groupsConfig.verifiedGroupEmail || '').trim()
  if (audience === 'registered') return String(groupsConfig.registeredGroupEmail || '').trim()
  return ''
}
