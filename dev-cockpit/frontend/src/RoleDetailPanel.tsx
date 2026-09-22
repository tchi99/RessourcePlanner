import { useEffect, useRef, useState } from 'react'
import type {
  ChatConversationStatus,
  Dashboard,
  Job,
  RoleConfig,
  Run,
} from './types'

const APP_ARCHITECTURE = [
  'React',
  'FastAPI',
  'Application / Domain',
  'Infrastructure',
  'SQLAlchemy / DB / intégrations',
]

function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  return new Intl.DateTimeFormat('fr-CA', {
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(new Date(value))
}

function formatAge(seconds: number | null | undefined): string {
  if (seconds == null) return '—'
  if (seconds < 60) return `${seconds} s`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes} min`
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  return rest ? `${hours} h ${rest} min` : `${hours} h`
}

function latestRun(dashboard: Dashboard): Run | null {
  return (
    dashboard.active_work.primary_pr?.runs?.[0] ??
    dashboard.active_work.active_runs?.[0] ??
    null
  )
}

function JobSummary({ job }: { job: Job }) {
  const label =
    job.status === 'completed'
      ? job.conclusion || 'completed'
      : job.status || 'unknown'
  return (
    <a
      className="role-detail-job"
      href={job.url || undefined}
      target="_blank"
      rel="noreferrer"
    >
      <span>{job.name}</span>
      <strong>{label}</strong>
    </a>
  )
}

function ChatStatusBlock({
  role,
  chatStatus,
}: {
  role: RoleConfig
  chatStatus: ChatConversationStatus | null
}) {
  return (
    <section className="role-detail-section">
      <div className="role-detail-section-title">Conversation ChatGPT</div>
      {role.chat_url ? (
        <>
          <dl className="role-detail-facts compact">
            <div>
              <dt>État</dt>
              <dd>{chatStatus?.effective_state ?? 'offline'}</dd>
            </div>
            <div>
              <dt>Dernier heartbeat</dt>
              <dd>{formatAge(chatStatus?.last_seen_seconds)}</dd>
            </div>
            <div>
              <dt>Visible</dt>
              <dd>{chatStatus ? (chatStatus.page_visible ? 'oui' : 'non') : '—'}</dd>
            </div>
            <div>
              <dt>Focus</dt>
              <dd>{chatStatus ? (chatStatus.page_focused ? 'oui' : 'non') : '—'}</dd>
            </div>
          </dl>
          <a
            className="button role-detail-primary-link"
            href={role.chat_url}
            target="_blank"
            rel="noreferrer"
          >
            Ouvrir la conversation ↗
          </a>
        </>
      ) : (
        <p className="role-detail-muted">Aucune conversation n'est associée à ce rôle.</p>
      )}
    </section>
  )
}

function ProductOwnerDetails({ dashboard }: { dashboard: Dashboard | null }) {
  if (!dashboard) {
    return <p className="role-detail-muted">Données GitHub indisponibles.</p>
  }

  return (
    <>
      <section className="role-detail-hero">
        <span>Bloc actif</span>
        <strong>{dashboard.roadmap.effective_active}</strong>
        <p>{dashboard.active_work.title || dashboard.active_work.issue.title}</p>
      </section>

      <section className="role-detail-section">
        <div className="role-detail-section-title">Roadmap maître</div>
        <div className="role-detail-roadmap">
          {dashboard.roadmap.items.map((item) => {
            const active = item.key === dashboard.roadmap.effective_active
            return (
              <div
                className={`role-detail-roadmap-row ${active ? 'active' : ''}`}
                key={item.key}
              >
                <span>{item.done ? '✓' : active ? '→' : '·'}</span>
                <div>
                  <strong>{/^\d+$/.test(item.key) ? `#${item.key}` : item.key}</strong>
                  <small>{item.title}</small>
                </div>
              </div>
            )
          })}
        </div>
        <a
          className="role-detail-inline-link"
          href={dashboard.roadmap.url}
          target="_blank"
          rel="noreferrer"
        >
          Ouvrir le roadmap GitHub ↗
        </a>
      </section>

      <section className="role-detail-section">
        <div className="role-detail-section-title">Prochaines étapes</div>
        <div className="role-detail-next-action">{dashboard.next_action}</div>
        {dashboard.active_work.remaining_subitems.length > 0 && (
          <div className="role-detail-chips">
            {dashboard.active_work.remaining_subitems.map((item) => (
              <span key={item}>{item}</span>
            ))}
          </div>
        )}
      </section>

      {dashboard.warnings.length > 0 && (
        <section className="role-detail-section">
          <div className="role-detail-section-title">Décalages détectés</div>
          <div className="role-detail-warning-list">
            {dashboard.warnings.map((warning) => (
              <div key={warning}>⚠ {warning}</div>
            ))}
          </div>
        </section>
      )}

      {dashboard.related_issues.length > 0 && (
        <section className="role-detail-section">
          <div className="role-detail-section-title">Issues liées</div>
          <div className="role-detail-link-list">
            {dashboard.related_issues.map((issue) => (
              <a key={issue.number} href={issue.url} target="_blank" rel="noreferrer">
                #{issue.number} · {issue.title}
              </a>
            ))}
          </div>
        </section>
      )}
    </>
  )
}

