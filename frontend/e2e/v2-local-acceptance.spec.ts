import { Browser, BrowserContext, Locator, Page, expect, test } from "@playwright/test";

const BASE_URL = process.env.RESOURCEPLANNER_E2E_BASE_URL || "http://127.0.0.1:8765";

type Role = "ADMIN" | "PROJECT_MANAGER" | "COORDINATOR" | "TECHNICIAN";

const TEST_DOMAIN = "example.test";

function testEmail(localPart: string) {
  return `${localPart}${String.fromCharCode(64)}${TEST_DOMAIN}`;
}

function testPhone() {
  return ["450", "555", "0199"].join("-");
}

const DISPLAY_NAMES: Record<Role, string> = {
  ADMIN: "Administrateur E2E",
  PROJECT_MANAGER: "Chargé E2E",
  COORDINATOR: "Coordonnateur E2E",
  TECHNICIAN: "Technicien Alice",
};

function addDays(value: Date, days: number) {
  const next = new Date(value);
  next.setDate(next.getDate() + days);
  return next;
}

function localIso(value: Date) {
  const adjusted = new Date(value.getTime() - value.getTimezoneOffset() * 60_000);
  return adjusted.toISOString().slice(0, 10);
}

function startOfWeek(value: Date) {
  const day = value.getDay();
  return addDays(value, -(day === 0 ? 6 : day - 1));
}

function acceptanceDates() {
  const today = new Date();
  const nextMonday = addDays(startOfWeek(today), 7);
  return {
    today: localIso(today),
    d1: localIso(nextMonday),
    d2: localIso(addDays(nextMonday, 1)),
    d3: localIso(addDays(nextMonday, 2)),
    d4: localIso(addDays(nextMonday, 3)),
    d5: localIso(addDays(nextMonday, 4)),
  };
}

async function openAs(browser: Browser, role?: Role) {
  const context = await browser.newContext({
    baseURL: BASE_URL,
    locale: "fr-CA",
    extraHTTPHeaders: role ? { "X-E2E-Role": role } : { "X-E2E-Anonymous": "1" },
  });
  const page = await context.newPage();
  await page.goto("/");
  if (role) await expect(page.locator(".sidebar-footer")).toContainText(DISPLAY_NAMES[role]);
  return { context, page };
}

async function closeContext(context: BrowserContext) {
  await context.close();
}

async function navigateMain(page: Page, label: string) {
  await page.locator(".main-nav").getByRole("button", { name: new RegExp(label, "i") }).click();
}

function labelled(scope: Locator, label: string, control: "select" | "input" | "textarea") {
  return scope.locator("label").filter({ hasText: label }).first().locator(control);
}

async function dragWithDataTransfer(page: Page, source: Locator, target: Locator) {
  const dataTransfer = await page.evaluateHandle(() => new DataTransfer());
  await source.dispatchEvent("dragstart", { dataTransfer });
  await target.dispatchEvent("dragenter", { dataTransfer });
  await target.dispatchEvent("dragover", { dataTransfer });
  await target.dispatchEvent("drop", { dataTransfer });
  await source.dispatchEvent("dragend", { dataTransfer });
  await dataTransfer.dispose();
}

async function selectOptionContaining(select: Locator, text: string) {
  const option = select.locator("option", { hasText: text }).first();
  await expect(option).toBeAttached();
  const value = await option.getAttribute("value");
  expect(value).not.toBeNull();
  await select.selectOption(value!);
}

function demandNumberFrom(text: string | null) {
  const match = String(text || "").match(/\b(DMO-[A-Za-z0-9-]+)\b/);
  expect(match, `Numéro de demande introuvable dans: ${text}`).not.toBeNull();
  return match![1];
}

async function createDemand(
  page: Page,
  input: {
    start: string;
    end: string;
    priority?: string;
    hours: string;
    activeDays: string;
    description: string;
    proposedResource?: string;
    workPackage?: string;
  },
) {
  await navigateMain(page, "Demandes");
  await expect(page.getByRole("heading", { name: "Demandes", level: 1 })).toBeVisible();
  await page.getByRole("button", { name: /Nouvelle demande/ }).click();
  const editor = page.locator(".demand-editor-form");
  await expect(editor.getByRole("heading", { name: "Nouvelle demande" })).toBeVisible();

  await labelled(editor, "Projet", "select").selectOption("P-251");
  await labelled(editor, "Recherche catalogue ERP", "input").fill("automatisation");
  const taskSelect = labelled(editor, "Tâche ERP", "select");
  await expect(taskSelect.locator("option", { hasText: "210 — AUTOMATISATION E2E" })).toBeAttached();
  await taskSelect.selectOption("210");
  if (input.workPackage) {
    await selectOptionContaining(labelled(editor, "Plage moyen terme", "select"), input.workPackage);
  }
  await labelled(editor, "Priorité", "select").selectOption(input.priority || "Normale");
  await labelled(editor, "Confirmation", "select").selectOption("Confirmée");
  await labelled(editor, "Début souhaité", "input").fill(input.start);
  await labelled(editor, "Fin souhaitée", "input").fill(input.end);
  await labelled(editor, "Heures estimées totales", "input").fill(input.hours);
  await labelled(editor, "Jours actifs souhaités", "input").fill(input.activeDays);
  await labelled(editor, "Description", "textarea").fill(input.description);
  if (input.proposedResource) {
    await labelled(editor, "Ressource proposée", "select").selectOption(input.proposedResource);
  }
  return editor;
}

async function openDemandDetail(page: Page, demandNumber: string) {
  await navigateMain(page, "Demandes");
  const demandSubnav = page.locator(".demands-subnav");
  if (await demandSubnav.isVisible()) {
    const requestsButton = demandSubnav.getByRole("button", { name: "Demandes", exact: true });
    if (await requestsButton.count()) {
      await requestsButton.click();
    }
  }
  const card = page.locator(".demand-card").filter({ hasText: demandNumber }).first();
  await expect(card).toBeVisible();
  await card.click();
  await expect(page.locator(`.demand-detail-context[data-demand-number="${demandNumber}"]`)).toBeVisible();
}

async function workflowSelect(page: Page, demandNumber: string) {
  await openDemandDetail(page, demandNumber);
  const section = page.locator(".demand-detail-section").filter({ hasText: "Workflow et impact" }).first();
  const isOpen = await section.evaluate((node) => (node as HTMLDetailsElement).open);
  if (!isOpen) {
    await section.locator("summary").click();
  }
  await expect(section.locator(".workflow-detail-panel")).toBeVisible();
}

async function periodsSelect(page: Page, demandNumber: string) {
  await openDemandDetail(page, demandNumber);
  const section = page.locator(".demand-detail-section").filter({ hasText: "Périodes de travail" }).first();
  const isOpen = await section.evaluate((node) => (node as HTMLDetailsElement).open);
  if (!isOpen) {
    await section.locator("summary").click();
  }
  await expect(section.locator(".period-demand-summary")).toBeVisible();
}

