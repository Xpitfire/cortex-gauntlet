const messages = document.getElementById("messages");
const composer = document.getElementById("composer");
const input = document.getElementById("input");

function bubble(role, content) {
  const el = document.createElement("div");
  el.className = "bubble bubble--" + role;
  el.textContent = content;
  messages.appendChild(el);
  messages.scrollTop = messages.scrollHeight;
}

async function loadHistory() {
  const res = await fetch("/api/history");
  const history = await res.json();
  messages.innerHTML = "";
  history.forEach((m) => bubble(m.role, m.content));
}

composer.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  bubble("user", text);
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ message: text }),
  });
  const data = await res.json();
  bubble("assistant", data.reply);
});

loadHistory();
