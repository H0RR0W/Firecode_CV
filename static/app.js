// ── Theme ──────────────────────────────────────────────────────────────────
(function () {
  const saved = localStorage.getItem("theme") || "dark";
  document.documentElement.setAttribute("data-theme", saved);
  const btn = document.getElementById("themeBtn");
  if (btn) btn.textContent = saved === "dark" ? "☀️ Светлая" : "🌙 Тёмная";
})();

function toggleTheme() {
  const html = document.documentElement;
  const next = html.getAttribute("data-theme") === "dark" ? "light" : "dark";
  html.setAttribute("data-theme", next);
  localStorage.setItem("theme", next);
  const btn = document.getElementById("themeBtn");
  if (btn) btn.textContent = next === "dark" ? "☀️ Светлая" : "🌙 Тёмная";
}

// ── Tabs ───────────────────────────────────────────────────────────────────
document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    const tabName = btn.dataset.tab;
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));
    btn.classList.add("active");
    const content = document.getElementById("tab-" + tabName);
    if (content) content.classList.add("active");
  });
});

// ── Generate CV ────────────────────────────────────────────────────────────
async function generateCV() {
  const prompt = (document.getElementById("genPrompt")?.value || "").trim();
  if (!prompt) {
    showStatus("genStatus", "error", "Введите промпт");
    return;
  }
  const btn = document.getElementById("btnGenerate");
  const status = document.getElementById("genStatus");
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Генерирую…';
  status.innerHTML = "";

  try {
    const res = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt }),
    });
    const data = await res.json();
    if (!res.ok) {
      showStatus("genStatus", "error", data.error || "Ошибка генерации");
      return;
    }
    window.location.href = data.redirect;
  } catch (e) {
    showStatus("genStatus", "error", "Сетевая ошибка: " + e.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = "⚡ Сгенерировать CV";
  }
}

// ── CV List Filtering ──────────────────────────────────────────────────────
let _filterTimer = null;
function filterCVs() {
  clearTimeout(_filterTimer);
  _filterTimer = setTimeout(async () => {
    const name = document.getElementById("fName")?.value || "";
    const spec = document.getElementById("fSpec")?.value || "";
    const stack = document.getElementById("fStack")?.value || "";
    const sort = document.getElementById("fSort")?.value || "desc";
    const params = new URLSearchParams({ name, spec, stack, sort });
    try {
      const res = await fetch("/api/cvs?" + params);
      if (!res.ok) return;
      const cvs = await res.json();
      const grid = document.getElementById("cvGrid");
      if (!grid) return;
      if (cvs.length === 0) {
        grid.innerHTML =
          '<div style="color:var(--text-muted);grid-column:1/-1;padding:2rem 0;text-align:center;">Ничего не найдено</div>';
        return;
      }
      grid.innerHTML = cvs
        .map(
          (cv) => `
        <div class="card" style="cursor:pointer;" onclick="location.href='/cv/${cv.id}'">
          <div style="font-weight:700;font-size:0.95rem;">${escHtml(cv.name)}</div>
          <div class="cv-card-spec">${escHtml(cv.specialization)}</div>
          ${cv.languages ? `<div class="cv-card-stack">${escHtml((cv.languages || "").slice(0, 60))}${(cv.languages || "").length > 60 ? "…" : ""}</div>` : ""}
          <div class="cv-card-meta">${cv.created_at.slice(0, 10)}</div>
        </div>`
        )
        .join("");
    } catch (e) {
      console.error("Filter error:", e);
    }
  }, 300);
}

function escHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ── Project Accordion ──────────────────────────────────────────────────────
function toggleProject(header) {
  const body = header.nextElementSibling;
  const isOpen = body.classList.contains("open");
  body.classList.toggle("open", !isOpen);
  header.classList.toggle("open", !isOpen);
}

function updateProjectTitle(idx, value) {
  const accordion = document.querySelector(`[data-project-idx="${idx}"]`);
  if (accordion) {
    const nameDisplay = accordion.querySelector(".project-name-display");
    if (nameDisplay) nameDisplay.textContent = value || `Проект ${Number(idx) + 1}`;
  }
  syncPreview();
}

