function getCookie(name) {
  const prefix = `${name}=`;
  const item = document.cookie.split("; ").find((entry) => entry.startsWith(prefix));
  return item ? decodeURIComponent(item.slice(prefix.length)) : "";
}

async function api(url, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (options.method && options.method !== "GET") headers["X-CSRF-Token"] = getCookie("csrf_token");
  const response = await fetch(url, { ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || "请求失败，请稍后再试。");
  return data;
}

function showToast(message) {
  const toast = document.getElementById("toast");
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add("show");
  window.setTimeout(() => toast.classList.remove("show"), 2600);
}

function setBusy(button, busy, text = "处理中……") {
  if (!button) return;
  if (busy) {
    button.dataset.original = button.textContent;
    button.textContent = text;
    button.disabled = true;
  } else {
    button.textContent = button.dataset.original || button.textContent;
    button.disabled = false;
  }
}

function appendMessage(role, text, pending = false) {
  document.getElementById("chat-empty")?.remove();
  const list = document.getElementById("message-list");
  const node = document.createElement("div");
  node.className = `message ${role}${pending ? " pending" : ""}`;
  const author = document.createElement("span");
  author.className = "message-author";
  author.textContent = role === "user" ? "你扮演的老人" : "Agent";
  const body = document.createElement("p");
  body.textContent = text;
  node.append(author, body);
  list.append(node);
  list.scrollTop = list.scrollHeight;
  return node;
}

document.addEventListener("DOMContentLoaded", () => {
  const page = document.body.dataset.page;

  if (page === "login") {
    const form = document.getElementById("invite-form");
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = form.querySelector("button");
      const error = document.getElementById("form-error");
      error.textContent = "";
      setBusy(button, true, "正在验证……");
      try {
        await api("/api/session/invite", { method: "POST", body: JSON.stringify({ code: document.getElementById("invite-code").value }) });
        window.location.href = "/app";
      } catch (err) {
        error.textContent = err.message;
        setBusy(button, false);
      }
    });
  }

  if (page === "home") {
    document.getElementById("logout-button")?.addEventListener("click", async (event) => {
      const logoutButton = event.currentTarget;
      setBusy(logoutButton, true, "正在退出……");
      try {
        await api("/api/session/logout", { method: "POST", body: "{}" });
        window.location.href = "/";
      } catch (err) {
        showToast(err.message);
        setBusy(logoutButton, false);
      }
    });
    const check = document.getElementById("consent-check");
    const consentButton = document.getElementById("consent-button");
    if (check) check.addEventListener("change", () => { consentButton.disabled = !check.checked; });
    if (consentButton) consentButton.addEventListener("click", async () => {
      setBusy(consentButton, true);
      try {
        await api("/api/consents", { method: "POST", body: JSON.stringify({ agreed: true }) });
        window.location.reload();
      } catch (err) {
        showToast(err.message);
        setBusy(consentButton, false);
      }
    });
    document.querySelectorAll("[data-mode]").forEach((button) => button.addEventListener("click", async () => {
      setBusy(button, true, "正在创建会话……");
      try {
        const result = await api("/api/conversations", { method: "POST", body: JSON.stringify({ mode: button.dataset.mode }) });
        window.location.href = `/conversations/${result.id}`;
      } catch (err) {
        showToast(err.message);
        setBusy(button, false);
      }
    }));
  }

  if (page === "chat") {
    const shell = document.querySelector(".chat-shell");
    const form = document.getElementById("message-form");
    const input = document.getElementById("message-input");
    const count = document.getElementById("char-count");
    const list = document.getElementById("message-list");
    const resizer = document.getElementById("chat-resizer");
    const panelWidthKey = "roleplay-session-panel-width-v2";
    const minPanelWidth = 300;
    const defaultPanelWidth = 360;
    const maxPanelWidth = () => Math.min(560, Math.max(minPanelWidth, window.innerWidth - 560));
    const setPanelWidth = (width, persist = false) => {
      const nextWidth = Math.round(Math.min(maxPanelWidth(), Math.max(minPanelWidth, width)));
      shell.style.setProperty("--session-panel-width", `${nextWidth}px`);
      resizer?.setAttribute("aria-valuenow", String(nextWidth));
      resizer?.setAttribute("aria-valuemax", String(maxPanelWidth()));
      if (persist) {
        try { window.localStorage.setItem(panelWidthKey, String(nextWidth)); } catch (_err) { /* Storage may be unavailable. */ }
      }
      return nextWidth;
    };
    if (resizer) {
      let initialWidth = defaultPanelWidth;
      try {
        const savedWidth = Number(window.localStorage.getItem(panelWidthKey));
        if (Number.isFinite(savedWidth) && savedWidth > 0) initialWidth = savedWidth;
      } catch (_err) { /* Use the default width. */ }
      setPanelWidth(initialWidth);

      let dragging = false;
      const finishResize = (event) => {
        if (!dragging) return;
        dragging = false;
        document.body.classList.remove("resizing-chat");
        if (resizer.hasPointerCapture?.(event.pointerId)) resizer.releasePointerCapture(event.pointerId);
        const currentWidth = Number.parseFloat(getComputedStyle(shell).getPropertyValue("--session-panel-width"));
        setPanelWidth(currentWidth, true);
      };
      resizer.addEventListener("pointerdown", (event) => {
        if (event.button !== 0) return;
        dragging = true;
        resizer.setPointerCapture(event.pointerId);
        document.body.classList.add("resizing-chat");
      });
      resizer.addEventListener("pointermove", (event) => {
        if (!dragging) return;
        setPanelWidth(event.clientX - shell.getBoundingClientRect().left);
      });
      resizer.addEventListener("pointerup", finishResize);
      resizer.addEventListener("pointercancel", finishResize);
      resizer.addEventListener("dblclick", () => setPanelWidth(defaultPanelWidth, true));
      resizer.addEventListener("keydown", (event) => {
        const currentWidth = Number.parseFloat(getComputedStyle(shell).getPropertyValue("--session-panel-width"));
        let nextWidth = currentWidth;
        if (event.key === "ArrowLeft") nextWidth -= 20;
        else if (event.key === "ArrowRight") nextWidth += 20;
        else if (event.key === "Home") nextWidth = minPanelWidth;
        else if (event.key === "End") nextWidth = maxPanelWidth();
        else return;
        event.preventDefault();
        setPanelWidth(nextWidth, true);
      });
      window.addEventListener("resize", () => setPanelWidth(
        Number.parseFloat(getComputedStyle(shell).getPropertyValue("--session-panel-width")),
      ));
    }
    list.scrollTop = list.scrollHeight;
    document.getElementById("end-conversation")?.addEventListener("click", async () => {
      try {
        await api(`/api/conversations/${shell.dataset.conversationId}/end`, { method: "POST", body: "{}" });
        window.location.href = "/app";
      } catch (err) { showToast(err.message); }
    });
    document.getElementById("delete-conversation")?.addEventListener("click", async () => {
      if (!window.confirm("确定永久删除本次会话和全部审计记录吗？")) return;
      try {
        await api(`/api/conversations/${shell.dataset.conversationId}`, { method: "DELETE" });
        window.location.href = "/app";
      } catch (err) { showToast(err.message); }
    });
    if (!form) return;
    input.addEventListener("input", () => { count.textContent = `${input.value.length} / 2000`; });
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        form.requestSubmit();
      }
    });
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const content = input.value.trim();
      if (!content) return;
      const button = form.querySelector("button");
      appendMessage("user", content);
      input.value = "";
      count.textContent = "0 / 2000";
      input.disabled = true;
      setBusy(button, true, "等待回复……");
      const pending = appendMessage("agent", "正在组织回复……", true);
      try {
        const result = await api(`/api/conversations/${shell.dataset.conversationId}/messages`, {
          method: "POST",
          body: JSON.stringify({ content, idempotency_key: crypto.randomUUID() }),
        });
        pending.querySelector("p").textContent = result.reply;
        pending.classList.remove("pending");
        if (result.safety_event) showToast("本轮触发了安全提示并已记录。");
      } catch (err) {
        pending.querySelector("p").textContent = `回复失败：${err.message}`;
        pending.classList.remove("pending");
        pending.classList.add("error-message");
      } finally {
        input.disabled = false;
        input.focus();
        setBusy(button, false);
      }
    });
  }

  if (page === "admin-login") {
    const form = document.getElementById("admin-login-form");
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = form.querySelector("button");
      const error = document.getElementById("form-error");
      error.textContent = "";
      setBusy(button, true, "正在登录……");
      try {
        await api("/api/admin/login", { method: "POST", body: JSON.stringify({ password: document.getElementById("admin-password").value }) });
        window.location.href = "/admin";
      } catch (err) {
        error.textContent = err.message;
        setBusy(button, false);
      }
    });
  }

  if (page === "admin-list") {
    const search = document.getElementById("admin-search");
    const mode = document.getElementById("mode-filter");
    const version = document.getElementById("version-filter");
    const status = document.getElementById("status-filter");
    const date = document.getElementById("date-filter");
    const versionPlaceholder = version.options[0].cloneNode(true);
    const versionOptions = Array.from(version.options).slice(1).map((option) => ({
      value: option.value,
      label: option.textContent,
      mode: option.dataset.mode,
    }));
    const updateVersionOptions = () => {
      const matchingOptions = versionOptions
        .filter((option) => option.mode === mode.value)
        .map((item) => {
          const option = document.createElement("option");
          option.value = item.value;
          option.textContent = item.label;
          return option;
        });
      version.replaceChildren(versionPlaceholder.cloneNode(true), ...matchingOptions);
    };
    const filter = () => {
      const query = search.value.trim().toLowerCase();
      document.querySelectorAll("#conversation-table tr").forEach((row) => {
        row.hidden = Boolean(
          (query && !row.dataset.search.toLowerCase().includes(query)) ||
          (mode.value && row.dataset.mode !== mode.value) ||
          (version.value && row.dataset.version !== version.value) ||
          (status.value && row.dataset.status !== status.value) ||
          (date.value && row.dataset.date !== date.value)
        );
      });
    };
    search.addEventListener("input", filter);
    mode.addEventListener("change", () => {
      updateVersionOptions();
      filter();
    });
    version.addEventListener("change", filter);
    status.addEventListener("change", filter);
    date.addEventListener("change", filter);
    updateVersionOptions();
  }

  if (page === "admin-detail") {
    const button = document.getElementById("admin-delete");
    button?.addEventListener("click", async () => {
      if (!window.confirm("确定永久删除该会话、消息与审计事件吗？")) return;
      setBusy(button, true, "正在删除……");
      try {
        await api(`/api/admin/conversations/${button.dataset.conversationId}`, { method: "DELETE" });
        window.location.href = "/admin";
      } catch (err) {
        showToast(err.message);
        setBusy(button, false);
      }
    });
  }
});
