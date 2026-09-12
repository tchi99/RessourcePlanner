import { useMemo } from "react";

import { MediumTermCapacityBucketReadModel } from "./api";

function hours(value: number) {
  return `${new Intl.NumberFormat("fr-CA", { maximumFractionDigits: 1 }).format(value)} h`;
}

function weekLabel(value: string) {
  return new Intl.DateTimeFormat("fr-CA", { month: "short", day: "numeric" }).format(
    new Date(`${value}T12:00:00`),
  );
}

function CapacityCell({ bucket }: { bucket: MediumTermCapacityBucketReadModel }) {
  return (
    <div
      className={`mt-capacity-cell is-${bucket.state}`}
      title={[
        `Capacité ${hours(bucket.capacity_hours)}`,
        `Ferme ${hours(bucket.firm_hours)}`,
        `Tentative courante ${hours(bucket.current_potential_hours)}`,
        `Soumise additive ${hours(bucket.submitted_hours)}`,
        `Exposition ${hours(bucket.exposure_hours)}`,
        `Résiduel ${hours(bucket.residual_hours)}`,
        bucket.replacement_proposal_hours
          ? `Remplacement proposé ${hours(bucket.replacement_proposal_hours)} (delta ${hours(bucket.replacement_delta_hours)})`
          : "",
      ].filter(Boolean).join(" · ")}
    >
      <div className="mt-capacity-main">
        <strong>{hours(bucket.exposure_hours)}</strong>
        <span>/ {hours(bucket.capacity_hours)}</span>
      </div>
      <small>Résiduel {hours(bucket.residual_hours)}</small>
      <div className="mt-capacity-detail">
        <span>F {hours(bucket.firm_hours)}</span>
        {bucket.current_potential_hours > 0 && <span>T {hours(bucket.current_potential_hours)}</span>}
        {bucket.submitted_hours > 0 && <span>S {hours(bucket.submitted_hours)}</span>}
      </div>
      {bucket.replacement_proposal_hours > 0 && (
        <div className="mt-capacity-replacement">
          ↻ {hours(bucket.replacement_proposal_hours)} · Δ {hours(bucket.replacement_delta_hours)}
        </div>
      )}
    </div>
  );
}

export default function MediumTermCapacityPanel({
  buckets,
  loading,
}: {
  buckets: MediumTermCapacityBucketReadModel[];
  loading: boolean;
}) {
  const totals = useMemo(
    () => buckets.filter((bucket) => bucket.resource_class === null),
    [buckets],
  );
  const classes = useMemo(
    () => [...new Set(
      buckets
        .map((bucket) => bucket.resource_class)
        .filter((value): value is string => Boolean(value)),
    )].sort((left, right) => left.localeCompare(right, "fr-CA")),
    [buckets],
  );
  const byClassWeek = useMemo(
    () => new Map(
      buckets
        .filter((bucket) => bucket.resource_class !== null)
        .map((bucket) => [`${bucket.resource_class}|${bucket.week_start}`, bucket]),
    ),
    [buckets],
  );

  return (
    <section className={`mt-capacity-panel ${loading ? "is-loading" : ""}`}>
      <header className="mt-capacity-heading">
        <div>
          <span className="eyebrow">Capacité moyen terme</span>
          <h2>Charge et capacité standard</h2>
        </div>
        <p>
          F = ferme · T = plan courant tentative · S = demande soumise additive. Les propositions ↻ remplacent un plan existant et ne sont jamais additionnées à l’exposition.
        </p>
      </header>

      {!loading && totals.length === 0 ? (
        <div className="mt-capacity-empty">Aucune capacité disponible pour cet horizon.</div>
      ) : (
        <div className="mt-capacity-scroll">
          <div
            className="mt-capacity-grid"
            style={{ gridTemplateColumns: `170px repeat(${Math.max(totals.length, 1)}, minmax(138px, 1fr))` }}
          >
            <div className="mt-capacity-corner">Classe</div>
            {totals.map((bucket) => (
              <div className="mt-capacity-week" key={bucket.week_start}>
                <strong>{weekLabel(bucket.week_start)}</strong>
                <span>{weekLabel(bucket.week_end)}</span>
              </div>
            ))}

            <div className="mt-capacity-label">
              <strong>Équipe entière</strong>
              <span>Capacité globale</span>
            </div>
            {totals.map((bucket) => <CapacityCell bucket={bucket} key={`all-${bucket.week_start}`} />)}

            {classes.map((resourceClass) => (
              <div className="mt-capacity-row" key={resourceClass}>
                <div className="mt-capacity-label">
                  <strong>{resourceClass}</strong>
                  <span>Par classe de ressource</span>
                </div>
                {totals.map((week) => {
                  const bucket = byClassWeek.get(`${resourceClass}|${week.week_start}`);
                  return bucket
                    ? <CapacityCell bucket={bucket} key={`${resourceClass}-${week.week_start}`} />
                    : <div className="mt-capacity-cell is-unavailable" key={`${resourceClass}-${week.week_start}`}>—</div>;
                })}
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