// ── Inline Regen ───────────────────────────────────────────────────────────
function openRegen(field, projectIdx) {
  const panelId =
    projectIdx !== null && projectIdx !== undefined
      ? `regen-${projectIdx}-${field}`
      : `regen-${field}`;
  // Close others
  document.querySelectorAll(".regen-panel.open").forEach((p) => {
    if (p.id !== panelId) p.classList.remove("open");
  });
  const panel = document.getElementById(panelId);
  if (panel) panel.classList.toggle("open");
}

function closeRegen(field, projectIdx) {
  const panelId =
    projectIdx !== null && projectIdx !== undefined
      ? `regen-${projectIdx}-${field}`
      : `regen-${field}`;
  const panel = document.getElementById(panelId);
  if (panel) panel.classList.remove("open");
}

async function doRegen(field, projectIdx) {
  const isProject = projectIdx !== null && projectIdx !== undefined;
  const hintId = isProject
    ? `hint-${projectIdx}-${field}`
    : `hint-${field}`;
  const fieldId = isProject
    ? `proj-${projectIdx}-${field}`
    : `field-${field}`;
  const hint = document.getElementById(hintId)?.value || "";
  const context = buildContext(isProject ? projectIdx : null);
  const fieldEl = document.getElementById(fieldId);
  if (!fieldEl) return;

  const original = fieldEl.value;
  fieldEl.disabled = true;
  fieldEl.classList.add("shimmer");

  try {
    const res = await fetch(`/api/cvs/${CV_ID}/regen-field`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ field, project_index: projectIdx, hint, context }),
    });
    const data = await res.json();
    if (!res.ok) {
      alert(data.error || "Ошибка перегенерации");
      fieldEl.value = original;
      return;
    }
    const value = data.value;
    if (Array.isArray(value)) {
      fieldEl.value = value.join("\n");
    } else {
      fieldEl.value = value;
    }
    closeRegen(field, projectIdx);
    if (field === "name") updateProjectTitle(projectIdx, value);
    syncPreview();
  } catch (e) {
    alert("Сетевая ошибка: " + e.message);
    fieldEl.value = original;
  } finally {
    fieldEl.disabled = false;
    fieldEl.classList.remove("shimmer");
  }
}

function buildContext(projectIdx) {
  const ctx = {
    name: document.getElementById("field-name")?.value || "",
    specialization: document.getElementById("field-specialization")?.value || "",
    experience: document.getElementById("field-experience")?.value || "",
    languages: document.getElementById("field-languages")?.value || "",
    frameworks: document.getElementById("field-frameworks")?.value || "",
  };
  if (projectIdx !== null && projectIdx !== undefined) {
    ctx.project_name =
      document.getElementById(`proj-${projectIdx}-name`)?.value || "";
    ctx.project_role =
      document.getElementById(`proj-${projectIdx}-role`)?.value || "";
    ctx.project_tech_stack =
      document.getElementById(`proj-${projectIdx}-tech_stack`)?.value || "";
    ctx.project_description =
      document.getElementById(`proj-${projectIdx}-description`)?.value || "";
    ctx.project_duration =
      document.getElementById(`proj-${projectIdx}-duration`)?.value || "";
  }
  return ctx;
}