test("V2 local acceptance path runs through React, Chromium, FastAPI and SQLite", async ({ browser }) => {
  test.setTimeout(240_000);
  const { today, d1, d2, d3, d4, d5 } = acceptanceDates();
  let demandNumber = "";
  let urgentNumber = "";

  await test.step("401 and role-guided shell are visible in React", async () => {
    const anonymous = await openAs(browser);
    await expect(anonymous.page.getByRole("heading", { name: "Connexion requise" })).toBeVisible();
    await expect(anonymous.page.getByText("session RessourcePlanner est absente ou expirée", { exact: false })).toBeVisible();
    await closeContext(anonymous.context);

    const admin = await openAs(browser, "ADMIN");
    await expect(admin.page.locator(".main-nav").getByText("Ressources", { exact: true })).toBeVisible();
    await expect(admin.page.locator(".main-nav").getByText("Utilisateurs", { exact: true })).toBeVisible();
    await expect(admin.page.locator(".main-nav").getByText("Configuration", { exact: true })).toBeVisible();

    await navigateMain(admin.page, "Configuration");
    await expect(admin.page.getByRole("heading", { name: "Configuration", level: 2 })).toBeVisible();
    const smtpForm = admin.page.locator(".smtp-form");
    await labelled(smtpForm, "Serveur SMTP", "input").fill("smtp.example.invalid");
    await labelled(smtpForm, "Port", "input").fill("587");
    await labelled(smtpForm, "Sécurité", "select").selectOption("STARTTLS");
    await labelled(smtpForm, "Courriel expéditeur", "input").fill(testEmail("planning"));
    await smtpForm.getByLabel("Envoi SMTP activé").check();
    await smtpForm.getByRole("button", { name: "Enregistrer", exact: true }).click();
    await expect(admin.page.locator(".configuration-notice")).toContainText("Configuration SMTP enregistrée");
    await smtpForm.getByRole("button", { name: "Tester la connexion enregistrée" }).click();
    await expect(admin.page.locator(".configuration-notice")).toContainText("Connexion SMTP réussie");
    await closeContext(admin.context);

    const projectManager = await openAs(browser, "PROJECT_MANAGER");
    await expect(projectManager.page.locator(".main-nav").getByText("Communications", { exact: true })).toHaveCount(0);
    await expect(projectManager.page.locator(".main-nav").getByText("Ressources", { exact: true })).toHaveCount(0);
    await expect(projectManager.page.locator(".main-nav").getByText("Utilisateurs", { exact: true })).toHaveCount(0);
    await expect(projectManager.page.locator(".main-nav").getByText("Configuration", { exact: true })).toHaveCount(0);
    await closeContext(projectManager.context);
  });

  await test.step("project manager creates WorkPackage, demand, periods and selected alternative", async () => {
    const { context, page } = await openAs(browser, "PROJECT_MANAGER");

    await navigateMain(page, "Moyen terme");
    await page.getByRole("button", { name: /WorkPackage/ }).click();
    const workPackageDialog = page.getByRole("dialog", { name: "Créer un lot" });
    await labelled(workPackageDialog, "Projet", "select").selectOption("P-251");
    await labelled(workPackageDialog, "Code", "input").fill("WP-E2E");
    await labelled(workPackageDialog, "Nom", "input").fill("Lot acceptation Playwright");
    await labelled(workPackageDialog, "Début", "input").fill(d1);
    await labelled(workPackageDialog, "Fin", "input").fill(d5);
    await labelled(workPackageDialog, "Heures prévues", "input").fill("40");
    await labelled(workPackageDialog, "Description", "textarea").fill("Parcours React V2 avec Chromium");
    await workPackageDialog.getByRole("button", { name: "Créer le WorkPackage" }).click();
    await expect(workPackageDialog).toBeHidden();
    await expect(page.getByText("WP-E2E", { exact: true }).first()).toBeVisible();

    const editor = await createDemand(page, {
      start: d1,
      end: d5,
      hours: "20",
      activeDays: "6",
      description: "Demande acceptation navigateur V2",
      proposedResource: "Alice",
      workPackage: "WP-E2E",
    });
    await editor.getByRole("button", { name: "Créer le brouillon" }).click();
    await expect(page.locator(".error-panel")).toContainText("cible de 6 jours actifs dépasse les 5 dates");

    await labelled(editor, "Jours actifs souhaités", "input").fill("4");
    await editor.getByRole("button", { name: "Créer le brouillon" }).click();
    const createdNotice = page.locator(".demand-notice");
    await expect(createdNotice).toContainText("créée en brouillon");
    demandNumber = demandNumberFrom(await createdNotice.textContent());
    await expect(page.locator(".demand-editor-panel")).toContainText(demandNumber);

    await periodsSelect(page, demandNumber);
    await page.getByRole("button", { name: /Période cumulative/ }).click();
    await page.getByRole("button", { name: /Groupe alternatif/ }).click();

    const cumulative = page.locator(".period-card.cumulative").first();
    await labelled(cumulative, "Début", "input").fill(d1);
    await labelled(cumulative, "Fin", "input").fill(d3);
    await labelled(cumulative, "Heures totales", "input").fill("12");
    await labelled(cumulative, "Ressources simultanées", "input").fill("1");
    await labelled(cumulative, "Jours actifs souhaités", "input").fill("3");
    await labelled(cumulative, "Confirmation", "select").selectOption("Tentative");
    await labelled(cumulative, "Ressource proposée", "select").selectOption("Alice");

    const alternatives = page.locator(".alternative-option");
    await expect(alternatives).toHaveCount(2);
    for (const [card, day, confirmation] of [
      [alternatives.nth(0).locator(".period-card"), d4, "Confirmée"],
      [alternatives.nth(1).locator(".period-card"), d5, "Tentative"],
    ] as const) {
      await labelled(card, "Début", "input").fill(day);
      await labelled(card, "Fin", "input").fill(day);
      await labelled(card, "Heures totales", "input").fill("8");
      await labelled(card, "Ressources simultanées", "input").fill("1");
      await labelled(card, "Jours actifs souhaités", "input").fill("1");
      await labelled(card, "Confirmation", "select").selectOption(confirmation);
      await labelled(card, "Ressource proposée", "select").selectOption("Bob");
    }

    await page.getByRole("button", { name: "Enregistrer les périodes" }).click();
    await expect(page.locator(".demand-notice").filter({ hasText: "Périodes enregistrées." })).toHaveText("Périodes enregistrées.");
    await alternatives.nth(0).getByRole("button", { name: "Retenir cette option" }).click();
    await expect(alternatives.nth(0).getByRole("button", { name: "Option retenue" })).toBeVisible();

    await workflowSelect(page, demandNumber);
    await page.getByRole("button", { name: "Soumettre", exact: true }).click();
    await expect(page.locator(".demand-notice").filter({ hasText: "soumise pour approbation" })).toContainText("soumise pour approbation");
    await expect(page.getByTestId("plan-delta-preview")).toBeVisible();

    await expect(
      page.getByRole("button", { name: "Approuver", exact: true }),
    ).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Segments", exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Urgence", exact: true })).toHaveCount(0);

    await closeContext(context);
  });

  await test.step("coordinator approves, sees generated segments and current plan", async () => {
    const { context, page } = await openAs(browser, "COORDINATOR");
    await navigateMain(page, "Demandes");
    await workflowSelect(page, demandNumber);
    await expect(page.getByTestId("plan-delta-preview")).toContainText("Plan actuel → plan proposé");
    await page.getByLabel(/Commentaire d’approbation/).fill("Acceptation initiale Playwright");
    await page.getByRole("button", { name: "Approuver", exact: true }).click();
    await expect(page.locator(".demand-notice").filter({ hasText: "Demande approuvée" })).toContainText("Demande approuvée");

    await page.getByRole("button", { name: "Segments", exact: true }).click();
    await page.locator(".segment-demand-card").filter({ hasText: demandNumber }).click();
    const segmentCards = page.locator(".segment-list .segment-card");
    await expect(segmentCards).toHaveCount(2);
    const cumulativeCard = segmentCards.filter({ hasText: d1 }).filter({ hasText: d3 }).first();
    const alternativeCard = segmentCards.filter({ hasText: d4 }).first();
    await expect(cumulativeCard).toContainText("12 h");
    await expect(cumulativeCard).toContainText("Tentative");
    await expect(cumulativeCard).toContainText("Cible 3 jour(s) actif(s)");
    await expect(alternativeCard).toContainText("8 h");
    await expect(alternativeCard).toContainText("Confirmée");

    await navigateMain(page, "Planning opérationnel");
    await page.getByRole("button", { name: /Suivante/ }).click();
    await page.getByLabel("Recherche").fill(demandNumber);
    await expect(page.locator(".shift-card")).toHaveCount(4);
    await expect(page.locator(".shift-card").filter({ hasText: "Tentative" }).first()).toBeVisible();
    await expect(page.locator(".shift-card").filter({ hasText: "Confirmée" }).first()).toBeVisible();

    await closeContext(context);
  });

  await test.step("approved envelope change shows read-only delta before reapproval", async () => {
    const projectManager = await openAs(browser, "PROJECT_MANAGER");
    await navigateMain(projectManager.page, "Demandes");
    await periodsSelect(projectManager.page, demandNumber);
    const cumulative = projectManager.page.locator(".period-card.cumulative").first();
    await labelled(cumulative, "Heures totales", "input").fill("16");
    await projectManager.page.getByRole("button", { name: "Enregistrer les périodes" }).click();
    await expect(projectManager.page.locator(".demand-notice").filter({ hasText: "doit être approuvée de nouveau" })).toContainText("doit être approuvée de nouveau");

    const firstAlternative = projectManager.page.locator(".alternative-option").nth(0);
    await firstAlternative.getByRole("button", { name: "Retenir cette option" }).click();
    await expect(firstAlternative.getByRole("button", { name: "Option retenue" })).toBeVisible();

    await workflowSelect(projectManager.page, demandNumber);
    await expect(projectManager.page.getByTestId("approval-state")).toContainText("CAPTURED");
    await expect(projectManager.page.getByTestId("envelope-decision")).toContainText(
      "Réapprobation requise",
    );
    await expect(projectManager.page.getByTestId("envelope-decision")).toContainText(
      "l’ancien plan reste la référence",
    );
    const delta = projectManager.page.getByTestId("plan-delta-preview");
    await expect(delta).toContainText("Plan actuel → plan proposé");
    await expect(delta.locator(".plan-delta-row").first()).toBeVisible();
    await closeContext(projectManager.context);

    const coordinator = await openAs(browser, "COORDINATOR");
    await navigateMain(coordinator.page, "Demandes");
    await workflowSelect(coordinator.page, demandNumber);
    await expect(coordinator.page.getByTestId("plan-delta-preview").locator(".plan-delta-row").first()).toBeVisible();
    await coordinator.page.getByLabel(/Commentaire d’approbation/).fill("Réapprobation après delta Playwright");
    await coordinator.page.getByRole("button", { name: "Approuver", exact: true }).click();
    await expect(coordinator.page.locator(".demand-notice").filter({ hasText: "Demande approuvée" })).toContainText("Demande approuvée");
    await closeContext(coordinator.context);
  });

  await test.step("segment profile, active days and audit are editable through React", async () => {
    const { context, page } = await openAs(browser, "COORDINATOR");
    await navigateMain(page, "Demandes");
    await page.getByRole("button", { name: "Segments", exact: true }).click();
    await page.locator(".segment-demand-card").filter({ hasText: demandNumber }).click();
    const cumulativeCard = page.locator(".segment-list .segment-card").filter({ hasText: d1 }).filter({ hasText: d3 }).first();
    await expect(cumulativeCard).toContainText("16 h");
    await cumulativeCard.click();

    const dialog = page.getByRole("dialog", { name: "Modifier le segment" });
    await labelled(dialog, "Profil de charge", "select").selectOption("BELL");
    await labelled(dialog, "Description", "textarea").fill("Profil en cloche validé par Playwright");
    await dialog.getByRole("button", { name: "Enregistrer", exact: true }).click();
    await expect(dialog).toBeHidden();

    const refreshedCard = page.locator(".segment-list .segment-card").filter({ hasText: d1 }).filter({ hasText: d3 }).first();
    await expect(refreshedCard).toContainText("Charge en cloche");
    await expect(refreshedCard).toContainText("Cible 3 jour(s) actif(s)");
    await refreshedCard.click();
    const reopened = page.getByRole("dialog", { name: "Modifier le segment" });
    await expect(labelled(reopened, "Profil de charge", "select")).toHaveValue("BELL");
    await expect(reopened.getByLabel("Historique des changements")).toContainText("Coordonnateur E2E");
    await reopened.getByRole("button", { name: "Fermer" }).first().click();

    await closeContext(context);
  });

  await test.step("editing a shift forces an explicit overallocation decision and keeps audit visible", async () => {
    const { context, page } = await openAs(browser, "COORDINATOR");
    await navigateMain(page, "Planning opérationnel");
    await page.getByRole("button", { name: /Suivante/ }).click();
    await page.getByLabel("Recherche").fill(demandNumber);

    const bobRow = page.locator(".resource-row").filter({ hasText: "Bob" });
    await expect(bobRow).toBeVisible();
    await bobRow.getByRole("button", { name: /Modifier le quart P-251, 8 heures/ }).first().click();
    let dialog = page.getByRole("dialog", { name: "Modifier le quart" });
    await labelled(dialog, "Heures", "input").fill("10");
    await dialog.getByRole("button", { name: "Enregistrer les modifications" }).click();
    const choice = dialog.getByRole("alert");
    await expect(choice).toContainText("dépasse les heures prévues du segment");
    await choice.getByRole("button", { name: /Conserver la dérogation/ }).click();
    await expect(dialog).toBeHidden();

    const updatedBobRow = page.locator(".resource-row").filter({ hasText: "Bob" });
    await updatedBobRow.getByRole("button", { name: /Modifier le quart P-251, 10 heures/ }).first().click();
    dialog = page.getByRole("dialog", { name: "Modifier le quart" });
    await expect(dialog).toContainText("Surallocation manuelle active : +2 h");
    await expect(dialog.getByLabel("Historique des changements")).toContainText("Coordonnateur E2E");
    await dialog.getByRole("button", { name: "Fermer" }).first().click();

    await closeContext(context);
  });

  await test.step("communications use project To/CC, manual review and only create fake local drafts", async () => {
    const { context, page } = await openAs(browser, "COORDINATOR");
    await navigateMain(page, "Communications");
    await expect(page.getByRole("heading", { name: "Communications de planification" })).toBeVisible();
    await expect(page.getByText("Destinataires gérés dans Utilisateurs")).toBeVisible();
    await expect(page.locator(".contact-row")).toHaveCount(0);

    await page.getByLabel("Semaine du").fill(d1);
    await page.getByRole("button", { name: "Générer la prévisualisation" }).click();

    const draft = page.locator(".draft-card").filter({ hasText: "Projet P-251" }).first();
    await expect(draft).toBeVisible();
    await expect(draft.locator(".draft-recipients")).toContainText(testEmail("pm"));
    await expect(draft.locator(".draft-recipients")).toContainText(testEmail("alice"));
    await expect(draft.locator(".draft-recipients")).toContainText(testEmail("bob"));
    await expect(draft.getByText("Courriel manquant")).toHaveCount(0);
    await expect(draft.locator("textarea")).toHaveValue(/Chargé de projet Démo/);
    await expect(draft.locator("textarea")).toHaveValue(new RegExp(testPhone()));
    await draft.locator(".draft-subject").fill("Confirmation E2E — P-251");

    await page.getByRole("button", { name: "Préparer le lot" }).click();
    await expect(page.locator(".communications-notice")).toContainText("Lot projet préparé");

    const batch = page.locator(".batch-row").first();
    await expect(batch).toContainText("Sujet : Confirmation E2E — P-251");
    await expect(batch).toContainText(`To : ${testEmail("pm")}`);
    await expect(batch).toContainText(testEmail("alice"));
    await expect(batch).toContainText(testEmail("bob"));

    await batch.getByRole("button", { name: "Approuver" }).click();
    await expect(page.locator(".communications-notice")).toContainText("Lot projet approuvé");
    page.once("dialog", (dialog) => dialog.accept());
    await page.locator(".batch-row").first().getByRole("button", { name: "Créer brouillons M365" }).click();
    await expect(page.locator(".communications-notice")).toContainText("brouillon(s) M365 créé(s)");

    page.once("dialog", (dialog) => dialog.accept());
    await page.locator(".batch-row").first().getByRole("button", { name: "Envoyer par SMTP" }).click();
    await expect(page.locator(".communications-notice")).toContainText("Envoi SMTP complété");
    await expect(page.locator(".batch-row").first()).toContainText("COMMUNICATED");
    await expect(page.locator(".batch-row").first()).toContainText("SMTP : SENT");
    await expect(page.locator(".batch-row").first().getByRole("button", { name: "Envoyer par SMTP" })).toHaveCount(0);
    await closeContext(context);
  });

  await test.step("demand history exposes backend audit actors", async () => {
    const { context, page } = await openAs(browser, "COORDINATOR");
    await openDemandDetail(page, demandNumber);
    const historySection = page.locator(".demand-detail-section").filter({ hasText: "Historique" }).first();
    const isOpen = await historySection.evaluate((node) => (node as HTMLDetailsElement).open);
    if (!isOpen) {
      await historySection.locator("summary").click();
    }
    await expect(historySection.locator(".demand-history-timeline")).toContainText("Coordonnateur E2E");
    await expect(historySection.locator(".demand-history-timeline li").first()).toBeVisible();
    await closeContext(context);
  });

  await test.step("React-created Urgente demand can use emergency override and regular approval", async () => {
    const projectManager = await openAs(browser, "PROJECT_MANAGER");
    const editor = await createDemand(projectManager.page, {
      start: today,
      end: today,
      priority: "Urgente",
      hours: "4",
      activeDays: "1",
      description: "Intervention urgente créée dans React",
      proposedResource: "Alice",
    });
    await editor.getByRole("button", { name: "Créer le brouillon" }).click();
    const urgentNotice = projectManager.page.locator(".demand-notice");
    await expect(urgentNotice).toContainText("créée en brouillon");
    urgentNumber = demandNumberFrom(await urgentNotice.textContent());
    await workflowSelect(projectManager.page, urgentNumber);
    await projectManager.page.getByRole("button", { name: "Soumettre", exact: true }).click();
    await expect(projectManager.page.locator(".demand-notice").filter({ hasText: "soumise pour approbation" })).toContainText("soumise pour approbation");
    await closeContext(projectManager.context);

    const coordinator = await openAs(browser, "COORDINATOR");
    await navigateMain(coordinator.page, "Demandes");
    await coordinator.page.getByRole("button", { name: "Urgence", exact: true }).click();
    const urgentPanel = coordinator.page.locator(".workflow-list-panel");
    await labelled(urgentPanel, "Demande urgente", "select").selectOption(urgentNumber);
    await expect(coordinator.page.locator(".workflow-detail-panel")).toContainText("Urgente");
    await coordinator.page.getByLabel(/Justification de l’urgence/).fill("Intervention requise aujourd'hui");
    coordinator.page.once("dialog", (dialog) => dialog.accept());
    await coordinator.page.getByRole("button", { name: "Planifier en urgence" }).click();
    await expect(coordinator.page.getByTestId("emergency-override-active")).toContainText("Dérogation d’approbation active");
    await expect(coordinator.page.getByTestId("emergency-override-active")).toContainText("Coordonnateur E2E");

    await workflowSelect(coordinator.page, urgentNumber);
    await coordinator.page.getByLabel(/Commentaire d’approbation/).fill("Régularisation après urgence");
    await coordinator.page.getByRole("button", { name: "Approuver", exact: true }).click();
    await expect(coordinator.page.locator(".demand-notice").filter({ hasText: "Demande approuvée" })).toContainText("Demande approuvée");
    await closeContext(coordinator.context);
  });

  await test.step("technician lands on Today and can inspect Tomorrow and My week without mutation navigation", async () => {
    const { context, page } = await openAs(browser, "TECHNICIAN");
    await expect(page.getByRole("heading", { name: "Aujourd’hui", level: 1 })).toBeVisible();
    await expect(page.locator(".my-schedule-summary")).toContainText("Alice");
    await expect(page.locator(".my-schedule-summary")).toContainText("4 h");
    await expect(page.locator(".my-shift-card").first()).toContainText("P-251");

    await page.getByRole("button", { name: "Demain", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Demain", level: 1 })).toBeVisible();
    await page.getByRole("button", { name: "Ma semaine", exact: true }).click();
    await expect(page.getByRole("heading", { name: /Semaine du/ })).toBeVisible();
    await expect(page.locator(".my-schedule-summary")).toContainText("Alice");

    await expect(page.locator(".main-nav").getByText("Communications", { exact: true })).toHaveCount(0);
    await expect(page.locator(".main-nav").getByText("Ressources", { exact: true })).toHaveCount(0);
    await expect(page.locator(".main-nav").getByText("Utilisateurs", { exact: true })).toHaveCount(0);
    await expect(page.locator(".main-nav").getByText("Configuration", { exact: true })).toHaveCount(0);

    await navigateMain(page, "Demandes");
    await expect(page.getByRole("button", { name: "Segments", exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /Périodes & alternatives/ })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Workflow", exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Urgence", exact: true })).toHaveCount(0);

    await closeContext(context);
  });

  await test.step("coordinator uses the contextual DnD dialog for cancel, extend, move, split and duplicate", async () => {
    const { context, page } = await openAs(browser, "COORDINATOR");
    await navigateMain(page, "Planning opérationnel");
    await page.getByRole("button", { name: /Suivante/ }).click();

    await page.getByRole("button", { name: /Quick Shift/ }).click();
    const quickShift = page.getByRole("dialog", { name: "Créer un Quick Shift" });
    await labelled(quickShift, "Projet", "select").selectOption("P-251");
    await labelled(quickShift, "Technicien", "select").selectOption("Alice");
    await labelled(quickShift, "Date", "input").fill(d2);
    await labelled(quickShift, "Heures", "input").fill("1.25");
    await labelled(quickShift, "Confirmation", "select").selectOption("Confirmée");
    await labelled(quickShift, "Description", "textarea").fill("Validation drag-and-drop Playwright");
    await labelled(quickShift, "Note", "textarea").fill("DnD #275");
    await quickShift.getByRole("button", { name: "Créer le Quick Shift" }).click();
    await expect(quickShift).toBeHidden();

    const shiftsResponse = await page.request.get(
      `/api/v1/shifts?start=${d1}&end=${d5}`,
    );
    expect(shiftsResponse.ok()).toBeTruthy();
    const shifts = await shiftsResponse.json() as Array<{
      allocation_id: string;
      segment_id: string;
      resource_name: string;
      work_date: string;
      note: string | null;
    }>;
    const createdShift = shifts.find((row) => row.note === "DnD #275");
    expect(createdShift, "Quart Quick Shift DnD introuvable après création").toBeDefined();
    const allocationId = createdShift!.allocation_id;
    expect(createdShift!.resource_name).toBe("Alice");
    expect(createdShift!.work_date).toBe(d2);

    const segmentResponse = await page.request.get(
      `/api/v1/segments/${encodeURIComponent(createdShift!.segment_id)}`,
    );
    expect(segmentResponse.ok()).toBeTruthy();
    const createdSegment = await segmentResponse.json() as {
      segment_id: string;
      start_date: string;
      end_date: string;
    };
    expect(createdSegment.segment_id).toBe(createdShift!.segment_id);
    expect(createdSegment.start_date).toBe(d2);
    expect(createdSegment.end_date).toBe(d2);

    const aliceRow = page.locator(".resource-identity").filter({ hasText: "Alice" }).first().locator("..");
    const bobRow = page.locator(".resource-identity").filter({ hasText: "Bob" }).first().locator("..");
    const sourceCell = aliceRow.locator(`.planning-drop-day[data-day="${d2}"]`);
    const source = sourceCell.locator(`.shift-card[data-allocation-id="${allocationId}"]`);
    await expect(source).toBeVisible();

    const outsideTarget = bobRow.locator(`.planning-drop-day[data-day="${d3}"]`);
    const evaluatePromise = page.waitForResponse((response) => (
      response.request().method() === "POST"
      && response.url().includes(`/api/v1/allocations/${encodeURIComponent(allocationId)}/evaluate-drop`)
    ));
    await dragWithDataTransfer(page, source, outsideTarget);
    const evaluated = await evaluatePromise;
    expect(evaluated.status(), await evaluated.text()).toBe(200);
    expect(evaluated.request().postDataJSON()).toEqual({
      resource_id: "R-BOB",
      day: d3,
      outside_standard_hours: false,
    });
    expect((await evaluated.json()).actions.map((row: { code: string }) => row.code)).toEqual([
      "EXTEND_AND_MOVE",
      "CANCEL",
    ]);

    let dropDialog = page.getByRole("dialog", { name: "Choisir l’action du déplacement" });
    await expect(dropDialog).toContainText("Fenêtre proposée");
    await expect(dropDialog).toContainText("Besoin autonome");
    await dropDialog.getByRole("button", { name: "Annuler", exact: true }).click();
    await expect(dropDialog).toBeHidden();

    const unchangedSegmentResponse = await page.request.get(
      `/api/v1/segments/${encodeURIComponent(createdShift!.segment_id)}`,
    );
    expect(unchangedSegmentResponse.ok()).toBeTruthy();
    expect((await unchangedSegmentResponse.json()).end_date).toBe(d2);
    const unchangedShiftsResponse = await page.request.get(
      `/api/v1/shifts?start=${d1}&end=${d5}`,
    );
    const unchangedShift = (await unchangedShiftsResponse.json() as Array<{
      allocation_id: string;
      resource_name: string;
      work_date: string;
    }>).find((row) => row.allocation_id === allocationId);
    expect(unchangedShift?.resource_name).toBe("Alice");
    expect(unchangedShift?.work_date).toBe(d2);

    await dragWithDataTransfer(
      page,
      sourceCell.locator(`.shift-card[data-allocation-id="${allocationId}"]`),
      outsideTarget,
    );
    dropDialog = page.getByRole("dialog", { name: "Choisir l’action du déplacement" });
    await expect(dropDialog).toBeVisible();
    const extendPromise = page.waitForResponse((response) => (
      response.request().method() === "POST"
      && response.url().includes(`/api/v1/allocations/${encodeURIComponent(allocationId)}/extend-and-move`)
    ));
    await dropDialog.getByRole("button", { name: "Étendre la période et déplacer", exact: true }).click();
    const extended = await extendPromise;
    expect(extended.status(), await extended.text()).toBe(200);
    expect(extended.request().headers()["idempotency-key"]).toBeTruthy();
    expect(typeof extended.request().postDataJSON().expected_planning_version).toBe("number");
    await expect(page.locator(".planning-drag-feedback")).toContainText("Période étendue et quart déplacé");

    const extendedSegmentResponse = await page.request.get(
      `/api/v1/segments/${encodeURIComponent(createdShift!.segment_id)}`,
    );
    expect(extendedSegmentResponse.ok()).toBeTruthy();
    expect((await extendedSegmentResponse.json()).end_date).toBe(d3);
    await expect(
      bobRow.locator(`.planning-drop-day[data-day="${d3}"] .shift-card[data-allocation-id="${allocationId}"]`),
    ).toBeVisible();

    const bobD3Source = bobRow
      .locator(`.planning-drop-day[data-day="${d3}"]`)
      .locator(`.shift-card[data-allocation-id="${allocationId}"]`);
    const aliceD2Target = aliceRow.locator(`.planning-drop-day[data-day="${d2}"]`);
    await dragWithDataTransfer(page, bobD3Source, aliceD2Target);
    dropDialog = page.getByRole("dialog", { name: "Choisir l’action du déplacement" });
    await expect(dropDialog.getByRole("button", { name: "Déplacer", exact: true })).toBeVisible();
    await expect(dropDialog.getByRole("button", { name: "Partager", exact: true })).toBeVisible();
    await expect(dropDialog.getByRole("button", { name: "Dupliquer", exact: true })).toBeVisible();
    const movePromise = page.waitForResponse((response) => (
      response.request().method() === "POST"
      && response.url().includes(`/api/v1/allocations/${encodeURIComponent(allocationId)}/move`)
    ));
    await dropDialog.getByRole("button", { name: "Déplacer", exact: true }).click();
    expect((await movePromise).status()).toBe(200);
    await expect(page.locator(".planning-drag-feedback")).toContainText("Quart déplacé vers Alice");

    const aliceD2Source = aliceRow
      .locator(`.planning-drop-day[data-day="${d2}"]`)
      .locator(`.shift-card[data-allocation-id="${allocationId}"]`);
    const bobD3Target = bobRow.locator(`.planning-drop-day[data-day="${d3}"]`);
    await dragWithDataTransfer(page, aliceD2Source, bobD3Target);
    dropDialog = page.getByRole("dialog", { name: "Choisir l’action du déplacement" });
    const transfer = dropDialog.locator(".planning-drop-split-hours input");
    await transfer.fill("0.5");
    const splitPromise = page.waitForResponse((response) => (
      response.request().method() === "POST"
      && response.url().includes(`/api/v1/allocations/${encodeURIComponent(allocationId)}/split`)
    ));
    await dropDialog.getByRole("button", { name: "Partager", exact: true }).click();
    const split = await splitPromise;
    expect(split.status(), await split.text()).toBe(201);
    expect(split.request().headers()["idempotency-key"]).toBeTruthy();

    const afterSplitResponse = await page.request.get(
      `/api/v1/shifts?start=${d1}&end=${d5}`,
    );
    const afterSplitRows = (await afterSplitResponse.json() as Array<{
      allocation_id: string;
      segment_id: string;
      resource_id: string;
      work_date: string;
      hours: number;
    }>).filter((row) => row.segment_id === createdShift!.segment_id);
    const splitTarget = afterSplitRows.find((row) => (
      row.resource_id === "R-BOB"
      && row.work_date === d3
      && Math.abs(row.hours - 0.5) < 0.001
    ));
    expect(splitTarget, "Quart cible du partage DnD introuvable").toBeDefined();

    const bobSplitCard = bobRow
      .locator(`.planning-drop-day[data-day="${d3}"]`)
      .locator(`.shift-card[data-allocation-id="${splitTarget!.allocation_id}"]`);
    const aliceD3Target = aliceRow.locator(`.planning-drop-day[data-day="${d3}"]`);
    await dragWithDataTransfer(page, bobSplitCard, aliceD3Target);
    dropDialog = page.getByRole("dialog", { name: "Choisir l’action du déplacement" });

    const duplicateFirstPromise = page.waitForResponse((response) => (
      response.request().method() === "POST"
      && response.url().includes(`/api/v1/allocations/${encodeURIComponent(splitTarget!.allocation_id)}/duplicate`)
    ));
    await dropDialog.getByRole("button", { name: "Dupliquer", exact: true }).click();
    const duplicateFirst = await duplicateFirstPromise;
    expect(duplicateFirst.status(), await duplicateFirst.text()).toBe(422);
    const duplicateKey = duplicateFirst.request().headers()["idempotency-key"];
    expect(duplicateKey).toBeTruthy();
    await expect(dropDialog).toContainText("Décision de surallocation requise");

    await dropDialog.getByRole("radio", { name: /Conserver la surallocation comme dérogation/ }).check();
    const duplicateRetryPromise = page.waitForResponse((response) => (
      response.request().method() === "POST"
      && response.url().includes(`/api/v1/allocations/${encodeURIComponent(splitTarget!.allocation_id)}/duplicate`)
    ));
    await dropDialog.getByRole("button", { name: "Dupliquer", exact: true }).click();
    const duplicateRetry = await duplicateRetryPromise;
    expect(duplicateRetry.status(), await duplicateRetry.text()).toBe(201);
    expect(duplicateRetry.request().headers()["idempotency-key"]).toBe(duplicateKey);
    await expect(page.locator(".planning-drag-feedback")).toContainText("Quart dupliqué vers Alice");

    await closeContext(context);
  });
});


