import {
  IconBulb,
  IconChartDots,
  IconLayoutGrid,
  IconMessage2,
  IconSettings,
  IconShieldCheck,
  IconSpeakerphone,
  IconUsers,
} from '@tabler/icons-react'
import {
  AdminPage,
  CampaignsAudienceWorkspace,
  CRMPage,
  DataHubPage,
  DeliberationPage,
  DueDiligencePage,
  HowItWorksPage,
  PublicCampaignPage,
} from '../modules'

export const MODULE_ICON_MAP = {
  'how-it-works': IconBulb,
  crm: IconUsers,
  campaigns: IconSpeakerphone,
  deliberation: IconMessage2,
  'due-diligence': IconShieldCheck,
  'data-hub': IconChartDots,
  admin: IconSettings,
}

export const renderModuleIcon = (moduleId, size = 18) => {
  const Icon = MODULE_ICON_MAP[moduleId] || IconLayoutGrid
  return <Icon size={size} />
}

// All modules shown; Network and Survey/Consensus are active
export const HUB_MODULE_IDS = [
  'crm',
  'campaigns',
  'deliberation',
  'due-diligence',
  'data-hub',
]

// All modules shown; Network and Survey/Consensus are active (others show "In Progress")
export const buildModules = (t) => {
  return [
    {
      id: 'how-it-works',
      label: t('module.howItWorks'),
      description: t('module.howItWorks.desc'),
      status: 'In Progress',
      Component: HowItWorksPage,
    },
    // `task` is the plain-language action shown on the home screen; `label` stays
    // the product name so existing users still recognise where they landed.
    {
      id: 'crm',
      label: t('module.network'),
      task: t('task.crm'),
      description: t('module.network.desc'),
      Component: CRMPage,
      // No status = Ready/Active
    },
    // Unfinished modules keep status: 'In Progress' and are shown but not clickable
    {
      id: 'deliberation',
      label: t('module.deliberation'),
      task: t('task.deliberation'),
      description: t('module.deliberation.desc'),
      Component: DeliberationPage,
    },
    {
      id: 'campaigns',
      label: 'Campaigns & Audience',
      task: t('task.campaigns'),
      description: 'Match campaigns, issues, and causes to the messengers who can amplify them, with reach projections.',
      Component: CampaignsAudienceWorkspace,
    },
    {
      id: 'due-diligence',
      label: t('module.dueDiligence'),
      task: t('task.dueDiligence'),
      description: t('module.dueDiligence.desc'),
      Component: DueDiligencePage,
    },
    {
      id: 'data-hub',
      label: t('module.dataHub'),
      task: t('task.dataHub'),
      description: t('module.dataHub.desc'),
      Component: DataHubPage,
    },
    {
      id: 'admin',
      label: t('module.settings'),
      description: t('module.settings.desc'),
      status: 'In Progress',
      Component: AdminPage,
    },
  ]
}