function DeveloperDetails({ dashboard }: { dashboard: Dashboard | null }) {
  const [copied, setCopied] = useState(false)
  if (!dashboard) {
    return <p className="role-detail-muted">Données GitHub indisponibles.</p>
  }

  const work = dashboard.active_work
  const run = latestRun(dashboard)
  const prompt = dashboard.dev_prompt

  async function copyPrompt() {
    if (!prompt) return
    await navigator.clipboard.writeText(prompt)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1500)
  }

  return (
    <>
      <section className="role-detail-hero">
        <span>Travail actif</span>
        <strong>{work.subitem_key || `#${work.issue_number}`}</strong>
        <p>{work.title || work.issue.title}</p>
        <div className="role-detail-chips">
          {work.states.map((state) => (
            <span key={state}>{state}</span>
          ))}
        </div>
      </section>

      <section className="role-detail-section">
        <div className="role-detail-section-title">Exécution GitHub</div>
        <dl className="role-detail-facts">
          <div>
            <dt>Issue</dt>
            <dd>
              <a href={work.issue.url} target="_blank" rel="noreferrer">
                #{work.issue.number} · {work.issue.title}
              </a>
            </dd>
          </div>
          <div>
            <dt>Branche</dt>
            <dd>
              {work.active_branch ? (
                <a href={work.active_branch.url} target="_blank" rel="noreferrer">
                  {work.active_branch.name}
                </a>
              ) : (
                '—'
              )}
            </dd>
          </div>
          <div>
            <dt>Dernier commit</dt>
            <dd>
              {work.last_commit ? (
                <a href={work.last_commit.url} target="_blank" rel="noreferrer">
                  {work.last_commit.short_sha} · {work.last_commit.message}
                </a>
              ) : (
                '—'
              )}
            </dd>
          </div>
          <div>
            <dt>PR</dt>
            <dd>
              {work.primary_pr ? (
                <a href={work.primary_pr.url} target="_blank" rel="noreferrer">
                  #{work.primary_pr.number} · {work.primary_pr.title}
                </a>
              ) : (
                'Aucune PR associée'
              )}
            </dd>
          </div>
        </dl>
      </section>

      <section className="role-detail-section">
        <div className="role-detail-section-title">CI</div>
        {run ? (
          <>
            <div className="role-detail-run-head">
              <a href={run.url || undefined} target="_blank" rel="noreferrer">
                {run.name} #{run.run_number ?? ''}
              </a>
              <strong>
                {run.status === 'completed' ? run.conclusion || 'completed' : run.status}
              </strong>
            </div>
            {run.jobs.length > 0 && (
              <div className="role-detail-jobs">
                {run.jobs.map((job) => (
                  <JobSummary key={job.id ?? job.name} job={job} />
                ))}
              </div>
            )}
          </>
        ) : (
          <p className="role-detail-muted">Aucun workflow associé au travail actif.</p>
        )}
      </section>

      {work.stalled && (
        <section className="role-detail-section danger">
          <div className="role-detail-section-title">Diagnostic de stall</div>
          <dl className="role-detail-facts compact">
            <div>
              <dt>Niveau</dt>
              <dd>{work.stall_level || '—'}</dd>
            </div>
            <div>
              <dt>Dernière activité</dt>
              <dd>
                {work.stalled_details.last_activity_minutes == null
                  ? '—'
                  : `${work.stalled_details.last_activity_minutes} min`}
              </dd>
            </div>
            <div>
              <dt>Source</dt>
              <dd>{work.stalled_details.last_activity_source || '—'}</dd>
            </div>
            <div>
              <dt>Workflow actif</dt>
              <dd>{work.stalled_details.no_active_workflow ? 'non' : 'oui'}</dd>
            </div>
          </dl>
        </section>
      )}

      <section className="role-detail-section">
        <div className="role-detail-section-title">Prompt de reprise</div>
        <pre className="role-detail-prompt">{prompt}</pre>
        <button className="primary" type="button" onClick={() => void copyPrompt()}>
          {copied ? '✓ Copié' : 'Copier le prompt Dev'}
        </button>
      </section>
    </>
  )
}