test("REQUEST window proposal never replays the original drag after direct approval", async ({ browser }) => {
  test.setTimeout(120_000);
  const { d1, d2, d3, d5 } = acceptanceDates();
  const { context, page } = await openAs(browser, "COORDINATOR");

  const created = await page.request.post("/api/v1/demands", {
    data: {
      project_number: "P-251",
      desired_start: d2,
      desired_end: d2,
      estimated_hours: 2,
      proposed_technician: "Alice",
      description: "Proposition fenêtre DnD #333C",
      submit: true,
    },
  });
  expect(created.status(), await created.text()).toBe(201);
  const demandNumber = (await created.json()).demand_number as string;

  const snapshotBeforeApproval = await page.request.get(
    `/api/v1/planning/snapshot?start=${d1}&end=${d5}&scope=global`,
  );
  expect(snapshotBeforeApproval.ok()).toBeTruthy();
  const planningVersion = (await snapshotBeforeApproval.json()).planning_version as number;

  const approved = await page.request.post(
    `/api/v1/demands/${encodeURIComponent(demandNumber)}/approve`,
    {
      data: {
        comment: "Approbation initiale DnD #333C",
        expected_planning_version: planningVersion,
      },
    },
  );
  expect(approved.status(), await approved.text()).toBe(200);

  const shiftsResponse = await page.request.get(
    `/api/v1/shifts?start=${d1}&end=${d5}`,
  );
  expect(shiftsResponse.ok()).toBeTruthy();
  const shift = (await shiftsResponse.json() as Array<{
    allocation_id: string;
    segment_id: string;
    demand_number: string | null;
    resource_name: string;
    work_date: string;
  }>).find((row) => row.demand_number === demandNumber);
  expect(shift, "Quart REQUEST #333C introuvable après approbation").toBeDefined();
  expect(shift!.resource_name).toBe("Alice");
  expect(shift!.work_date).toBe(d2);

  await navigateMain(page, "Planning opérationnel");
  await page.getByRole("button", { name: /Suivante/ }).click();

  const aliceRow = page.locator(".resource-identity").filter({ hasText: "Alice" }).first().locator("..");
  const bobRow = page.locator(".resource-identity").filter({ hasText: "Bob" }).first().locator("..");
  const source = aliceRow
    .locator(`.planning-drop-day[data-day="${d2}"]`)
    .locator(`.shift-card[data-allocation-id="${shift!.allocation_id}"]`);
  const target = bobRow.locator(`.planning-drop-day[data-day="${d3}"]`);
  await expect(source).toBeVisible();

  await dragWithDataTransfer(page, source, target);
  let dialog = page.getByRole("dialog", { name: "Choisir l’action du déplacement" });
  await expect(dialog).toContainText("Extension hors enveloppe approuvée");
  await expect(
    dialog.getByRole("button", { name: "Soumettre l'extension de période", exact: true }),
  ).toBeVisible();

  const proposalPromise = page.waitForResponse((response) => (
    response.request().method() === "POST"
    && response.url().includes(
      `/api/v1/allocations/${encodeURIComponent(shift!.allocation_id)}/propose-window-extension`,
    )
  ));
  await dialog.getByRole("button", { name: "Soumettre l'extension de période", exact: true }).click();
  const proposal = await proposalPromise;
  expect(proposal.status(), await proposal.text()).toBe(200);
  expect(proposal.request().headers()["idempotency-key"]).toBeTruthy();
  const proposalResult = await proposal.json() as {
    status: string | null;
    reapproval_required: boolean;
  };
  expect(proposalResult.reapproval_required).toBeFalsy();
  expect(proposalResult.status).toBe("En planification");
  await expect(page.locator(".planning-drag-feedback")).toContainText("Extension approuvée");
  await expect(page.locator(".planning-drag-feedback")).toContainText("Aucun quart n’a été déplacé");

  const afterProposalResponse = await page.request.get(
    `/api/v1/shifts?start=${d1}&end=${d5}`,
  );
  const unchangedShift = (await afterProposalResponse.json() as Array<{
    allocation_id: string;
    resource_name: string;
    work_date: string;
  }>).find((row) => row.allocation_id === shift!.allocation_id);
  expect(unchangedShift?.resource_name).toBe("Alice");
  expect(unchangedShift?.work_date).toBe(d2);

  const segmentAfterProposal = await page.request.get(
    `/api/v1/segments/${encodeURIComponent(shift!.segment_id)}`,
  );
  expect(segmentAfterProposal.ok()).toBeTruthy();
  expect((await segmentAfterProposal.json()).end_date).toBe(d3);

  await expect(source).toBeVisible();
  await dragWithDataTransfer(page, source, target);
  dialog = page.getByRole("dialog", { name: "Choisir l’action du déplacement" });
  await expect(dialog.getByRole("button", { name: "Déplacer", exact: true })).toBeVisible();
  await expect(
    dialog.getByRole("button", { name: "Soumettre l'extension de période", exact: true }),
  ).toHaveCount(0);
  await dialog.getByRole("button", { name: "Annuler", exact: true }).click();

  const afterCancelResponse = await page.request.get(
    `/api/v1/shifts?start=${d1}&end=${d5}`,
  );
  const afterCancel = (await afterCancelResponse.json() as Array<{
    allocation_id: string;
    resource_name: string;
    work_date: string;
  }>).find((row) => row.allocation_id === shift!.allocation_id);
  expect(afterCancel?.resource_name).toBe("Alice");
  expect(afterCancel?.work_date).toBe(d2);

  await closeContext(context);
});


