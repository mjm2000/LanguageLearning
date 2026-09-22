const STORAGE_KEY = "latin-study-progress-backup";

const state = {
  defaults: { from_rank: 1, to_rank: 10, all_words: false },
  drills: [],
  mastered: new Set(),
  passDrills: [],
  index: 0,
  passNum: 0,
  feedbackOpen: false,
};

const el = {
  loading: document.getElementById("loading"),
  card: document.getElementById("card"),
  done: document.getElementById("done"),
  scopeLabel: document.getElementById("scope-label"),
  statsLine: document.getElementById("stats-line"),
  meta: document.getElementById("meta"),
  word: document.getElementById("word"),
  english: document.getElementById("english"),
  prompt: document.getElementById("prompt"),
  classEl: document.getElementById("class"),
  form: document.getElementById("answer-form"),
  answer: document.getElementById("answer"),
  feedback: document.getElementById("feedback"),
  hintBtn: document.getElementById("hint-btn"),
  skipBtn: document.getElementById("skip-btn"),
  doneText: document.getElementById("done-text"),
  restartBtn: document.getElementById("restart-btn"),
};

function scopeParams() {
  if (state.defaults.all_words) {
    return { from_rank: 1, to_rank: 10, all_words: true };
  }
  return {
    from_rank: state.defaults.from_rank,
    to_rank: state.defaults.to_rank,
    all_words: false,
  };
}

function query(params) {
  const usp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null) usp.set(k, String(v));
  }
  return usp.toString();
}

async function apiGet(path, params = {}) {
  const q = query(params);
  const res = await fetch(q ? `${path}?${q}` : path);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function apiPost(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function backupProgress(masteredForms) {
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ mastered_forms: masteredForms, saved_at: Date.now() })
    );
  } catch (_) {
    /* ignore quota errors */
  }
}

function updateStats(stats) {
  state.mastered = new Set(stats.mastered_forms || []);
  backupProgress([...state.mastered]);
  const scope = state.defaults.all_words
    ? "full list"
    : `ranks ${state.defaults.from_rank}–${state.defaults.to_rank}`;
  el.scopeLabel.textContent = scope;
  el.statsLine.textContent = `${stats.forms_mastered}/${stats.total_forms} forms mastered · ${stats.words_complete}/${stats.word_total} words complete · ${stats.forms_remaining} remaining`;
}

function unmasteredDrills() {
  return state.drills.filter((d) => !state.mastered.has(d.form_key));
}

function startPass() {
  state.passDrills = unmasteredDrills();
  state.index = 0;
  state.passNum += 1;
  if (!state.passDrills.length) {
    showDone();
    return;
  }
  showDrill();
}

function skipRemainingSameRank() {
  const rank = state.passDrills[state.index]?.rank;
  if (rank === undefined) return;
  state.index += 1;
  while (state.index < state.passDrills.length && state.passDrills[state.index].rank === rank) {
    state.index += 1;
  }
}

function showDone() {
  el.card.classList.add("hidden");
  el.done.classList.remove("hidden");
  el.doneText.textContent = "Every form in this range is mastered. Progress is saved on the server.";
}

function showDrill() {
  if (state.index >= state.passDrills.length) {
    if (unmasteredDrills().length) {
      startPass();
      return;
    }
    showDone();
    return;
  }

  const drill = state.passDrills[state.index];
  const remaining = state.passDrills.length - state.index;
  el.meta.textContent = `[${remaining}/${state.passDrills.length}] #${drill.rank} (${drill.part_of_speech}) · pass ${state.passNum}`;
  el.word.textContent = `Word: ${drill.english}`;
  el.english.textContent = `English: ${drill.english_sentence}`;
  el.prompt.textContent = `Give: ${drill.form_prompt}`;
  el.classEl.textContent = `Class: ${drill.morph_class}`;
  el.answer.value = "";
  el.feedback.classList.add("hidden");
  el.feedback.textContent = "";
  state.feedbackOpen = false;
  el.card.classList.remove("hidden");
  el.done.classList.add("hidden");
  el.answer.focus();
}

function showFeedback({ correct, latin_form, latin_sentence, forms_mastered, total_forms }) {
  el.feedback.classList.remove("hidden");
  el.feedback.classList.toggle("ok", correct);
  el.feedback.classList.toggle("bad", !correct);
  const head = correct
    ? `Correct — ${latin_form}. Saved (${forms_mastered}/${total_forms} in range).`
    : `Not quite — expected ${latin_form}. Moving to next word.`;
  el.feedback.innerHTML = `${head}<div class="latin">Latin: ${latin_sentence}</div>`;
  state.feedbackOpen = true;
}

async function refreshStats() {
  const stats = await apiGet("/api/stats", scopeParams());
  updateStats(stats);
}

async function submitAnswer(event) {
  event.preventDefault();
  if (state.feedbackOpen) {
    advanceAfterFeedback();
    return;
  }
  const drill = state.passDrills[state.index];
  const result = await apiPost("/api/check", {
    ...scopeParams(),
    form_key: drill.form_key,
    answer: el.answer.value,
  });
  await refreshStats();
  showFeedback(result);
}

function advanceAfterFeedback() {
  const drill = state.passDrills[state.index];
  const lastCorrect = el.feedback.classList.contains("ok");
  if (lastCorrect) {
    state.index += 1;
  } else {
    skipRemainingSameRank();
  }
  showDrill();
}

async function hint() {
  const drill = state.passDrills[state.index];
  const result = await apiPost("/api/hint", {
    ...scopeParams(),
    form_key: drill.form_key,
  });
  el.feedback.classList.remove("hidden");
  el.feedback.classList.remove("ok", "bad");
  el.feedback.innerHTML = `Answer: ${result.latin_form}<div class="latin">Latin: ${result.latin_sentence}</div>`;
}

function skipWord() {
  skipRemainingSameRank();
  showDrill();
}

async function boot() {
  try {
    const defaults = await apiGet("/api/defaults");
    state.defaults.from_rank = defaults.from_rank;
    state.defaults.to_rank = defaults.to_rank;

    const [stats, drillsPayload] = await Promise.all([
      apiGet("/api/stats", scopeParams()),
      apiGet("/api/drills", scopeParams()),
    ]);
    state.drills = drillsPayload.drills;
    updateStats(stats);

    el.loading.classList.add("hidden");
    if (!unmasteredDrills().length) {
      showDone();
      return;
    }
    state.passNum = 0;
    startPass();
  } catch (err) {
    el.loading.innerHTML = `<p>Failed to load: ${err.message}</p>`;
  }
}

el.form.addEventListener("submit", submitAnswer);
el.hintBtn.addEventListener("click", hint);
el.skipBtn.addEventListener("click", skipWord);
el.restartBtn.addEventListener("click", () => window.location.reload());

window.addEventListener("beforeunload", () => backupProgress([...state.mastered]));

boot();
