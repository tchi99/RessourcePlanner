export type Job = {
  id: number | null
  name: string
  status: string | null
  conclusion: string | null
  url: string | null
  started_at?: string | null
  completed_at?: string | null
}

export type Run = {
  id: number
  name: string
  status: string
  conclusion: string | null
  url: string | null
  run_number: number | null
  created_at: string | null
  updated_at: string | null
  jobs: Job[]
}

export type PullRequest = {
  number: number
  title: string
  body: string
  state: string
  merged: boolean
  draft: boolean
  mergeable: boolean | null
  mergeable_state: string | null
  url: string
  head: string
  head_sha: string
  base: string
  updated_at: string
  merged_at: string | null
  runs: Run[]
}

export type RoadmapItem = {
  key: string
  title: string
  done: boolean
  marker: string | null
  issue_number: number | null
}

export type Issue = {
  number: number
  title: string
  state: string
  url: string
  updated_at: string
}

export type Branch = {
  name: string
  sha: string | null
  url: string
}

export type Commit = {
  sha: string
  short_sha: string
  message: string
  date: string
  url: string
}

export type StalledDetails = {
  level: 'confirmed' | 'stalled' | 'possible' | null
  threshold_minutes: number
  ci_failed_at: string | null
  ci_failed_minutes: number | null
  last_commit_at: string | null
  last_commit_minutes: number | null
  last_activity_at: string | null
  last_activity_minutes: number | null
  last_activity_source: string | null
  no_new_commit: boolean
  no_active_workflow: boolean
  branch_present: boolean
  pr_present: boolean
  explicit_in_progress: boolean
}

export type Dashboard = {
  repo: string
  generated_at: string
  config: {
    roadmap_issue: number
    stalled_after_minutes: number
    token_configured: boolean
  }
  roadmap: {
    number: number
    title: string
    url: string
    updated_at: string
    declared_active: string | null
    active_issue: number
    effective_active: string
    items: RoadmapItem[]
  }
  active_work: {
    key: string
    issue_number: number
    title: string | null
    issue: Issue
    subitem_key: string | null
    block_done: boolean
    can_chain_block: boolean
    remaining_subitems: string[]
    primary_pr: PullRequest | null
    active_branch: Branch | null
    last_commit: Commit | null
    states: string[]
    stalled: boolean
    stall_level: 'confirmed' | 'stalled' | 'possible' | null
    stalled_details: StalledDetails
    failed_jobs: string[]
    explicit_in_progress: boolean
    active_runs: Run[]
    merged_but_unmarked_pr: {
      number: number
      title: string
      url: string
      merged_at: string
    } | null
  }
  architecture: {
    path: string
    url: string
    adrs: Array<{ name: string; url: string }>
    referenced_adrs: string[]
  }
  open_prs: PullRequest[]
  related_issues: Issue[]
  latest_commit: Commit | null
  next_action: string
  dev_prompt: string
  warnings: string[]
}

export type CockpitConfig = {
  repository: string
  roadmap_issue: number
  stalled_after_minutes: number
  token_configured: boolean
}

export type AvatarPreset =
  | 'product-owner'
  | 'developer'
  | 'architect'
  | 'reviewer'
  | 'generic'

export type RoleConfig = {
  id: string
  name: string
  avatar: AvatarPreset
  chat_url: string
  enabled: boolean
  order: number
}

export type RolesConfig = {
  roles: RoleConfig[]
}

export type ChatEffectiveState =
  | 'working'
  | 'idle'
  | 'possible_stall'
  | 'disconnected'

export type ChatConversationStatus = {
  conversation_url: string
  state: 'working' | 'idle'
  effective_state: ChatEffectiveState
  connected: boolean
  page_visible: boolean
  page_focused: boolean
  ui_signal: 'stop-control' | 'none'
  last_seen_at: string
  last_seen_seconds: number
  working_since: string | null
  last_completed_at: string | null
  last_completed_seconds: number | null
}

export type ChatStatusResponse = {
  stale_after_seconds: number
  conversations: ChatConversationStatus[]
}

export type MarkdownSection = {
  title: string
  level: number
  work_key: string | null
  content: string
}

export type DetailDocument = {
  name: string
  path: string
  url: string
  title: string
  status: string | null
  content: string
}

export type IssueDetail = Issue & {
  body: string
  sections: MarkdownSection[]
  referenced_issues: number[]
  documents: DetailDocument[]
}

export type RoadmapDetail = Issue & {
  body: string
  items: RoadmapItem[]
}

export type CommitFileDetail = {
  filename: string
  status: string | null
  additions: number | null
  deletions: number | null
  changes: number | null
  url: string | null
}

export type CommitDetail = Commit & {
  author: string | null
  stats: {
    additions: number | null
    deletions: number | null
    total: number | null
  }
  files: CommitFileDetail[]
  documentation: DetailDocument[]
}

export type ArchitectureDetail = {
  path: string
  url: string
  documents: DetailDocument[]
}
