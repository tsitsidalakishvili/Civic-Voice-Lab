const moduleSectionScripts = {
  crm: {
    overview: {
      title: 'Network overview',
      body: 'Start here to read the health of your supporter network: totals, engagement signals, location coverage, and the next actions that need attention.',
      contentBody: 'Use this overview to decide what needs action first before adding people, reviewing records, or building segments.',
    },
    intake: {
      title: 'New supporters',
      body: 'Use this section to add new supporters, import people, and capture the basic profile data that powers segmentation and outreach later.',
      contentBody: 'This is where new supporter data enters the platform. Add people carefully here so later outreach, campaigns, and analytics have clean records.',
    },
    people: {
      title: 'People database',
      body: 'This is the searchable supporter list. Review contact details, engagement history, tags, groups, and individual records before taking action.',
      contentBody: 'Use the people table as the operating database for follow-up, filtering, record review, and relationship history.',
    },
    segments: {
      title: 'Supporter segments',
      body: 'Build practical groups for outreach: volunteers, donors, regional contacts, issue-based audiences, or people ready for campaign actions.',
      contentBody: 'Segments turn raw supporter records into useful audiences for campaign targeting, invitations, and field work.',
    },
  },
  campaigns: {
    campaigns: {
      title: 'Campaign planning',
      body: 'Create campaign plans, track execution, connect budgets and goals, and keep the campaign work tied to measurable outcomes.',
      contentBody: 'Use this workspace to plan the campaign itself: objectives, funding, execution, and progress tracking.',
    },
    outreach: {
      title: 'Outreach actions',
      body: 'Invite people or saved segments into events, campaign actions, and mobilization flows without leaving the campaign workspace.',
      contentBody: 'Outreach connects your campaign plan to people. Choose recipients, prepare actions, and move supporters into real engagement.',
    },
    'audience-overview': {
      title: 'Audience discovery',
      body: 'Run AI-assisted audience research from websites or documents, then use those findings to sharpen campaign targeting.',
      contentBody: 'This is the research step: gather audience intelligence before deciding which groups and messages matter most.',
    },
    'audience-segments': {
      title: 'Audience segments',
      body: 'Review discovered audience groups, compare motivations and barriers, and decide which groups should become campaign targets.',
      contentBody: 'Use segment findings to decide who the campaign should prioritize and why that audience is reachable.',
    },
    'audience-evidence': {
      title: 'Evidence review',
      body: 'Inspect source pages, clusters, and supporting evidence so strategy is grounded in material you can verify.',
      contentBody: 'Evidence keeps the audience analysis auditable. Review the source material before using insights in strategy.',
    },
    'audience-messaging': {
      title: 'Messaging',
      body: 'Turn audience insights into message frames, talking points, and campaign language that fits each target group.',
      contentBody: 'Messaging converts research into usable language for campaign teams, field organizers, and communications.',
    },
  },
  deliberation: {
    overview: {
      title: 'Deliberation overview',
      body: 'Start with the conversation status, participation signals, and what needs attention before inviting people in.',
      contentBody: 'Use the overview to understand the current state of the conversation before changing setup, sharing links, or interpreting results.',
    },
    setup: {
      title: 'Setup',
      body: 'Define the question, statements, and configuration. This is where a raw issue becomes a structured public or internal deliberation.',
      contentBody: 'Setup is the design step. A clear question and strong statements make the rest of the deliberation more useful.',
    },
    distribute: {
      title: 'Share section',
      body: 'Use Share to distribute the questionnaire, copy links, prepare invites, and bring participants into the conversation.',
      contentBody: 'This is the participant acquisition step. Share the right link with the right audience and track how people enter the process.',
    },
    insights: {
      title: 'Insights',
      body: 'Review agreement patterns, clusters, comments, and summaries that help decision makers understand where common ground exists.',
      contentBody: 'Insights turn participation into decision support. Use this section to read patterns, not individual responses in isolation.',
    },
  },
  'due-diligence': {
    overview: {
      title: 'Case setup',
      body: 'Create or edit the person or organization case, including Georgian and English names so local media and international sources both match well.',
      contentBody: 'Start by making the subject profile accurate. Good names and aliases make the scan more reliable across sources.',
    },
    checks: {
      title: 'Run DD scan',
      body: 'Run configured checks across Wikipedia, OpenSanctions, Georgian media, and asset declarations, then store the evidence on the case.',
      contentBody: 'This is the evidence collection step. Run the configured sources, then inspect warnings and hits before using the result.',
    },
    reports: {
      title: 'Reports',
      body: 'Review saved scans, source evidence, AI synthesis, and downloadable PDF reports for decision-ready due diligence output.',
      contentBody: 'Reports turn raw findings into a decision document. Use this area to review evidence, AI synthesis, and PDF output.',
    },
  },
  'data-hub': {
    connectors: {
      title: 'Connectors',
      body: 'Configure and review data sources that feed the platform, including internal datasets and external systems.',
      contentBody: 'Connectors are the source layer. Use them to see what data can flow into the rest of the platform.',
    },
    explorer: {
      title: 'Data explorer',
      body: 'Inspect connected records, check what data is available, and prepare information for analysis or module workflows.',
      contentBody: 'Explorer is for checking data shape and contents before using it in analysis, CRM, campaigns, or reporting.',
    },
  },
}

