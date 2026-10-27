/* Local Companion UI.
 *
 * Rules this file follows:
 *   - every string from the server is inserted with textContent / createTextNode,
 *     never innerHTML: a build log is attacker-influenced if the paper is;
 *   - the bootstrap token is read from the URL fragment, sent once, then the
 *     fragment is cleared so it does not survive in history or in a screenshot;
 *   - no external request is ever made.
 */
"use strict";

const POLL_MS = 500;
const $ = (id) => document.getElementById(id);

let sessionReady = false;
let pollTimer = null;
let runningJobId = null;

/* ------------------------------------------------------------------ utils */

async function api(path, options = {}) {
  const opts = Object.assign({ credentials: "same-origin", cache: "no-store" }, options);
  const res = await fetch(path, opts);
  let body = null;
  try { body = await res.json(); } catch (_) { body = null; }
  return { ok: res.ok, status: res.status, body };
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function setState(pill, kind, text) {
  pill.className = "pill " + kind;
  pill.textContent = text;
}

/* --------------------------------------------------------------- session */

function fragmentToken() {
  const hash = window.location.hash.replace(/^#/, "");
  if (!hash) return "";
  const params = new URLSearchParams(hash);
  return params.get("t") || "";
}

function clearFragment() {
  if (window.location.hash) {
    history.replaceState(null, "", window.location.pathname + window.location.search);
  }
}

async function bootstrap(token) {
  const res = await api("/api/bootstrap", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token })
  });
  return res.ok;
}

async function ensureSession() {
  const probe = await api("/api/session");
  if (probe.ok && probe.body && probe.body.has_session) {
    sessionReady = true;
    $("unlock").classList.add("hidden");
    return true;
  }

  const token = fragmentToken();
  if (token) {
    const ok = await bootstrap(token);
    clearFragment();
    if (ok) {
      sessionReady = true;
      $("unlock").classList.add("hidden");
      return true;
    }
  }
  $("unlock").classList.remove("hidden");
  return false;
}

$("unlock-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const value = $("unlock-token").value.trim();
  $("unlock-error").textContent = "";
  if (!value) return;
  const ok = await bootstrap(value);
  $("unlock-token").value = "";
  if (ok) {
    sessionReady = true;
    $("unlock").classList.add("hidden");
    await loadAll();
  } else {
    $("unlock-error").textContent =
      "That token was not accepted. Copy the full URL printed by the launcher.";
  }
});

/* ----------------------------------------------------------- environment */

function renderEnv(data) {
  $("project-name").textContent = data.project_name || "Paper workbench";
  // Show the folder name, not the absolute path: a screenshot of this page is
  // the kind of thing that ends up in a bug report or a slide, and a home
  // directory in it leaks the user name for no benefit.
  $("footer-root").textContent = data.project_name
    ? "Project folder: " + data.project_name
    : "";

  const summary = $("env-summary");
  const list = $("env-list");
  list.replaceChildren();

  // A cold scan runs in the background; until it lands, say so instead of
  // claiming the environment is ready when nothing has been checked yet.
  if (data.scanning) {
    summary.textContent = "Checking what is installed…";
    $("build-btn").disabled = true;
    return true;      // still scanning: the caller should keep polling
  }

  for (const item of data.items) {
    const li = el("li", (item.present ? "present" : "absent") +
                       (item.required ? "" : " optional"));
    li.appendChild(el("span", "tick", item.present ? "✓" : "✗"));

    const body = el("div");
    body.appendChild(el("div", "name", item.label));
    body.appendChild(el("div", "why", item.purpose));
    if (item.detail) body.appendChild(el("div", "ver", item.detail));

    if (!item.present) {
      const install = el("div", "install");
      install.appendChild(el("code", null, item.install));
      const link = el("a", null, "official download");
      link.href = item.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      install.appendChild(link);
      body.appendChild(install);
    }

    li.appendChild(body);
    li.appendChild(el("span", "tag " + (item.required ? "required" : "optional"),
                      item.required ? "required" : "optional"));
    list.appendChild(li);
  }

  if (data.can_build) {
    summary.textContent = "Ready to compile. Everything the build needs is present.";
    $("build-btn").disabled = false;
  } else {
    summary.textContent =
      "Compiling is disabled until these are installed: " + data.blocking.join(", ") +
      ". The workbench still works for everything else.";
    $("build-btn").disabled = true;
  }
}

/* ----------------------------------------------------------------- build */

