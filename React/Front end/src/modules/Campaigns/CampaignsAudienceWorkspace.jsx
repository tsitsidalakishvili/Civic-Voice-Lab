import { useMemo } from 'react'
import { CRMPage } from '../CRM/CRMPage.jsx'
import { AudienceDiscoveryPage } from '../AudienceDiscovery/AudienceDiscoveryPage.jsx'

const AUDIENCE_TAB_MAP = {
  audience: 'overview',
  'audience-overview': 'overview',
  'audience-segments': 'segments',
  'audience-evidence': 'evidence',
  'audience-messaging': 'messaging',
}

const CAMPAIGN_TABS = new Set(['campaigns', 'outreach'])

export function CampaignsAudienceWorkspace({
  t,
  language,
  activeTabOverride,
  onTabChange,
  showTabs = false,
  showIntro = false,
}) {
  const activeArea = useMemo(() => {
    const tab = activeTabOverride || 'campaigns'
    if (AUDIENCE_TAB_MAP[tab]) return 'audience'
    return 'campaigns'
  }, [activeTabOverride])

  if (activeArea === 'audience') {
    const activeView = AUDIENCE_TAB_MAP[activeTabOverride || 'audience'] || 'overview'
    return (
      <AudienceDiscoveryPage
        t={t}
        language={language}
        activeViewOverride={activeView}
        onViewChange={(view) => onTabChange?.(`audience-${view}`)}
        showTabs={showTabs}
        showIntro={showIntro}
      />
    )
  }

  const activeCampaignTab = CAMPAIGN_TABS.has(activeTabOverride) ? activeTabOverride : 'campaigns'
  return (
    <CRMPage
      t={t}
      language={language}
      initialTab={activeCampaignTab}
      activeTabOverride={activeCampaignTab}
      onTabChange={onTabChange}
      hideTabs
      showTabs={showTabs}
      showIntro={showIntro}
    />
  )
}