export const hubWalkthroughScenario = [
  {
    selector: '[data-tour="brand"]',
    title: 'Freedom Square platform',
    body: 'This is the main civic engagement suite. The hub below is the starting point for each workflow.',
    placement: 'bottom',
  },
  {
    selector: '[data-tour="module-hub"]',
    title: 'Module hub',
    body: 'Choose a module based on the job you want to do: manage people, run campaigns, deliberate, research risk, or organize data.',
    placement: 'bottom',
  },
  {
    selector: '[data-tour="module-tile-crm"]',
    title: 'Network module',
    body: 'Start here for supporters: add new people, maintain the database, build segments, and understand engagement.',
    placement: 'top',
  },
  {
    selector: '[data-tour="module-tile-deliberation"]',
    title: 'Deliberation module',
    body: 'Use this for structured conversations: setup, share links, collect input, analyze agreement, and moderate content.',
    placement: 'top',
  },
  {
    selector: '[data-tour="module-tile-due-diligence"]',
    title: 'Due Diligence',
    body: 'Use DD to create a case, scan configured sources, compile an AI-assisted report, and download evidence-backed PDFs.',
    placement: 'top',
  },
  {
    selector: '[data-tour="module-tile-campaigns"]',
    title: 'Campaigns and audience',
    body: 'This combined workspace connects audience discovery, campaign planning, outreach, segments, evidence, and messaging.',
    placement: 'top',
  },
  {
    selector: '[data-tour="module-tile-data-hub"]',
    title: 'Data Hub',
    body: 'Use Data Hub to organize connectors and explore the data layer that supports the rest of the platform.',
    placement: 'top',
  },
  {
    selector: '[data-tour="global-search"]',
    title: 'Search modules',
    body: 'Use search when you already know where you want to go. It keeps navigation fast as more modules become active.',
    placement: 'bottom',
  },
  {
    selector: '[data-tour="language-menu"]',
    title: 'Language switcher',
    body: 'Switch the interface language here. DD cases can still keep both Georgian and English subject names for source matching.',
    placement: 'bottom',
  },
  {
    selector: '[data-tour="about-platform"]',
    title: 'Platform overview',
    body: 'Open this section for a fuller description of how the platform pieces fit together.',
    placement: 'top',
  },
  {
    selector: '[data-tour="feedback"]',
    title: 'Feedback while testing',
    body: 'Use this floating button to record issues, improvement ideas, or questions while you explore.',
    placement: 'left',
  },
]

function sectionSelector(value) {
  return `[data-tour="module-section-${value}"]`
}

export function buildModuleWalkthroughScenario(activeModule, activeModuleConfig) {
  const tabSections = (activeModuleConfig?.sections || []).filter((section) => section.type === 'tab')
  const moduleScript = moduleSectionScripts[activeModule.id] || {}
  const steps = [
    {
      selector: '[data-tour="module-context"]',
      moduleId: activeModule.id,
      title: `${activeModule.label} workspace`,
      body: 'This badge shows where you are. Use Back to return to the module hub whenever you need to switch work areas.',
      placement: 'bottom',
    },
    {
      selector: '[data-tour="module-sidebar"]',
      moduleId: activeModule.id,
      title: 'Workflow map',
      body: activeModuleConfig?.flowSummary || 'The left side explains the workflow and keeps navigation close while you work.',
      placement: 'right',
    },
  ]

  tabSections.forEach((section, index) => {
    const script = moduleScript[section.value] || {}
    const title = script.title || section.label
    steps.push({
      selector: sectionSelector(section.value),
      moduleId: activeModule.id,
      sectionValue: section.value,
      title: `${index + 1}. ${title}`,
      body: script.body || section.hint || 'This section contains the main actions and records for this part of the workflow.',
      placement: 'right',
    })
    steps.push({
      selector: '[data-tour="module-content"]',
      moduleId: activeModule.id,
      sectionValue: section.value,
      title: `${title}: working area`,
      body: script.contentBody || 'The main panel now shows this section. Complete the forms, review the tables, or run the actions here before moving to the next step.',
      placement: 'top',
    })
  })

  steps.push(
    {
      selector: '[data-tour="global-search"]',
      moduleId: activeModule.id,
      title: 'Fast module search',
      body: 'Open search to jump directly to another module when you already know where you want to go.',
      placement: 'bottom',
    },
    {
      selector: '[data-tour="feedback"]',
      moduleId: activeModule.id,
      title: 'Leave implementation notes',
      body: 'Use this button to capture feedback while testing. It includes the active module so notes stay contextual.',
      placement: 'left',
    },
  )

  return steps
}


