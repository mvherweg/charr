"use strict";

// Single-page review UI. The whole substrate arrives once as JSON; navigation, filtering, and image prefetch are all
// client-side so stepping through results stays instant (see docs/adr/0023).

// The confusion outcomes, in display order, with human labels. Keys match data.Outcome (app-side mirror). TN is split
// into an exact agreement (pass/pass, na/na) and a loose one (pass vs not_applicable) so each can be filtered on its own.
const OUTCOMES = [
  { key: "TP", label: "TP" },
  { key: "FP", label: "FP" },
  { key: "FN", label: "FN" },
  { key: "TN_EXACT", label: "TN (exact)" },
  { key: "TN_LOOSE", label: "TN (loose)" },
  { key: "ERROR", label: "ERROR" },
];
// Default view: the fail-class errors plus the error bucket (FP/FN/ERROR). This intentionally differs from the old
// "only mismatches" filter, which keyed off !correct and so also surfaced pass<->not_applicable rows; those are now
// TN_LOOSE and hidden by default - the fix for #35. Untick a chip to hide it, tick TP/TN to bring correct rows back.
const DEFAULT_OUTCOMES = ["FP", "FN", "ERROR"];

function outcomeLabel(key) {
  const found = OUTCOMES.find((o) => o.key === key);
  return found ? found.label : key;
}

const state = {
  rows: [],
  filtered: [],
  selected: 0,
  outcomes: new Set(DEFAULT_OUTCOMES),
};

const els = {
  summary: document.getElementById("summary"),
  warnings: document.getElementById("warnings"),
  ruleFilter: document.getElementById("rule-filter"),
  outcomeFilters: document.getElementById("outcome-filters"),
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
  renderOutcomeFilters(data.summary);
  populateRuleFilter(state.rows);

  els.ruleFilter.addEventListener("change", applyFilter);
  document.addEventListener("keydown", onKey);
  applyFilter();
}

function renderOutcomeFilters(summary) {
  els.outcomeFilters.innerHTML = "";
  for (const { key, label } of OUTCOMES) {
    const active = state.outcomes.has(key);
    const chip = document.createElement("label");
    chip.className = "filter-chip outcome-" + key + (active ? "" : " off");

    const box = document.createElement("input");
    box.type = "checkbox";
    box.checked = active;
    box.addEventListener("change", () => {
      if (box.checked) state.outcomes.add(key);
      else state.outcomes.delete(key);
      chip.classList.toggle("off", !box.checked);
      applyFilter();
    });

    const text = document.createElement("span");
    text.textContent = label + " (" + (summary[key] || 0) + ")";

    chip.append(box, text);
    els.outcomeFilters.appendChild(chip);
  }
}

function renderSummary(summary) {
  const order = ["total", ...OUTCOMES.map((o) => o.key)];
  els.summary.innerHTML = "";
  for (const key of order) {
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.textContent = (key === "total" ? "total" : outcomeLabel(key)) + ": " + (summary[key] || 0);
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
  const rule = els.ruleFilter.value;
  state.filtered = state.rows.filter((row) => {
    if (!state.outcomes.has(row.outcome)) return false;
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
    badge.textContent = outcomeLabel(row.outcome);

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
      badge.textContent = outcomeLabel(value);
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
