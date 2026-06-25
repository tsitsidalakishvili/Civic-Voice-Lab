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
    {
      id: 'crm',
      label: t('module.network'),
      description: t('module.network.desc'),
      Component: CRMPage,
      // No status = Ready/Active
    },
    // Unfinished modules keep status: 'In Progress' and are shown but not clickable
    {
      id: 'deliberation',
      label: t('module.deliberation'),
      description: t('module.deliberation.desc'),
      Component: DeliberationPage,
    },
    {
      id: 'campaigns',
      label: 'Campaigns & Audience',
      description: 'Discover audiences, plan campaigns, coordinate outreach, and track results.',
      Component: CampaignsAudienceWorkspace,
    },
    {
      id: 'due-diligence',
      label: t('module.dueDiligence'),
      description: t('module.dueDiligence.desc'),
      Component: DueDiligencePage,
    },
    {
      id: 'data-hub',
      label: t('module.dataHub'),
      description: t('module.dataHub.desc'),
      status: 'In Progress',
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
      { label: t('nav.crm.people'), type: 'tab', value: 'people', hint: t('nav.crm.peopleHint') },
      { label: t('nav.crm.segments'), type: 'tab', value: 'segments', hint: t('nav.crm.segmentsHint') },
    ],
  },
  campaigns: {
    title: 'Campaigns & Audience',
    description: 'One workspace for audience intelligence, campaign planning, outreach, and results.',
    flowTitle: 'Discover, plan, mobilize',
    flowSummary: 'Use audience discovery to shape campaign strategy, then move directly into outreach and campaign execution.',
    defaultTab: 'campaigns',
    sections: [
      { label: 'Campaigns', type: 'tab', value: 'campaigns', hint: 'Plan, fund, execute, and monitor campaigns.' },
      { label: 'Outreach', type: 'tab', value: 'outreach', hint: 'Invite people or saved segments into events and actions.' },
      { label: 'Audience discovery', type: 'tab', value: 'audience-overview', hint: 'Run AI-assisted audience analysis from websites or documents.' },
      { label: 'Segments', type: 'tab', value: 'audience-segments', hint: 'Review audience segments and choose targets for campaigns.' },
      { label: 'Evidence', type: 'tab', value: 'audience-evidence', hint: 'Inspect source pages, clusters, and supporting evidence.' },
      { label: 'Messaging', type: 'tab', value: 'audience-messaging', hint: 'Turn audience insights into campaign messages.' },
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
      { label: t('nav.deliberation.moderation'), type: 'tab', value: 'moderation', hint: t('nav.deliberation.moderationHint') },
    ],
  },
  'due-diligence': {
    title: t('module.dueDiligence'),
    description: t('module.dueDiligence.desc'),
    flowTitle: t('nav.dd.flowTitle'),
    flowSummary: t('nav.dd.flowSummary'),
    defaultTab: 'overview',
    sections: [
      { label: 'Case', type: 'tab', value: 'overview', hint: 'Create or edit the due diligence case.' },
      { label: 'Run DD', type: 'tab', value: 'checks', hint: 'Run Wikipedia, OpenSanctions, and configured Georgian media sources.' },
      { label: 'Report', type: 'tab', value: 'reports', hint: 'Review saved evidence, AI synthesis, and PDF reports.' },
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