export const buildModuleSections = (t) => ({
  crm: {
    title: t('module.network'),
    description: t('module.network.desc'),
    flowTitle: t('nav.crm.flowTitle'),
    flowSummary: t('nav.crm.flowSummary'),
    defaultTab: 'overview',
    sections: [
      { label: t('nav.crm.overview'), type: 'tab', value: 'overview', hint: t('nav.crm.overviewHint') },
      { label: t('nav.crm.intake'), type: 'tab', value: 'intake', hint: t('nav.crm.intakeHint') },
      { label: 'People & Segments', type: 'tab', value: 'people', hint: 'Find people, edit records, and create reusable audience segments.' },
    ],
  },
  campaigns: {
    title: 'Campaigns & Audience',
    description: 'Match campaigns, issues, and causes to the messengers who can amplify them, with reach projections.',
    flowTitle: 'Analyze, match, project',
    flowSummary: 'Enter a campaign, issue, or cause, get ranked messenger matches, then project reach and engagement before you mobilize.',
    defaultTab: 'match',
    sections: [
      { label: 'Match', type: 'tab', value: 'match', hint: 'Enter a campaign, issue, or cause and get ranked messenger matches with reach projections.' },
      { label: 'Roster', type: 'tab', value: 'roster', hint: 'Browse, search, import, and export your messenger roster.' },
    ],
  },
  deliberation: {
    title: t('module.deliberation'),
    description: t('module.deliberation.desc'),
    flowTitle: t('nav.deliberation.flowTitle'),
    flowSummary: t('nav.deliberation.flowSummary'),
    defaultTab: 'overview',
    sections: [
      { label: t('nav.deliberation.overview'), type: 'tab', value: 'overview', hint: t('nav.deliberation.overviewHint') },
      { label: t('nav.deliberation.setup'), type: 'tab', value: 'setup', hint: t('nav.deliberation.setupHint') },
      { label: t('nav.deliberation.share'), type: 'tab', value: 'distribute', hint: t('nav.deliberation.shareHint') },
      { label: t('nav.deliberation.insights'), type: 'tab', value: 'insights', hint: t('nav.deliberation.insightsHint') },
    ],
  },
    'due-diligence': {
      title: t('module.dueDiligence'),
      description: t('module.dueDiligence.desc'),
      flowTitle: t('dd.flowTitle'),
      flowSummary: t('dd.flowSummary'),
      // Land on the screen that can actually start work. The previous default,
      // 'sources', dropped every user into stage one of the expert workflow.
      defaultTab: 'overview',
      sections: [
        { label: t('nav.dd.start'), type: 'tab', value: 'overview', hint: t('nav.dd.startHint') },
        { label: t('nav.dd.evidence'), type: 'tab', value: 'checks', hint: t('nav.dd.evidenceHint') },
        { label: t('nav.dd.report'), type: 'tab', value: 'graph', hint: t('nav.dd.reportHint') },
        { label: t('nav.dd.decision'), type: 'tab', value: 'decision', hint: t('nav.dd.decisionHint') },
        { label: t('nav.dd.history'), type: 'tab', value: 'reports', hint: t('nav.dd.historyHint') },
        { label: t('nav.dd.media'), type: 'tab', value: 'sources', hint: t('nav.dd.mediaHint') },
        { label: t('nav.dd.advanced'), type: 'tab', value: 'advanced', hint: t('nav.dd.advancedHint') },
      ],
    },
  'data-hub': {
    title: t('module.dataHub'),
    description: t('module.dataHub.desc'),
    flowTitle: t('nav.dataHub.flowTitle'),
    flowSummary: t('nav.dataHub.flowSummary'),
    defaultTab: 'connectors',
    sections: [
      { label: t('nav.dataHub.connectors'), type: 'tab', value: 'connectors', hint: t('nav.dataHub.connectorsHint') },
      { label: t('nav.dataHub.explorer'), type: 'tab', value: 'explorer', hint: t('nav.dataHub.explorerHint') },
    ],
  },
  'how-it-works': {
    title: t('module.howItWorks'),
    description: t('module.howItWorks.desc'),
    flowTitle: t('nav.how.flowTitle'),
    flowSummary: t('nav.how.flowSummary'),
    sections: [
      { label: t('nav.how.overview'), type: 'anchor', value: 'how-overview', hint: t('nav.how.overviewHint') },
      { label: t('nav.how.modules'), type: 'anchor', value: 'how-modules', hint: t('nav.how.modulesHint') },
      { label: t('nav.how.faq'), type: 'anchor', value: 'how-faq', hint: t('nav.how.faqHint') },
    ],
  },
  admin: {
    title: t('module.settings'),
    description: t('module.settings.desc'),
    flowTitle: t('nav.admin.flowTitle'),
    flowSummary: t('nav.admin.flowSummary'),
    defaultTab: 'admin',
    sections: [
      { label: t('nav.admin.operations'), type: 'tab', value: 'admin', hint: t('nav.admin.operationsHint') },
      { label: t('nav.admin.data'), type: 'tab', value: 'data', hint: t('nav.admin.dataHint') },
    ],
  },
})

export const MODULE_SECTIONS = buildModuleSections((k) => k)

