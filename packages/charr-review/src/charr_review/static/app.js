"use strict";

// Single-page review UI. The whole substrate arrives once as JSON; navigation, filtering, and image prefetch are all
// client-side so stepping through results stays instant (see docs/adr/0023).

const state = {
  rows: [],
  filtered: [],
  selected: 0,
};

const els = {
  summary: document.getElementById("summary"),
  warnings: document.getElementById("warnings"),
  ruleFilter: document.getElementById("rule-filter"),
  onlyMismatches: document.getElementById("only-mismatches"),
  list: document.getElementById("list"),
  img: document.getElementById("chart-img"),
  meta: document.getElementById("meta"),
};

async function init() {
  const response = await fetch("/api/rows");
  if (!response.ok) {
    els.list.innerHTML = '<div class="empty">Failed to load /api/rows.</div>';
    return;
  }
  const data = await response.json();
  state.rows = data.rows;
  renderSummary(data.summary);
  renderWarnings(data.warnings);
  populateRuleFilter(state.rows);

  els.onlyMismatches.addEventListener("change", applyFilter);
  els.ruleFilter.addEventListener("change", applyFilter);
  document.addEventListener("keydown", onKey);
  applyFilter();
}

function renderSummary(summary) {
  const order = ["total", "mismatches", "TP", "FP", "FN", "TN", "ERROR"];
  els.summary.innerHTML = "";
  for (const key of order) {
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.textContent = key + ": " + (summary[key] || 0);
    els.summary.appendChild(chip);
  }
}

function renderWarnings(warnings) {
  els.warnings.innerHTML = "";
  for (const text of warnings || []) {
    const div = document.createElement("div");
    div.className = "warning";
    div.textContent = text;
    els.warnings.appendChild(div);
  }
}

function populateRuleFilter(rows) {
  const rules = Array.from(new Set(rows.map((r) => r.rule_id))).sort();
  for (const rule of rules) {
    const option = document.createElement("option");
    option.value = rule;
    option.textContent = rule;
    els.ruleFilter.appendChild(option);
  }
}

function applyFilter() {
  const onlyMismatches = els.onlyMismatches.checked;
  const rule = els.ruleFilter.value;
  state.filtered = state.rows.filter((row) => {
    if (onlyMismatches && row.correct) return false;
    if (rule && row.rule_id !== rule) return false;
    return true;
  });
  state.selected = 0;
  renderList();
  if (state.filtered.length > 0) {
    select(0);
  } else {
    els.img.removeAttribute("src");
    els.meta.innerHTML = "";
    els.list.innerHTML = '<div class="empty">No rows match the current filter.</div>';
  }
}

function renderList() {
  els.list.innerHTML = "";
  state.filtered.forEach((row, position) => {
    const item = document.createElement("div");
    item.className = "row" + (position === state.selected ? " selected" : "");
    item.dataset.position = String(position);

    const badge = document.createElement("span");
    badge.className = "badge outcome-" + row.outcome;
    badge.textContent = row.outcome;

    const rule = document.createElement("span");
    rule.className = "rule";
    rule.textContent = row.rule_id;

    const verdicts = document.createElement("span");
    verdicts.className = "verdicts";
    verdicts.textContent = row.truth + " -> " + (row.predicted === null ? "error" : row.predicted);

    item.append(badge, rule, verdicts);
    item.addEventListener("click", () => select(position));
    els.list.appendChild(item);
  });
}

function select(position) {
  if (position < 0 || position >= state.filtered.length) return;
  state.selected = position;
  const row = state.filtered[position];

  els.img.src = "/img/" + row.index;
  renderMeta(row);

  const items = els.list.querySelectorAll(".row");
  items.forEach((item, i) => item.classList.toggle("selected", i === position));
  const current = items[position];
  if (current) current.scrollIntoView({ block: "nearest" });

  prefetch(position + 1);
  prefetch(position - 1);
}

function renderMeta(row) {
  const fields = [
    ["rule", row.rule_id],
    ["expected", row.truth],
    ["predicted", row.predicted === null ? "(error)" : row.predicted],
    ["outcome", row.outcome],
    ["correct", row.correct ? "yes" : "no"],
    ["rationale", row.rationale || ""],
    ["error", row.error || ""],
    ["library", row.library || ""],
    ["polarity", row.polarity || ""],
    ["manifest", row.manifest],
    ["image", row.image],
  ];
  els.meta.innerHTML = "";
  for (const [label, value] of fields) {
    if (value === "" || value === null) continue;
    const tr = document.createElement("tr");
    const th = document.createElement("th");
    th.textContent = label;
    const td = document.createElement("td");
    if (label === "outcome") {
      const badge = document.createElement("span");
      badge.className = "badge outcome-" + value;
      badge.textContent = value;
      td.appendChild(badge);
    } else {
      td.textContent = value;
    }
    tr.append(th, td);
    els.meta.appendChild(tr);
  }
}

function prefetch(position) {
  if (position < 0 || position >= state.filtered.length) return;
  const image = new Image();
  image.src = "/img/" + state.filtered[position].index;
}

function onKey(event) {
  // Leave form controls (and modified key chords) to the browser, so e.g. the rule dropdown navigates normally.
  if (event.altKey || event.ctrlKey || event.metaKey) return;
  const tag = event.target && event.target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
  if (event.key === "ArrowDown" || event.key === "j") {
    event.preventDefault();
    select(state.selected + 1);
  } else if (event.key === "ArrowUp" || event.key === "k") {
    event.preventDefault();
    select(state.selected - 1);
  }
}

init();
