// 내 에이전트 플랫폼의 화면 코드. dashboard.py의 JSON API를 부른다.
// 새 기능은 먼저 dashboard.py에 API를 더하고, 여기서 그 API를 부르게 만든다.

const $ = (id) => document.getElementById(id);
let last = 0;          // 마지막으로 받은 사건 번호
let answer = null;     // 지금 쓰는 중인 에이전트의 답 칸
const cards = {};      // 허락 요청 카드: 번호 → 칸

async function api(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

function add(className, text) {
  const div = document.createElement("div");
  div.className = "msg " + className;
  div.textContent = text;
  $("log").appendChild(div);
  $("log").scrollTop = $("log").scrollHeight;
  return div;
}

// ---- 에이전트 ----

const STATE = { idle: "연결하지 않음", starting: "연결하는 중…", ready: "준비됨", busy: "답을 쓰는 중…", error: "오류" };
const LOGIN = { true: "로그인됨", false: "로그인 필요", null: "알 수 없음" };

async function loadAgents() {
  const data = await api("GET", "/api/agents");
  $("agent").innerHTML = "";
  for (const a of data.agents) {
    const option = document.createElement("option");
    option.value = a.name;
    option.textContent = `${a.name} · ${LOGIN[a.loggedIn]}`;
    $("agent").appendChild(option);
  }
  if (data.current) $("agent").value = data.current;
  showState(data.state, data.current);
}

function showState(state, agent) {
  $("state").textContent = agent ? `${agent} · ${STATE[state] || state}` : STATE[state] || state;
}

$("connect").onclick = async () => {
  try { await api("POST", "/api/session", { agent: $("agent").value }); }
  catch (e) { add("note error", e.message); }
};

// ---- 대화 ----

$("composer").onsubmit = async (event) => {
  event.preventDefault();
  const text = $("text").value.trim();
  if (!text) return;
  try { await api("POST", "/api/prompt", { text }); $("text").value = ""; }
  catch (e) { add("note error", e.message); }
};

$("text").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    $("composer").requestSubmit();
  }
});

function permissionCard(event) {
  const card = document.createElement("div");
  card.className = "card";
  const title = document.createElement("b");
  title.textContent = `허락 요청 · ${event.title}`;
  const detail = document.createElement("div");
  detail.className = "detail";
  detail.textContent = event.detail || "";
  const actions = document.createElement("div");
  actions.className = "actions";
  for (const [label, allow] of [["허락", true], ["거절", false]]) {
    const button = document.createElement("button");
    button.textContent = label;
    if (!allow) button.className = "ghost";
    button.onclick = () => api("POST", `/api/permissions/${event.id}`, { allow }).catch((e) => add("note error", e.message));
    actions.appendChild(button);
  }
  card.append(title, detail, actions);
  $("log").appendChild(card);
  $("log").scrollTop = $("log").scrollHeight;
  cards[event.id] = card;
}

// 서버의 사건을 차례로 화면에 옮긴다.
function handle(event) {
  switch (event.type) {
    case "status":
      showState(event.state, event.agent);
      if (event.state === "ready") add("note", `${event.agent}에 연결됨`);
      if (event.state === "error") add("note error", event.message || "오류");
      break;
    case "user":
      add("user", event.text);
      answer = null;
      break;
    case "text":
      if (!answer) answer = add("agent", "");
      answer.textContent += event.text;
      $("log").scrollTop = $("log").scrollHeight;
      break;
    case "tool":
      add("note", `도구 · ${event.title}`);
      answer = null;
      break;
    case "permission":
      permissionCard(event);
      answer = null;
      break;
    case "permission_result": {
      const card = cards[event.id];
      if (card) card.querySelector(".actions").textContent = event.timeout ? "답이 없어 거절함" : event.allow ? "허락함" : "거절함";
      break;
    }
    case "done":
      add("note", `끝 · ${event.usage}`);
      answer = null;
      break;
    case "task":
      add("note", event.state === "running" ? `일 '${event.name}' 실행 시작 (${event.agent})` : `일 '${event.name}' 끝 → 결과함 ${event.file}`);
      if (event.state === "done") loadOutbox();
      break;
  }
}

async function poll() {
  while (true) {
    try {
      const data = await api("GET", `/api/events?after=${last}`);
      for (const event of data.events) handle(event);
      last = data.last;
      showState(data.state, data.agent);
    } catch (e) {
      await new Promise((r) => setTimeout(r, 2000));
    }
  }
}

// ---- 일과 결과함 ----

async function loadTasks() {
  const data = await api("GET", "/api/tasks");
  $("tasks").innerHTML = "";
  for (const task of data.tasks) {
    const li = document.createElement("li");
    li.className = "task";
    const info = document.createElement("div");
    const name = document.createElement("div");
    name.textContent = task.name;
    const meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent = `${task.agent} · ${task.time ? "매일 " + task.time : "직접 실행"}${task.lastRun ? " · 마지막 " + task.lastRun : ""}`;
    info.append(name, meta);
    const run = document.createElement("button");
    run.textContent = "실행";
    run.onclick = () => api("POST", `/api/tasks/${encodeURIComponent(task.name)}/run`).catch((e) => add("note error", e.message));
    li.append(info, run);
    $("tasks").appendChild(li);
  }
  if (!data.tasks.length) $("tasks").innerHTML = '<li class="meta">일이 없다</li>';
}

async function loadOutbox() {
  const data = await api("GET", "/api/outbox");
  $("outbox").innerHTML = "";
  for (const file of data.files.slice(0, 20)) {
    const li = document.createElement("li");
    li.className = "clickable";
    li.textContent = file.name;
    li.onclick = async () => {
      const f = await api("GET", `/api/outbox/${encodeURIComponent(file.name)}`);
      add("file", f.text);
    };
    $("outbox").appendChild(li);
  }
  if (!data.files.length) $("outbox").innerHTML = '<li class="meta">아직 없다</li>';
}

$("reload-tasks").onclick = loadTasks;
$("reload-outbox").onclick = loadOutbox;

add("note", "왼쪽에서 에이전트를 고르고 연결을 누르면 시작한다. 일은 실행을 누르거나 정해진 시각에 돈다.");
loadAgents();
loadTasks();
loadOutbox();
poll();