function ArchitectDetails({ dashboard }: { dashboard: Dashboard | null }) {
  if (!dashboard) {
    return <p className="role-detail-muted">Données GitHub indisponibles.</p>
  }

  const referenced = new Set(dashboard.architecture.referenced_adrs)

  return (
    <>
      <section className="role-detail-hero">
        <span>Architecture du bloc actif</span>
        <strong>{dashboard.active_work.subitem_key || `#${dashboard.active_work.issue_number}`}</strong>
        <p>{dashboard.active_work.title || dashboard.active_work.issue.title}</p>
      </section>

      <section className="role-detail-section">
        <div className="role-detail-section-title">Architecture de l'application</div>
        <div className="role-detail-architecture-flow" aria-label="Architecture applicative">
          {APP_ARCHITECTURE.map((layer, index) => (
            <div key={layer}>
              <span>{layer}</span>
              {index < APP_ARCHITECTURE.length - 1 && <b aria-hidden="true">↓</b>}
            </div>
          ))}
        </div>
      </section>

      <section className="role-detail-section">
        <div className="role-detail-section-title">ADR du bloc</div>
        {dashboard.architecture.referenced_adrs.length ? (
          <div className="role-detail-link-list">
            {dashboard.architecture.adrs
              .filter((adr) => referenced.has(adr.name))
              .map((adr) => (
                <a key={adr.name} href={adr.url} target="_blank" rel="noreferrer">
                  {adr.name}
                </a>
              ))}
          </div>
        ) : (
          <p className="role-detail-muted">
            Aucun ADR n'est explicitement référencé par le bloc actif.
          </p>
        )}
      </section>

      <section className="role-detail-section">
        <div className="role-detail-section-title">
          Documentation d'architecture · {dashboard.architecture.adrs.length} ADR
        </div>
        <div className="role-detail-link-list dense">
          {dashboard.architecture.adrs.map((adr) => (
            <a
              className={referenced.has(adr.name) ? 'referenced' : ''}
              key={adr.name}
              href={adr.url}
              target="_blank"
              rel="noreferrer"
            >
              {referenced.has(adr.name) ? '● ' : ''}
              {adr.name}
            </a>
          ))}
        </div>
        <a
          className="role-detail-inline-link"
          href={dashboard.architecture.url}
          target="_blank"
          rel="noreferrer"
        >
          Ouvrir docs/architecture ↗
        </a>
      </section>

      {dashboard.related_issues.length > 0 && (
        <section className="role-detail-section">
          <div className="role-detail-section-title">Contexte lié au bloc</div>
          <div className="role-detail-link-list">
            {dashboard.related_issues.map((issue) => (
              <a key={issue.number} href={issue.url} target="_blank" rel="noreferrer">
                #{issue.number} · {issue.title}
              </a>
            ))}
          </div>
        </section>
      )}
    </>
  )
}

