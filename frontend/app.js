import * as api from "./api.js";
import { clearMap, fitTrack, focusObservation, setMap } from "./map.js";

const $ = (id) => document.getElementById(id);
const count = (n) => Number(n).toLocaleString();
const percent = (n) => `${(100 * n).toFixed(2)}%`;
const text = (id, value) => { $(id).textContent = value; };
const isActive = (job) => job.state === "queued" || job.state === "running";

let selectedJob;
let failedDemo;
let generation = 0;
let observations = [];
let page = 0;
const pageSize = 20;
const filters = {
  all: () => true,
  unmatched: (row) => row.predicted_arc_id < 0,
  disagreement: (row) => row.correct === false,
  events: (row) => Boolean(row.decoder_event),
};

function setStatus(message, error = false) {
  text("run-status", message);
  $("run-status").classList.toggle("error", error);
}

function setMode(isDemo) {
  $("demo-tab").setAttribute("aria-pressed", isDemo);
  $("upload-tab").setAttribute("aria-pressed", !isDemo);
  $("demo-form").hidden = !isDemo;
  $("upload-form").hidden = isDemo;
}

async function refreshJobs() {
  const jobs = await api.getJobs();
  $("jobs").replaceChildren(...jobs.map((job) => {
    const button = document.createElement("button");
    button.type = "button";
    const name = document.createElement("strong");
    name.textContent = job.trip_id;
    const state = document.createElement("small");
    state.textContent = `${job.source === "demo" ? "Demo" : "Upload"} · ${job.state}`;
    button.setAttribute("aria-current", job.job_id === selectedJob);
    button.append(name, state);
    button.addEventListener("click", () => viewJob(job));
    return button;
  }));
  if (jobs.length === 0) $("jobs").textContent = "No runs yet";
  return jobs;
}

function renderRows() {
  const rows = observations.filter(filters[$("table-filter").value]);
  const lastPage = Math.max(0, Math.ceil(rows.length / pageSize) - 1);
  page = Math.min(page, lastPage);
  const start = page * pageSize;
  $("observation-rows").replaceChildren(...rows.slice(start, start + pageSize).map((row) => {
    const tr = document.createElement("tr");
    const first = tr.insertCell();
    const locate = document.createElement("button");
    locate.type = "button";
    locate.textContent = row.observation_id;
    locate.setAttribute("aria-label", `Show observation ${row.observation_id} on map`);
    locate.addEventListener("click", () => {
      focusObservation(row.observation_id);
      $("map").scrollIntoView({ block: "nearest" });
    });
    first.append(locate);
    for (const value of [row.raw_row, row.timestamp, row.candidate_count,
      row.predicted_arc_id < 0 ? "Unmatched" : row.predicted_arc_id,
      row.reference_arc_id ?? "—", row.decoder_event || "—"]) {
      tr.insertCell().textContent = value;
    }
    return tr;
  }));
  text("page-status", rows.length ? `${count(start + 1)}–${count(Math.min(start + pageSize, rows.length))} of ${count(rows.length)}` :
    observations.length ? "No observations match this filter" : "No observations loaded");
  $("prev-page").disabled = page === 0;
  $("next-page").disabled = page === lastPage;
}

function showRunState(tripId, subtitle, mapMessage) {
  text("result-title", tripId ? `Trip ${tripId}` : "Trip overview");
  text("result-subtitle", subtitle);
  for (const id of ["n-observations", "n-matched", "agreement", "continuity"]) text(id, "—");
  for (const id of ["n-cleaned", "n-unmatched", "agreement-detail", "continuity-detail", "network-note"]) text(id, "");
  $("downloads").hidden = true;
  $("fit-map").disabled = true;
  $("run-details").hidden = true;
  $("table-filter").disabled = true;
  $("table-filter").value = "all";
  $("retry-demo").hidden = true;
  failedDemo = undefined;
  text("map-message", mapMessage);
  $("map-message").hidden = false;
  clearMap();
  observations = [];
  page = 0;
  renderRows();
}

function showJobFailure(job, message) {
  showRunState(job.trip_id, "Run failed", "No map was generated for this run.");
  setStatus(`Trip ${job.trip_id}: ${message}`, true);
  if (job.source === "demo") {
    failedDemo = job.trip_id;
    $("retry-demo").hidden = false;
  }
}

