import {
  IconBulb,
  IconChartDots,
  IconLayoutGrid,
  IconMessage2,
  IconSettings,
  IconShieldCheck,
  IconSpeakerphone,
  IconTarget,
  IconUsers,
} from '@tabler/icons-react'
import {
  AdminPage,
  AudienceDiscoveryPage,
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
  'audience-discovery': IconTarget,
  'data-hub': IconChartDots,
  admin: IconSettings,
}

export const renderModuleIcon = (moduleId, size = 18) => {
  const Icon = MODULE_ICON_MAP[moduleId] || IconLayoutGrid
  return <Icon size={size} />
}

export const HUB_MODULE_IDS = [
  'crm',
  'campaigns',
  'deliberation',
  'due-diligence',
  'audience-discovery',
  'data-hub',
]

export const buildModules = (t) => {
  const CampaignsModule = (props) => (
    <CRMPage {...props} initialTab="campaigns" hideTabs />
  )
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
    },
    {
      id: 'deliberation',
      label: t('module.deliberation'),
      description: t('module.deliberation.desc'),
      Component: DeliberationPage,
    },
    {
      id: 'campaigns',
      label: t('module.campaigns'),
      description: t('module.campaigns.desc'),
      status: 'In Progress',
      Component: CampaignsModule,
    },
    {
      id: 'due-diligence',
      label: t('module.dueDiligence'),
      description: t('module.dueDiligence.desc'),
      status: 'In Progress',
      Component: DueDiligencePage,
    },
    {
      id: 'audience-discovery',
      label: t('module.audienceDiscovery'),
      description: t('module.audienceDiscovery.desc'),
      status: 'In Progress',
      Component: AudienceDiscoveryPage,
    },
    {
      id: 'data-hub',
      label: t('module.dataHub'),
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

export const MODULE_SECTIONS = {
  crm: {
    title: 'Network',
    description: 'Manage supporters, outreach, events, and coverage.',
    flowTitle: 'Build the network',
    flowSummary: 'Build, engage, and mobilize in one place.',
    defaultTab: 'overview',
    primaryActions: [
      { label: 'People directory', type: 'tab', value: 'people', hint: 'Search and update people.' },
      { label: 'Outreach & events', type: 'tab', value: 'outreach', hint: 'Segments and messaging.' },
    ],
    sections: [
      { label: 'Overview', type: 'tab', value: 'overview', hint: 'Map, filters, and coverage charts.' },
      { label: 'People directory', type: 'tab', value: 'people', hint: 'Profiles and segments.' },
      { label: 'Outreach & events', type: 'tab', value: 'outreach', hint: 'Segments, messaging, and events.' },
    ],
  },
  campaigns: {
    title: 'Campaigns',
    description: 'Plan campaigns, launch surveys, and track outcomes.',
    flowTitle: 'Plan',
    flowSummary: 'Plan campaigns, launch surveys, and track outcomes.',
    defaultTab: 'campaigns',
    primaryActions: [
      { label: 'Create campaign', type: 'anchor', value: 'campaigns-create' },
      { label: 'View campaigns', type: 'anchor', value: 'campaigns-list' },
    ],
    sections: [
      { label: 'Overview', type: 'anchor', value: 'campaigns-overview' },
      { label: 'Create', type: 'anchor', value: 'campaigns-create' },
      { label: 'Campaigns', type: 'anchor', value: 'campaigns-list' },
    ],
  },
  deliberation: {
    title: 'Survey & Consensus',
    description: 'Launch surveys, collect votes, and surface consensus.',
    flowTitle: 'Listen to your supporters',
    flowSummary: 'Set up a conversation, share the link, and review insights.',
    defaultTab: 'overview',
    primaryActions: [
      { label: 'Set up', type: 'tab', value: 'setup', hint: 'Create a conversation.' },
      { label: 'Share', type: 'tab', value: 'distribute', hint: 'Share the link.' },
      { label: 'Insights', type: 'tab', value: 'insights', hint: 'Review results.' },
    ],
    sections: [
      { label: 'Overview', type: 'tab', value: 'overview', hint: 'Quick start and active conversation.' },
      { label: 'Set up', type: 'tab', value: 'setup', hint: 'Create and configure.' },
      { label: 'Share', type: 'tab', value: 'distribute', hint: 'Send the link out.' },
      { label: 'Insights', type: 'tab', value: 'insights', hint: 'Consensus analytics.' },
      { label: 'Moderate', type: 'tab', value: 'moderation', hint: 'Review comments.' },
    ],
  },
  'due-diligence': {
    title: 'Due Diligence',
    description: 'Investigate subjects and manage watchlists.',
    flowTitle: 'Investigate',
    flowSummary: 'Assess risk, evidence, and watchlists in one flow.',
    defaultTab: 'overview',
    primaryActions: [
      { label: 'Overview', type: 'tab', value: 'overview', hint: 'Pipeline summary.' },
      { label: 'Checks', type: 'tab', value: 'checks', hint: 'Run screenings.' },
      { label: 'Reports', type: 'tab', value: 'reports', hint: 'Review outputs.' },
    ],
    sections: [
      { label: 'Overview', type: 'tab', value: 'overview', hint: 'Cases and risk pulse.' },
      { label: 'Checks', type: 'tab', value: 'checks', hint: 'Run screenings.' },
      { label: 'Reports', type: 'tab', value: 'reports', hint: 'Review outputs.' },
      { label: 'Tasks', type: 'tab', value: 'tasks', hint: 'Assignment workflow.' },
      { label: 'Decision', type: 'tab', value: 'decision', hint: 'Finalize outcome.' },
      { label: 'Advanced tools', type: 'tab', value: 'advanced', hint: 'Deep research.' },
    ],
  },
  'audience-discovery': {
    title: 'Audience Discovery',
    description: 'Turn product pages into segments with evidence.',
    flowTitle: 'Discover',
    flowSummary: 'Turn product pages into segments with evidence.',
    defaultTab: 'overview',
    primaryActions: [
      { label: 'Start run', type: 'tab', value: 'overview', hint: 'Add sources and run.' },
      { label: 'Review segments', type: 'tab', value: 'segments', hint: 'Verify key segments.' },
      { label: 'Messaging', type: 'tab', value: 'messaging', hint: 'Messaging ideas.' },
    ],
    sections: [
      { label: 'Overview', type: 'tab', value: 'overview', hint: 'Add sources and run.' },
      { label: 'Segments', type: 'tab', value: 'segments', hint: 'Review and verify.' },
      { label: 'Evidence', type: 'tab', value: 'evidence', hint: 'Inspect sources and themes.' },
      { label: 'Messaging', type: 'tab', value: 'messaging', hint: 'Headlines and CTAs.' },
    ],
  },
  'data-hub': {
    title: 'Data Hub',
    description: 'Upload module CSVs into Neo4j and inspect the shared graph.',
    flowTitle: 'Upload CSVs into Neo4j',
    flowSummary: 'Use Data Hub as the single CSV intake gate for every module, then inspect the graph.',
    defaultTab: 'connectors',
    primaryActions: [
      { label: 'Data connectors', type: 'tab', value: 'connectors', hint: 'CSV intake by module.' },
      { label: 'Graph explorer', type: 'tab', value: 'explorer', hint: 'Neo4j DBMS explorer.' },
    ],
    sections: [
      { label: 'Data connectors', type: 'tab', value: 'connectors', hint: 'CSV intake by module.' },
      { label: 'Graph explorer', type: 'tab', value: 'explorer', hint: 'Graph, labels, nodes, and relationships.' },
    ],
  },
  'how-it-works': {
    title: 'How it works',
    description: 'Understand the platform, modules, and trust model.',
    flowTitle: 'Learn the platform flow',
    flowSummary: 'Start with the overview, then review modules and FAQs.',
    primaryActions: [
      { label: 'Overview', type: 'anchor', value: 'how-overview', hint: 'Platform pulse.' },
      { label: 'Modules', type: 'anchor', value: 'how-modules', hint: 'Module walkthroughs.' },
      { label: 'FAQ', type: 'anchor', value: 'how-faq', hint: 'Common questions.' },
    ],
    sections: [
      { label: 'Overview', type: 'anchor', value: 'how-overview', hint: 'Platform pulse.' },
      { label: 'Modules', type: 'anchor', value: 'how-modules', hint: 'Module walkthroughs.' },
      { label: 'FAQ', type: 'anchor', value: 'how-faq', hint: 'Common questions.' },
    ],
  },
  admin: {
    title: 'Settings',
    description: 'Manage operations, approvals, and data health.',
    flowTitle: 'Operate the platform',
    flowSummary: 'Monitor system readiness and manage data workflows.',
    defaultTab: 'admin',
    primaryActions: [
      { label: 'Operations', type: 'tab', value: 'admin', hint: 'Queues and system status.' },
      { label: 'Data quality', type: 'tab', value: 'data', hint: 'Exports and health.' },
    ],
    sections: [
      { label: 'Operations', type: 'tab', value: 'admin', hint: 'Queues and system status.' },
      { label: 'Data quality', type: 'tab', value: 'data', hint: 'Exports and health.' },
    ],
  },
}