export function buildModuleSectionWalkthroughScenario(activeModule, activeModuleConfig, section) {
  const script = moduleSectionScripts[activeModule.id]?.[section.value] || {}
  const title = script.title || section.label

  return [
    {
      selector: '[data-tour="module-context"]',
      moduleId: activeModule.id,
      title: `${activeModule.label}: ${title}`,
      body: section.hint || script.body || 'This flow opens the right module and section so you can perform this part of the workflow.',
      placement: 'bottom',
    },
    {
      selector: sectionSelector(section.value),
      moduleId: activeModule.id,
      sectionValue: section.value,
      title,
      body: script.body || section.hint || 'This section contains the main actions and records for this part of the workflow.',
      placement: 'right',
    },
    {
      selector: '[data-tour="module-content"]',
      moduleId: activeModule.id,
      sectionValue: section.value,
      title: `${title}: working area`,
      body: script.contentBody || 'Use the main panel to complete the forms, review the tables, or run the actions for this workflow.',
      placement: 'top',
    },
  ]
}
export const taskWalkthroughScenarios = {
  'create-segment': {
    label: 'Create a segment',
    steps: [
      {
        moduleId: 'crm',
        sectionValue: 'segments',
        selector: '[data-tour="module-section-segments"]',
        title: 'Open Network segments',
        body: 'Start in Network > Segments. This workflow creates a reusable audience group from supporter records.',
        placement: 'right',
      },
      {
        moduleId: 'crm',
        sectionValue: 'segments',
        selector: '[data-tour="network-segment-builder"]',
        title: 'Segment workspace',
        body: 'Use this area to pick an existing segment, inspect its size and filters, or open the new-segment form.',
        placement: 'top',
      },
      {
        moduleId: 'crm',
        sectionValue: 'segments',
        selector: '[data-tour="network-segment-form"]',
        title: 'Define the audience',
        body: 'Name the segment, choose filters like group, availability, age, location, tags, skills, and then save it for campaigns and surveys.',
        placement: 'top',
      },
    ],
  },
  'create-conversation': {
    label: 'Create conversation and statements',
    steps: [
      {
        moduleId: 'deliberation',
        sectionValue: 'setup',
        selector: '[data-tour="module-section-setup"]',
        title: 'Open survey setup',
        body: 'Start in Survey & Consensus > Setup. This is where a conversation becomes a structured survey.',
        placement: 'right',
      },
      {
        moduleId: 'deliberation',
        sectionValue: 'setup',
        selector: '[data-tour="survey-setup-mode"]',
        title: 'Choose new or existing',
        body: 'Use these controls to create a new conversation or edit an existing one. For a new survey, keep the new conversation mode selected.',
        placement: 'bottom',
      },
      {
        moduleId: 'deliberation',
        sectionValue: 'setup',
        selector: '[data-tour="survey-create-conversation"]',
        title: 'Create the survey',
        body: 'Enter the topic and basic rules. The topic should be clear enough for participants to understand what decision or issue they are responding to.',
        placement: 'top',
      },
      {
        moduleId: 'deliberation',
        sectionValue: 'setup',
        selector: '[data-tour="survey-statements"]',
        title: 'Add voting statements',
        body: 'Statements become participant voting cards. Add enough clear statements to reveal agreement, disagreement, and useful clusters.',
        placement: 'top',
      },
    ],
  },
  'distribute-survey': {
    label: 'Distribute survey',
    steps: [
      {
        moduleId: 'deliberation',
        sectionValue: 'distribute',
        selector: '[data-tour="module-section-distribute"]',
        title: 'Open Share',
        body: 'Use Survey & Consensus > Share to choose the audience and distribute the participant link.',
        placement: 'right',
      },
      {
        moduleId: 'deliberation',
        sectionValue: 'distribute',
        selector: '[data-tour="survey-segment-builder"]',
        title: 'Choose or create an audience',
        body: 'Select an existing Network segment or open the segment builder to define the group that should receive the survey.',
        placement: 'top',
      },
      {
        moduleId: 'deliberation',
        sectionValue: 'distribute',
        selector: '[data-tour="survey-segment-form"]',
        title: 'Optional segment builder',
        body: 'When you need a new audience, use this builder to save a segment directly from the Share workflow.',
        placement: 'top',
      },
      {
        moduleId: 'deliberation',
        sectionValue: 'distribute',
        selector: '[data-tour="survey-send-link"]',
        title: 'Send link',
        body: 'This is the distribution card. Choose email, WhatsApp, Slack, or QR depending on how participants should receive the survey.',
        placement: 'top',
      },
      {
        moduleId: 'deliberation',
        sectionValue: 'distribute',
        selector: '[data-tour="survey-invite-form"]',
        title: 'Prepare the invite',
        body: 'Choose single recipient, everyone, verified users, or registered users, then send or copy the link using the action buttons.',
        placement: 'top',
      },
    ],
  },
  'analyze-results': {
    label: 'Collect and analyze results',
    steps: [
      {
        moduleId: 'deliberation',
        sectionValue: 'distribute',
        selector: '[data-tour="survey-send-link"]',
        title: 'Collect responses',
        body: 'Responses start with distribution. Keep sharing the participant link until the conversation has enough input to analyze.',
        placement: 'top',
      },
      {
        moduleId: 'deliberation',
        sectionValue: 'insights',
        selector: '[data-tour="module-section-insights"]',
        title: 'Open Insights',
        body: 'After responses arrive, move to Insights to read agreement patterns, clusters, comments, and generated summaries.',
        placement: 'right',
      },
      {
        moduleId: 'deliberation',
        sectionValue: 'insights',
        selector: '[data-tour="survey-results-analysis"]',
        title: 'Analyze results',
        body: 'Use this area to refresh analysis, inspect clusters, compare signals, and turn participation into decision support.',
        placement: 'top',
      },
    ],
  },
  'survey-lifecycle': {
    label: 'Full survey lifecycle',
    steps: [
      {
        moduleId: 'deliberation',
        sectionValue: 'setup',
        selector: '[data-tour="survey-create-conversation"]',
        title: '1. Create the conversation',
        body: 'Begin with a clear topic and basic rules in Setup.',
        placement: 'top',
      },
      {
        moduleId: 'deliberation',
        sectionValue: 'setup',
        selector: '[data-tour="survey-statements"]',
        title: '2. Add statements',
        body: 'Write statements participants can vote on. These drive the analysis later.',
        placement: 'top',
      },
      {
        moduleId: 'deliberation',
        sectionValue: 'distribute',
        selector: '[data-tour="survey-segment-builder"]',
        title: '3. Choose the audience',
        body: 'Select or create a segment before sending the survey.',
        placement: 'top',
      },
      {
        moduleId: 'deliberation',
        sectionValue: 'distribute',
        selector: '[data-tour="survey-send-link"]',
        title: '4. Send the link',
        body: 'Distribute the survey by email, WhatsApp, Slack, QR, or copied link.',
        placement: 'top',
      },
      {
        moduleId: 'deliberation',
        sectionValue: 'insights',
        selector: '[data-tour="survey-results-analysis"]',
        title: '5. Analyze results',
        body: 'Use Insights to understand patterns, clusters, comments, and decision-ready summaries.',
        placement: 'top',
      },
    ],
  },
}
export const taskWalkthroughPlacements = {
  'create-segment': { moduleId: 'crm', sectionValue: 'segments' },
  'create-conversation': { moduleId: 'deliberation', sectionValue: 'setup' },
  'distribute-survey': { moduleId: 'deliberation', sectionValue: 'distribute' },
  'analyze-results': { moduleId: 'deliberation', sectionValue: 'insights' },
  'survey-lifecycle': { moduleId: 'deliberation', sectionValue: 'overview' },
}

export function getSectionTaskScenarios(moduleId, sectionValue) {
  return Object.entries(taskWalkthroughScenarios)
    .filter(([key]) => {
      const placement = taskWalkthroughPlacements[key]
      return placement?.moduleId === moduleId && placement?.sectionValue === sectionValue
    })
    .map(([key, scenario]) => ({ key, ...scenario }))
}
