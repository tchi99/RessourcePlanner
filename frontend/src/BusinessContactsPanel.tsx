import { FormEvent, useMemo, useState } from "react";

import {
  ApiError,
  BusinessContactReadModel,
  createBusinessContact,
  updateBusinessContact,
} from "./api";

function message(reason: unknown) {
  if (reason instanceof ApiError) return `${reason.message}${reason.code ? ` (${reason.code})` : ""}`;
  return reason instanceof Error ? reason.message : "Impossible d'enregistrer le contact.";
}

export default function BusinessContactsPanel({
  contacts,
  onChanged,
}: {
  contacts: BusinessContactReadModel[];
  onChanged: () => void;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [active, setActive] = useState(true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selected = useMemo(
    () => contacts.find((row) => row.id === selectedId) ?? null,
    [contacts, selectedId],
  );

  function edit(contact: BusinessContactReadModel) {
    setCreating(false);
    setSelectedId(contact.id);
    setName(contact.display_name);
    setEmail(contact.email ?? "");
    setPhone(contact.phone ?? "");
    setActive(contact.active);
    setError(null);
  }

  function create() {
    setCreating(true);
    setSelectedId(null);
    setName("");
    setEmail("");
    setPhone("");
    setActive(true);
    setError(null);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!name.trim() || pending) return;
    setPending(true);
    setError(null);
    try {
      if (creating) {
        await createBusinessContact({
          display_name: name.trim(),
          email: email.trim() || null,
          phone: phone.trim() || null,
          active,
          source: "LOCAL",
        });
      } else if (selected) {
        await updateBusinessContact(selected.id, {
          display_name: name.trim(),
          email: email.trim() || null,
          phone: phone.trim() || null,
          active,
          expected_version: selected.version,
        });
      }
      setCreating(false);
      setSelectedId(null);
      setName("");
      setEmail("");
      setPhone("");
      onChanged();
    } catch (reason) {
      setError(message(reason));
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="admin-card business-contact-panel">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">Référentiel métier</span>
          <h2>Contacts opérationnels</h2>
          <p>Personnes utilisées comme chargé de projet, responsable opérationnel ou coordonnateur. Aucun rôle d'accès n'est accordé ici.</p>
        </div>
        <button className="secondary-button" type="button" onClick={create}>+ Contact</button>
      </div>

      <div className="business-contact-grid">
        <div className="business-contact-list">
          {contacts.length === 0 && <p className="empty-admin-state">Aucun contact métier.</p>}
          {contacts.map((contact) => (
            <button
              type="button"
              key={contact.id}
              className={`resource-list-item ${selectedId === contact.id ? "selected" : ""} ${contact.active ? "" : "inactive"}`}
              onClick={() => edit(contact)}
            >
              <span className="resource-list-main">
                <strong>{contact.display_name}</strong>
                <small>{[contact.phone, contact.email].filter(Boolean).join(" · ") || "Coordonnées non renseignées"}</small>
              </span>
              <span className="resource-order">v{contact.version}</span>
            </button>
          ))}
        </div>

        {(creating || selected) && (
          <form className="admin-editor" onSubmit={submit}>
            <div className="editor-heading">
              <div><span className="eyebrow">{creating ? "Créer" : "Modifier"}</span><h3>Contact métier</h3></div>
              <button className="quiet-button" type="button" onClick={() => { setCreating(false); setSelectedId(null); }}>Fermer</button>
            </div>
            <label>Nom<input value={name} onChange={(event) => setName(event.target.value)} required /></label>
            <div className="form-grid two-columns">
              <label>Téléphone<input value={phone} onChange={(event) => setPhone(event.target.value)} /></label>
              <label>Courriel<input value={email} onChange={(event) => setEmail(event.target.value)} /></label>
            </div>
            <label className="checkbox-row">
              <input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} />
              Contact actif
            </label>
            {error && <div className="inline-error">{error}</div>}
            <div className="editor-actions">
              <button className="primary-button" type="submit" disabled={pending}>{pending ? "Enregistrement…" : "Enregistrer"}</button>
            </div>
          </form>
        )}
      </div>
    </section>
  );
}