function renderJob(job) {
  const pill = $("build-state");
  const meta = $("build-meta");
  const problem = $("build-problem");
  const log = $("build-log");

  if (!job) {
    setState(pill, "idle", "not run yet");
    meta.textContent = "";
    problem.classList.add("hidden");
    log.textContent = "";
    return;
  }

  if (job.state === "running") {
    setState(pill, "running", "compiling…");
    const secs = Math.round(Date.now() / 1000 - job.started_at);
    meta.textContent = "job " + job.id + " · " + secs + "s";
    problem.classList.add("hidden");
    return;
  }

  setState(pill, job.exit_code === 0 ? "ok" : "bad",
           job.exit_code === 0 ? "succeeded" : "failed (exit " + job.exit_code + ")");
  meta.textContent = "job " + job.id + " · " + job.duration_s + "s" +
                     (job.timed_out ? " · stopped at the time limit" : "");

  if (job.problem) {
    problem.textContent = job.problem.line;
    problem.classList.remove("hidden");
    $("build-log-wrap").open = true;
  } else if (job.exit_code !== 0) {
    problem.textContent = job.timed_out
      ? "The build ran past the time limit and was stopped."
      : "The build failed. Open the log; the first error explains the rest.";
    problem.classList.remove("hidden");
    $("build-log-wrap").open = true;
  } else {
    problem.classList.add("hidden");
  }

  log.textContent = job.log || "(no output)";
}

async function pollJob() {
  const res = await api("/api/build/status");
  if (!res.ok || !res.body) return;
  const job = res.body.job;
  renderJob(job);
  if (!job || job.state !== "running") {
    stopPolling();
    if (job && job.exit_code === 0) {
      $("preview-note").textContent = "A fresh PDF is ready. Open it below.";
    }
  }
}

function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(pollJob, POLL_MS);
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  runningJobId = null;
}

$("build-btn").addEventListener("click", async () => {
  const btn = $("build-btn");
  btn.disabled = true;
  const res = await api("/api/build", { method: "POST" });
  btn.disabled = false;

  if (!res.ok && res.status !== 409) {
    $("build-problem").textContent = "Could not start the build: " +
      (res.body && res.body.error ? res.body.error : "HTTP " + res.status);
    $("build-problem").classList.remove("hidden");
    return;
  }
  runningJobId = res.body.job.id;
  renderJob(res.body.job);
  startPolling();
});

/* --------------------------------------------------------------- preview */

$("pdf-btn").addEventListener("click", async () => {
  const note = $("preview-note");
  const wrap = $("pdf-frame-wrap");
  // A build id in the query defeats a cached preview; the server ignores it.
  const bust = Date.now();
  const probe = await fetch("/api/pdf?b=" + bust, { credentials: "same-origin", cache: "no-store" });
  if (!probe.ok) {
    note.textContent = probe.status === 404
      ? "There is no build/main.pdf yet. Compile the paper first."
      : "Could not open the PDF (HTTP " + probe.status + ").";
    wrap.classList.add("hidden");
    return;
  }
  note.textContent = "Showing build/main.pdf (build " + bust + ").";
  $("pdf-frame").src = "/api/pdf?b=" + bust;
  wrap.classList.remove("hidden");
});

$("code-btn").addEventListener("click", async () => {
  const note = $("preview-note");
  const res = await api("/api/open-vscode", { method: "POST" });
  if (!res.ok) {
    note.textContent = "Could not ask VS Code to open (HTTP " + res.status + ").";
    return;
  }
  note.textContent = res.body.opened
    ? "VS Code should be opening " + res.body.path + "."
    : res.body.note + " " + res.body.path;
});

/* ---------------------------------------------------------------- prompt */

async function loadSections() {
  const res = await api("/api/sections");
  if (!res.ok || !res.body) return;
  const target = $("prompt-target");
  const kind = $("prompt-kind");
  target.replaceChildren();
  kind.replaceChildren();

  if (!res.body.sections.length) {
    target.appendChild(el("option", null, "no sections/*.tex found"));
    target.disabled = true;
    $("prompt-btn").disabled = true;
    return;
  }
  for (const section of res.body.sections) {
    const opt = el("option", null, section);
    opt.value = section;
    target.appendChild(opt);
  }
  for (const [key, label] of Object.entries(res.body.kinds)) {
    const opt = el("option", null, label);
    opt.value = key;
    kind.appendChild(opt);
  }
}