test("coordinator splits and duplicates a shift atomically from React", async ({ browser }) => {
  test.setTimeout(120_000);
  const { d1, d2, d5 } = acceptanceDates();
  const { context, page } = await openAs(browser, "COORDINATOR");

  await navigateMain(page, "Planning opérationnel");
  await page.getByRole("button", { name: /Suivante/ }).click();

  await page.getByRole("button", { name: /Quick Shift/ }).click();
  const quickShift = page.getByRole("dialog", { name: "Créer un Quick Shift" });
  await labelled(quickShift, "Projet", "select").selectOption("P-251");
  await labelled(quickShift, "Technicien", "select").selectOption("Alice");
  await labelled(quickShift, "Date", "input").fill(d2);
  await labelled(quickShift, "Heures", "input").fill("4");
  await labelled(quickShift, "Confirmation", "select").selectOption("Confirmée");
  await labelled(quickShift, "Description", "textarea").fill("Validation partage et duplication #332");
  await labelled(quickShift, "Note", "textarea").fill("Atomic #332");
  await quickShift.getByRole("button", { name: "Créer le Quick Shift" }).click();
  await expect(quickShift).toBeHidden();

  const createdResponse = await page.request.get(
    `/api/v1/shifts?start=${d1}&end=${d5}`,
  );
  expect(createdResponse.ok()).toBeTruthy();
  const createdRows = await createdResponse.json() as Array<{
    allocation_id: string;
    segment_id: string;
    resource_id: string;
    work_date: string;
    hours: number;
    note: string | null;
    locked: boolean;
    source: string;
  }>;
  const sourceShift = createdRows.find((row) => row.note === "Atomic #332");
  expect(sourceShift, "Quart source #332 introuvable").toBeDefined();
  const segmentId = sourceShift!.segment_id;

  const aliceRow = page.locator(".resource-identity").filter({ hasText: "Alice" }).first().locator("..");
  const sourceCard = aliceRow
    .locator(`.planning-drop-day[data-day="${d2}"]`)
    .locator(`.shift-card[data-allocation-id="${sourceShift!.allocation_id}"]`);
  await expect(sourceCard).toBeVisible();
  await sourceCard.click();

  const editor = page.getByRole("dialog", { name: "Modifier le quart" });
  await expect(editor).toBeVisible();
  await editor.getByRole("button", { name: "Partager", exact: true }).click();
  const splitPanel = editor.getByTestId("atomic-split-panel");
  await expect(splitPanel).toBeVisible();
  await labelled(splitPanel, "Ressource du nouveau quart", "select").selectOption("R-BOB");
  await labelled(splitPanel, "Date du nouveau quart", "input").fill(d2);
  await labelled(splitPanel, "Heures à transférer", "input").fill("1.5");

  const splitResponsePromise = page.waitForResponse((response) => (
    response.request().method() === "POST"
    && response.url().includes(`/api/v1/allocations/${encodeURIComponent(sourceShift!.allocation_id)}/split`)
  ));
  await splitPanel.getByRole("button", { name: "Partager le quart", exact: true }).click();
  const splitResponse = await splitResponsePromise;
  expect(splitResponse.status(), await splitResponse.text()).toBe(201);
  const splitRequest = splitResponse.request();
  expect(splitRequest.headers()["idempotency-key"]).toBeTruthy();
  const splitBody = splitRequest.postDataJSON() as Record<string, unknown>;
  expect(typeof splitBody.expected_planning_version).toBe("number");
  expect(splitBody.resource_id).toBe("R-BOB");
  expect(splitBody.transfer_hours).toBe(1.5);
  await expect(editor).toBeHidden();

  const afterSplitResponse = await page.request.get(
    `/api/v1/shifts?start=${d1}&end=${d5}`,
  );
  expect(afterSplitResponse.ok()).toBeTruthy();
  const afterSplitRows = (await afterSplitResponse.json() as Array<{
    allocation_id: string;
    segment_id: string;
    resource_id: string;
    work_date: string;
    hours: number;
    locked: boolean;
    source: string;
  }>).filter((row) => row.segment_id === segmentId);
  expect(afterSplitRows).toHaveLength(2);
  expect(afterSplitRows.reduce((sum, row) => sum + row.hours, 0)).toBeCloseTo(4, 2);
  expect(afterSplitRows.every((row) => row.locked && row.source === "MANUAL")).toBeTruthy();
  const bobShift = afterSplitRows.find((row) => row.resource_id === "R-BOB");
  expect(bobShift?.hours).toBeCloseTo(1.5, 2);

  const bobRow = page.locator(".resource-identity").filter({ hasText: "Bob" }).first().locator("..");
  const bobCard = bobRow
    .locator(`.planning-drop-day[data-day="${d2}"]`)
    .locator(`.shift-card[data-allocation-id="${bobShift!.allocation_id}"]`);
  await expect(bobCard).toBeVisible();
  await bobCard.click();

  const duplicateEditor = page.getByRole("dialog", { name: "Modifier le quart" });
  await duplicateEditor.getByRole("button", { name: "Dupliquer", exact: true }).click();
  const duplicatePanel = duplicateEditor.getByTestId("atomic-duplicate-panel");
  await expect(duplicatePanel).toBeVisible();

  const firstDuplicatePromise = page.waitForResponse((response) => (
    response.request().method() === "POST"
    && response.url().includes(`/api/v1/allocations/${encodeURIComponent(bobShift!.allocation_id)}/duplicate`)
  ));
  await duplicatePanel.getByRole("button", { name: "Dupliquer le quart", exact: true }).click();
  const firstDuplicate = await firstDuplicatePromise;
  expect(firstDuplicate.status(), await firstDuplicate.text()).toBe(422);
  const firstKey = firstDuplicate.request().headers()["idempotency-key"];
  expect(firstKey).toBeTruthy();
  await expect(duplicateEditor.locator(".overallocation-choice")).toContainText(
    "dépasse les heures prévues",
  );

  const keptDuplicatePromise = page.waitForResponse((response) => (
    response.request().method() === "POST"
    && response.url().includes(`/api/v1/allocations/${encodeURIComponent(bobShift!.allocation_id)}/duplicate`)
  ));
  await duplicateEditor.getByRole("button", { name: /Conserver la dérogation/ }).click();
  const keptDuplicate = await keptDuplicatePromise;
  expect(keptDuplicate.status(), await keptDuplicate.text()).toBe(201);
  expect(keptDuplicate.request().headers()["idempotency-key"]).toBe(firstKey);
  expect(
    (keptDuplicate.request().postDataJSON() as Record<string, unknown>).overallocation_policy,
  ).toBe("KEEP_EXCEPTION");
  await expect(duplicateEditor).toBeHidden();

  const finalResponse = await page.request.get(
    `/api/v1/shifts?start=${d1}&end=${d5}`,
  );
  expect(finalResponse.ok()).toBeTruthy();
  const finalRows = (await finalResponse.json() as Array<{
    segment_id: string;
    resource_id: string;
    hours: number;
    locked: boolean;
    source: string;
    segment_overallocated_hours?: number;
  }>).filter((row) => row.segment_id === segmentId);
  expect(finalRows).toHaveLength(3);
  expect(finalRows.reduce((sum, row) => sum + row.hours, 0)).toBeCloseTo(5.5, 2);
  expect(finalRows.every((row) => row.locked && row.source === "MANUAL")).toBeTruthy();
  expect(finalRows.filter((row) => row.resource_id === "R-BOB")).toHaveLength(2);
  expect(finalRows.some((row) => Number(row.segment_overallocated_hours ?? 0) > 0)).toBeTruthy();

  await closeContext(context);
});


