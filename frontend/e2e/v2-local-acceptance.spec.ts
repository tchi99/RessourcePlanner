import { Browser, BrowserContext, Locator, Page, expect, test } from "@playwright/test";

const BASE_URL = process.env.RESOURCEPLANNER_E2E_BASE_URL || "http://127.0.0.1:8765";

type Role = "ADMIN" | "PROJECT_MANAGER" | "COORDINATOR" | "TECHNICIAN";

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
    extraHTTPHeaders: role ? { "X-E2E-Role": role } : {},
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

async function workflowSelect(page: Page, demandNumber: string) {
  await page.getByRole("button", { name: "Workflow", exact: true }).click();
  const panel = page.locator(".workflow-list-panel");
  await labelled(panel, "Demande", "select").selectOption(demandNumber);
  await expect(page.locator(".workflow-summary-card")).toContainText(demandNumber);
}

async function periodsSelect(page: Page, demandNumber: string) {
  await page.getByRole("button", { name: /Périodes & alternatives/ }).click();
  const picker = page.locator(".period-demand-picker");
  const select = labelled(picker, "Demande", "select");
  await select.selectOption(demandNumber);
  await expect(select).toHaveValue(demandNumber);
  await expect(page.locator(".period-demand-summary")).toBeVisible();
}

test("V2 local acceptance path runs through React, Chromium, FastAPI and SQLite", async ({ browser }) => {
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
    await closeContext(admin.context);

    const projectManager = await openAs(browser, "PROJECT_MANAGER");
    await expect(projectManager.page.locator(".main-nav").getByText("Communications", { exact: true })).toHaveCount(0);
    await expect(projectManager.page.locator(".main-nav").getByText("Ressources", { exact: true })).toHaveCount(0);
    await expect(projectManager.page.locator(".main-nav").getByText("Utilisateurs", { exact: true })).toHaveCount(0);
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
    await expect(page.locator(".demand-notice")).toHaveText("Périodes enregistrées.");
    await alternatives.nth(0).getByRole("button", { name: "Retenir cette option" }).click();
    await expect(alternatives.nth(0).getByRole("button", { name: "Option retenue" })).toBeVisible();

    await workflowSelect(page, demandNumber);
    await page.getByRole("button", { name: "Soumettre", exact: true }).click();
    await expect(page.locator(".demand-notice")).toContainText("soumise pour approbation");
    await expect(page.getByTestId("plan-delta-preview")).toBeVisible();

    await page.getByRole("button", { name: "Approuver", exact: true }).click();
    await expect(page.locator(".error-panel")).toContainText("permission_denied");
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
    await expect(page.locator(".demand-notice")).toContainText("Demande approuvée");

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
    await expect(projectManager.page.locator(".demand-notice")).toContainText("doit être approuvée de nouveau");

    const firstAlternative = projectManager.page.locator(".alternative-option").nth(0);
    await firstAlternative.getByRole("button", { name: "Retenir cette option" }).click();
    await expect(firstAlternative.getByRole("button", { name: "Option retenue" })).toBeVisible();

    await workflowSelect(projectManager.page, demandNumber);
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
    await expect(coordinator.page.locator(".demand-notice")).toContainText("Demande approuvée");
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

  await test.step("communications are reviewed in React and only create fake local drafts", async () => {
    const { context, page } = await openAs(browser, "COORDINATOR");
    await navigateMain(page, "Communications");
    await expect(page.getByRole("heading", { name: "Communications de planification" })).toBeVisible();
    await page.getByLabel("Semaine du").fill(d1);
    await page.getByRole("button", { name: "Générer la prévisualisation" }).click();
    await expect(page.locator(".draft-card").first()).toBeVisible();
    await expect(page.locator(".communications-warning")).toHaveCount(0);
    await page.getByRole("button", { name: "Préparer le lot" }).click();
    await expect(page.locator(".communications-notice")).toContainText("Lot préparé");
    await page.locator(".batch-row").first().getByRole("button", { name: "Approuver" }).click();
    await expect(page.locator(".communications-notice")).toContainText("Lot approuvé");
    page.once("dialog", (dialog) => dialog.accept());
    await page.locator(".batch-row").first().getByRole("button", { name: "Créer brouillons M365" }).click();
    await expect(page.locator(".communications-notice")).toContainText("brouillon(s) M365 créé(s)");
    await closeContext(context);
  });

  await test.step("demand history exposes backend audit actors", async () => {
    const { context, page } = await openAs(browser, "COORDINATOR");
    await navigateMain(page, "Demandes");
    await page.getByRole("button", { name: "Historique", exact: true }).click();
    const selector = page.locator(".demand-history-selector");
    await labelled(selector, "Demande", "select").selectOption(demandNumber);
    await expect(page.locator(".demand-history-timeline")).toContainText("Coordonnateur E2E");
    await expect(page.locator(".demand-history-timeline li").first()).toBeVisible();
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
    await expect(projectManager.page.locator(".demand-notice")).toContainText("soumise pour approbation");
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

    await coordinator.page.getByRole("button", { name: "Workflow", exact: true }).click();
    const workflowPanel = coordinator.page.locator(".workflow-list-panel");
    await labelled(workflowPanel, "Demande", "select").selectOption(urgentNumber);
    await coordinator.page.getByLabel(/Commentaire d’approbation/).fill("Régularisation après urgence");
    await coordinator.page.getByRole("button", { name: "Approuver", exact: true }).click();
    await expect(coordinator.page.locator(".demand-notice")).toContainText("Demande approuvée");
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

    await navigateMain(page, "Demandes");
    await expect(page.getByRole("button", { name: "Segments", exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /Périodes & alternatives/ })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Workflow", exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Urgence", exact: true })).toHaveCount(0);

    await closeContext(context);
  });
});