function ReviewerDetails({ dashboard }: { dashboard: Dashboard | null }) {
  if (!dashboard) {
    return <p className="role-detail-muted">Données GitHub indisponibles.</p>
  }
  return (
    <>
      <section className="role-detail-hero">
        <span>Revue active</span>
        <strong>{dashboard.active_work.subitem_key || dashboard.active_work.key}</strong>
        <p>{dashboard.active_work.title || dashboard.active_work.issue.title}</p>
      </section>
      <section className="role-detail-section">
        <div className="role-detail-section-title">Jobs en échec</div>
        {dashboard.active_work.failed_jobs.length ? (
          <div className="role-detail-warning-list">
            {dashboard.active_work.failed_jobs.map((job) => (
              <div key={job}>✕ {job}</div>
            ))}
          </div>
        ) : (
          <p className="role-detail-muted">Aucun job CI en échec sur le travail actif.</p>
        )}
      </section>
      <section className="role-detail-section">
        <div className="role-detail-section-title">PR ouvertes</div>
        <div className="role-detail-link-list">
          {dashboard.open_prs.length ? (
            dashboard.open_prs.map((pr) => (
              <a key={pr.number} href={pr.url} target="_blank" rel="noreferrer">
                #{pr.number} · {pr.title}
              </a>
            ))
          ) : (
            <span className="role-detail-muted">Aucune PR ouverte.</span>
          )}
        </div>
      </section>
    </>
  )
}

export default function RoleDetailPanel({
  role,
  dashboard,
  chatStatus,
  onClose,
}: {
  role: RoleConfig
  dashboard: Dashboard | null
  chatStatus: ChatConversationStatus | null
  onClose: () => void
}) {
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    closeRef.current?.focus()

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }

    window.addEventListener('keydown', onKeyDown)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [onClose])

  let details
  if (role.avatar === 'product-owner') {
    details = <ProductOwnerDetails dashboard={dashboard} />
  } else if (role.avatar === 'developer') {
    details = <DeveloperDetails dashboard={dashboard} />
  } else if (role.avatar === 'architect') {
    details = <ArchitectDetails dashboard={dashboard} />
  } else if (role.avatar === 'reviewer') {
    details = <ReviewerDetails dashboard={dashboard} />
  } else {
    details = (
      <section className="role-detail-section">
        <div className="role-detail-section-title">Rôle personnalisé</div>
        <p className="role-detail-muted">
          Ce rôle n'a pas encore de vue métier spécialisée.
        </p>
      </section>
    )
  }

  return (
    <div className="role-detail-backdrop" onMouseDown={onClose}>
      <aside
        className="role-detail-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="role-detail-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="role-detail-header">
          <div>
            <span className="panel-kicker">DÉTAIL DU RÔLE</span>
            <h2 id="role-detail-title">{role.name}</h2>
          </div>
          <button
            ref={closeRef}
            className="role-detail-close"
            type="button"
            onClick={onClose}
            aria-label="Fermer le panneau"
          >
            ×
          </button>
        </header>

        <div className="role-detail-content">
          {details}
          <ChatStatusBlock role={role} chatStatus={chatStatus} />
        </div>

        <footer className="role-detail-footer">
          <span>Actualisé {formatDate(dashboard?.generated_at)}</span>
          <span>GitHub reste la source de vérité.</span>
        </footer>
      </aside>
    </div>
  )
}