test("multi-line demand editor generates independent RequestLines and materializes them", async ({ browser }) => {
  const { d1, d2 } = acceptanceDates();
  const projectManager = await openAs(browser, "PROJECT_MANAGER");
  await navigateMain(projectManager.page, "Demandes");
  await projectManager.page.getByRole("button", { name: /Nouvelle demande/ }).click();
  const editor = projectManager.page.locator(".demand-editor-form");
  await expect(editor.getByRole("heading", { name: "Nouvelle demande" })).toBeVisible();

  await labelled(editor, "Projet", "select").selectOption("P-251");
  await labelled(editor, "Début souhaité", "input").fill(d1);
  await labelled(editor, "Fin souhaitée", "input").fill(d2);
  await labelled(editor, "Nombre de ressources simultanées", "input").fill("2");
  await labelled(editor, "Jours actifs souhaités", "input").fill("1");
  await labelled(editor, "Description / contexte de la demande", "textarea").fill(
    "Demande multi-lignes React #288",
  );

  await editor.getByRole("button", { name: "Passer aux lignes multiples" }).click();
  const cards = editor.locator(".request-line-card");
  await expect(cards).toHaveCount(2);
  await expect(editor.locator(".request-lines-summary")).toContainText("16");
  await expect(editor.locator(".request-lines-summary")).toContainText("heure(s) projetées");

  const generationCount = editor.getByLabel("Quantité de lignes à générer");
  await generationCount.fill("3");
  await editor.getByRole("button", { name: "Générer les lignes" }).click();
  await expect(cards).toHaveCount(3);
  await cards.nth(2).getByRole("button", { name: "Retirer" }).click();
  await expect(cards).toHaveCount(2);

  await cards.nth(0).getByRole("button", { name: "Dupliquer" }).click();
  await expect(cards).toHaveCount(3);
  await cards.nth(1).getByRole("button", { name: "Retirer" }).click();
  await expect(cards).toHaveCount(2);

  const line1 = cards.nth(0);
  const line2 = cards.nth(1);
  await labelled(line1, "Classe de ressource", "select").selectOption("Programmation");
  await line1.locator('select[aria-label="Compétences requises — ligne 1"]').selectOption(["C-SCADA"]);
  await labelled(line1, "Ressource proposée", "select").selectOption("R-ALICE");
  await labelled(line1, "Description spécifique", "textarea").fill("SCADA en début de fenêtre");

  await labelled(line2, "Classe de ressource", "select").selectOption("Programmation");
  await line2.locator('select[aria-label="Compétences requises — ligne 2"]').selectOption(["C-PLC"]);
  await labelled(line2, "Début", "input").fill(d2);
  await labelled(line2, "Fin", "input").fill(d2);
  await labelled(line2, "Ressource proposée", "select").selectOption("R-BOB");
  await labelled(line2, "Confirmation", "select").selectOption("Tentative");
  await labelled(line2, "Description spécifique", "textarea").fill("PLC en deuxième journée");

  await editor.getByRole("button", { name: "Créer le brouillon" }).click();
  const notice = projectManager.page.locator(".demand-notice");
  await expect(notice).toContainText("créée en brouillon");
  const number = demandNumberFrom(await notice.textContent());

  const detailResponse = await projectManager.page.request.get(
    `/api/v1/demands/${encodeURIComponent(number)}`,
  );
  expect(detailResponse.ok()).toBeTruthy();
  const detail = await detailResponse.json() as {
    line_mode: boolean;
    lines: Array<{
      line_id: string;
      active: boolean;
      required_resource_class: string | null;
      required_competency_ids: string[];
      estimated_hours: number | null;
      estimated_hours_source: string | null;
      proposed_resource_id: string | null;
      confirmation: string;
    }>;
  };
  const activeLines = detail.lines.filter((line) => line.active);
  expect(detail.line_mode).toBeTruthy();
  expect(activeLines).toHaveLength(2);
  expect(activeLines.map((line) => line.required_resource_class)).toEqual([
    "Programmation",
    "Programmation",
  ]);
  expect(activeLines.map((line) => line.required_competency_ids)).toEqual([
    ["C-SCADA"],
    ["C-PLC"],
  ]);
  expect(activeLines.map((line) => line.estimated_hours)).toEqual([8, 8]);
  expect(activeLines.map((line) => line.estimated_hours_source)).toEqual([
    "DEFAULT_8H",
    "DEFAULT_8H",
  ]);
  expect(activeLines.map((line) => line.proposed_resource_id)).toEqual([
    "R-ALICE",
    "R-BOB",
  ]);
  expect(activeLines.map((line) => line.confirmation)).toEqual([
    "Confirmée",
    "Tentative",
  ]);

  await expect(editor.locator(".request-line-card")).toHaveCount(2);
  await expect(labelled(editor.locator(".request-line-card").nth(0), "Heures", "input")).toHaveValue("");

  await periodsSelect(projectManager.page, number);
  const lineSelector = projectManager.page.getByLabel("Ligne de demande");
  await expect(lineSelector).toBeVisible();
  await expect(lineSelector.locator("option")).toHaveCount(2);

  await lineSelector.selectOption(activeLines[0].line_id);
  await expect(projectManager.page.locator(".period-demand-summary")).toContainText("Ligne 1");
  await projectManager.page.getByRole("button", { name: /Période cumulative/ }).click();
  let linePeriod = projectManager.page.locator(".period-card.cumulative").first();
  await labelled(linePeriod, "Début", "input").fill(d1);
  await labelled(linePeriod, "Fin", "input").fill(d1);
  await labelled(linePeriod, "Heures totales", "input").fill("8");
  await expect(labelled(linePeriod, "Ressources simultanées", "input")).toBeDisabled();
  await expect(labelled(linePeriod, "Ressources simultanées", "input")).toHaveValue("1");
  await projectManager.page.getByRole("button", { name: "Enregistrer les périodes" }).click();
  await expect(projectManager.page.locator(".demand-notice").filter({ hasText: "Périodes enregistrées." })).toHaveText("Périodes enregistrées.");

  await lineSelector.selectOption(activeLines[1].line_id);
  await expect(projectManager.page.locator(".period-demand-summary")).toContainText("Ligne 2");
  await expect(projectManager.page.locator(".period-empty")).toBeVisible();
  await projectManager.page.getByRole("button", { name: /Période cumulative/ }).click();
  linePeriod = projectManager.page.locator(".period-card.cumulative").first();
  await labelled(linePeriod, "Début", "input").fill(d2);
  await labelled(linePeriod, "Fin", "input").fill(d2);
  await labelled(linePeriod, "Heures totales", "input").fill("8");
  await expect(labelled(linePeriod, "Ressources simultanées", "input")).toBeDisabled();
  await projectManager.page.getByRole("button", { name: "Enregistrer les périodes" }).click();
  await expect(projectManager.page.locator(".demand-notice").filter({ hasText: "Périodes enregistrées." })).toHaveText("Périodes enregistrées.");

  const firstLinePeriods = await projectManager.page.request.get(
    `/api/v1/demands/${encodeURIComponent(number)}/lines/${encodeURIComponent(activeLines[0].line_id)}/periods`,
  );
  expect(firstLinePeriods.ok()).toBeTruthy();
  expect((await firstLinePeriods.json()) as Array<unknown>).toHaveLength(1);
  const secondLinePeriods = await projectManager.page.request.get(
    `/api/v1/demands/${encodeURIComponent(number)}/lines/${encodeURIComponent(activeLines[1].line_id)}/periods`,
  );
  expect(secondLinePeriods.ok()).toBeTruthy();
  expect((await secondLinePeriods.json()) as Array<unknown>).toHaveLength(1);

  await workflowSelect(projectManager.page, number);
  await projectManager.page.getByRole("button", { name: "Soumettre", exact: true }).click();
  await expect(projectManager.page.locator(".demand-notice").filter({ hasText: "soumise pour approbation" })).toContainText("soumise pour approbation");
  await closeContext(projectManager.context);

  const coordinator = await openAs(browser, "COORDINATOR");
  await navigateMain(coordinator.page, "Demandes");
  await workflowSelect(coordinator.page, number);
  await coordinator.page.getByLabel(/Commentaire d’approbation/).fill("Approbation multi-lignes #288");
  await coordinator.page.getByRole("button", { name: "Approuver", exact: true }).click();
  await expect(coordinator.page.locator(".demand-notice").filter({ hasText: "Demande approuvée" })).toContainText("Demande approuvée");

  const segmentsResponse = await coordinator.page.request.get("/api/v1/segments?include_cancelled=false");
  expect(segmentsResponse.ok()).toBeTruthy();
  const segments = await segmentsResponse.json() as Array<{
    demand_number: string | null;
    resource_name: string | null;
    planned_hours: number;
  }>;
  const materialized = segments.filter((row) => row.demand_number === number);
  expect(materialized).toHaveLength(2);
  expect(materialized.map((row) => row.planned_hours).sort((a, b) => a - b)).toEqual([8, 8]);
  expect(new Set(materialized.map((row) => row.resource_name))).toEqual(new Set(["Alice", "Bob"]));

  await closeContext(coordinator.context);
});


