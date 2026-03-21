import { useMemo, useState } from 'react'
import { Accordion, Timeline } from '@mantine/core'
import { IconChartDots, IconTarget, IconUsers } from '@tabler/icons-react'
import { CivicStatGrid } from '../../ui'

export function HowItWorksPage({ t }) {
  const translate = t || ((key) => key)
  const [activeTile, setActiveTile] = useState('network')
  const [expandedTile, setExpandedTile] = useState('')
  const vennCounts = {
    aOnly: 1,
    bOnly: 3,
    cOnly: 2,
    abOnly: 2,
    acOnly: 0,
    bcOnly: 0,
    abc: 0,
  }

  const makeClusterPoints = (count, cx, cy, clusterId) => {
    const points = []
    for (let i = 0; i < count; i += 1) {
      const angle = (i / count) * Math.PI * 2
      const radius = 0.4 + (i % 5) * 0.05
      points.push({
        x: cx + Math.cos(angle) * radius,
        y: cy + Math.sin(angle) * radius,
        clusterId,
      })
    }
    return points
  }

  const samplePoints = [
    ...makeClusterPoints(22, -0.6, 0.2, 'cluster-0'),
    ...makeClusterPoints(20, 0.5, 0.1, 'cluster-1'),
    ...makeClusterPoints(18, 0.1, -0.6, 'cluster-2'),
  ]

  const clusterColor = (clusterId) => {
    const idx = Number(String(clusterId).replace(/\D/g, '') || 1)
    return `hsl(${(idx * 57) % 360} 70% 45%)`
  }

  const tiles = [
    {
      id: 'network',
      title: translate('module.network'),
      pill: 'Build',
      desc: (
        <>
          <strong>Build the network.</strong> {translate('module.network.desc')}
        </>
      ),
      detailIntro:
        'Capture people, volunteers, tasks, and events so outreach is coordinated from a single hub.',
      details: [
        {
          title: 'Inputs',
          items: [
            'People and supporters',
            'Volunteers and skills',
            'Events and attendance',
            'Tasks and follow-ups',
            'Furry friends directory',
          ],
        },
        {
          title: 'Actions',
          items: [
            'Segment and filter groups',
            'Assign owners and tasks',
            'Track outreach activity',
            'Plan events and attendance',
          ],
        },
        {
          title: 'Outputs',
          items: [
            'Network dashboard',
            'Map coverage and clusters',
            'Engagement insights',
            'Exportable lists',
          ],
        },
        {
          title: 'Data flow',
          items: [
            'CSV import and edits',
            'Aura DB sync',
            'Live filters and counts',
          ],
        },
      ],
      flow: (
        <svg viewBox="0 0 720 160" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <marker
              id="arrow-network"
              markerWidth="8"
              markerHeight="8"
              refX="6"
              refY="3"
              orient="auto"
            >
              <path d="M0,0 L6,3 L0,6 Z" fill="#64748B" />
            </marker>
          </defs>
          <rect x="20" y="44" width="120" height="44" rx="10" fill="#E0F2FE" stroke="#7DD3FC" />
          <rect x="160" y="44" width="120" height="44" rx="10" fill="#E0F2FE" stroke="#7DD3FC" />
          <rect x="300" y="44" width="120" height="44" rx="10" fill="#E0F2FE" stroke="#7DD3FC" />
          <rect x="440" y="44" width="120" height="44" rx="10" fill="#FFF7ED" stroke="#FDBA74" />
          <rect x="580" y="44" width="120" height="44" rx="10" fill="#ECFDF3" stroke="#86EFAC" />
          <line x1="140" y1="66" x2="160" y2="66" stroke="#64748B" strokeWidth="2" markerEnd="url(#arrow-network)" />
          <line x1="280" y1="66" x2="300" y2="66" stroke="#64748B" strokeWidth="2" markerEnd="url(#arrow-network)" />
          <line x1="420" y1="66" x2="440" y2="66" stroke="#64748B" strokeWidth="2" markerEnd="url(#arrow-network)" />
          <line x1="560" y1="66" x2="580" y2="66" stroke="#64748B" strokeWidth="2" markerEnd="url(#arrow-network)" />
          <text x="80" y="62" fontSize="9" textAnchor="middle" fill="#1E3A8A">
            <tspan x="80" dy="-2">Data</tspan>
            <tspan x="80" dy="12">entry</tspan>
          </text>
          <text x="220" y="62" fontSize="9" textAnchor="middle" fill="#1E3A8A">
            <tspan x="220" dy="-2">People</tspan>
            <tspan x="220" dy="12">&amp; Volunteers</tspan>
          </text>
          <text x="360" y="62" fontSize="9" textAnchor="middle" fill="#1E3A8A">
            <tspan x="360" dy="-2">Outreach</tspan>
            <tspan x="360" dy="12">&amp; Events</tspan>
          </text>
          <text x="500" y="62" fontSize="9" textAnchor="middle" fill="#9A3412">
            <tspan x="500" dy="-2">Tasks</tspan>
            <tspan x="500" dy="12">&amp; Follow-up</tspan>
          </text>
          <text x="640" y="62" fontSize="9" textAnchor="middle" fill="#166534">
            <tspan x="640" dy="-2">Dashboard</tspan>
            <tspan x="640" dy="12">&amp; Map</tspan>
          </text>
        </svg>
      ),
      diagram: (
        <div className="how-tile__diagram how-tile__diagram--double">
          <svg viewBox="0 0 160 120" xmlns="http://www.w3.org/2000/svg">
            <rect x="10" y="18" width="50" height="28" rx="6" fill="#E0F2FE" stroke="#7DD3FC" />
            <rect x="70" y="18" width="50" height="28" rx="6" fill="#E0F2FE" stroke="#7DD3FC" />
            <rect x="120" y="18" width="30" height="28" rx="6" fill="#E0F2FE" stroke="#7DD3FC" />
            <line x1="60" y1="32" x2="70" y2="32" stroke="#64748B" strokeWidth="2" />
            <line x1="120" y1="32" x2="120" y2="32" stroke="#64748B" strokeWidth="2" />
            <text x="35" y="36" fontSize="9" textAnchor="middle" fill="#1E3A8A">
              People
            </text>
            <text x="95" y="36" fontSize="9" textAnchor="middle" fill="#1E3A8A">
              Tasks
            </text>
            <text x="135" y="36" fontSize="9" textAnchor="middle" fill="#1E3A8A">
              Out
            </text>
            <rect x="30" y="64" width="100" height="32" rx="8" fill="#ECFDF3" stroke="#86EFAC" />
            <text x="80" y="84" fontSize="9" textAnchor="middle" fill="#166534">
              Engagement
            </text>
          </svg>
          <svg viewBox="0 0 160 120" xmlns="http://www.w3.org/2000/svg">
            <rect x="14" y="18" width="60" height="28" rx="6" fill="#E0F2FE" stroke="#7DD3FC" />
            <rect x="86" y="18" width="60" height="28" rx="6" fill="#E0F2FE" stroke="#7DD3FC" />
            <line x1="74" y1="32" x2="86" y2="32" stroke="#64748B" strokeWidth="2" />
            <text x="44" y="36" fontSize="9" textAnchor="middle" fill="#1E3A8A">
              Events
            </text>
            <text x="116" y="36" fontSize="9" textAnchor="middle" fill="#1E3A8A">
              Map
            </text>
            <rect x="30" y="64" width="100" height="32" rx="8" fill="#FFF7ED" stroke="#FDBA74" />
            <text x="80" y="84" fontSize="9" textAnchor="middle" fill="#9A3412">
              Coverage
            </text>
          </svg>
        </div>
      ),
    },
    {
      id: 'campaigns',
      title: translate('module.campaigns'),
      pill: 'Plan',
      desc: translate('module.campaigns.desc'),
      detailIntro:
        'Turn topics into statements, launch surveys, and convert insights into tasks.',
      details: [
        {
          title: 'Inputs',
          items: [
            'Topic and legislation',
            'Manifesto statements',
            'Expert prompts',
            'Target audiences',
          ],
        },
        {
          title: 'Actions',
          items: [
            'Generate statements',
            'Launch survey flow',
            'Moderate feedback',
            'Assign tasks',
          ],
        },
        {
          title: 'Outputs',
          items: [
            'Final statements',
            'Consensus insights',
            'Action plan',
            'Campaign tasks',
          ],
        },
        {
          title: 'Signals',
          items: [
            'Votes and comments',
            'Polarization scores',
            'Top agreements',
          ],
        },
      ],
      flow: (
        <svg viewBox="0 0 720 160" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <marker
              id="arrow-campaigns"
              markerWidth="8"
              markerHeight="8"
              refX="6"
              refY="3"
              orient="auto"
            >
              <path d="M0,0 L6,3 L0,6 Z" fill="#64748B" />
            </marker>
          </defs>
          <rect x="20" y="44" width="120" height="44" rx="10" fill="#F5F3FF" stroke="#C4B5FD" />
          <rect x="160" y="44" width="120" height="44" rx="10" fill="#F5F3FF" stroke="#C4B5FD" />
          <rect x="300" y="44" width="120" height="44" rx="10" fill="#FFF7ED" stroke="#FDBA74" />
          <rect x="440" y="44" width="120" height="44" rx="10" fill="#E0F2FE" stroke="#7DD3FC" />
          <rect x="580" y="44" width="120" height="44" rx="10" fill="#ECFDF3" stroke="#86EFAC" />
          <line x1="140" y1="66" x2="160" y2="66" stroke="#64748B" strokeWidth="2" markerEnd="url(#arrow-campaigns)" />
          <line x1="280" y1="66" x2="300" y2="66" stroke="#64748B" strokeWidth="2" markerEnd="url(#arrow-campaigns)" />
          <line x1="420" y1="66" x2="440" y2="66" stroke="#64748B" strokeWidth="2" markerEnd="url(#arrow-campaigns)" />
          <line x1="560" y1="66" x2="580" y2="66" stroke="#64748B" strokeWidth="2" markerEnd="url(#arrow-campaigns)" />
          <text x="80" y="62" fontSize="9" textAnchor="middle" fill="#6D28D9">
            <tspan x="80" dy="-2">Inputs</tspan>
            <tspan x="80" dy="12">setup</tspan>
          </text>
          <text x="220" y="62" fontSize="9" textAnchor="middle" fill="#6D28D9">
            <tspan x="220" dy="-2">Analysis</tspan>
            <tspan x="220" dy="12">engine</tspan>
          </text>
          <text x="360" y="62" fontSize="9" textAnchor="middle" fill="#9A3412">
            <tspan x="360" dy="-2">Statements</tspan>
            <tspan x="360" dy="12">draft</tspan>
          </text>
          <text x="500" y="62" fontSize="9" textAnchor="middle" fill="#1E3A8A">
            <tspan x="500" dy="-2">Survey</tspan>
            <tspan x="500" dy="12">launch</tspan>
          </text>
          <text x="640" y="62" fontSize="9" textAnchor="middle" fill="#166534">
            <tspan x="640" dy="-2">Actions</tspan>
            <tspan x="640" dy="12">&amp; tasks</tspan>
          </text>
        </svg>
      ),
      diagram: (
        <div className="how-tile__diagram how-tile__diagram--double">
          <svg viewBox="0 0 160 120" xmlns="http://www.w3.org/2000/svg">
            <rect x="18" y="18" width="50" height="28" rx="6" fill="#F5F3FF" stroke="#C4B5FD" />
            <rect x="92" y="18" width="50" height="28" rx="6" fill="#F5F3FF" stroke="#C4B5FD" />
            <line x1="68" y1="32" x2="92" y2="32" stroke="#64748B" strokeWidth="2" />
            <text x="43" y="36" fontSize="9" textAnchor="middle" fill="#6D28D9">
              Inputs
            </text>
            <text x="117" y="36" fontSize="9" textAnchor="middle" fill="#6D28D9">
              Analysis
            </text>
            <rect x="30" y="64" width="100" height="32" rx="8" fill="#FFF7ED" stroke="#FDBA74" />
            <text x="80" y="84" fontSize="9" textAnchor="middle" fill="#9A3412">
              Statements
            </text>
          </svg>
          <svg viewBox="0 0 160 120" xmlns="http://www.w3.org/2000/svg">
            <rect x="18" y="18" width="50" height="28" rx="6" fill="#F5F3FF" stroke="#C4B5FD" />
            <rect x="92" y="18" width="50" height="28" rx="6" fill="#F5F3FF" stroke="#C4B5FD" />
            <line x1="68" y1="32" x2="92" y2="32" stroke="#64748B" strokeWidth="2" />
            <text x="43" y="36" fontSize="9" textAnchor="middle" fill="#6D28D9">
              Survey
            </text>
            <text x="117" y="36" fontSize="9" textAnchor="middle" fill="#6D28D9">
              Tasks
            </text>
            <rect x="30" y="64" width="100" height="32" rx="8" fill="#ECFDF3" stroke="#86EFAC" />
            <text x="80" y="84" fontSize="9" textAnchor="middle" fill="#166534">
              Actions
            </text>
          </svg>
        </div>
      ),
    },
    {
      id: 'survey',
      title: translate('module.deliberation'),
      pill: 'Listen to your supporters',
      desc: translate('module.deliberation.desc'),
      detailIntro:
        'Survey and Consensus is a deliberation process: run surveys in supporters and members, engage them, collect comments, gather votes, and review analytics.',
      details: [
        {
          title: 'Inputs',
          items: [
            'Statements to test',
            'Participant groups',
            'Moderation settings',
            'Optional seed prompts',
          ],
        },
        {
          title: 'Actions',
          items: [
            'Collect votes',
            'Capture comments',
            'Cluster participants',
            'Score consensus',
          ],
        },
        {
          title: 'Outputs',
          items: [
            'Survey report',
            'Top consensus',
            'Top polarization',
            'Cluster summaries',
          ],
        },
        {
          title: 'Signals',
          items: [
            'Agree / disagree',
            'Comment reactions',
            'Participation rate',
          ],
        },
      ],
      flow: (
        <svg viewBox="0 0 720 160" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <marker
              id="arrow-survey"
              markerWidth="8"
              markerHeight="8"
              refX="6"
              refY="3"
              orient="auto"
            >
              <path d="M0,0 L6,3 L0,6 Z" fill="#64748B" />
            </marker>
          </defs>
          <rect x="20" y="44" width="120" height="44" rx="10" fill="#E0F2FE" stroke="#7DD3FC" />
          <rect x="160" y="44" width="120" height="44" rx="10" fill="#E0F2FE" stroke="#7DD3FC" />
          <rect x="300" y="44" width="120" height="44" rx="10" fill="#FFF7ED" stroke="#FDBA74" />
          <rect x="440" y="44" width="120" height="44" rx="10" fill="#F5F3FF" stroke="#C4B5FD" />
          <rect x="580" y="44" width="120" height="44" rx="10" fill="#ECFDF3" stroke="#86EFAC" />
          <line x1="140" y1="66" x2="160" y2="66" stroke="#64748B" strokeWidth="2" markerEnd="url(#arrow-survey)" />
          <line x1="280" y1="66" x2="300" y2="66" stroke="#64748B" strokeWidth="2" markerEnd="url(#arrow-survey)" />
          <line x1="420" y1="66" x2="440" y2="66" stroke="#64748B" strokeWidth="2" markerEnd="url(#arrow-survey)" />
          <line x1="560" y1="66" x2="580" y2="66" stroke="#64748B" strokeWidth="2" markerEnd="url(#arrow-survey)" />
          <text x="80" y="62" fontSize="9" textAnchor="middle" fill="#1E3A8A">
            <tspan x="80" dy="-2">Statements</tspan>
            <tspan x="80" dy="12">ready</tspan>
          </text>
          <text x="220" y="62" fontSize="9" textAnchor="middle" fill="#1E3A8A">
            <tspan x="220" dy="-2">Participants</tspan>
            <tspan x="220" dy="12">join</tspan>
          </text>
          <text x="360" y="62" fontSize="9" textAnchor="middle" fill="#9A3412">
            <tspan x="360" dy="-2">Votes</tspan>
            <tspan x="360" dy="12">&amp; comments</tspan>
          </text>
          <text x="500" y="62" fontSize="9" textAnchor="middle" fill="#6D28D9">
            <tspan x="500" dy="-2">Clusters</tspan>
            <tspan x="500" dy="12">model</tspan>
          </text>
          <text x="640" y="62" fontSize="9" textAnchor="middle" fill="#166534">
            <tspan x="640" dy="-2">Report</tspan>
            <tspan x="640" dy="12">&amp; insights</tspan>
          </text>
        </svg>
      ),
      diagram: (
        <div className="how-tile__diagram how-tile__diagram--double">
          <svg viewBox="0 0 160 120" xmlns="http://www.w3.org/2000/svg">
            <rect x="4" y="4" width="152" height="112" rx="10" fill="#F8FAFC" stroke="#E2E8F0" />
            <circle cx="60" cy="60" r="32" fill={clusterColor('cluster-0')} opacity="0.35" />
            <circle cx="100" cy="60" r="32" fill={clusterColor('cluster-1')} opacity="0.35" />
            <text x="60" y="60" textAnchor="middle" fontSize="10" fill="#0F172A">
              {vennCounts.aOnly}
            </text>
            <text x="100" y="60" textAnchor="middle" fontSize="10" fill="#0F172A">
              {vennCounts.bOnly}
            </text>
            <text x="80" y="60" textAnchor="middle" fontSize="10" fill="#0F172A">
              {vennCounts.abOnly}
            </text>
          </svg>
          <svg viewBox="0 0 160 120" xmlns="http://www.w3.org/2000/svg">
            <rect x="4" y="4" width="152" height="112" rx="10" fill="#F8FAFC" stroke="#E2E8F0" />
            {samplePoints.slice(0, 22).map((point, idx) => {
              const x = 80 + point.x * 50
              const y = 60 - point.y * 50
              return (
                <circle
                  key={`${point.clusterId}-${idx}`}
                  cx={x}
                  cy={y}
                  r="2.6"
                  fill={clusterColor(point.clusterId)}
                  opacity="0.85"
                />
              )
            })}
          </svg>
        </div>
      ),
    },
    {
      id: 'due',
      title: translate('module.dueDiligence'),
      pill: 'Investigate',
      desc: translate('module.dueDiligence.desc'),
      detailIntro:
        'Investigate people or organizations, manage watchlists, assess risk, and prepare for debates.',
      details: [
        {
          title: 'Inputs',
          items: [
            'Subject profile',
            'Source selection',
            'Time range',
            'Watchlist flags',
          ],
        },
        {
          title: 'Actions',
          items: [
            'Enrich with sources',
            'Analyze connections',
            'Generate summaries',
            'Prepare debate flow',
          ],
        },
        {
          title: 'Outputs',
          items: [
            'Risk overview',
            'Evidence cards',
            'Exportable report',
            'Watchlist record',
          ],
        },
        {
          title: 'Evidence',
          items: [
            'Wikidata and sanctions',
            'News signals',
            'Source citations',
          ],
        },
      ],
      flow: (
        <svg viewBox="0 0 720 160" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <marker
              id="arrow-due"
              markerWidth="8"
              markerHeight="8"
              refX="6"
              refY="3"
              orient="auto"
            >
              <path d="M0,0 L6,3 L0,6 Z" fill="#64748B" />
            </marker>
          </defs>
          <rect x="20" y="44" width="120" height="44" rx="10" fill="#FFF7ED" stroke="#FDBA74" />
          <rect x="160" y="44" width="120" height="44" rx="10" fill="#FFF7ED" stroke="#FDBA74" />
          <rect x="300" y="44" width="120" height="44" rx="10" fill="#F8FAFC" stroke="#CBD5E1" />
          <rect x="440" y="44" width="120" height="44" rx="10" fill="#E0F2FE" stroke="#7DD3FC" />
          <rect x="580" y="44" width="120" height="44" rx="10" fill="#ECFDF3" stroke="#86EFAC" />
          <line x1="140" y1="66" x2="160" y2="66" stroke="#64748B" strokeWidth="2" markerEnd="url(#arrow-due)" />
          <line x1="280" y1="66" x2="300" y2="66" stroke="#64748B" strokeWidth="2" markerEnd="url(#arrow-due)" />
          <line x1="420" y1="66" x2="440" y2="66" stroke="#64748B" strokeWidth="2" markerEnd="url(#arrow-due)" />
          <line x1="560" y1="66" x2="580" y2="66" stroke="#64748B" strokeWidth="2" markerEnd="url(#arrow-due)" />
          <text x="80" y="62" fontSize="9" textAnchor="middle" fill="#9A3412">
            <tspan x="80" dy="-2">Subject</tspan>
            <tspan x="80" dy="12">intake</tspan>
          </text>
          <text x="220" y="62" fontSize="9" textAnchor="middle" fill="#9A3412">
            <tspan x="220" dy="-2">Enrich</tspan>
            <tspan x="220" dy="12">sources</tspan>
          </text>
          <text x="360" y="62" fontSize="9" textAnchor="middle" fill="#334155">
            <tspan x="360" dy="-2">Evidence</tspan>
            <tspan x="360" dy="12">graph</tspan>
          </text>
          <text x="500" y="62" fontSize="9" textAnchor="middle" fill="#1E3A8A">
            <tspan x="500" dy="-2">Analysis</tspan>
            <tspan x="500" dy="12">&amp; debate</tspan>
          </text>
          <text x="640" y="62" fontSize="9" textAnchor="middle" fill="#166534">
            <tspan x="640" dy="-2">Report</tspan>
            <tspan x="640" dy="12">&amp; watchlist</tspan>
          </text>
        </svg>
      ),
      diagram: (
        <div className="how-tile__diagram how-tile__diagram--double">
          <svg viewBox="0 0 160 120" xmlns="http://www.w3.org/2000/svg">
            <rect x="14" y="18" width="50" height="28" rx="6" fill="#FFF7ED" stroke="#FDBA74" />
            <rect x="96" y="18" width="50" height="28" rx="6" fill="#FFF7ED" stroke="#FDBA74" />
            <line x1="64" y1="32" x2="96" y2="32" stroke="#64748B" strokeWidth="2" />
            <text x="39" y="36" fontSize="9" textAnchor="middle" fill="#9A3412">
              Intake
            </text>
            <text x="121" y="36" fontSize="9" textAnchor="middle" fill="#9A3412">
              Enrich
            </text>
            <rect x="30" y="64" width="100" height="32" rx="8" fill="#F8FAFC" stroke="#CBD5E1" />
            <text x="80" y="84" fontSize="9" textAnchor="middle" fill="#334155">
              Evidence
            </text>
          </svg>
          <svg viewBox="0 0 160 120" xmlns="http://www.w3.org/2000/svg">
            <rect x="14" y="18" width="50" height="28" rx="6" fill="#FFF7ED" stroke="#FDBA74" />
            <rect x="96" y="18" width="50" height="28" rx="6" fill="#FFF7ED" stroke="#FDBA74" />
            <line x1="64" y1="32" x2="96" y2="32" stroke="#64748B" strokeWidth="2" />
            <text x="39" y="36" fontSize="9" textAnchor="middle" fill="#9A3412">
              Risk
            </text>
            <text x="121" y="36" fontSize="9" textAnchor="middle" fill="#9A3412">
              Report
            </text>
            <rect x="30" y="64" width="100" height="32" rx="8" fill="#ECFDF3" stroke="#86EFAC" />
            <text x="80" y="84" fontSize="9" textAnchor="middle" fill="#166534">
              Watchlist
            </text>
          </svg>
        </div>
      ),
    },
    {
      id: 'audience-discovery',
      title: translate('module.audienceDiscovery'),
      pill: 'Discover',
      desc: translate('module.audienceDiscovery.desc'),
      detailIntro:
        'Extract cited evidence from product pages, build audience segments, and draft tailored messaging.',
      details: [
        {
          title: 'Inputs',
          items: [
            'Product pages and docs',
            'Brand positioning',
            'Competitor references',
            'Target geography',
          ],
        },
        {
          title: 'Actions',
          items: [
            'Clean and chunk content',
            'Extract claims and citations',
            'Cluster audience signals',
            'Draft messaging hooks',
          ],
        },
        {
          title: 'Outputs',
          items: [
            'Audience segments',
            'Cited evidence',
            'Messaging angles',
            'Exportable briefs',
          ],
        },
        {
          title: 'Signals',
          items: [
            'Citation coverage',
            'Segment density',
            'Top claims',
            'Sentiment cues',
          ],
        },
      ],
      flow: (
        <svg viewBox="0 0 720 160" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <marker
              id="arrow-audience"
              markerWidth="8"
              markerHeight="8"
              refX="6"
              refY="3"
              orient="auto"
            >
              <path d="M0,0 L6,3 L0,6 Z" fill="#64748B" />
            </marker>
          </defs>
          <rect x="20" y="44" width="120" height="44" rx="10" fill="#F1F5F9" stroke="#CBD5E1" />
          <rect x="160" y="44" width="120" height="44" rx="10" fill="#E0F2FE" stroke="#7DD3FC" />
          <rect x="300" y="44" width="120" height="44" rx="10" fill="#F5F3FF" stroke="#C4B5FD" />
          <rect x="440" y="44" width="120" height="44" rx="10" fill="#FFF7ED" stroke="#FDBA74" />
          <rect x="580" y="44" width="120" height="44" rx="10" fill="#ECFDF3" stroke="#86EFAC" />
          <line x1="140" y1="66" x2="160" y2="66" stroke="#64748B" strokeWidth="2" markerEnd="url(#arrow-audience)" />
          <line x1="280" y1="66" x2="300" y2="66" stroke="#64748B" strokeWidth="2" markerEnd="url(#arrow-audience)" />
          <line x1="420" y1="66" x2="440" y2="66" stroke="#64748B" strokeWidth="2" markerEnd="url(#arrow-audience)" />
          <line x1="560" y1="66" x2="580" y2="66" stroke="#64748B" strokeWidth="2" markerEnd="url(#arrow-audience)" />
          <text x="80" y="62" fontSize="9" textAnchor="middle" fill="#334155">
            <tspan x="80" dy="-2">Pages</tspan>
            <tspan x="80" dy="12">ingest</tspan>
          </text>
          <text x="220" y="62" fontSize="9" textAnchor="middle" fill="#1E3A8A">
            <tspan x="220" dy="-2">Clean</tspan>
            <tspan x="220" dy="12">&amp; chunk</tspan>
          </text>
          <text x="360" y="62" fontSize="9" textAnchor="middle" fill="#6D28D9">
            <tspan x="360" dy="-2">Claims</tspan>
            <tspan x="360" dy="12">&amp; evidence</tspan>
          </text>
          <text x="500" y="62" fontSize="9" textAnchor="middle" fill="#9A3412">
            <tspan x="500" dy="-2">Segments</tspan>
            <tspan x="500" dy="12">cluster</tspan>
          </text>
          <text x="640" y="62" fontSize="9" textAnchor="middle" fill="#166534">
            <tspan x="640" dy="-2">Messaging</tspan>
            <tspan x="640" dy="12">briefs</tspan>
          </text>
        </svg>
      ),
      diagram: (
        <div className="how-tile__diagram how-tile__diagram--double">
          <svg viewBox="0 0 160 120" xmlns="http://www.w3.org/2000/svg">
            <rect x="18" y="10" width="60" height="92" rx="8" fill="#F8FAFC" stroke="#CBD5E1" />
            <line x1="28" y1="28" x2="66" y2="28" stroke="#94A3B8" strokeWidth="2" />
            <line x1="28" y1="40" x2="66" y2="40" stroke="#94A3B8" strokeWidth="2" />
            <line x1="28" y1="52" x2="66" y2="52" stroke="#94A3B8" strokeWidth="2" />
            <rect x="92" y="20" width="50" height="18" rx="6" fill="#E0F2FE" stroke="#7DD3FC" />
            <rect x="92" y="50" width="50" height="18" rx="6" fill="#F5F3FF" stroke="#C4B5FD" />
            <rect x="92" y="80" width="50" height="18" rx="6" fill="#ECFDF3" stroke="#86EFAC" />
            <text x="117" y="33" fontSize="9" textAnchor="middle" fill="#1E3A8A">
              Claims
            </text>
            <text x="117" y="63" fontSize="9" textAnchor="middle" fill="#6D28D9">
              Evidence
            </text>
            <text x="117" y="93" fontSize="9" textAnchor="middle" fill="#166534">
              Hooks
            </text>
          </svg>
          <svg viewBox="0 0 160 120" xmlns="http://www.w3.org/2000/svg">
            <rect x="4" y="4" width="152" height="112" rx="10" fill="#F8FAFC" stroke="#E2E8F0" />
            {samplePoints.slice(0, 26).map((point, idx) => {
              const x = 80 + point.x * 50
              const y = 58 - point.y * 46
              return (
                <circle
                  key={`${point.clusterId}-${idx}`}
                  cx={x}
                  cy={y}
                  r="2.4"
                  fill={clusterColor(point.clusterId)}
                  opacity="0.85"
                />
              )
            })}
            <rect x="16" y="84" width="40" height="18" rx="6" fill="#E0F2FE" stroke="#7DD3FC" />
            <rect x="60" y="84" width="40" height="18" rx="6" fill="#F5F3FF" stroke="#C4B5FD" />
            <rect x="104" y="84" width="40" height="18" rx="6" fill="#FFF7ED" stroke="#FDBA74" />
            <text x="36" y="96" fontSize="8" textAnchor="middle" fill="#1E3A8A">
              Segment A
            </text>
            <text x="80" y="96" fontSize="8" textAnchor="middle" fill="#6D28D9">
              Segment B
            </text>
            <text x="124" y="96" fontSize="8" textAnchor="middle" fill="#9A3412">
              Segment C
            </text>
          </svg>
        </div>
      ),
    },
  ]

  const renderTileContent = (tile, { expanded = false } = {}) => (
    <>
      <div className="how-tile__header">
        <h4 className="how-tile__title">{tile.title}</h4>
        <span className="pill">{tile.pill}</span>
      </div>
      <p className="muted how-tile__desc">{tile.desc}</p>
      {expanded && tile.detailIntro ? (
        <p className="how-tile__detail-intro">{tile.detailIntro}</p>
      ) : null}
      {expanded && tile.details ? (
        <div className="how-tile__details">
          <div className="how-tile__details-grid">
            {tile.details.map((section) => (
              <div key={section.title} className="how-tile__details-card">
                <h5>{section.title}</h5>
                <ul>
                  {section.items.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
          {tile.flow ? <div className="how-tile__flow">{tile.flow}</div> : null}
        </div>
      ) : null}
      {tile.diagram}
    </>
  )

  const howPulse = useMemo(
    () => [
      {
        label: 'Modules',
        value: tiles.length,
        icon: <IconTarget size={18} />,
        badge: 'Civic',
      },
      {
        label: 'Decision tracks',
        value: 4,
        icon: <IconChartDots size={18} />,
        note: 'Network, Campaigns, Surveys, Data',
      },
      {
        label: 'Community',
        value: 'Always-on',
        icon: <IconUsers size={18} />,
        note: 'Participation loop',
      },
      {
        label: 'Insights',
        value: 'Real-time',
        icon: <IconChartDots size={18} />,
        note: 'Consensus signals',
      },
    ],
    [tiles.length],
  )

  return (
    <section className="module">
      <CivicStatGrid
        title="Platform pulse"
        description="A civic operating system built for trust, speed, and transparency."
        items={howPulse}
      />
      <Timeline active={1} color="civic" bulletSize={26} lineWidth={2} mb="md">
        <Timeline.Item title="Listen">
          Capture community input and surface lived experience signals.
        </Timeline.Item>
        <Timeline.Item title="Align">
          Build consensus and prioritize the actions that matter.
        </Timeline.Item>
        <Timeline.Item title="Mobilize">
          Activate supporters with clear tasks, events, and campaigns.
        </Timeline.Item>
      </Timeline>
      <div className="module-grid">
        <div className="module-card module-card__wide how-hero">
          <h3>What this platform does</h3>
          <p className="muted">
            One connected workspace to manage your network, run campaigns, measure
            consensus, and investigate risk.
          </p>
        </div>

        <div className="module-card module-card__wide">
          <h3>How each module works</h3>
          <div className="how-tile-grid">
            {tiles.map((tile) => (
              <button
                key={tile.id}
                className={`how-tile ${activeTile === tile.id ? 'how-tile--active' : ''}`}
                type="button"
                onClick={() => {
                  setActiveTile(tile.id)
                  setExpandedTile(tile.id)
                }}
              >
                {renderTileContent(tile)}
              </button>
            ))}
          </div>
        </div>
      </div>
      <Accordion variant="separated" radius="lg">
        <Accordion.Item value="trust">
          <Accordion.Control>How does this build trust?</Accordion.Control>
          <Accordion.Panel>
            Every action is tied to evidence, visible progress, and clear accountability.
          </Accordion.Panel>
        </Accordion.Item>
        <Accordion.Item value="speed">
          <Accordion.Control>How do teams move faster?</Accordion.Control>
          <Accordion.Panel>
            Shared dashboards remove context switching and turn insights into tasks quickly.
          </Accordion.Panel>
        </Accordion.Item>
        <Accordion.Item value="public">
          <Accordion.Control>What is public vs internal?</Accordion.Control>
          <Accordion.Panel>
            Public views are tailored for campaigns and events, while internal views manage operations.
          </Accordion.Panel>
        </Accordion.Item>
      </Accordion>
      {expandedTile ? (
        <div
          className="how-tile-modal"
          role="dialog"
          aria-modal="true"
          onClick={() => setExpandedTile('')}
        >
          <div className="how-tile-modal__card" onClick={(event) => event.stopPropagation()}>
            <button
              className="button-secondary how-tile-modal__close"
              type="button"
              onClick={() => setExpandedTile('')}
            >
              Close
            </button>
            <div className="how-tile how-tile--expanded">
              {renderTileContent(tiles.find((tile) => tile.id === expandedTile) || tiles[0], {
                expanded: true,
              })}
            </div>
          </div>
        </div>
      ) : null}
    </section>
  )
}