// ── Save CV ────────────────────────────────────────────────────────────────
async function saveCV() {
  const btn = document.getElementById("btnSave");
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Сохраняю…';

  const body = {
    name: document.getElementById("field-name")?.value || "",
    specialization: document.getElementById("field-specialization")?.value || "",
    experience: document.getElementById("field-experience")?.value || "",
    languages: document.getElementById("field-languages")?.value || "",
    frameworks: document.getElementById("field-frameworks")?.value || "",
    libraries: document.getElementById("field-libraries")?.value || "",
    other_skills: document.getElementById("field-other_skills")?.value || "",
    projects: collectProjects(),
  };

  try {
    const res = await fetch(`/api/cvs/${CV_ID}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) {
      showStatus("saveStatus", "error", data.error || "Ошибка сохранения");
    } else {
      showStatus("saveStatus", "success", "✓ Сохранено, docx обновлён");
      setTimeout(() => {
        const s = document.getElementById("saveStatus");
        if (s) s.innerHTML = "";
      }, 3000);
    }
  } catch (e) {
    showStatus("saveStatus", "error", "Сетевая ошибка: " + e.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = "💾 Сохранить";
  }
}

function collectProjects() {
  const accordions = document.querySelectorAll(".project-accordion");
  return Array.from(accordions).map((acc) => {
    const idx = acc.dataset.projectIdx;
    const implRaw =
      document.getElementById(`proj-${idx}-implementation`)?.value || "";
    const impl = implRaw
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean);
    return {
      name: document.getElementById(`proj-${idx}-name`)?.value || "",
      role: document.getElementById(`proj-${idx}-role`)?.value || "",
      team: document.getElementById(`proj-${idx}-team`)?.value || "",
      description:
        document.getElementById(`proj-${idx}-description`)?.value || "",
      tech_stack:
        document.getElementById(`proj-${idx}-tech_stack`)?.value || "",
      duration:
        document.getElementById(`proj-${idx}-duration`)?.value || "",
      implementation: impl,
    };
  });
}

// ── Delete CV ──────────────────────────────────────────────────────────────
async function deleteCV(cvId) {
  if (!confirm("Удалить этот CV? Действие необратимо.")) return;
  try {
    const res = await fetch(`/api/cvs/${cvId}`, { method: "DELETE" });
    if (res.ok) {
      window.location.href = "/";
    } else {
      const d = await res.json();
      alert(d.error || "Ошибка удаления");
    }
  } catch (e) {
    alert("Сетевая ошибка: " + e.message);
  }
}

// ── Admin — User management ────────────────────────────────────────────────
async function deleteUser(userId, login) {
  if (!confirm(`Удалить пользователя «${login}»?`)) return;
  try {
    const res = await fetch(`/admin/users/${userId}`, { method: "DELETE" });
    if (res.ok) {
      location.reload();
    } else {
      const d = await res.json();
      alert(d.error || "Ошибка удаления");
    }
  } catch (e) {
    alert("Сетевая ошибка: " + e.message);
  }
}

function togglePwForm(userId) {
  const form = document.getElementById("pwform-" + userId);
  if (form) form.classList.toggle("open");
}

// ── Live Preview ───────────────────────────────────────────────────────────
function syncPreview() {
  const set = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.textContent = val || "—";
  };
  set("prev-name", document.getElementById("field-name")?.value);
  set("prev-spec", document.getElementById("field-specialization")?.value);
  set("prev-exp", document.getElementById("field-experience")?.value);
  set("prev-lang", document.getElementById("field-languages")?.value);
  set("prev-fw", document.getElementById("field-frameworks")?.value);
  set("prev-lib", document.getElementById("field-libraries")?.value);
  set("prev-other", document.getElementById("field-other_skills")?.value);

  const prevProjects = document.getElementById("prev-projects");
  if (!prevProjects) return;
  const accordions = document.querySelectorAll(".project-accordion");
  prevProjects.innerHTML = Array.from(accordions)
    .map((acc) => {
      const idx = acc.dataset.projectIdx;
      const name =
        document.getElementById(`proj-${idx}-name`)?.value || `Проект ${Number(idx) + 1}`;
      const role =
        document.getElementById(`proj-${idx}-role`)?.value || "";
      return `<div style="margin-bottom:0.5rem;">
        <div style="font-weight:600;color:var(--accent);font-size:0.82rem;">${escHtml(name)}</div>
        ${role ? `<div style="font-size:0.75rem;color:var(--text-muted);">${escHtml(role)}</div>` : ""}
      </div>`;
    })
    .join("");
}

// ── Status helper ──────────────────────────────────────────────────────────
function showStatus(containerId, type, message) {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = `<div class="alert alert-${type}">${escHtml(message)}</div>`;
}

// ── Init live preview listeners ────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  const watchIds = [
    "field-name", "field-specialization", "field-experience",
    "field-languages", "field-frameworks", "field-libraries", "field-other_skills",
  ];
  watchIds.forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("input", syncPreview);
  });
  syncPreview();
});

// CV_ID is defined inline in cv_detail.html; safe to reference globally