function showResult(job, summary, data, result, demoRoads) {
  const a = summary.reference_agreement;
  const cleaned = summary.cleaning;
  text("result-title", `Trip ${job.trip_id}`);
  text("result-subtitle", job.source === "demo" ? "Bundled held-out trip" : "Uploaded trip");
  text("n-observations", count(summary.observations));
  text("n-cleaned", `${count(cleaned.raw_observations - cleaned.observations)} rows removed during cleaning`);
  text("n-matched", count(summary.matched));
  text("n-unmatched", `${count(summary.unmatched)} unmatched`);
  text("agreement", a ? percent(a.fraction) : "—");
  text("agreement-detail", a ? `${count(a.correct)} of ${count(a.total)} observations` : "No reference route supplied");
  text("continuity", percent(summary.route_continuity));
  text("continuity-detail", `${count(summary.continuous_pairs)} of ${count(summary.continuity_pair_count)} consecutive pairs`);
  let networkNote = summary.network.partial ? `${count(summary.network.displayed_arcs)} nearby arcs displayed` : "";
  if (job.source === "demo") {
    networkNote = demoRoads?.coordinates.length
      ? `${count(demoRoads.coordinates.length)} road segments · built-in map`
      : "Built-in road map unavailable. Showing nearby roads.";
  }
  text("network-note", networkNote);
  $("downloads").hidden = false;
  for (const type of ["csv", "geojson", "json"]) $(`${type}-export`).href = api.exportUrl(job.job_id, type);
  setMap(data, demoRoads);
  $("map-message").hidden = true;
  $("fit-map").disabled = false;
  observations = result.observations;
  page = 0;
  $("table-filter").value = "all";
  $("table-filter").disabled = false;
  $("table-filter").querySelector('[value="disagreement"]').disabled = !a;
  renderRows();
  const details = {
    "Invalid GPS rows discarded": count(cleaned.invalid_gps_dropped),
    "Duplicate timestamps discarded": count(cleaned.duplicate_times_dropped),
    "Rows shifted by timestamp sorting": count(cleaned.reordered_rows),
    "Gaps over 30 seconds": count(cleaned.gaps_over_30s),
    "UTM projection": `EPSG:${summary.projection_epsg}`,
    "Network nodes": count(cleaned.nodes),
    "Directed network arcs": count(cleaned.arcs),
    "Degenerate arcs excluded": count(summary.zero_length_arcs),
    "Emission candidates": count(summary.candidate_rows),
    "Reference candidate coverage": a ? percent(a.candidate_coverage) : "—",
    ...summary.decoder_events,
  };
  $("details-list").replaceChildren(...Object.entries(details).flatMap(([label, value]) => {
    const term = document.createElement("dt");
    const definition = document.createElement("dd");
    term.textContent = label;
    definition.textContent = value;
    return [term, definition];
  }));
  $("run-details").hidden = false;
}

async function viewJob(initial) {
  const current = ++generation;
  selectedJob = initial.job_id;
  if (initial.source === "demo") $("demo-trip").value = initial.trip_id;
  showRunState(initial.trip_id, isActive(initial) ? "Running" : "Loading run",
               "Waiting for trip data…");
  setStatus(`Loading trip ${initial.trip_id}…`);
  try {
    let job = initial;
    await refreshJobs();
    while (current === generation && isActive(job)) {
      setStatus(`Trip ${job.trip_id} · ${job.state}`);
      await new Promise((resolve) => setTimeout(resolve, 450));
      if (current !== generation) return;
      job = await api.getJob(job.job_id);
    }
    if (current !== generation) return;
    await refreshJobs();
    if (current !== generation) return;
    if (job.state === "failed") {
      showJobFailure(job, job.error?.message || "Inference failed. Check the server terminal.");
      return;
    }
    const [map, result, demoRoads] = await Promise.all([
      api.getMap(job.job_id),
      api.getResult(job.job_id),
      job.source === "demo" ? api.getDemoRoads(job.trip_id).catch(() => null) : null,
    ]);
    if (current !== generation) return;
    showResult(job, result.summary, map, result, demoRoads);
    setStatus(`Trip ${job.trip_id} completed`);
  } catch (error) {
    if (current === generation) showJobFailure(initial, error.message);
  }
}

async function submit(button, action, tripId, source) {
  button.disabled = true;
  const current = ++generation;
  selectedJob = undefined;
  showRunState(tripId, "Submitting trip", "Waiting for trip data…");
  setStatus("Submitting trip…");
  try {
    const job = await action();
    if (current === generation) void viewJob(job);
  } catch (error) {
    if (current === generation) showJobFailure({ trip_id: tripId, source }, error.message);
  } finally {
    button.disabled = false;
  }
}

$("demo-tab").addEventListener("click", () => setMode(true));
$("upload-tab").addEventListener("click", () => setMode(false));
$("demo-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const trip = $("demo-trip").value;
  void submit($("run-demo"), () => api.startDemo(trip), trip, "demo");
});
$("upload-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  void submit(event.submitter, () => api.startUpload(form), $("trip-id").value, "upload");
});
$("retry-demo").addEventListener("click", () => {
  const trip = failedDemo;
  if (trip) void submit($("run-demo"), () => api.startDemo(trip), trip, "demo");
});
$("fit-map").addEventListener("click", fitTrack);
$("table-filter").addEventListener("change", () => { page = 0; renderRows(); });
$("prev-page").addEventListener("click", () => { page--; renderRows(); });
$("next-page").addEventListener("click", () => { page++; renderRows(); });

async function initialize() {
  try {
    const [demos, model, jobs] = await Promise.all([api.getDemos(), api.getModel(), refreshJobs()]);
    $("demo-trip").replaceChildren(...demos.map((demo) => new Option(
      `${demo.trip_id} · ${count(demo.observations)} points`, demo.trip_id)));
    $("run-demo").disabled = demos.length === 0;
    $("demo-trip").disabled = demos.length === 0;
    text("benchmark-value", percent(model.benchmark.test_top1_accuracy));
    text("benchmark-note", `${count(model.benchmark.correct_observations)} of ${count(model.benchmark.total_observations)} held-out observations agree with weak reference labels.`);
    if (generation === 0 && jobs.length) void viewJob(jobs[0]);
    else if (generation === 0 && demos.length) {
      const trip = demos[0].trip_id;
      void submit($("run-demo"), () => api.startDemo(trip), trip, "demo");
    }
    else if (!demos.length) setMode(false);
  } catch (error) {
    setStatus(error.message, true);
  }
}

void initialize();
