import { useEffect, useMemo, useState } from "react";

import {
  CommunicationBatch,
  CommunicationContact,
  CommunicationPreview,
  CommunicationReview,
  communicationBatchAction,
  getCommunicationPreview,
  listCommunicationBatches,
  listCommunicationContacts,
  prepareCommunicationBatch,
  saveCommunicationContact,
} from "./communicationsApi";

function nextMondayIso() {
  const today = new Date();
  const day = today.getDay();
  const daysUntilMonday = day === 0 ? 1 : 8 - day;
  const next = new Date(today);
  next.setDate(today.getDate() + daysUntilMonday);
  return next.toISOString().slice(0, 10);
}

function formatDateTime(value: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("fr-CA", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

type DraftState = CommunicationReview & { recipient_email: string };

export default function CommunicationsPage() {
  const [weekStart, setWeekStart] = useState(nextMondayIso);
  const [contacts, setContacts] = useState<CommunicationContact[]>([]);
  const [batches, setBatches] = useState<CommunicationBatch[]>([]);
  const [preview, setPreview] = useState<CommunicationPreview | null>(null);
  const [drafts, setDrafts] = useState<DraftState[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const missingContactSet = useMemo(
    () => new Set(preview?.missing_contact_ids ?? []),
    [preview],
  );

  async function reloadLists() {
    const [contactRows, batchRows] = await Promise.all([
      listCommunicationContacts(),
      listCommunicationBatches(weekStart),
    ]);
    setContacts(contactRows);
    setBatches(batchRows);
  }

  useEffect(() => {
    setPreview(null);
    setDrafts([]);
    setError(null);
    void reloadLists().catch((reason: unknown) => {
      setError(reason instanceof Error ? reason.message : "Impossible de charger les communications.");
    });
  }, [weekStart]);

  async function runPreview() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const row = await getCommunicationPreview(weekStart);
      setPreview(row);
      setDrafts(
        row.drafts.map((draft) => ({
          audience: draft.audience,
          recipient_id: draft.recipient_id,
          recipient_email: draft.recipient_email,
          include: true,
          subject: draft.subject,
          body: draft.body,
        })),
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Prévisualisation impossible.");
    } finally {
      setBusy(false);
    }
  }

  async function saveContact(contact: CommunicationContact) {
    setBusy(true);
    setError(null);
    try {
      const saved = await saveCommunicationContact(contact);
      setContacts((rows) => rows.map((row) => row.recipient_id === saved.recipient_id ? saved : row));
      setNotice(`Contact ${saved.display_name} enregistré.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Enregistrement impossible.");
    } finally {
      setBusy(false);
    }
  }

  async function prepare() {
    if (!preview) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await prepareCommunicationBatch(
        preview.week_start,
        preview.snapshot_fingerprint,
        drafts.map(({ recipient_email: _recipientEmail, ...row }) => row),
      );
      setNotice("Lot préparé. Aucun message n’a été envoyé.");
      setPreview(null);
      setDrafts([]);
      await reloadLists();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Préparation impossible.");
    } finally {
      setBusy(false);
    }
  }

  async function batchAction(
    batch: CommunicationBatch,
    action: "approve" | "cancel" | "mark-communicated",
  ) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await communicationBatchAction(batch.id, action);
      setNotice(
        action === "approve"
          ? "Lot approuvé. Aucun message n’a été envoyé."
          : action === "mark-communicated"
            ? "Lot confirmé comme communiqué."
            : "Lot annulé.",
      );
      await reloadLists();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Action impossible.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="communications-page">
      <header className="communications-header">
        <div>
          <span className="eyebrow">Révision manuelle</span>
          <h2>Communications de planification</h2>
          <p>
            Préparez, révisez et approuvez les messages. Cette version ne transmet aucun
            courriel et ne crée aucun brouillon M365 automatiquement.
          </p>
        </div>
        <label>
          Semaine du
          <input type="date" value={weekStart} onChange={(event) => setWeekStart(event.target.value)} />
        </label>
      </header>

      {error && <div className="error-panel"><strong>Erreur</strong><span>{error}</span></div>}
      {notice && <div className="communications-notice">{notice}</div>}

      <div className="communications-grid">
        <section className="communications-card contacts-card">
          <div className="communications-card-heading">
            <div>
              <span className="eyebrow">Répertoire explicite</span>
              <h3>Contacts</h3>
            </div>
            <span>{contacts.length} contact(s)</span>
          </div>
          <p className="communications-help">
            Les adresses ne sont jamais déduites d’un nom. Les techniciens sont liés à une ressource
            stable; les chargés de projet nécessitent un identifiant externe stable.
          </p>
          <div className="contacts-list">
            {contacts.map((contact) => (
              <div
                className={`contact-row ${missingContactSet.has(contact.recipient_id) ? "is-missing" : ""}`}
                key={contact.recipient_id}
              >
                <div className="contact-identity">
                  <strong>{contact.display_name}</strong>
                  <small>{contact.audience === "technician" ? "Technicien" : "Chargé de projet"}</small>
                </div>
                <input
                  type="email"
                  aria-label={`Courriel de ${contact.display_name}`}
                  placeholder="adresse@entreprise"
                  value={contact.email ?? ""}
                  onChange={(event) => setContacts((rows) => rows.map((row) =>
                    row.recipient_id === contact.recipient_id ? { ...row, email: event.target.value || null } : row
                  ))}
                />
                <label className="contact-active">
                  <input
                    type="checkbox"
                    checked={contact.active}
                    onChange={(event) => setContacts((rows) => rows.map((row) =>
                      row.recipient_id === contact.recipient_id ? { ...row, active: event.target.checked } : row
                    ))}
                  />
                  Actif
                </label>
                <button type="button" disabled={busy} onClick={() => void saveContact(contact)}>
                  Enregistrer
                </button>
              </div>
            ))}
          </div>
        </section>

        <section className="communications-card preview-card">
          <div className="communications-card-heading">
            <div>
              <span className="eyebrow">Planning courant</span>
              <h3>Prévisualisation</h3>
            </div>
            <button type="button" disabled={busy} onClick={() => void runPreview()}>
              Générer la prévisualisation
            </button>
          </div>

          {!preview ? (
            <p className="communications-empty">Aucune prévisualisation générée.</p>
          ) : (
            <>
              <div className="preview-summary">
                <strong>{preview.mode === "weekly_plan" ? "Plan hebdomadaire" : "Avis de modification"}</strong>
                <span>{preview.drafts.length} message(s)</span>
                <span>{preview.has_communicated_baseline ? "Snapshot communiqué trouvé" : "Premier envoi de cette semaine"}</span>
              </div>
              {preview.missing_contact_ids.length > 0 && (
                <div className="communications-warning">
                  Coordonnées manquantes : {preview.missing_contact_ids.join(", ")}. Complétez-les avant de préparer le lot.
                </div>
              )}
              {drafts.length === 0 ? (
                <p className="communications-empty">Aucun changement à communiquer pour cette version.</p>
              ) : (
                <div className="draft-list">
                  {drafts.map((draft, index) => (
                    <article className="draft-card" key={`${draft.audience}:${draft.recipient_id}`}>
                      <div className="draft-heading">
                        <label>
                          <input
                            type="checkbox"
                            checked={draft.include}
                            onChange={(event) => setDrafts((rows) => rows.map((row, rowIndex) =>
                              rowIndex === index ? { ...row, include: event.target.checked } : row
                            ))}
                          />
                          Inclure
                        </label>
                        <span>{draft.recipient_email}</span>
                      </div>
                      <input
                        className="draft-subject"
                        value={draft.subject}
                        onChange={(event) => setDrafts((rows) => rows.map((row, rowIndex) =>
                          rowIndex === index ? { ...row, subject: event.target.value } : row
                        ))}
                      />
                      <textarea
                        rows={9}
                        value={draft.body}
                        onChange={(event) => setDrafts((rows) => rows.map((row, rowIndex) =>
                          rowIndex === index ? { ...row, body: event.target.value } : row
                        ))}
                      />
                    </article>
                  ))}
                </div>
              )}
              <div className="communications-actions">
                <button
                  type="button"
                  disabled={busy || drafts.length === 0 || preview.missing_contact_ids.length > 0}
                  onClick={() => void prepare()}
                >
                  Préparer le lot
                </button>
                <small>Cette action persiste la révision. Elle n’envoie rien.</small>
              </div>
            </>
          )}
        </section>
      </div>

      <section className="communications-card batches-card">
        <div className="communications-card-heading">
          <div>
            <span className="eyebrow">Journal SQL</span>
            <h3>Lots de la semaine</h3>
          </div>
          <span>{batches.length} lot(s)</span>
        </div>
        {batches.length === 0 ? (
          <p className="communications-empty">Aucun lot préparé pour cette semaine.</p>
        ) : (
          <div className="batch-list">
            {batches.map((batch) => {
              const included = batch.messages.filter((message) => message.included).length;
              return (
                <article className={`batch-row status-${batch.status.toLowerCase()}`} key={batch.id}>
                  <div>
                    <strong>{batch.kind === "weekly_plan" ? "Plan hebdomadaire" : "Modification"}</strong>
                    <span>{batch.status} · {included}/{batch.messages.length} message(s) inclus</span>
                    <small>Préparé {formatDateTime(batch.prepared_at)} par {batch.prepared_by ?? "—"}</small>
                    {batch.stale && <small className="stale-label">Le planning a changé depuis ce lot.</small>}
                  </div>
                  <div className="batch-actions">
                    {batch.status === "PREPARED" && (
                      <button type="button" disabled={busy || batch.stale} onClick={() => void batchAction(batch, "approve")}>Approuver</button>
                    )}
                    {(batch.status === "PREPARED" || batch.status === "APPROVED") && (
                      <button type="button" className="secondary" disabled={busy} onClick={() => void batchAction(batch, "cancel")}>Annuler</button>
                    )}
                    {batch.status === "APPROVED" && (
                      <button type="button" disabled={busy || batch.stale} onClick={() => void batchAction(batch, "mark-communicated")}>Confirmer communiqué</button>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        )}
        <p className="communications-help">
          « Confirmer communiqué » enregistre uniquement le snapshot de référence pour détecter les futurs changements. Aucun transport n’est exécuté.
        </p>
      </section>
    </section>
  );
}
