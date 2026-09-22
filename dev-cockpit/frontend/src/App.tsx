import { FormEvent, useEffect, useMemo, useState } from 'react'
import type { CockpitConfig, Dashboard, Job, PullRequest, Run } from './types'

function statusClass(status?: string | null, conclusion?: string | null) {
  if (status && status !== 'completed') return 'running'
  if (conclusion === 'success') return 'good'
  if (conclusion && conclusion !== 'skipped' && conclusion !== 'neutral') return 'bad'
  return 'muted'
}

function statusIcon(status?: string | null, conclusion?: string | null) {
  if (status && status !== 'completed') return 'â—Œ'
  if (conclusion === 'success') return 'âœ“'
  if (conclusion && conclusion !== 'skipped' && conclusion !== 'neutral') return 'âœ•'
  return 'Â·'
}

function formatDate(value?: string | null) {
  if (!value) return 'â€”'
  return new Intl.DateTimeFormat('fr-CA', {
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(new Date(value))
}

function formatMinutes(value?: number | null) {
  if (value == null) return 'â€”'
  if (value < 60) return `${value} min`
  const hours = Math.floor(value / 60)
  const minutes = value % 60
  return minutes ? `${hours} h ${minutes} min` : `${hours} h`
}

function latestRun(pr?: PullRequest | null): Run | null {
  return pr?.runs?.[0] ?? null
}

function JobLine({ job }: { job: Job }) {
  return (
    <a className="job-line" href={job.url || undefined} target="_blank" rel="noreferrer">
      <span className={`job-icon ${statusClass(job.status, job.conclusion)}`}>
        {statusIcon(job.status, job.conclusion)}
      </span>
      <span>{job.name}</span>
      <span className="job-state">{job.status === 'completed' ? job.conclusion : job.status}</span>
    </a>
  )
}

function StateBadge({ value }: { value: string }) {
  const tone = value === 'CI_RED' || value === 'BLOCKED' || value === 'STALLED'
    ? 'danger'
    : value === 'MERGEABLE' || value === 'DONE'
      ? 'success'
      : value === 'CI_RUNNING'
        ? 'progress'
        : 'neutral'
  return <span className={`state-badge ${tone}`}>{value}</span>
}

export default function App() {
  const storedRepo = localStorage.getItem('dev-cockpit-repo') || ''
  const [repo, setRepo] = useState(storedRepo)
  const [repoDraft, setRepoDraft] = useState(storedRepo)
  const [data, setData] = useState<Dashboard | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    async function loadConfig() {
      try {
        const response = await fetch('/api/config')
        const config = await response.json() as CockpitConfig
        if (!repo) {
          setRepo(config.repository)
          setRepoDraft(config.repository)
        }
      } catch {
        if (!repo) {
          setRepo('tchi99/RessourcePlanner')
          setRepoDraft('tchi99/RessourcePlanner')
        }
      }
    }
    void loadConfig()
    // config is intentionally loaded once
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function load(targetRepo = repo) {
    if (!targetRepo) return
    setLoading(true)
    setError(null)
    try {
      const response = await fetch(`/api/dashboard?repo=${encodeURIComponent(targetRepo)}`)
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || `Erreur HTTP ${response.status}`)
      setData(payload)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur inconnue')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (repo) void load(repo)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repo])

  useEffect(() => {
    if (!repo) return
    const timer = window.setInterval(() => void load(repo), 60_000)
    return () => window.clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repo])

  function changeRepo(event: FormEvent) {
    event.preventDefault()
    const value = repoDraft.trim()
    if (!value) return
    localStorage.setItem('dev-cockpit-repo', value)
    setRepo(value)
  }

  async function copyPrompt() {
    if (!data?.dev_prompt) return
    await navigator.clipboard.writeText(data.dev_prompt)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1400)
  }

  const primaryPr = data?.active_work.primary_pr ?? null
  const run = useMemo(() => latestRun(primaryPr), [primaryPr])
  const failedJobs = data?.active_work.failed_jobs ?? []
  const issueUrl = data?.active_work.issue?.url

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">RESSOURCEPLANNER Â· DEV TOOL</p>
          <h1>Dev Cockpit</h1>
          <p className="subtitle">GitHub reste la source de vÃ©ritÃ©. Le cockpit observe, dÃ©rive et gÃ©nÃ¨re un prompt Ã  copier.</p>
        </div>
        <form className="repo-form" onSubmit={changeRepo}>
          <label htmlFor="repo">DÃ©pÃ´t surveillÃ©</label>
          <div className="repo-input-row">
            <input id="repo" value={repoDraft} onChange={(e) => setRepoDraft(e.target.value)} spellCheck={false} />
            <button type="submit">Charger</button>
            <button className="ghost" type="button" onClick={() => void load(repo)} disabled={loading}>â†»</button>
          </div>
        </form>
      </header>

      {error && <section className="error-panel"><strong>Configuration / GitHub</strong><span>{error}</span></section>}
      {loading && !data && <section className="loading-panel">Lecture de GitHubâ€¦</section>}

      {data && (
        <>
          {data.warnings.length > 0 && (
            <div className="warnings">
              {data.warnings.map((warning) => <div key={warning}>âš  {warning}</div>)}
            </div>
          )}

          <section className="dashboard-grid">
            <article className="panel roadmap-panel">
              <div className="panel-header">
                <div>
                  <span className="panel-kicker">ROADMAP</span>
                  <h2>MaÃ®tre #{data.roadmap.number}</h2>
                </div>
                <a href={data.roadmap.url} target="_blank" rel="noreferrer">GitHub â†—</a>
              </div>
              <div className="roadmap-list">
                {data.roadmap.items.map((item) => {
                  const active = item.key === data.roadmap.effective_active
                  return (
                    <div className={`roadmap-row ${active ? 'active' : ''}`} key={item.key}>
                      <span className={`roadmap-mark ${item.done ? 'done' : active ? 'current' : ''}`}>
                        {item.done ? 'âœ“' : active ? 'â†’'"¢|+rwĞ¢Â÷7ãà¢ÆF—cà¢Ç7G&öæsç¶—FVÒæ¶W’æÖF6‚‚õåÆB²Bò’ò2G¶—FVÒæ¶W—Ö¢—FVÒæ¶W—ÓÂ÷7G&öæsà¢Ç6ÖÆÃç¶—FVÒçF—FÆWÓÂ÷6ÖÆÃà¢ÂöF—cà¢ÂöF—cà¢¢Ò—Ğ¢ÂöF—cà¢ÆF—b6Æ74æÖSÒ'æVÂÖfö÷B#à¢—77VR7F—fR7¶FFç&öFÖæ7F—fUö—77VWÒ+r6÷W2×G&æ6†R¶FFæ7F—fU÷v÷&²ç7V&—FVÕö¶W’ÇÂ~(	BwĞ¢ÂöF—cà¢Âö'F–6ÆSà ¢Æ'F–6ÆR6Æ74æÖSÒ'æVÂ7F—fR×æVÂ#à¢ÆF—b6Æ74æÖSÒ'æVÂÖ†VFW"#à¢ÆF—cà¢Ç7â6Æ74æÖSÒ'æVÂÖ¶–6¶W"#åE$d”Â5D”cÂ÷7ãà¢Æƒ#â7¶FFæ7F—fU÷v÷&²æ—77VUöçVÖ&W'×¶FFæ7F—fU÷v÷&²ç7V&—FVÕö¶W’ò+rG¶FFæ7F—fU÷v÷&²ç7V&—FVÕö¶W—Ö¢rwÓÂöƒ#à¢ÂöF—cà¢ÆF—b6Æ74æÖSÒ'7FFR×7F6²#ç¶FFæ7F—fU÷v÷&²ç7FFW2æÖ‚‡7FFR’ÓâÅ7FFT&FvR¶W“×·7FFWÒfÇVS×·7FFWÒóâ—ÓÂöF—cà¢ÂöF—cà ¢¶FFæ7F—fU÷v÷&²ç7FÆÆVBbb€¢ÆF—b6Æ74æÖSÒ'7FÆÆVBÖ&ææW"#à¢Ç7G&öæsî)ªFWb&ö&&ÆVÖVçB',:§L:“Â÷7G&öæsà¢Ç7ãä4’&÷VvRFWV—2¶f÷&ÖDÖ–çWFW2†FFæ7F—fU÷v÷&²ç7FÆÆVEöFWF–Ç2æ6•öf–ÆVEöÖ–çWFW2—ÓÂ÷7ãà¢Ç7ãç¶FFæ7F—fU÷v÷&²ç7FÆÆVEöFWF–Ç2ææõöæWuö6öÖÖ—BòtV7Vâæ÷WfVR6öÖÖ—Br¢uVâ6öÖÖ—BÇW2,:–6VçBW†—7FRwÓÂ÷7ãà¢Ç7ãç¶FFæ7F—fU÷v÷&²ç7FÆÆVEöFWF–Ç2ææõö7F—fU÷v÷&¶fÆ÷ròtV7Vâv÷&¶fÆ÷r7F–br¢uv÷&¶fÆ÷r7F–bwÓÂ÷7ãà¢ÂöF—cà¢—Ğ ¢ÆFÂ6Æ74æÖSÒ&f7G2#à¢ÆF—cãÆGCä—77VSÂöGCãÆFCãÆ‡&Vc×¶FFæ7F—fU÷v÷&²æ—77VRçW&ÇÒF&vWCÒ%ö&Ææ²"&VÃÒ&æ÷&VfW'&W"#â7¶FFæ7F—fU÷v÷&²æ—77VRæçVÖ&W'Ò+r¶FFæ7F—fU÷v÷&²æ—77VRçF—FÆWÓÂöãÂöFCãÂöF—cà¢ÆF—cãÆGCå6÷W2×G&æ6†SÂöGCãÆFCç¶FFæ7F—fU÷v÷&²ç7V&—FVÕö¶W’ÇÂvV7VæR6÷W2×G&æ6†RW‡Æ–6—FRwÒ+r¶FFæ7F—fU÷v÷&²çF—FÆRÇÂ~(	BwÓÂöFCãÂöF—cà¢ÆF—cãÆGCäVæ6†:ææVÖVçCÂöGCãÆFCç¶FFæ7F—fU÷v÷&²æ6åö6†–åö&Æö6²òWF÷&—<:’Fç26R&Æö2‚G¶FFæ7F—fU÷v÷&²ç&VÖ–æ–æu÷7V&—FV×2æ¦ö–â‚r(i"r—Ò–¢væöâL:–GV—BWFöÖF—VVÖVçBwÓÂöFCãÂöF—cà¢ÆF—cãÆGCå#ÂöGCãÆFCç·&–Ö'•"òÆ‡&Vc×·&–Ö'•"çW&ÇÒF&vWCÒ%ö&Ææ²"&VÃÒ&æ÷&VfW'&W"#â7·&–Ö'•"æçVÖ&W'Ò+r·&–Ö'•"çF—FÆWÓÂöâ¢tV7VæR"76ö6œ:–RwÓÂöFCãÂöF—cà¢ÆF—cãÆGCä'&æ6†SÂöGCãÆFCç¶FFæ7F—fU÷v÷&²æ7F—fUö'&æ6‚òÆ6Æ74æÖSÒ&Ööæò"‡&Vc×¶FFæ7F—fU÷v÷&²æ7F—fUö'&æ6‚çW&ÇÒF&vWCÒ%ö&Ææ²"&VÃÒ&æ÷&VfW'&W"#ç¶FFæ7F—fU÷v÷&²æ7F—fUö'&æ6‚ææÖWÓÂöâ¢~(	BwÓÂöFCãÂöF—cà¢ÆF—cãÆGCäFW&æ–W"6öÖÖ—CÂöGCãÆFCç¶FFæ7F—fU÷v÷&²æÆ7Eö6öÖÖ—BòÆ‡&Vc×¶FFæ7F—fU÷v÷&²æÆ7Eö6öÖÖ—BçW&ÇÒF&vWCÒ%ö&Ææ²"&VÃÒ&æ÷&VfW'&W"#ãÇ7â6Æ74æÖSÒ&Ööæò#ç¶FFæ7F—fU÷v÷&²æÆ7Eö6öÖÖ—Bç6†÷'E÷6†ÓÂ÷7ãâ+r¶FFæ7F—fU÷v÷&²æÆ7Eö6öÖÖ—BæÖW76vWÓÂöâ¢~(	BwÓÂöFCãÂöF—cà¢ÆF—cãÆGCäÖW&vV&ÆSÂöGCãÆFCç·&–Ö'•"ò‡&–Ö'•"æÖW&vV&ÆRÓÓÒçVÆÂòv6Æ7VÂv—D‡V"VâGFVçFRr¢&–Ö'•"æÖW&vV&ÆRòv÷V’r¢væöâr’¢~(	BwÓÂöFCãÂöF—cà¢ÆF—cãÆGCäE#ÂöGCãÆFCãÆ‡&Vc×¶FFæ&6†—FV7GW&RçW&ÇÒF&vWCÒ%ö&Ææ²"&VÃÒ&æ÷&VfW'&W"#ç¶FFæ&6†—FV7GW&RæG'2æÆVæwF‡Ò,:—6VçB‡2“Âöç¶FFæ&6†—FV7GW&Rç&VfW&Væ6VEöG'2æÆVæwF‚ò+rG¶FFæ&6†—FV7GW&Rç&VfW&Væ6VEöG'2æÆVæwF‡Ò,:–l:—&Væ<:’‡2’"ÆR&Æö6¶¢rwÓÂöFCãÂöF—cà¢ÂöFÃà¢Âö'F–6ÆSà ¢Æ'F–6ÆR6Æ74æÖSÒ'æVÂ6’×æVÂ#à¢ÆF—b6Æ74æÖSÒ'æVÂÖ†VFW"#à¢ÆF—cà¢Ç7â6Æ74æÖSÒ'æVÂÖ¶–6¶W"#å"ò4“Â÷7ãà¢Æƒ#ç·'VâòG·'VâææÖWÒ2G·'Vâç'VåöçVÖ&W"óòrwÖ¢tV7VæR4’76ö6œ:–RwÓÂöƒ#à¢ÂöF—cà¢·'VãòçW&ÂbbÆ‡&Vc×·'VâçW&ÇÒF&vWCÒ%ö&Ææ²"&VÃÒ&æ÷&VfW'&W"#å'Vâ(isÂöçĞ¢ÂöF—cà ¢ÆF—b6Æ74æÖSÒ&6’×7VÖÖ'’#à¢Ç7ãì8—FB4“Â÷7ãà¢Ç7G&öæsç·'Vâò‡'Vâç7FGW2ÓÓÒv6ö×ÆWFVBrò'Vâæ6öæ6ÇW6–öâ¢'Vâç7FGW2’¢~(	BwÓÂ÷7G&öæsà¢ÂöF—cà ¢¶f–ÆVD¦ö'2æÆVæwF‚âbb€¢ÆF—b6Æ74æÖSÒ&f–ÆVBÖ¦ö'2#à¢Ç7ãä¦ö'2Vâ:–6†V3Â÷7ãà¢Ç7G&öæsç¶f–ÆVD¦ö'2æ¦ö–â‚rÂr—ÓÂ÷7G&öæsà¢ÂöF—cà¢—Ğ ¢·'Vãòæ¦ö'3òæÆVæwF‚ò€¢ÆF—b6Æ74æÖSÒ&¦ö'2#ç·'Vâæ¦ö'2æÖ‚†¦ö"’ÓâÄ¦ö$Æ–æR¶W“×¶¦ö"æ–Bóò¦ö"ææÖWÒ¦ö#×¶¦ö'Òóâ—ÓÂöF—cà¢’¢€¢ÆF—b6Æ74æÖSÒ&V×G’#äV7Vâ¦ö"v—D‡V"7F–öç276ö6œ:’:Æ"7F—fRãÂöF—cà¢—Ğ ¢ÆF—b6Æ74æÖSÒ'"ÖÆ—7B#à¢ÆF—b6Æ74æÖSÒ'6V7F–öâÖÆ&VÂ#å"÷WfW'FW2+r¶FFæ÷Vå÷'2æÆVæwF‡ÓÂöF—cà¢¶FFæ÷Vå÷'2æÆVæwF‚òFFæ÷Vå÷'2æÖ‚‡"’Óâ€¢Æ6Æ74æÖSÒ'"×&÷r"¶W“×·"æçVÖ&W'Ò‡&Vc×·"çW&ÇÒF&vWCÒ%ö&Ææ²"&VÃÒ&æ÷&VfW'&W"#à¢Ç7ãâ7·"æçVÖ&W'ÓÂ÷7ãà¢Ç7ãç·"çF—FÆWÓÂ÷7ãà¢Ç7ãç·7FGW4–6öâ†ÆFW7E'Vâ‡"“òç7FGW2ÂÆFW7E'Vâ‡"“òæ6öæ6ÇW6–öâ—ÓÂ÷7ãà¢Âöà¢’’¢ÆF—b6Æ74æÖSÒ&V×G’6ö×7B#äV7VæR"÷WfW'FRãÂöF—cçĞ¢ÂöF—cà¢Âö'F–6ÆSà¢Â÷6V7F–öãà ¢Ç6V7F–öâ6Æ74æÖSÒ&æW‡B×æVÂ#à¢ÆF—b6Æ74æÖSÒ&æW‡BÖ6÷’#à¢Ç7â6Æ74æÖSÒ'æVÂÖ¶–6¶W"#ääU…B5D”ôãÂ÷7ãà¢Æƒ#ç¶FFææW‡Eö7F–öçÓÂöƒ#à¢Ç&R6Æ74æÖSÒ'&ö×B×&Wf–Wr#ç¶FFæFWe÷&ö×GÓÂ÷&Sà¢ÂöF—cà¢ÆF—b6Æ74æÖSÒ&7F–öç2#à¢Æ'WGFöâ6Æ74æÖSÒ'&–Ö'’"G—SÒ&'WGFöâ"öä6Æ–6³×²‚’Óâfö–B6÷•&ö×B‚—Óç¶6÷–VBò~)É26÷œ:’r¢t6÷–W"&ö×BFWbwÓÂö'WGFöãà¢Æ6Æ74æÖS×¶'WGFöâG·&–Ö'•"òrr¢vF—6&ÆVBwÖÒ‡&Vc×·&–Ö'•#òçW&ÇÒF&vWCÒ%ö&Ææ²"&VÃÒ&æ÷&VfW'&W"#ä÷Wg&—"#Âöà¢Æ6Æ74æÖSÒ&'WGFöâ"‡&Vc×¶—77VUW&ÇÒF&vWCÒ%ö&Ææ²"&VÃÒ&æ÷&VfW'&W"#ä÷Wg&—"—77VSÂöà¢·'VãòçW&ÂbbÆ6Æ74æÖSÒ&'WGFöâ"‡&Vc×·'VâçW&ÇÒF&vWCÒ%ö&Ææ²"&VÃÒ&æ÷&VfW'&W"#ä÷Wg&—"'VãÂöçĞ¢ÂöF—cà¢Â÷6V7F–öãà ¢Æfö÷FW#à¢Ç7ãäFW&æ–W"6öÖÖ—BGRL:—;GB¢¶FFæÆFW7Eö6öÖÖ—BòÆ‡&Vc×¶FFæÆFW7Eö6öÖÖ—BçW&ÇÒF&vWCÒ%ö&Ææ²"&VÃÒ&æ÷&VfW'&W"#ãÇ7â6Æ74æÖSÒ&Ööæò#ç¶FFæÆFW7Eö6öÖÖ—Bç6†÷'E÷6†ÓÂ÷7ãâ+r¶FFæÆFW7Eö6öÖÖ—BæÖW76vWÓÂöâ¢~(	BwÓÂ÷7ãà¢Ç7ãä7GVÆ—<:’¶f÷&ÖDFFR†FFævVæW&FVEöB—Ò+rWFò×&Vg&W6‚c2+r5DÄÄTB(šR¶FFæ6öæf–rç7FÆÆVEögFW%öÖ–çWFW7ÒÖ–ãÂ÷7ãà¢Âöfö÷FW#à¢Âóà¢—Ğ¢ÂöÖ–ãà¢§Ğ 