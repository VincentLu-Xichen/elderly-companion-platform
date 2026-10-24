"use strict";

function courseCookie(name) {
  const item = document.cookie.split("; ").find((entry) => entry.startsWith(`${name}=`));
  return item ? decodeURIComponent(item.slice(name.length + 1)) : "";
}

async function courseApi(url, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (options.method && options.method !== "GET") headers["X-CSRF-Token"] = courseCookie("csrf_token");
  const response = await fetch(url, { ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "请求未完成，请刷新页面后再试。");
  return data;
}

function courseToast(message) {
  const toast = document.getElementById("course-toast");
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add("show");
  window.setTimeout(() => toast.classList.remove("show"), 4500);
}

function courseElement(tag, text, className = "") {
  const element = document.createElement(tag);
  if (text) element.textContent = text;
  if (className) element.className = className;
  return element;
}

function appendCourseMessage(role, text) {
  const list = document.getElementById("course-message-list");
  const article = courseElement("article", "", `course-message ${role}`);
  article.append(courseElement("span", role === "learner" ? "我的回答" : "课程引导"), courseElement("div", text, "course-message-bubble"));
  list.append(article);
  list.scrollTop = list.scrollHeight;
  return article;
}

document.addEventListener("DOMContentLoaded", () => {
  if (document.body.dataset.coursePage === "catalog") {
    document.querySelectorAll("[data-start-lesson]").forEach((button) => button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        const result = await courseApi(`/api/cbt-course/lessons/${button.dataset.startLesson}/start`, { method: "POST", body: "{}" });
        window.location.href = result.url;
      } catch (error) { courseToast(error.message); button.disabled = false; }
    }));
    return;
  }
  const initial = document.getElementById("course-initial-state");
  if (!initial) return;
  const session = JSON.parse(initial.textContent);
  const shell = document.querySelector(".course-conversation");
  const input = document.getElementById("course-message-input");
  const form = document.getElementById("course-message-form");
  const send = form.querySelector('[type="submit"]');
  const pause = document.getElementById("course-pause");
  const count = document.getElementById("course-char-count");
  const examples = document.getElementById("course-preview-example");
  const feedbackExample = document.getElementById("course-preview-feedback");
  const endpoint = `/api/cbt-course/conversations/${session.id}`;
  let course = session.course;
  let busy = false;
  let retry = null;
  let pollCount = 0;
  let diaryRetry = null;

  function renderDiaries(parent, entries) {
    entries.forEach(entry => {
      const group = courseElement("details");
      group.append(courseElement("summary", `${entry.created_at.slice(0,10)} · ${entry.source_kind === "fictional" ? "虚构练习" : "本人课后记录"}`));
      const labels = { situation: "情境", thought: "自动思维", emotion: "情绪", behavior: "行为" };
      Object.keys(labels).filter(key => key in (entry.fields || {})).forEach(key => group.append(courseElement("p", `${labels[key]}：${entry.fields[key] || "未记录"}`)));
      parent.append(group);
    });
  }

  function renderHomework() {
    const box = document.getElementById("course-homework");
    if (!box) return;
    box.hidden = !course.completed || !course.teacher_flow;
    if (box.hidden) return;
    if (box.dataset.ready) return;
    box.dataset.ready = "true";
    box.append(courseElement("h3", "课程练习 · 课后记录"), courseElement("p", course.lesson.id === "lesson-1" ? "按情境、想法、情绪、行为记录一件事。暂时想不到的部分可以留空。" : "用情境、自动思维、情绪三栏记录一件事。"));
    const list = courseElement("div");
    renderDiaries(list, session.homework_entries || []); box.append(list);
    if (session.read_only) return;
    const diaryForm = courseElement("form");
    const sourceLabel = courseElement("label", "这份记录来自：");
    const source = courseElement("select"); source.name = "source_kind";
    [["personal","自己的经历"],["fictional","虚构案例"]].forEach(([value,label]) => {
      const option = courseElement("option", label); option.value = value; source.append(option);
    });
    source.value = course.practice_source?.kind === "fictional" ? "fictional" : "personal";
    sourceLabel.append(source); diaryForm.append(sourceLabel);
    const fields = {};
    const labels = {situation:"情境：具体发生了什么",thought:"自动思维：当时怎样解释",emotion:"情绪：当时有什么感受",behavior:"行为：实际做了什么"};
    Object.keys(labels).filter(key => course.lesson.id === "lesson-1" || key !== "behavior").forEach(key => {
      const label = courseElement("label", labels[key]); const field = courseElement("textarea");
      field.maxLength = 500; field.rows = 2; field.required = key === "situation"; field.name = key;
      label.append(field); diaryForm.append(label); fields[key] = field;
    });
    const save = courseElement("button", "保存这份课后记录", "guided-action"); save.type = "submit";
    const status = courseElement("p"); status.setAttribute("role","status");
    diaryForm.append(save,status); box.append(diaryForm);
    diaryForm.addEventListener("submit", async event => {
      event.preventDefault(); save.disabled = true;
      const values = Object.fromEntries(Object.entries(fields).map(([key,field]) => [key,field.value]));
      const data = {source_kind:source.value,...values}; const fingerprint = JSON.stringify(data);
      if (!diaryRetry || diaryRetry.fingerprint !== fingerprint) diaryRetry = {fingerprint,key:crypto.randomUUID()};
      try {
        const result = await courseApi(`${endpoint}/homework`, {method:"POST",body:JSON.stringify({...data,idempotency_key:diaryRetry.key})});
        list.replaceChildren(); renderDiaries(list,result.entries); session.homework_entries = result.entries;
        const current = {source_kind:source.value,...Object.fromEntries(Object.entries(fields).map(([key,field]) => [key,field.value]))};
        const unchanged = JSON.stringify(current) === fingerprint;
        if (unchanged) Object.values(fields).forEach(field => {field.value="";});
        diaryRetry = null;
        status.textContent = "已加密保存，可在这里回看；这是您的记录，不代表系统核验过执行或效果。" + (unchanged ? "" : "您刚输入的新草稿仍保留在下方。");
      } catch (error) {status.textContent = error.message;} finally {save.disabled = false;}
    });
  }

  function button(text, action, parent) {
    const element = courseElement("button", text, "guided-action");
    element.type = "button";
    element.disabled = busy;
    element.addEventListener("click", () => submit(action));
    parent.append(element);
    return element;
  }

  function render(next) {
    const stageChanged = course.current_step !== next.current_step;
    course = next;
    renderHomework();
    const blocked = session.read_only || course.completed || course.safety_paused || course.paused;
    input.disabled = busy || blocked || course.needs_path_choice;
    send.disabled = busy || blocked || course.needs_path_choice;
    send.textContent = busy ? "正在回复……" : "发送 ↗";
    pause.hidden = session.read_only || course.completed || course.safety_paused;
    pause.disabled = busy;
    pause.textContent = course.paused ? "继续课程" : "暂停课程";
    input.placeholder = course.completed ? "本课已完成，可回看学习记录。" : course.safety_paused ? "课程已安全暂停，记录仍可查看。" : course.paused ? "课程已暂停，准备好时可继续。" : course.needs_path_choice ? "请先在学习记录区选择本课路径。" : "可以慢慢说，也可以告诉我哪里没讲清楚……";
    document.getElementById("course-phase").textContent = course.phase;
    document.getElementById("course-progress-value").textContent = session.read_only ? "历史版本，只读" : course.completed ? "本课已完成" : `第 ${course.stage_number} / ${course.stages.length} 阶段`;
    const stages = document.getElementById("course-stages");
    stages.replaceChildren();
    (course.stages || []).forEach((stage, index) => {
      const item = courseElement("li", `${index + 1}. ${stage.label}`);
      if (stage.id === course.current_step) { item.className = "is-current"; item.setAttribute("aria-current", "step"); }
      if (course.completed || index < course.stage_number - 1) item.classList.add("is-done");
      stages.append(item);
    });
    const focus = document.getElementById("course-stage-focus");
    focus.replaceChildren();
    focus.hidden = !course.stage_focus;
    if (!focus.hidden) focus.append(courseElement("strong", `现在练什么：${course.stage_focus.task || course.lesson2?.label}`),
      courseElement("p", `为什么练：${course.stage_focus.purpose}`), courseElement("p", `接下来：${course.stage_focus.exit}`));
    const practice = document.getElementById("course-practice-options");
    const skillMaterial = document.getElementById("course-skill-material");
    const skillActivities = document.getElementById("course-skill-activities");
    if (skillMaterial && skillActivities) {
      const skill = course.skill_lesson;
      const wasOpen = skillMaterial.querySelector("details")?.open || false;
      skillMaterial.replaceChildren(); skillActivities.replaceChildren();
      skillMaterial.hidden = !skill;
      skillActivities.hidden = !skill;
      if (skill) {
        const details = courseElement("details"); details.open = wasOpen;
        details.append(courseElement("summary", "本课方法与示范 · 点击回看"));
        skill.materials.forEach(item => details.append(courseElement("h3",item.title),courseElement("p",item.text)));
        if (skill.guided_question) details.append(courseElement("h3","共同练习（获得教学帮助）"),courseElement("p",skill.guided_question));
        skillMaterial.append(details);
        skillActivities.append(courseElement("h3","本课教学活动"),courseElement("p","示范、共同练习与应用分别记录；完成不等于独立掌握。","notebook-muted"));
        skill.activities.forEach(item => skillActivities.append(courseElement("p", item.status === "participated_with_support" ? `共同练习：${item.value}` : "共同练习：本次暂留或未观察")));
        Object.entries(skill.deferred).forEach(([field]) => skillActivities.append(courseElement("p", `暂留：${skill.deferred_labels[field]}`)));
        if (skill.ladder_record) skillActivities.append(courseElement("h3", skill.scope === "fictional" ? "虚构案例的排序（待尝试计划）" : "本人表达的排序（未自动换算分数）"), courseElement("p",skill.ladder_record.value));
      }
    }
    const teaching = document.getElementById("course-teacher-material");
    if (teaching) {
      const openDetails = new Map(Array.from(teaching.querySelectorAll("details[data-material-key]"), item => [item.dataset.materialKey, item.open]));
      teaching.replaceChildren();
      const flow = course.teacher_flow;
      teaching.hidden = !flow;
      if (flow) {
        if (flow.overview_pending) {
          teaching.append(courseElement("h3", "八次课程 · 先了解学习内容"));
          const overview = courseElement("ol");
          (flow.overview || []).forEach(item => {
            const row = courseElement("li"); row.append(courseElement("strong",item.title),courseElement("p",item.practice)); overview.append(row);
          });
          teaching.append(overview);
          if (!blocked) button("已看完，开始心境检查", "start_mood_check", teaching);
        } else if (course.current_step === "check_in") {
          teaching.append(courseElement("h3", "心境检查 · 上周的整体状态"), courseElement("p", flow.mood_question));
          const scores = courseElement("div", "", "weekly-score-buttons");
          for (let i = 1; i <= 10; i++) {
            const score = courseElement("button", String(i), "guided-action");
            score.type = "button"; score.disabled = busy || blocked;
            score.setAttribute("aria-label", `上周整体状态${i}分`);
            score.addEventListener("click", () => { input.value = `${i}分`; submit("chat"); });
            scores.append(score);
          }
          teaching.append(scores);
        } else {
          teaching.append(courseElement("h3", "本课教学材料"));
          if (flow.weekly_mood.status === "provided") teaching.append(courseElement("p", `上周整体状态：${flow.weekly_mood.value}/10（与本次事件的情绪强度分开记录）`, "notebook-muted"));
          if (flow.automatic_thought_teaching && ["rain","contrast","rain_insight","personal","model","plan","summary","completed"].includes(course.current_step)) {
            teaching.append(courseElement("p", flow.automatic_thought_teaching));
          }
          (flow.cards || []).forEach((card, i) => {
            const detail = courseElement("details");
            detail.dataset.materialKey = card.id || `${card.title}:${card.help}:${i}`;
            detail.open = openDetails.get(detail.dataset.materialKey) ?? false;
            detail.append(courseElement("summary", `${card.help ? "换一种说明：" : ""}${card.title}`));
            ["definition","example","explanation","expression","vocabulary"].forEach(key => {
              if (card[key]) detail.append(courseElement("p", card[key]));
            });
            teaching.append(detail);
          });
          if (["review","model","assessment","check_feedback"].includes(course.current_step)) teaching.append(courseElement("p", flow.model_explanation));
          if (course.current_step === "learning_goal") {
            teaching.append(courseElement("h4", "课程提供的目标参考"));
            const goals = courseElement("ol");
            (flow.goal_examples || []).forEach(text => goals.append(courseElement("li",text)));
            teaching.append(goals,courseElement("p","这些是原课程的参考方向和频率，不是效果承诺或必须全部完成的任务。请结合自己的需要选择、修改，也可以暂不设置。"));
          }
          const contents = courseElement("details");
          contents.dataset.materialKey = "all-teaching";
          contents.open = openDetails.get("all-teaching") ?? false;
          contents.append(courseElement("summary", "本课教学材料 · 点击展开或收起"));
          while (teaching.firstChild) contents.append(teaching.firstChild);
          teaching.append(contents);
        }
      }
    }
    const fictional = course.practice_source?.kind === "fictional";
    document.getElementById("course-record-heading").textContent = fictional ? "这次的案例练习" : "这次的个人练习";
    document.getElementById("record-empty").textContent = fictional ? "这里只记录您对虚构案例的辨认，不是您的个人经历。" : "聊到自己的例子时，记录会逐项出现在这里。";
    const material = document.getElementById("course-practice-material");
    material.replaceChildren();
    material.hidden = !fictional || course.boundary_confirmation_pending || !["practice", "review", "personal", "model", "application", "pattern"].includes(course.current_step);
    if (!material.hidden) material.append(courseElement("h3", "虚构案例 · 一起练习"), courseElement("p", course.practice_source.story));
    practice.replaceChildren();
    practice.hidden = blocked || course.show_practice_controls === false || course.boundary_confirmation_pending || course.current_step !== "practice" || !course.personal_practice?.current_field;
    if (!practice.hidden) {
      practice.append(courseElement("span", `当前只看：${course.personal_practice.current_label}`));
      if (!course.natural_feedback_enabled && course.interaction_adaptation?.status === "awaiting_choice") {
        button("直接看解释", "show_brief_explanation", practice);
        button("继续聊", "continue_practice_dialogue", practice);
      } else {
        button(course.practice_control_labels?.defer_practice_field || "这一项暂时想不起", "defer_practice_field", practice);
        button(course.practice_control_labels?.decline_practice_field || "这一项先不谈", "decline_practice_field", practice);
        if (!course.natural_feedback_enabled && course.interaction_adaptation?.status === "explanation_shown") button("继续聊", "continue_practice_dialogue", practice);
        else if (!course.natural_feedback_enabled) button("我想少解释一点", "request_less_probing", practice).className = "guided-text-button";
      }
    }
    if (!blocked && course.lesson.id === "lesson-1" && course.current_step === "review") {
      practice.hidden = false;
      practice.append(courseElement("span", "没有补充也可以先核对记录，确认后继续。"));
      button("核对无误，继续", "confirm_record", practice);
      button("修改记录", "edit_record", practice);
    }
    const record = document.getElementById("course-record");
    record.replaceChildren();
    (course.record || []).forEach((field) => {
      const row = courseElement("div");
      row.append(courseElement("dt", field.label), courseElement("dd", field.value));
      if (field.source_artifact_id) row.append(courseElement("small", "来自您本次选择沿用的前课记录", "notebook-muted"));
      record.append(row);
    });
    (course.personal_practice?.deferred || []).forEach((field) => {
      if (course.blueprint?.source_kind === "fictional" && ["thought_belief", "emotion_intensity"].includes(field.field)) return;
      const row = courseElement("div", "", "notebook-muted");
      row.append(courseElement("dt", field.label), courseElement("dd", field.status_label));
      record.append(row);
    });
    const hasRecord = Boolean(course.record?.length || course.personal_practice?.deferred?.length);
    document.getElementById("record-empty").hidden = hasRecord;
    document.getElementById("record-confirmation").textContent = course.record_confirmed ? "本人已确认" : hasRecord ? "待本人核对" : "待整理";
    const memory = document.getElementById("course-carryover");
    memory.replaceChildren();
    memory.hidden = !["offered", "accepted"].includes(course.carryover?.status);
    if (!memory.hidden) {
      const bundle = course.carryover.kind === "course_review";
      memory.append(courseElement("h3", bundle ? (course.carryover.status === "offered" ? "要回顾这些课程收获吗？" : "正在回顾已授权的课程成果") : (course.carryover.status === "offered" ? "要接着上一课的收获吗？" : "正在参考上一课摘要")));
      const summaries = bundle ? course.carryover.sources.map((item) => item.summary) : [course.carryover.summary];
      summaries.forEach((summary) => {
        const fieldNames = summary.record_labels || { situation: "事情", thought: "想法", emotion: "心情", behavior: "做法", awareness_note: "线索" };
        memory.append(courseElement("p", `来源：第 ${summary.lesson_id.split("-").pop()} 课本人已确认的记录${summary.path_label ? " · " + summary.path_label : ""}`, "notebook-muted"));
        const previous = summary.record || {};
        const fieldOrder = summary.record_order || Object.keys(previous);
        const values = fieldOrder.filter((key) => previous[key]).map((key) => `${fieldNames[key] || key}：${previous[key].value}${previous[key].truncated ? "…（摘录）" : ""}`).join("；");
        const contents = courseElement(bundle || fieldOrder.length > 4 ? "details" : "div", "", "course-source-details");
        if (contents.tagName === "DETAILS") contents.append(courseElement("summary", "展开查看这课的记录"));
        contents.append(courseElement("p", values, "carryover-quote"));
        if (!bundle && summary.practice_plan?.text) contents.append(courseElement("p", summary.practice_plan.text, "notebook-muted"));
        if (!bundle && course.lesson.id === "lesson-2") contents.append(courseElement("p", "选择使用后，本课也会回顾上次课程练习中最近三条日记（如有）；不选择则不会传入教学上下文。", "notebook-muted"));
        if (summary.practice_scope?.description) contents.append(courseElement("p", summary.practice_scope.description, "notebook-muted"));
        memory.append(contents);
        if (["action_plan", "coping_plan"].includes(summary.artifact_kind)) memory.append(courseElement("p", "已确认的是计划，实际运用与效果尚待反馈。", "notebook-muted"));
      });
      memory.append(courseElement("p", "仅参考本人确认的记录与课后安排，您也可以用新例子开始。", "notebook-muted"));
      if (course.carryover.status === "offered" && !blocked) {
        button(bundle ? "参考这些课程成果" : "使用上一课摘要", "accept_carryover", memory);
        button("本课重新开始", "decline_carryover", memory);
      }
    }
    const paths = document.getElementById("course-path-choice");
    paths.replaceChildren();
    paths.hidden = !course.path_choices?.length || Boolean(course.skill_lesson && !course.path && course.current_step !== "choose_path");
    if (!paths.hidden) {
      paths.append(courseElement("h3", course.path_label ? "本课选择的路径" : "先选本课想探索的路径"));
      if (course.path_label) paths.append(courseElement("p", course.path_label, "carryover-quote"));
      else paths.append(courseElement("p", "两条路径任选一条，可以只整理计划。", "notebook-muted"));
      if (!blocked && course.needs_path_choice) course.path_choices.forEach((choice) => button(choice.label, choice.action, paths));
      if (!blocked && course.path) {
        paths.append(courseElement("p", "重新选择会撤回本课原路径的记录与课后安排，从新例子开始。", "notebook-muted"));
        button("重新选择路径", "change_path", paths);
      }
    }
    const patterns = document.getElementById("course-pattern-review");
    patterns.replaceChildren();
    patterns.hidden = !course.pattern_required || !["practice", "review", "plan", "summary", "completed", "pattern"].includes(course.current_step);
    if (!patterns.hidden) {
      patterns.append(courseElement("h3", "这个解释适合这次经历吗？"));
      const candidate = course.domain_candidates?.[0];
      if (candidate) patterns.append(courseElement("p", candidate.label), courseElement("p", candidate.explanation, "notebook-muted"));
      else patterns.append(courseElement("p", "目前没有必须接受的分类解释，可以保留不确定或没有明显模式。", "notebook-muted"));
      if (course.pattern_review) patterns.append(courseElement("p", `我的选择：${course.pattern_choices[course.pattern_review.status]}`, "carryover-quote"));
      if (!blocked && course.current_step === "review" && !course.skill_lesson) {
        if (candidate) { button("这次像这种情况", "accept_pattern", patterns); button("这个解释不太符合", "reject_pattern", patterns); }
        button("暂时不确定", "unsure_pattern", patterns);
        button("没有明显的思维模式", "no_pattern", patterns);
      }
    }
    const plan = document.getElementById("course-practice-plan");
    plan.replaceChildren();
    plan.hidden = !course.practice_plan?.text;
    if (!plan.hidden) plan.append(courseElement("h3", "我选择的课后安排"), courseElement("p", course.practice_plan.text));
    const check = course.learning_check;
    const checkCard = document.getElementById("course-check-card");
    checkCard.replaceChildren();
    checkCard.hidden = !check?.checking;
    if (!checkCard.hidden) {
      checkCard.append(courseElement("p", check.retrying ? "新案例补练 · 首次回答仍保留" : "换个例子试一试", "notebook-kicker"),
        courseElement("p", check.story, "learning-check-story"),
        courseElement("h2", `第 ${check.number} / ${check.total} 题：${check.question}`),
            courseElement("p", "故事可以反复阅读。可以用下方操作，也可以直接说需要提示、不想继续这些题，或想暂停。", "notebook-muted"));
    }
    const checkResults = document.getElementById("course-check-results");
    checkResults.replaceChildren();
    checkResults.hidden = !check?.result;
    if (!checkResults.hidden) {
      checkResults.append(courseElement("h3", "这次的检验记录"), courseElement("p", check.result.scope, "notebook-muted"));
      [["首次作答", check.result.first_attempt], ["反馈后的补练", check.result.retry_attempt]].forEach(([title, attempts]) => {
        if (!attempts?.length) return;
        const group = courseElement("details", "", "learning-check-attempts");
        group.append(courseElement("summary", title));
        attempts.forEach((item) => {
          const row = courseElement("div", "", "learning-check-result");
          row.append(courseElement("strong", `${item.label} · ${item.verdict_label}`), courseElement("p", item.answer ? `我的回答：${item.answer}` : "本题未作答"),
            courseElement("p", item.help_label, "notebook-muted"), courseElement("p", item.reason, "notebook-muted"));
          group.append(row);
        });
        checkResults.append(group);
      });
    }
    const model = document.getElementById("course-blueprint-model");
    if (model) {
      model.replaceChildren();
      model.hidden = !course.blueprint || !["practice", "review", "assessment", "check_feedback", "learning_goal", "plan", "summary", "completed"].includes(course.current_step);
      if (!model.hidden) {
        model.append(courseElement("h3", course.blueprint.source_kind === "fictional" ? "虚构案例的认知行为模型" : "这件事的认知行为模型"));
        const diagram = courseElement("div", "", "blueprint-model");
        const values = Object.fromEntries((course.record || []).map(item => [item.field, item.value]));
        [["situation", "情境"], ["thought", "想法"], ["emotion", "情绪"], ["behavior", "行为"]].forEach(([field, label], i) => {
          if (i) diagram.append(courseElement("span", i === 1 ? "↓ 解读" : i === 2 ? "↙↗　↘↖" : "↔", `blueprint-arrow blueprint-arrow-${i}`));
          const node = courseElement("div", "", `blueprint-node blueprint-${field}`);
          node.append(courseElement("strong", label), courseElement("p", values[field] || "暂未记录"));
          const rating = course.blueprint.ratings[field === "thought" ? "thought_belief" : field === "emotion" ? "emotion_intensity" : ""];
          if (["thought", "emotion"].includes(field) && (rating || course.blueprint.source_kind !== "fictional")) node.append(courseElement("p", `${field === "thought" ? "相信程度" : "情绪强度"}：${rating ? `${rating.value}/10` : "未提供"}`, "notebook-muted"));
          diagram.append(node);
        });
        model.append(diagram, courseElement("p", course.blueprint.relations, "notebook-muted"));
        const concepts = courseElement("details", "", "blueprint-concepts");
        concepts.append(courseElement("summary", "回看四个概念与示例"));
        course.blueprint.concepts.forEach(text => concepts.append(courseElement("p", text)));
        (course.blueprint.materials || []).forEach(material => {
          const image = courseElement("img", "");
          image.src = material.src; image.alt = material.alt; image.loading = "lazy";
          concepts.append(image);
        });
        model.append(concepts);
        if (course.blueprint.relationship) model.append(courseElement("p", `回看后的补充：${course.blueprint.relationship.value}`));
      }
    }
    const learningGoal = document.getElementById("course-learning-goal");
    learningGoal.replaceChildren();
    learningGoal.hidden = !course.learning_goal;
    if (!learningGoal.hidden) learningGoal.append(courseElement("h3", "我的练习目标"),
      courseElement("p", course.learning_goal.status === "skipped" ? "本次暂不设置目标。" : course.learning_goal.value),
      courseElement("p", course.learning_goal.status === "draft" ? "待您核对确认，可以直接修改。" : "已保存您的选择。", "notebook-muted"));
    if (!learningGoal.hidden && course.learning_goal.items?.length) {
      const list = courseElement("ol", "");
      course.learning_goal.items.forEach(item => list.append(courseElement("li", item.value)));
      learningGoal.replaceChildren(courseElement("h3", "整套课程的具体目标"), list,
        courseElement("p", course.learning_goal.status === "draft" ? "待本人确认，可以修改；目标不是效果承诺。" : "已按本人确认保存，之后也可修改。", "notebook-muted"));
    }
    const evidence = document.getElementById("course-learning-evidence");
    evidence.replaceChildren();
    evidence.hidden = !course.completed;
    if (!evidence.hidden) {
      evidence.append(courseElement("h3", "这次的进展"), courseElement("p", course.personal_practice_scope?.description || `完成一次引导下的${course.record_kind || "学习记录"}整理和本人核对。`), courseElement("p", "生活中运用与实际效果：尚待之后的本人反馈。", "notebook-muted"));
    }
    const second = document.getElementById("course-lesson2");
    second.replaceChildren();
    second.hidden = !course.lesson2;
    if (course.lesson2) {
      const activity = course.lesson2;
      if (course.current_step === "homework") {
        second.append(courseElement("h3", "回顾上次课后练习"));
        if (activity.previous_diaries?.length) renderDiaries(second, activity.previous_diaries);
        else second.append(courseElement("p", "当前没有获准引用的课后记录；这不代表您没有练习，可以按自己的实际情况说说。", "notebook-muted"));
      }
      const homework = activity.homework;
      second.append(courseElement("h3", "第二课 · 活动与来源"));
      const homeworkLabels = {unknown:"尚未回顾", skipped:"本次跳过回顾", previous_declined:"上课已选择不安排", not_planned:"本人表示未安排", not_attempted:"本人表示未尝试", self_reported_attempt:"本人报告曾尝试"};
      second.append(courseElement("p", `课后尝试：${homeworkLabels[homework.status] || "待本人说明"}；用于调整教学，不计服从分。`, "notebook-muted"));
      if (homework.homework_report) second.append(courseElement("p", homework.homework_report.value));
      if (activity.quiz.answers.length) {
        const details = courseElement("details");
        details.append(courseElement("summary", "三题复习：原答、帮助与反馈"));
        activity.quiz.answers.forEach((answer) => details.append(courseElement("p", `${answer.question_index+1}. 原答：${answer.answer || "未作答"}；${answer.reason} ${answer.assisted ? "有提示。" : ""}${answer.prior_feedback ? "此前已有逐题反馈。" : ""}`)));
        second.append(details);
      }
      if (["rain","contrast","rain_insight","personal","model","plan","summary","completed"].includes(course.current_step)) {
        const rainPanel = courseElement("details");
        rainPanel.open = ["rain", "contrast", "rain_insight"].includes(course.current_step);
        rainPanel.append(courseElement("summary", "雨天教学对照 · 想象练习"), courseElement("p", activity.rain_story));
        const table = courseElement("table");
        table.setAttribute("aria-label", "同一雨天情境的想法和情绪对照");
        const head = courseElement("tr");
        ["来源", "想法", "情绪"].forEach((label) => head.append(courseElement("th", label)));
        table.append(head);
        const row = (label, thought, emotion) => {
          const tr = courseElement("tr");
          [label, thought || "未表达", emotion || "未表达"].forEach((value) => tr.append(courseElement("td", value)));
          table.append(tr);
        };
        row("您在想象中的回答", activity.rain.fields.thought?.value, activity.rain.fields.emotion?.value);
        if (activity.contrast) row("小雨（预设教学示范）", activity.contrast.thought, activity.contrast.emotion);
        const tableWrap = courseElement("div", "", "lesson2-table-wrap");
        tableWrap.append(table);
        rainPanel.append(tableWrap, courseElement("p", "这里的感受不判对错，也不作为您的真实经历或稳定思维习惯。", "notebook-muted"));
        second.append(rainPanel);
      }
      if (course.record?.length) {
        second.append(courseElement("h4", fictional ? "虚构案例三栏 · 辨认记录" : "当前个人案例 · 三栏记录"));
        const labels = {situation:"情境", thought:"想法", emotion:"情绪"};
        const diagram = courseElement("div", "", "lesson2-triad");
        diagram.setAttribute("aria-label", "三栏模型：情境、想法和情绪；联系尚待本人核对");
        ["situation", "thought", "emotion"].forEach((key) => {
          const node = courseElement("div", "", "lesson2-triad-node");
          node.append(courseElement("strong", labels[key]), courseElement("p", course.record.find((field) => field.field === key)?.value || "本次未提供"));
          diagram.append(node);
        });
        second.append(diagram);
        if (activity.rating) second.append(courseElement("p", `本人评分：${activity.rating.target} ${activity.rating.value}/10`));
        if (activity.relationship) second.append(courseElement("p", `本人对联系的看法：${activity.relationship.value}`));
        if (activity.case_review?.status === "ready") second.append(courseElement("p", activity.case_review.summary));
        second.append(courseElement("p", "三栏用于一起核对可能的联系；不代表已经证实单向因果或情绪改善。", "notebook-muted"));
      }
    }
    const actions = document.getElementById("course-actions");
    actions.replaceChildren();
    if (!blocked && course.skill_lesson) {
      course.skill_lesson.actions.forEach((item) => button(item.label, item.action, actions));
    } else if (!blocked && course.lesson2) {
      course.lesson2.actions.forEach((item) => button(item.label, item.action, actions));
    } else if (!blocked) {
      if (course.current_step === "check_in" && !course.teacher_flow?.overview_pending) button(course.blueprint ? "这次暂不评分" : "先看例子，不评分", "skip_checkin", actions);
      if (course.can_reuse_case) button("沿用上一课这件事", "reuse_case", actions);
      if (course.current_step === "review") {
        button(fictional ? "确认练习记录" : "确认这份记录", "confirm_record", actions).disabled = busy || (course.pattern_required && !course.pattern_review);
        button("我要修改记录", "edit_record", actions);
      }
      if (check?.checking) {
        button("需要一点提示", "request_check_hint", actions);
        button("这题先跳过", "skip_check_question", actions);
        if (check.retrying) button("结束这次补练", "finish_check_retry", actions);
      }
      if (course.current_step === "check_feedback" && !check?.retrying) {
        button("继续，设置练习目标", "continue_after_check", actions);
        if (check.can_retry) button("换个例子再练一次", "start_check_retry", actions);
      }
      if (course.current_step === "learning_goal") {
        if (course.learning_goal?.status === "draft") button(course.blueprint ? "确认这些目标" : "确认这个目标", "confirm_learning_goal", actions);
        button("暂不设置目标", "skip_learning_goal", actions);
      }
      if (course.current_step === "plan") {
        button("愿意试一次", "accept_practice", actions);
        button("这次不安排", "decline_practice", actions);
      }
      if (course.current_step === "summary") button("完成本课", "finish", actions);
      if (["plan", "summary"].includes(course.current_step)) button("修改已确认的记录", "edit_record", actions);
      if (course.blueprint && ["plan", "summary"].includes(course.current_step)) button("修改课程目标", "edit_learning_goal", actions);
    }
    const reflection = document.getElementById("course-reflection");
    reflection.replaceChildren();
    reflection.hidden = !course.completed || !course.guided;
    if (!reflection.hidden) {
      reflection.append(courseElement("h3", "课后教学复盘"));
      const review = course.reflection || {};
      if (review.status === "ready") {
        (review.observations || []).forEach((note) => reflection.append(courseElement("p", note.text)));
        (review.suggestions || []).forEach((note) => reflection.append(courseElement("p", note.text, "reflection-suggestion")));
        (review.hypotheses || []).forEach((note) => {
          const group = courseElement("div", "", "learning-hypothesis");
          group.append(courseElement("h4", "待核对的学习观察"), courseElement("p", note.text),
            courseElement("p", `适用范围：${note.context}`, "notebook-muted"),
            courseElement("p", `其他可能解释：${note.alternative_explanation}`, "notebook-muted"),
            courseElement("p", `下一步：${note.next_action}`), courseElement("p", `怎样核对：${note.verification}`));
          reflection.append(group);
        });
        if (!review.observations?.length && !review.suggestions?.length && !review.hypotheses?.length) reflection.append(courseElement("p", "本课没有足够依据形成额外指导建议。"));
        reflection.append(courseElement("p", "以上是待验证的教学观察，不是对您的能力或心理状态的判断，尚未自动用于之后的课程。", "notebook-muted"));
      } else {
        reflection.append(courseElement("p", review.status === "failed" ? review.error : "正在单独整理，不影响已保存的学习记录。"));
        const retryReflection = courseElement("button", "重新整理课后复盘", "guided-action");
        retryReflection.type = "button";
        retryReflection.addEventListener("click", async () => {
          retryReflection.disabled = true;
          try { await courseApi(`${endpoint}/reflection`, { method: "POST", body: "{}" }); pollCount = 0; pollReflection(); }
          catch (error) { courseToast(error.message); retryReflection.disabled = false; }
        });
        reflection.append(retryReflection);
      }
    }
    examples.hidden = document.body.dataset.preview !== "true" || blocked || course.needs_path_choice || !["check_in", "learn", "practice", "summary", "assessment", "learning_goal", ...(check?.retrying ? ["check_feedback"] : [])].includes(course.current_step);
    examples.disabled = busy;
    feedbackExample.hidden = document.body.dataset.preview !== "true" || blocked || course.needs_path_choice || !["learn", "practice"].includes(course.current_step);
    feedbackExample.disabled = busy;
    const debug = document.getElementById("course-debug-state");
    if (debug) debug.textContent = JSON.stringify({ phase: course.current_step, path: course.path, task_step_id: course.task_step_id,
      policy: course.workflow?.policy, trigger: course.workflow?.last_trigger,
      model_calls_this_turn: course.workflow?.last_model_call_count || 0,
      latest_reflection: course.workflow?.reflections?.at(-1) || null }, null, 2);
    if (stageChanged && window.matchMedia("(max-width: 680px)").matches) {
      const target = course.needs_path_choice ? "course-path-choice" : course.current_step === "assessment" || check?.retrying ? "course-check-card" : course.current_step === "check_feedback" ? "course-check-results" : course.current_step === "learning_goal" ? "course-learning-goal" : ["review", "plan", "summary"].includes(course.current_step) ? "course-record" : null;
      if (target) document.getElementById(target).scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  async function submit(action = "chat", retryRequest = null) {
    if (busy) return;
    const content = action === "chat" ? input.value.trim() : "";
    if (!retryRequest && action === "chat" && !content) return;
    const payload = retryRequest?.payload || { content, action, expected_revision: course.revision, idempotency_key: crypto.randomUUID() };
    const controlLabels = { request_less_probing: "我想少解释一点", show_brief_explanation: "直接看解释", continue_practice_dialogue: "继续聊", defer_practice_field: "这一项暂时想不起", decline_practice_field: "这一项先不谈", request_check_hint: "需要一点提示", skip_check_question: "这题先跳过", continue_after_check: "继续，设置练习目标", start_check_retry: "换个例子再练一次", finish_check_retry: "结束这次补练", confirm_learning_goal: "确认这个目标", skip_learning_goal: "暂不设置目标" };
    const userMessage = retryRequest?.userMessage || appendCourseMessage("learner", content || course.skill_lesson?.actions.find((item) => item.action === action)?.label || course.lesson2?.actions.find((item) => item.action === action)?.label || course.practice_control_labels?.[action] || controlLabels[action] || ({ start_mood_check: "已看完", confirm_record: "确认这份记录", edit_record: "我要修改记录", accept_practice: "愿意试一次", decline_practice: "这次不安排", finish: "完成本课", pause: "暂停课程", resume: "继续课程", skip_checkin: "暂不评分", accept_carryover: "使用已确认的课程摘要", decline_carryover: "本课重新开始", reuse_case: "沿用上一课这件事", accept_pattern: "这次像这种情况", reject_pattern: "这个解释不太符合", unsure_pattern: "暂时不确定", no_pattern: "没有明显的思维模式", choose_activation: "选择行为激活", choose_exposure: "选择行为暴露", choose_sleep: "选择睡眠路径", choose_relaxation: "选择放松路径", change_path: "重新选择路径" })[action]);
    // The request owns its snapshot; only a fresh chat submission consumes the draft.
    // Controls and retries must preserve any newer, unsent draft.
    if (!retryRequest && action === "chat") {
      input.value = ""; count.textContent = "0 / 2000";
    }
    const pending = retryRequest?.pending || appendCourseMessage("guide", "正在回复……");
    pending.querySelector(".course-message-bubble").textContent = "正在回复……";
    pending.className = "course-message guide pending";
    busy = true;
    render(course);
    document.getElementById("course-save-note").textContent = "正在生成回复，完成后自动保存";
    try {
      let streamedText = "";
      const result = await courseStreamRequest(`${endpoint}/messages/stream`, payload, (delta) => {
        streamedText += delta;
        pending.querySelector(".course-message-bubble").textContent = streamedText;
        pending.className = "course-message guide streaming";
        const list = document.getElementById("course-message-list");
        list.scrollTop = list.scrollHeight;
      }, courseCookie("csrf_token"));
      if (!streamedText) {
        pending.className = "course-message guide streaming";
        document.getElementById("course-save-note").textContent = "本轮已保存，正在显示回复";
        await courseRevealReply(result.reply, (text) => {
          pending.querySelector(".course-message-bubble").textContent = text;
          const list = document.getElementById("course-message-list"); list.scrollTop = list.scrollHeight;
        }, { immediate: document.hidden || window.matchMedia("(prefers-reduced-motion: reduce)").matches });
      }
      pending.querySelector(".course-message-bubble").textContent = result.reply;
      pending.className = "course-message guide";
      retry = null;
      render(result.course);
      if (result.course.completed) { pollCount = 0; pollReflection(); }
    } catch (error) {
      pending.querySelector(".course-message-bubble").textContent = error.message;
      pending.className = "course-message guide error";
      retry = { payload, pending, userMessage };
      const again = courseElement("button", "重试这一轮", "guided-action");
      again.type = "button";
      again.addEventListener("click", () => { again.remove(); submit(payload.action, retry); });
      pending.append(again);
    } finally {
      document.getElementById("course-save-note").textContent = "对话与学习记录自动加密保存";
      busy = false; render(course);
      if (!input.disabled && !["review", "plan", "summary"].includes(course.current_step)) input.focus();
      const list = document.getElementById("course-message-list"); list.scrollTop = list.scrollHeight;
    }
  }

  function pollReflection() {
    if (++pollCount > 35) return;
    window.setTimeout(async () => {
      try {
        const result = await courseApi(endpoint);
        render(result.course);
        if (["pending", "running"].includes(result.course.reflection?.status)) pollReflection();
      } catch (_) { /* Records remain visible; the explicit retry remains available. */ }
    }, 2000);
  }
  form.addEventListener("submit", (event) => { event.preventDefault(); submit(); });
  input.addEventListener("input", () => { count.textContent = `${input.value.length} / 2000`; });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing && event.keyCode !== 229) { event.preventDefault(); form.requestSubmit(); }
  });
  pause.addEventListener("click", () => submit(course.paused ? "resume" : "pause"));
  examples.addEventListener("click", () => {
    const values = { ...course.preview_examples };
    input.value = values[course.current_step] || ""; input.dispatchEvent(new Event("input")); input.focus();
  });
  feedbackExample.addEventListener("click", () => { input.value = "刚才这段没听懂，可以换个说法吗？"; input.dispatchEvent(new Event("input")); input.focus(); });
  render(course);
  const list = document.getElementById("course-message-list"); list.scrollTop = list.scrollHeight;
  if (course.completed && ["pending", "running"].includes(course.reflection?.status)) pollReflection();
});
