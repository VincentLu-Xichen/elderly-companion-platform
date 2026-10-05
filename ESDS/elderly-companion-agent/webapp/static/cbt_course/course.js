"use strict";

function courseCookie(name) {
  const prefix = `${name}=`;
  const item = document.cookie.split("; ").find((entry) => entry.startsWith(prefix));
  return item ? decodeURIComponent(item.slice(prefix.length)) : "";
}

async function courseApi(url, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (options.method && options.method !== "GET") headers["X-CSRF-Token"] = courseCookie("csrf_token");
  const response = await fetch(url, { ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || "请求失败，请稍后再试。");
  return data;
}

function courseToast(message) {
  const toast = document.getElementById("course-toast");
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add("show");
  window.setTimeout(() => toast.classList.remove("show"), 2800);
}

function setCourseBusy(button, busy, label = "正在进入……") {
  if (!button) return;
  if (busy) {
    button.dataset.original = button.textContent;
    button.textContent = label;
    button.disabled = true;
  } else {
    button.textContent = button.dataset.original || button.textContent;
    button.disabled = false;
  }
}

function createLegacyFormulationText(attachment) {
  const section = document.createElement("section");
  section.className = "course-formulation-text";
  section.setAttribute("aria-label", "历史认知行为模型");
  const thoughtNote = attachment.thought_belief == null ? "" : `（相信程度 ${attachment.thought_belief}/10）`;
  const emotionNote = attachment.emotion_intensity == null ? "" : `（强烈程度 ${attachment.emotion_intensity}/10）`;
  section.textContent = [
    "历史记录：",
    `情境：${attachment.situation || "尚未记录"}`,
    `想法：${attachment.thought || "尚未记录"}${thoughtNote}`,
    `情绪：${attachment.emotion || "尚未记录"}${emotionNote}`,
    `行为：${attachment.behavior || "尚未记录"}`,
  ].join("\n");
  return section;
}

function createAttachment(attachment) {
  if (!attachment || !attachment.kind) return null;
  if (attachment.kind === "formulation") return createLegacyFormulationText(attachment);
  if (attachment.kind === "image") {
    const figure = document.createElement("figure");
    figure.className = "course-attachment";
    const image = document.createElement("img");
    image.src = attachment.src;
    image.alt = attachment.alt || "课程学习材料";
    figure.append(image);
    if (attachment.caption) {
      const caption = document.createElement("figcaption");
      caption.textContent = attachment.caption;
      figure.append(caption);
    }
    return figure;
  }
  return null;
}

function appendCourseMessage(role, text, attachment = {}, pending = false) {
  const list = document.getElementById("course-message-list");
  const article = document.createElement("article");
  article.className = `course-message ${role}${pending ? " pending" : ""}`;
  const author = document.createElement("span");
  author.textContent = role === "learner" ? "我的回答" : "课程引导";
  const bubble = document.createElement("div");
  bubble.className = "course-message-bubble";
  bubble.textContent = text;
  article.append(author, bubble);
  const material = createAttachment(attachment);
  if (material) article.append(material);
  list.append(article);
  list.scrollTop = list.scrollHeight;
  return article;
}

document.addEventListener("DOMContentLoaded", () => {
  const page = document.body.dataset.coursePage;

  if (page === "catalog") {
    document.querySelectorAll("[data-start-lesson]").forEach((button) => {
      button.addEventListener("click", async () => {
        setCourseBusy(button, true);
        try {
          const result = await courseApi(`/api/cbt-course/lessons/${button.dataset.startLesson}/start`, {
            method: "POST",
            body: "{}",
          });
          window.location.href = result.url;
        } catch (error) {
          courseToast(error.message);
          setCourseBusy(button, false);
        }
      });
    });
  }

  if (page === "conversation") {
    const shell = document.querySelector(".course-conversation");
    const form = document.getElementById("course-message-form");
    const input = document.getElementById("course-message-input");
    const count = document.getElementById("course-char-count");
    const list = document.getElementById("course-message-list");
    const button = form.querySelector("button");

    list.scrollTop = list.scrollHeight;
    input.addEventListener("input", () => {
      count.textContent = `${input.value.length} / 2000`;
    });
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
      appendCourseMessage("learner", content);
      input.value = "";
      count.textContent = "0 / 2000";
      input.disabled = true;
      setCourseBusy(button, true, "等待回复……");
      const pending = appendCourseMessage("guide", "正在理解你的回答……", {}, true);
      try {
        const result = await courseApi(`/api/cbt-course/conversations/${shell.dataset.conversationId}/messages`, {
          method: "POST",
          body: JSON.stringify({ content, idempotency_key: crypto.randomUUID() }),
        });
        pending.remove();
        appendCourseMessage("guide", result.reply, result.attachment || {});
        document.getElementById("course-phase").textContent = result.course.phase;
        document.getElementById("course-progress-value").textContent = `${result.course.progress_percent}%`;
        document.getElementById("course-progress-bar").value = result.course.progress_percent;
        if (result.course.completed) {
          shell.dataset.completed = "true";
          input.placeholder = "本课已完成，可返回课程目录查看记录。";
        }
        if (result.safety_event) courseToast("本轮触发了安全提示，课程进度未改变。");
      } catch (error) {
        pending.querySelector(".course-message-bubble").textContent = `回复失败：${error.message}`;
        pending.classList.remove("pending");
        pending.classList.add("error");
      } finally {
        const completed = shell.dataset.completed === "true";
        input.disabled = completed;
        setCourseBusy(button, false);
        button.disabled = completed;
        if (!completed) input.focus();
      }
    });
  }
});
