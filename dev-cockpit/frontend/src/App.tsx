import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import RoleCards from './RoleCards'
import type {
  CockpitConfig,
  Dashboard,
  ExecutionControl,
  Job,
  PipelineReconciliation,
  PipelineStep,
  PullRequest,
  Run,
} from './types'

function latestRun(pr: PullRequest | null): Run | null {
  return pr?.runs?.[0] ?? null
}

function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  return new Intl.DateTimeFormat('fr-CA', {
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(new Date(value))
}

function formatMinutes(value: number | null | undefined): string {
  if (value == null) return '—'
  if (value < 60) return `${value} min`
  const hours = Math.floor(value / 60)
  const minutes = value % 60
  return minutes ? `${hours} h ${minutes} min` : `${hours} h`
}

function StateBadge({ value }: { value: string }) {
  const tone =
    value === 'CI_RED' ||
    value === 'BLOCKED' ||
    value === 'STALLED' ||
    value === 'STALLED_CONFIRMED' ||
    value === 'POSSIBLE_STALL'
      ? 'danger'
      : value === 'MERGEABLE' || value === 'DONE'
        ? 'success'
        : value === 'CI_RUNNING'
          ? 'progress'
          : 'neutral'

  return <span className={`state-badge ${tone}`}>{value}</span>
}

function PipelineRoadmapRow({
  step,
  active = false,
  parallel = false,
}: {
  step: PipelineStep
  active?: boolean
  parallel?: boolean
}) {
  const displayKey =
    step.kind === 'WORK' && /^\d/.test(step.key) ? `#${step.key}` : step.key
  const title = step.title
    .replace(/^En\s+parall[eè]le[^:]*:\s*/i, '')
    .replace(
      step.kind === 'WORK'
        ? new RegExp(`^#${step.key}\\s*(?:✅\\s*)?(?:[—–-]\\s*)?`, 'i')
        : /$^/,
      '',
    )
    .trim()

  return (
    <div className={`roadmap-row ${active ? 'active' : ''}`}>
      <span className={`roadmap-mark ${active || parallel ? 'current' : ''}`}>
        {active ? '→' : parallel ? '↗' : '·'}
      </span>
      <div>
        <strong>{displayKey}</strong>
        <small>{title || step.title}</small>
      </div>
    </div>
  )
}

function RoadmapReconciliationPanel({
  reconciliation,
  copied,
  onCopy,
}: {
  reconciliation: PipelineReconciliation
  copied: boolean
  onCopy: () => void
}) {
  if (reconciliation.status === 'legacy') return null

  const tone =
    reconciliation.status === 'coherent'
      ? 'coherent'
      : reconciliation.status === 'stale'
        ? 'stale'
        : reconciliation.status === 'invalid'
          ? 'invalid'
          : 'attention'
  const label =
    reconciliation.status === 'coherent'
      ? 'COHÉRENT'
      : reconciliation.status === 'stale'
        ? 'ROADMAP STALE'
        : reconciliation.status === 'invalid'
          ? 'INVALID'
          : 'ATTENTION'

  return (
    <section className={`reconciliation-panel ${tone}`}>
      <div className="reconciliation-header">
        <div>
          <span className="panel-kicker">COHÉRENCE ROADMAP</span>
          <h2>Contrat #55 ↔ réalité GitHub</h2>
        </div>
        <span className={`reconciliation-status ${tone}`}>{label}</span>
      </div>

      <p className="reconciliation-summary">{reconciliation.summary}</p>

      {reconciliation.findings.length > 0 && (
        <div className="reconciliation-findings">
          {reconciliation.findings.map((finding) => (
            <article key={`${finding.code}:${finding.key}`} className={finding.severity}>
              <strong>{finding.key}</strong>
              <span>{finding.message}</span>
              {finding.evidence.length > 0 && (
                <div className="reconciliation-evidence">
                  {finding.evidence.map((evidence) =>
                    evidence.url ? (
                      <a
                        key={`${finding.code}:${evidence.label}`}
                        href={evidence.url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {evidence.label} ↗
                      </a>
                    ) : (
                      <span key={`${finding.code}:${evidence.label}`}>
                        {evidence.label}
                      </span>
                    ),
                  )}
                </div>
              )}
            </article>
          ))}
        </div>
      )}

      {reconciliation.proposal && (
        <div className="reconciliation-proposal">
          <div>
            <strong>Proposition déterministe</strong>
            <span>
              {reconciliation.proposal.changes
                .map((change) => `${change.key}: ${change.from} → ${change.to}`)
                .join(' · ')}
            </span>
          </div>
          <button className="primary" type="button" onClick={onCopy}>
            {copied ? 'Bloc copié ✓' : 'Préparer la mise à jour de #55'}
          </button>
        </div>
      )}
    </section>
  )
}

function ExecutionControllerPanel({
  execution,
  copied,
  onCopy,
}: {
  execution: ExecutionControl
  copied: boolean
  onCopy: () => void
}) {
  const tone =
    execution.phase === 'CI_RED' ||
    execution.phase === 'PIPELINE_INVALID'
      ? 'danger'
      : execution.phase === 'ROADMAP_UPDATE_REQUIRED' ||
          execution.phase === 'DELIVERY_UNVERIFIED'
        ? 'warning'
        : execution.phase === 'READY_TO_MERGE'
          ? 'success'
          : execution.phase === 'CI_RUNNING'
            ? 'progress'
            : 'neutral'

  return (
    <section className={`execution-panel ${tone}`}>
      <div className="execution-main">
        <div className="execution-heading">
          <div>
            <span className="panel-kicker">CONTRÔLEUR D'EXÉCUTION</span>
            <h2>{execution.label}</h2>
          </div>
          <span className={`execution-phase ${tone}`}>{execution.phase}</span>
        </div>

        <p className="execution-summary">{execution.summary}</p>

        <div className="execution-next">
          <span>PROCHAINE ACTION · {execution.responsible_role}</span>
          <strong>{execution.next_action}</strong>
        </div>

        <pre className="prompt-preview execution-prompt">{execution.prompt}</pre>

        <div className="actions execution-actions">
          <button className="primary" type="button" onClick={onCopy}>
            {copied ? '✓ Prompt copié' : 'Copier le prompt de reprise'}
          </button>
          {execution.primary_link && (
            <a
              className="button"
              href={execution.primary_link.url}
              target="_blank"
              rel="noreferrer"
            >
              {execution.primary_link.label} ↗
            </a>
          )}
        </div>
      </div>

      <div className="execution-timeline">
        <div className="section-label">TIMELINE GITHUB</div>
        {execution.timeline.length ? (
          <div className="timeline-list">
            {execution.timeline.map((event) => (
              <article key={`${event.at}:${event.label}`}>
                <span className={`timeline-dot ${event.kind}`} />
                <div>
                  <strong>
                    {event.url ? (
                      <a href={event.url} target="_blank" rel="noreferrer">
                        {event.label}
                      </a>
                    ) : (
                      event.label
                    )}
                  </strong>
                  <small>{event.detail}</small>
                  <time>{formatDate(event.at)}</time>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="empty compact">Aucun événement GitHub pertinent.</div>
        )}
      </div>
    </section>
  )
}

function JobLine({ job }: { job: Job }) {
  const running = job.status && job.status !== 'completed'
  const success = job.conclusion === 'success'
  const failed =
    Boolean(job.conclusion) &&
    job.conclusion !== 'success' &&
    job.conclusion !== 'skipped' &&
    job.conclusion !== 'neutral'

  const icon = running ? '…' : success ? '✓' : failed ? '✕' : '·'
  const tone = running ? 'running' : success ? 'good' : failed ? 'bad' : 'muted'

  return (
    <a
      className="job-line"
      href={job.url || undefined}
      target="_blank"
      rel="noreferrer"
    >
      <span className={`job-icon ${tone}`}>{icon}</span>
      <span>{job.name}</span>
      <span className="job-state">
        {job.status === 'completed' ? job.conclusion : job.status}
      </span>
    </a>
  )
}

export default function App() {
  const storedRepo = localStorage.getItem('dev-cockpit-repo') || ''
  const [repo, setRepo] = useState(storedRepo)
  const [repoDraft, setRepoDraft] = useState(storedRepo)
  const [data, setData] = useState<Dashboard | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [roadmapCopied, setRoadmapCopied] = useState(false)

  async function load(targetRepo: string) {
    if (!targetRepo) return

    setLoading(true)
    setError(null)
    try {
      const response = await fetch(
        `/api/dashboard?repo=${encodeURIComponent(targetRepo)}`,
      )
      const payload = await response.json()
      if (!response.ok) {
        throw new Error(payload.detail || `Erreur HTTP ${response.status}`)
      }
      setData(payload as Dashboard)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Erreur inconnue')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    async function initialize() {
      try {
        const response = await fetch('/api/config')
        const config = (await response.json()) as CockpitConfig
        const initialRepo = storedRepo || config.repository
        setRepo(initialRepo)
        setRepoDraft(initialRepo)
      } catch {
        const fallback = storedRepo || 'tchi99/RessourcePlanner'
        setRepo(fallback)
        setRepoDraft(fallback)
      }
    }

    void initialize()
  }, [storedRepo])

  useEffect(() => {
    if (!repo) return
    void load(repo)
    const timer = window.setInterval(() => void load(repo), 60_000)
    return () => window.clearInterval(timer)
  }, [repo])

  function changeRepo(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const value = repoDraft.trim()
    if (!value) return
    localStorage.setItem('dev-cockpit-repo', value)
    setRepo(value)
  }

  async function copyPrompt() {
    if (!data?.execution.prompt) return
    await navigator.clipboard.writeText(data.execution.prompt)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1400)
  }

  async function copyRoadmapProposal() {
    const block = data?.reconciliation.proposal?.pipeline_block
    if (!block) return
    await navigator.clipboard.writeText(block)
    setRoadmapCopied(true)
    window.setTimeout(() => setRoadmapCopied(false), 1800)
  }

  const activeWork = data?.active_work ?? null
  const primaryPr = activeWork?.primary_pr ?? null
  const run = latestRun(primaryPr) ?? activeWork?.active_runs?.[0] ?? null
  const issueUrl = activeWork?.issue.url
  const stallDetails = activeWork?.stalled_details
  const stallTitle =
    activeWork?.stall_level === 'confirmed'
      ? '⚠ Dev probablement arrêté — CI rouge abandonnée'
      : activeWork?.stall_level === 'possible'
        ? '⚠ Travail possiblement interrompu'
        : '⚠ Dev probablement arrêté'

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">RESSOURCEPLANNER · DEV TOOL</p>
          <h1>Dev Cockpit</h1>
          <p className="subtitle">
            GitHub reste la source de vérité. Le cockpit observe, dérive et
            génère un prompt à copier.
          </p>
        </div>

        <form className="repo-form" onSubmit={changeRepo}>
          <label htmlFor="repo">Dépôt surveillé</label>
          <div className="repo-input-row">
            <input
              id="repo"
              value={repoDraft}
              onChange={(event) => setRepoDraft(event.target.value)}
              spellCheck={false}
            />
            <button type="submit">Charger</button>
            <button
              className="ghost"
              type="button"
              onClick={() => void load(repo)}
              disabled={loading}
              aria-label="Actualiser"
            >
              ↻
            </button>
          </div>
        </form>
      </header>

      {error && (
        <section className="error-panel">
          <strong>Configuration / GitHub</strong>
          <span>{error}</span>
        </section>
      )}

      {loading && !data && (
        <section className="loading-panel">Lecture de GitHub…</section>
      )}

      <RoleCards dashboard={data} />

      {data && (
        <ExecutionControllerPanel
          execution={data.execution}
          copied={copied}
          onCopy={() => void copyPrompt()}
        />
      )}

      {data && !data.pipeline.valid && (
        <section className="error-panel pipeline-invalid">
          <strong>Pipeline #55 invalide</strong>
          <span>
            Le bloc COCKPIT_PIPELINE_V1 doit être corrigé avant de déterminer
            une étape active.
          </span>
          {data.pipeline.errors.map((message) => (
            <span key={message}>• {message}</span>
          ))}
        </section>
      )}

      {data && data.pipeline.valid && !data.active_work && (
        <section className="loading-panel">
          Aucune étape MAIN active n'est déclarée dans le pipeline canonique.
        </section>
      )}

      {data && data.pipeline.valid && data.active_work && (
        <>
          {data.warnings.length > 0 && (
            <div className="warnings">
              {data.warnings.map((warning) => (
                <div key={warning}>⚠ {warning}</div>
              ))}
            </div>
          )}

          <RoadmapReconciliationPanel
            reconciliation={data.reconciliation}
            copied={roadmapCopied}
            onCopy={() => void copyRoadmapProposal()}
          />

          <section className="dashboard-grid">
            <article className="panel roadmap-panel">
              <div className="panel-header">
                <div>
                  <span className="panel-kicker">ROADMAP</span>
                  <h2>Maître #{data.roadmap.number}</h2>
                </div>
                <a href={data.roadmap.url} target="_blank" rel="noreferrer">
                  GitHub ↗
                </a>
              </div>

              {data.pipeline.steps.length > 0 ? (
                <div className="roadmap-list roadmap-pipeline">
                  <div className="roadmap-lane-label">MAINTENANT</div>
                  {data.pipeline.now ? (
                    <PipelineRoadmapRow step={data.pipeline.now} active />
                  ) : (
                    <div className="empty compact">Aucune étape principale restante.</div>
                  )}

                  {data.pipeline.parallel.length > 0 && (
                    <>
                      <div className="roadmap-lane-label">PARALLÈLE DISPONIBLE</div>
                      {data.pipeline.parallel.map((step) => (
                        <PipelineRoadmapRow
                          key={step.key}
                          step={step}
                          parallel
                        />
                      ))}
                    </>
                  )}

                  {data.pipeline.next.length > 0 && (
                    <>
                      <div className="roadmap-lane-label">ENSUITE</div>
                      {data.pipeline.next.map((step) => (
                        <PipelineRoadmapRow key={step.key} step={step} />
                      ))}
                    </>
                  )}
                </div>
              ) : (
                <div className="roadmap-list">
                  {data.roadmap.items.map((item) => {
                    const active = item.key === data.roadmap.effective_active
                    return (
                      <div
                        className={`roadmap-row ${active ? 'active' : ''}`}
                        key={item.key}
                      >
                        <span
                          className={`roadmap-mark ${item.done ? 'done' : active ? 'current' : ''}`}
                        >
                          {item.done ? '✓' : active ? '→' : '·'}
                        </span>
                        <div>
                          <strong>
                            {/^\d+$/.test(item.key) ? `#${item.key}` : item.key}
                          </strong>
                          <small>{item.title}</small>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}

              <div className="panel-foot">
                Issue active #{data.roadmap.active_issue}
                {data.pipeline.steps.length > 0
                  ? ' · pipeline #55 canonique'
                  : ` · sous-tranche ${data.active_work.subitem_key || '—'}`}
              </div>
            </article>

            <article className="panel active-panel">
              <div className="panel-header">
                <div>
                  <span className="panel-kicker">TRAVAIL ACTIF</span>
                  <h2>
                    #{data.active_work.issue_number}
                    {data.active_work.subitem_key
                      ? ` · ${data.active_work.subitem_key}`
                      : ''}
                  </h2>
                </div>
                <div className="state-stack">
                  {data.active_work.states.map((state) => (
                    <StateBadge key={state} value={state} />
                  ))}
                </div>
              </div>

              {data.active_work.stalled && stallDetails && (
                <div className="stalled-banner">
                  <strong>{stallTitle}</strong>
                  {stallDetails.ci_failed_minutes != null &&
                    data.active_work.stall_level === 'confirmed' && (
                      <span>
                        CI rouge depuis{' '}
                        {formatMinutes(stallDetails.ci_failed_minutes)}
                      </span>
                    )}
                  <span>
                    Dernière activité GitHub pertinente il y a{' '}
                    {formatMinutes(stallDetails.last_activity_minutes)}
                  </span>
                  <span>
                    {stallDetails.branch_present
                      ? 'Branche de travail détectée'
                      : 'Aucune branche associée'}
                    {' · '}
                    {stallDetails.pr_present ? 'PR détectée' : 'Aucune PR associée'}
                  </span>
                  <span>
                    {stallDetails.no_active_workflow
                      ? 'Aucun workflow actif'
                      : 'Workflow actif'}
                  </span>
                </div>
              )}

              <dl className="facts">
                <div>
                  <dt>Issue</dt>
                  <dd>
                    <a href={issueUrl} target="_blank" rel="noreferrer">
                      #{data.active_work.issue.number} ·{' '}
                      {data.active_work.issue.title}
                    </a>
                  </dd>
                </div>
                <div>
                  <dt>Sous-tranche</dt>
                  <dd>
                    {data.active_work.subitem_key || 'aucune sous-tranche explicite'}
                  </dd>
                </div>
                <div>
                  <dt>Enchaînement</dt>
                  <dd>
                    {data.active_work.can_chain_block
                      ? `autorisé dans ce bloc (${data.active_work.remaining_subitems.join(' → ')})`
                      : 'non déduit automatiquement'}
                  </dd>
                </div>
                <div>
                  <dt>PR</dt>
                  <dd>
                    {primaryPr ? (
                      <a href={primaryPr.url} target="_blank" rel="noreferrer">
                        #{primaryPr.number} · {primaryPr.title}
                      </a>
                    ) : (
                      'Aucune PR associée'
                    )}
                  </dd>
                </div>
                <div>
                  <dt>Branche</dt>
                  <dd>
                    {data.active_work.active_branch ? (
                      <a
                        className="mono"
                        href={data.active_work.active_branch.url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {data.active_work.active_branch.name}
                      </a>
                    ) : (
                      '—'
                    )}
                  </dd>
                </div>
                <div>
                  <dt>Dernier commit</dt>
                  <dd>
                    {data.active_work.last_commit ? (
                      <a
                        href={data.active_work.last_commit.url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        <span className="mono">
                          {data.active_work.last_commit.short_sha}
                        </span>{' '}
                        · {data.active_work.last_commit.message}
                      </a>
                    ) : (
                      '—'
                    )}
                  </dd>
                </div>
                <div>
                  <dt>Dernière activité</dt>
                  <dd>
                    {stallDetails?.last_activity_at
                      ? `${formatDate(stallDetails.last_activity_at)} · ${stallDetails.last_activity_source ?? 'GitHub'}`
                      : '—'}
                  </dd>
                </div>
                <div>
                  <dt>Mergeable</dt>
                  <dd>
                    {primaryPr
                      ? primaryPr.mergeable == null
                        ? 'calcul GitHub en attente'
                        : primaryPr.mergeable
                          ? 'oui'
                          : 'non'
                      : '—'}
                  </dd>
                </div>
                <div>
                  <dt>ADR</dt>
                  <dd>
                    <a
                      href={data.architecture.url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {data.architecture.adrs.length} présent(s)
                    </a>
                    {data.architecture.referenced_adrs.length
                      ? ` · ${data.architecture.referenced_adrs.length} référencé(s) par le bloc`
                      : ''}
                  </dd>
                </div>
              </dl>
            </article>

            <article className="panel ci-panel">
              <div className="panel-header">
                <div>
                  <span className="panel-kicker">PR / CI</span>
                  <h2>
                    {run
                      ? `${run.name} #${run.run_number ?? ''}`
                      : 'Aucune CI associée'}
                  </h2>
                </div>
                {run?.url && (
                  <a href={run.url} target="_blank" rel="noreferrer">
                    Run ↗
                  </a>
                )}
              </div>

              <div className="ci-summary">
                <span>État CI</span>
                <strong>
                  {run
                    ? run.status === 'completed'
                      ? run.conclusion
                      : run.status
                    : '—'}
                </strong>
              </div>

              {data.active_work.failed_jobs.length > 0 && (
                <div className="failed-jobs">
                  <span>Jobs en échec</span>
                  <strong>{data.active_work.failed_jobs.join(', ')}</strong>
                </div>
              )}

              {run?.jobs?.length ? (
                <div className="jobs">
                  {run.jobs.map((job) => (
                    <JobLine key={job.id ?? job.name} job={job} />
                  ))}
                </div>
              ) : (
                <div className="empty">
                  Aucun job GitHub Actions associé à la PR active.
                </div>
              )}

              <div className="pr-list">
                <div className="section-label">
                  PR ouvertes · {data.open_prs.length}
                </div>
                {data.open_prs.length ? (
                  data.open_prs.map((pr) => {
                    const prRun = latestRun(pr)
                    return (
                      <a
                        className="pr-row"
                        key={pr.number}
                        href={pr.url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        <span>#{pr.number}</span>
                        <span>{pr.title}</span>
                        <span>
                          {prRun
                            ? prRun.status === 'completed'
                              ? prRun.conclusion
                              : prRun.status
                            : '·'}
                        </span>
                      </a>
                    )
                  })
                ) : (
                  <div className="empty compact">Aucune PR ouverte.</div>
                )}
              </div>
            </article>
          </section>

          <footer>
            <span>
              Dernier commit de main (référence) :{' '}
              {data.latest_commit ? (
                <a
                  href={data.latest_commit.url}
                  target="_blank"
                  rel="noreferrer"
                >
                  <span className="mono">{data.latest_commit.short_sha}</span> ·{' '}
                  {data.latest_commit.message}
                </a>
              ) : (
                '—'
              )}
            </span>
            <span>
              Actualisé {formatDate(data.generated_at)} · auto-refresh 60 s ·
              STALLED ≥ {data.config.stalled_after_minutes} min
            </span>
          </footer>
        </>
      )}
    </main>
  )
}