test("development identity selector switches real local users and technician schedules", async ({ browser }) => {
  const context = await browser.newContext({
    baseURL: BASE_URL,
    locale: "fr-CA",
  });
  const page = await context.newPage();
  await page.goto("/");

  const selector = page.getByLabel("Identité de test");
  await expect(selector).toBeVisible();
  await expect(page.locator(".sidebar-footer")).toContainText("Administrateur bootstrap E2E");

  await selectOptionContaining(selector, "Technicien Démo A");
  await expect(page.locator(".sidebar-footer")).toContainText("Technicien Démo A");
  await expect(page.getByRole("heading", { name: "Aujourd’hui", level: 1 })).toBeVisible();
  await expect(page.locator(".main-nav").getByText("Utilisateurs", { exact: true })).toHaveCount(0);

  await page.getByRole("button", { name: "Ma semaine", exact: true }).click();
  await page.getByRole("button", { name: /Suivante/ }).click();
  await expect(page.locator(".my-schedule-days")).toBeVisible();
  const technicianAText = await page.locator(".my-schedule-days").innerText();
  expect(technicianAText).toContain("P-251");

  await selectOptionContaining(page.getByLabel("Identité de test"), "Technicien Démo B");
  await expect(page.locator(".sidebar-footer")).toContainText("Technicien Démo B");
  await page.getByRole("button", { name: "Ma semaine", exact: true }).click();
  await page.getByRole("button", { name: /Suivante/ }).click();
  await expect(page.locator(".my-schedule-days")).toBeVisible();
  const technicianBText = await page.locator(".my-schedule-days").innerText();
  expect(technicianBText).toContain("P-251");
  expect(technicianBText).not.toBe(technicianAText);

  await selectOptionContaining(page.getByLabel("Identité de test"), "Administrateur Démo");
  await expect(page.locator(".sidebar-footer")).toContainText("Administrateur Démo");
  await expect(page.locator(".main-nav").getByText("Utilisateurs", { exact: true })).toBeVisible();

  await context.close();
});