$("prompt-btn").addEventListener("click", async () => {
  const res = await api("/api/prompt", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      target: $("prompt-target").value,
      kind: $("prompt-kind").value
    })
  });
  const out = $("prompt-out");
  if (!res.ok) {
    out.value = "Could not generate: " +
      (res.body && res.body.error ? res.body.error : "HTTP " + res.status);
    return;
  }
  out.value = res.body.prompt;
  $("copy-state").textContent = "";
});

$("copy-btn").addEventListener("click", async () => {
  const out = $("prompt-out");
  const state = $("copy-state");
  if (!out.value) { state.textContent = "Nothing to copy yet."; return; }
  try {
    await navigator.clipboard.writeText(out.value);
    state.textContent = "Copied.";
  } catch (_) {
    // Clipboard is unavailable (no permission, or not a secure context).
    // Fall back to selecting the textarea so the user can copy by hand.
    out.focus();
    out.select();
    state.textContent = "Clipboard is blocked here. The text is selected — press Ctrl+C.";
  }
});

/* ------------------------------------------------------------------- git */

function renderGit(data) {
  const body = $("git-body");
  body.replaceChildren();
  const git = data.git || {};

  if (!git.is_repo) {
    body.appendChild(el("p", "empty", git.note || "Not a Git repository."));
    return;
  }

  const head = el("div", "kv");
  head.appendChild(el("span", "k", "HEAD"));
  head.appendChild(el("span", "v", git.head || "(no commits)"));
  body.appendChild(head);

  const branch = el("div", "kv");
  branch.appendChild(el("span", "k", "branch"));
  branch.appendChild(el("span", "v", git.branch || "(detached)"));
  body.appendChild(branch);

  body.appendChild(el("h3", null, "Working tree"));
  if (git.status && git.status.length) {
    body.appendChild(el("pre", null, git.status.join("\n")));
  } else {
    body.appendChild(el("p", "empty", "Clean: no uncommitted changes."));
  }

  body.appendChild(el("h3", null, "Diff summary"));
  if (git.diff_stat && git.diff_stat.length) {
    body.appendChild(el("pre", null, git.diff_stat.join("\n")));
  } else {
    body.appendChild(el("p", "empty", "No unstaged changes."));
  }

  const g = data.guardrail || {};
  body.appendChild(el("h3", null, "Guardrail"));
  if (!g.available) {
    body.appendChild(el("p", "empty", g.note || "Not available."));
    return;
  }
  const status = el("div", "kv");
  status.appendChild(el("span", "k", "status"));
  status.appendChild(el("span", "v", (g.status || "?") + " (exit " + g.exit + ")"));
  body.appendChild(status);

  if (g.findings && g.findings.length) {
    const lines = g.findings.map((f) =>
      "[" + f.severity + "] " + f.category + " · " + f.path + ": " + f.detail);
    body.appendChild(el("pre", null, lines.join("\n")));
  }
  if (g.not_checked && g.not_checked.length) {
    body.appendChild(el("p", "note",
      "Not checked: " + g.not_checked.join(", ") + "."));
  }
}

async function loadGit() {
  const res = await api("/api/git");
  if (!res.ok || !res.body) return;
  renderGit(res.body);
}

/* ------------------------------------------------------------------ boot */

let envScanTimer = null;

function pollUntilScanned() {
  if (envScanTimer) return;
  envScanTimer = setInterval(async () => {
    const res = await api("/api/env");
    if (!res.ok || !res.body) return;
    if (!res.body.scanning) {
      clearInterval(envScanTimer);
      envScanTimer = null;
      renderEnv(res.body);
    }
  }, 1000);
}

async function loadAll() {
  const env = await api("/api/env");
  if (env.ok && env.body) {
    const scanning = renderEnv(env.body);
    if (scanning) pollUntilScanned();
  }

  const status = await api("/api/build/status");
  if (status.ok && status.body) {
    renderJob(status.body.job);
    if (status.body.job && status.body.job.state === "running") startPolling();
  }

  await loadSections();
  await loadGit();
}

$("theme-toggle").addEventListener("click", () => {
  const current = document.documentElement.getAttribute("data-theme");
  const next = current === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  try { localStorage.setItem("alw-theme", next); } catch (_) { /* private mode */ }
});

(function initTheme() {
  let saved = null;
  try { saved = localStorage.getItem("alw-theme"); } catch (_) { /* ignore */ }
  if (!saved) {
    saved = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  document.documentElement.setAttribute("data-theme", saved);
})();

(async function start() {
  const ready = await ensureSession();
  if (ready) await loadAll();
})();
