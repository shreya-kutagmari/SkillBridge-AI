/* ── SkillBridge AI — app.js (Phase 3) ── */

/* ─── Utilities ─────────────────────────────────────────────────────────── */
function escapeHTML(v) {
  return String(v).replace(/[&<>"']/g, c =>
    ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}

async function postJSON(url, data) {
  const r = await fetch(url, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(data)
  });
  const json = await r.json();
  if (!r.ok) throw new Error(json.error || "Request failed");
  return json;
}

async function patchJSON(url, data) {
  const r = await fetch(url, {
    method: "POST",                   // Flask accepts POST for PATCH compat
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(data)
  });
  const json = await r.json();
  if (!r.ok) throw new Error(json.error || "Update failed");
  return json;
}

function showAlert(el, type, msg) {
  if (!el) return;
  el.className = `alert alert-${type} show`;
  el.textContent = msg;
  if (type !== "error") setTimeout(() => { el.className = "alert"; }, 4000);
}

function setLoading(btn, loading, originalText) {
  if (!btn) return;
  if (loading) {
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Working…';
  } else {
    btn.disabled = false;
    btn.textContent = originalText;
  }
}

/* ─── Language switcher ──────────────────────────────────────────────────── */
const I18N = {
  en: {
    home: "Home", jobs: "Explore jobs", dashboard: "Dashboard", tracker: "My tracker",
    matchBtn: "Match jobs", matchPlaceholder: "e.g. Python, SQL, HTML, Git",
    askBtn: "Get guidance", questionPlaceholder: "Example: How can I prepare for a Python developer interview?",
    uploadBtn: "Analyse resume", matched: "Matched skills", toLearn: "Skills to build",
    applyName: "Your name", applyBtn: "Save application", filterPlaceholder: "Filter by title or skill…",
    noJobs: "No jobs found.", thinking: "Thinking…", uploading: "Analysing resume…",
    updateStatus: "Update", notesPlaceholder: "Add notes…", langLabel: "EN"
  },
  kn: {
    home: "ಮುಖಪುಟ", jobs: "ಉದ್ಯೋಗ ಹುಡುಕಿ", dashboard: "ಡ್ಯಾಶ್‌ಬೋರ್ಡ್", tracker: "ನನ್ನ ಟ್ರ್ಯಾಕರ್",
    matchBtn: "ಉದ್ಯೋಗ ಹೊಂದಿಸಿ", matchPlaceholder: "ಉದಾ: Python, SQL, HTML, Git",
    askBtn: "ಮಾರ್ಗದರ್ಶನ ಪಡೆಯಿರಿ", questionPlaceholder: "ಉದಾ: Python ಡೆವಲಪರ್ ಸಂದರ್ಶನಕ್ಕೆ ಹೇಗೆ ತಯಾರಾಗಬೇಕು?",
    uploadBtn: "ರೆಸ್ಯೂಮ್ ವಿಶ್ಲೇಷಿಸಿ", matched: "ಹೊಂದಿದ ಕೌಶಲ್ಯಗಳು", toLearn: "ಕಲಿಯಬೇಕಾದ ಕೌಶಲ್ಯಗಳು",
    applyName: "ನಿಮ್ಮ ಹೆಸರು", applyBtn: "ಅರ್ಜಿ ಉಳಿಸಿ", filterPlaceholder: "ಶೀರ್ಷಿಕೆ ಅಥವಾ ಕೌಶಲ್ಯದಿಂದ ಫಿಲ್ಟರ್ ಮಾಡಿ…",
    noJobs: "ಯಾವುದೇ ಉದ್ಯೋಗ ಕಂಡುಬಂದಿಲ್ಲ.", thinking: "ಯೋಚಿಸುತ್ತಿದ್ದೇನೆ…", uploading: "ರೆಸ್ಯೂಮ್ ವಿಶ್ಲೇಷಿಸುತ್ತಿದ್ದೇನೆ…",
    updateStatus: "ನವೀಕರಿಸಿ", notesPlaceholder: "ಟಿಪ್ಪಣಿ ಸೇರಿಸಿ…", langLabel: "KN"
  }
};

let currentLang = localStorage.getItem("sb_lang") || "en";

function applyLanguage(lang) {
  currentLang = lang;
  localStorage.setItem("sb_lang", lang);
  const t = I18N[lang];

  // Nav links
  const navLinks = {
    "/": t.home, "/jobs": t.jobs, "/dashboard": t.dashboard, "/tracker": t.tracker
  };
  document.querySelectorAll("nav a").forEach(a => {
    const path = a.getAttribute("href");
    if (navLinks[path]) a.textContent = navLinks[path];
  });

  // Language toggle buttons
  document.querySelectorAll(".lang-btn").forEach(b => {
    b.classList.toggle("active", b.dataset.lang === lang);
  });

  // Translatable elements
  const map = {
    matchButton: "matchBtn", askAssistant: "askBtn", uploadResumeBtn: "uploadBtn"
  };
  for (const [id, key] of Object.entries(map)) {
    const el = document.getElementById(id);
    if (el && t[key]) el.textContent = t[key];
  }

  const phMap = {
    skillsInput: "matchPlaceholder", question: "questionPlaceholder",
    jobFilter: "filterPlaceholder"
  };
  for (const [id, key] of Object.entries(phMap)) {
    const el = document.getElementById(id);
    if (el && t[key]) el.placeholder = t[key];
  }

  // Apply name placeholders on job cards
  document.querySelectorAll("[data-i18n-apply-name]").forEach(el => {
    el.placeholder = t.applyName;
  });
  document.querySelectorAll("[data-i18n-apply-btn]").forEach(el => {
    el.textContent = t.applyBtn;
  });
}

document.addEventListener("DOMContentLoaded", () => {
  // Wire language buttons
  document.querySelectorAll(".lang-btn").forEach(b => {
    b.addEventListener("click", () => applyLanguage(b.dataset.lang));
  });
  applyLanguage(currentLang);
});

/* ─── Job Matcher ─────────────────────────────────────────────────────────── */
function scoreClass(s) {
  return s >= 75 ? "ring-high" : s >= 40 ? "ring-mid" : "ring-low";
}

function renderMatchItem(job) {
  const matched = job.matched_skills.map(s =>
    `<span class="pill pill-match">${escapeHTML(s)}</span>`).join("");
  const missing = job.missing_skills.map(s =>
    `<span class="pill pill-miss">${escapeHTML(s)}</span>`).join("");
  const explain = job.score === 100
    ? "Perfect match — you have all required skills."
    : job.score >= 75
    ? "Strong match — minor gaps remain."
    : job.score >= 40
    ? "Partial match — focused learning will close the gap."
    : "Early stage — prioritise foundation skills first.";
  return `
<article class="match-item">
  <div class="match-top">
    <div>
      <strong>${escapeHTML(job.title)}</strong>
      <span class="tag" style="margin-left:6px">${escapeHTML(job.job_type)}</span><br>
      <span class="muted">${escapeHTML(job.company)} &middot; ${escapeHTML(job.location)}</span>
    </div>
    <div style="text-align:center">
      <div class="score-ring ${scoreClass(job.score)}">${job.score}%</div>
      <div style="font-size:11px;color:var(--muted);margin-top:2px">match</div>
    </div>
  </div>
  ${matched ? `<div class="match-pills">${matched}</div>` : ""}
  ${missing ? `<div class="match-pills" style="margin-top:4px">${missing}</div>` : ""}
  <p class="match-explain">${escapeHTML(explain)}</p>
</article>`;
}
// Restore resume skills when opening the Jobs page
const savedSkills = sessionStorage.getItem("sb_resume_skills");
const skillsField = document.getElementById("skillsInput");

if (savedSkills && skillsField && !skillsField.value.trim()) {
    skillsField.value = savedSkills;
}
const matchButton = document.getElementById("matchButton");
if (matchButton) {
  matchButton.addEventListener("click", async () => {
    const skills = (document.getElementById("skillsInput") || {}).value || "";
    const output = document.getElementById("matchResults");
    if (!output) return;
    output.innerHTML = '<div class="loading-text"><span class="spinner"></span> Finding relevant demo roles…</div>';
    try {
      const jobs = await postJSON("/api/match", {skills});
      if (!jobs.length) { output.innerHTML = `<p class="muted">${I18N[currentLang].noJobs}</p>`; return; }
      output.innerHTML = jobs.map(renderMatchItem).join("");
    } catch (e) {
      output.innerHTML = `<div class="alert alert-error show">${escapeHTML(e.message)}</div>`;
    }
  });
}

/* ─── Job search / filter (jobs page) ────────────────────────────────────── */
const jobFilter = document.getElementById("jobFilter");
if (jobFilter) {
  jobFilter.addEventListener("input", () => {
    const q = jobFilter.value.toLowerCase();
    document.querySelectorAll(".job-card-static").forEach(card => {
      const text = card.textContent.toLowerCase();
      card.style.display = text.includes(q) ? "" : "none";
    });
  });
}

/* ─── Career assistant ────────────────────────────────────────────────────── */
const ask = document.getElementById("askAssistant");
if (ask) {
  ask.addEventListener("click", async () => {
    const reply = document.getElementById("assistantReply");
    if (!reply) return;
    reply.textContent = I18N[currentLang].thinking;
    const langSel = document.getElementById("language");
    const lang = langSel ? langSel.value : "English";
    const msg  = (document.getElementById("question") || {}).value || "";
    try {
      const result = await postJSON("/assistant", {message: msg, language: lang});
      reply.textContent = result.reply;
    } catch (e) {
      reply.textContent = e.message;
    }
  });
}

/* ─── Resume upload ──────────────────────────────────────────────────────── */
(function initResumeUpload() {
  const zone      = document.getElementById("uploadZone");
  const fileInput = document.getElementById("resumeFile");
  const btn       = document.getElementById("uploadResumeBtn");
  const preview   = document.getElementById("filePreview");
  const alert     = document.getElementById("uploadAlert");
  const results   = document.getElementById("resumeResults");
  const skillOut  = document.getElementById("extractedSkills");
  const textPrev  = document.getElementById("resumeTextPreview");
  const progress  = document.getElementById("uploadProgress");

  if (!zone || !fileInput) return;

  // Click zone to pick file
  zone.addEventListener("click", () => fileInput.click());

  // Drag-and-drop
  zone.addEventListener("dragover", e => { e.preventDefault(); zone.classList.add("dragover"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("dragover"));
  zone.addEventListener("drop", e => {
    e.preventDefault();
    zone.classList.remove("dragover");
    const file = e.dataTransfer.files[0];
    if (file) { fileInput.files = e.dataTransfer.files; showFilePreview(file); }
  });

  fileInput.addEventListener("change", () => {
    if (fileInput.files[0]) showFilePreview(fileInput.files[0]);
  });

  function showFilePreview(file) {
    if (!preview) return;
    const allowed = ["application/pdf",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "text/plain"];
    const ext = file.name.split(".").pop().toLowerCase();
    if (!["pdf","docx","txt"].includes(ext)) {
      showAlert(alert, "error", "Only PDF, DOCX and TXT files are supported.");
      return;
    }
    preview.style.display = "flex";
    preview.innerHTML = `<span>📄</span><span class="fname">${escapeHTML(file.name)}</span>
      <span class="muted" style="margin-left:auto">${(file.size/1024).toFixed(1)} KB</span>`;
  }

  if (btn) {
    btn.addEventListener("click", async () => {
      if (!fileInput.files[0]) {
        showAlert(alert, "error", "Please choose a resume file first.");
        return;
      }
      const originalText = btn.textContent;
      setLoading(btn, true, originalText);
      if (progress) { progress.style.display = "block"; progress.querySelector(".progress-fill").style.width = "0%"; }
      showAlert(alert, "info", I18N[currentLang].uploading);

      // Animate progress bar
      let pct = 0;
      const tick = setInterval(() => {
        pct = Math.min(pct + 15, 85);
        if (progress) progress.querySelector(".progress-fill").style.width = pct + "%";
      }, 200);

      const form = new FormData();
      form.append("resume", fileInput.files[0]);
      try {
        const r = await fetch("/resume", {method: "POST", body: form});
        const data = await r.json();
        clearInterval(tick);
        if (progress) progress.querySelector(".progress-fill").style.width = "100%";
        if (!r.ok) throw new Error(data.error || "Upload failed");

        showAlert(alert, "success", `Analysed: ${escapeHTML(data.filename)} — ${data.skills.length} skill(s) detected.`);

        // Show skill chips
        if (skillOut) {
          skillOut.innerHTML = data.skills.length
            ? data.skills.map(s => `<span class="chip chip-skill">${escapeHTML(s)}</span>`).join("")
            : `<span class="muted">No recognised skills found. Try a more detailed resume.</span>`;
        }
        // Show text preview
        if (textPrev && data.preview) {
          textPrev.textContent = data.preview;
          textPrev.style.display = "block";
          
// Display resume quality analysis
const analysis = data.analysis;

if (analysis) {
    const analysisBox = document.getElementById("resumeAnalysis");
    const score = document.getElementById("resumeScore");
    const breakdown = document.getElementById("resumeScoreBreakdown");
    const detected = document.getElementById("resumeDetectedSections");
    const missing = document.getElementById("resumeMissingSections");
    const suggestions = document.getElementById("resumeSuggestions");
    const disclaimer = document.getElementById("resumeDisclaimer");

    if (score) score.textContent = `${analysis.score}/100`;

    if (breakdown) {
        breakdown.innerHTML = Object.entries(analysis.score_breakdown)
            .map(([name, item]) =>
                `<p>${name}: ${item.earned}/${item.maximum}</p>`
            ).join("");
    }

    if (detected) {
        detected.textContent = analysis.detected_sections.join(", ") || "None";
    }

    if (missing) {
        missing.textContent = analysis.missing_sections.join(", ") || "None";
    }

    if (suggestions) {
        suggestions.innerHTML = "";
        analysis.suggestions.forEach(item => {
            const li = document.createElement("li");
            li.textContent = item;
            suggestions.appendChild(li);
        });
    }

    if (disclaimer) disclaimer.textContent = analysis.disclaimer;
    if (analysisBox) analysisBox.style.display = "block";
}

        }
        if (results) results.style.display = "block";

        // Pre-fill skills matcher
       // Save extracted skills for the Jobs page
if (data.skills.length) {
    const resumeSkills = data.skills.join(", ");
    sessionStorage.setItem("sb_resume_skills", resumeSkills);

    const si = document.getElementById("skillsInput");
    if (si) si.value = resumeSkills;
}
      } catch (e) {
        clearInterval(tick);
        if (progress) progress.querySelector(".progress-fill").style.width = "0%";
        showAlert(alert, "error", e.message);
      } finally {
        setLoading(btn, false, originalText);
      }
    });
  }
})();

/* ─── Kanban status updates ──────────────────────────────────────────────── */
async function updateStatus(appId, newStatus, notesEl, btn) {
  const notes = notesEl ? notesEl.value : undefined;
  const originalText = btn ? btn.textContent : "";
  if (btn) setLoading(btn, true, originalText);
  try {
    const payload = {status: newStatus};
    if (notes !== undefined) payload.notes = notes;
    await patchJSON(`/application/${appId}/status`, payload);
    // Move card to correct column
    const card = document.querySelector(`[data-app-id="${appId}"]`);
    if (card) {
      const colKey = newStatus.toLowerCase().replace(" ", "-");
      const target = document.getElementById(`col-${colKey}`);
      if (target) {
        // Update badge
        const badge = card.querySelector(".tag");
        if (badge) { badge.textContent = newStatus; badge.className = `tag status-${colKey}`; }
        target.appendChild(card);
      }
    }
    const feedbackEl = document.getElementById(`feedback-${appId}`);
    if (feedbackEl) showAlert(feedbackEl, "success", "Updated.");
  } catch (e) {
    const feedbackEl = document.getElementById(`feedback-${appId}`);
    if (feedbackEl) showAlert(feedbackEl, "error", e.message);
  } finally {
    if (btn) setLoading(btn, false, originalText);
  }
}

// Wire all kanban status buttons
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".status-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const appId = btn.dataset.appId;
      const newStatus = btn.dataset.status;
      const notesEl = document.getElementById(`notes-${appId}`);
      updateStatus(appId, newStatus, notesEl, btn);
    });
  });
});

/* ─── Consent banner ─────────────────────────────────────────────────────── */
(function initConsentBanner() {
  const banner = document.getElementById("consentBanner");
  const okBtn  = document.getElementById("consentOk");
  if (!banner) return;

  if (!localStorage.getItem("sb_consent")) {
    // Show banner — switch display from none to flex
    banner.style.display = "flex";
  }

  if (okBtn) {
    okBtn.addEventListener("click", () => {
      localStorage.setItem("sb_consent", "1");
      banner.style.display = "none";
    });
  }
})();
