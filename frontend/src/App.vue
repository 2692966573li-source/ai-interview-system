<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import ReportCharts from "./components/ReportCharts.vue";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api";
const activeArea = ref("preparation");
const loading = ref(false);
const notice = ref("");
const error = ref("");
const token = ref(localStorage.getItem("ai_interview_token") || "");
let storedUser = null;
try {
  storedUser = token.value ? JSON.parse(localStorage.getItem("ai_interview_user") || "null") : null;
} catch {
  storedUser = null;
}
const user = ref(storedUser);
const authMode = ref("login");
const authForm = ref({ username: "", password: "" });
const sessions = ref([]);
const current = ref(null);
const answerText = ref("");
const report = ref(null);
const resumeFile = ref(null);
const resumeInfo = ref(null);
const resumeConfirmed = ref(null);
const voiceInputSupported = ref(false);
const voiceOutputSupported = ref(false);
const isListening = ref(false);
const voiceStatus = ref("");
const voiceOutputEnabled = ref(localStorage.getItem("ai_interview_voice_output") === "true");
const speakingMessageId = ref("");
// P6 语音进阶：inputEngine=browser|server|websocket，失败自动降级。
const voiceMode = ref(localStorage.getItem("ai_interview_voice_mode") || "browser");
const voiceOutputMode = ref(localStorage.getItem("ai_interview_voice_output_mode") || "browser");
const serverTranscribing = ref(false);
const wsProgressBytes = ref(0);
let mediaRecorder = null;
let mediaChunks = [];
let wsVoice = null;
let wsRecorder = null;
let wsStream = null;
// 赛题三进阶 2：最近一次语音识别得到的音频情绪，随下一次回答一起上送落库。
let pendingAudioEmotion = null;
let recognition = null;
let voiceBaseText = "";
const form = ref({
  target_role: "Python 后端开发",
  difficulty: "中等",
  question_limit: 10,
  time_limit_seconds: 900,
  focus_skills: "项目深挖,数据库,接口设计",
  resume_text:
    "我正在开发一个 AI 电商问答系统，使用 Python、FastAPI 和向量检索。主要负责后端接口和会话数据保存。",
});

const areaMeta = {
  preparation: { label: "面试准备", icon: "01", hint: "先把面试目标和经历说清楚" },
  interview: { label: "智能面试", icon: "02", hint: "主 AI 面试官会根据回答追问" },
  growth: { label: "评估成长", icon: "03", hint: "结束后查看证据化评分报告" },
  records: { label: "记录交付", icon: "04", hint: "管理历史会话和复盘资料" },
};

const currentMessages = computed(() => current.value?.messages || []);
const isActive = computed(() => ["ACTIVE", "END_RECOMMENDED"].includes(current.value?.status));
const endRecommended = computed(() => current.value?.status === "END_RECOMMENDED");
const radarDimensions = [
  { key: "professional", label: "专业能力", angle: -90, labelX: 130, labelY: 13 },
  { key: "logic", label: "逻辑结构", angle: 30, labelX: 224, labelY: 184 },
  { key: "communication", label: "表达沟通", angle: 150, labelX: 36, labelY: 184 },
];
const radarPoints = computed(() => radarDimensions.map((item) => radarPoint(report.value?.dimensions?.[item.key]?.score || 0, item.angle)).join(" "));
const displayDimensions = computed(() => {
  const usedTurns = new Set();
  const usedQuotes = new Set();
  return Object.entries(report.value?.dimensions || {}).map(([key, item]) => {
    const evidence = Array.isArray(item.evidence) ? item.evidence : [];
    const chosen = evidence.find((entry) => !usedTurns.has(entry.turn))
      || evidence.find((entry) => entry.quote && !usedQuotes.has(entry.quote))
      || evidence[0];
    if (chosen) {
      usedTurns.add(chosen.turn);
      if (chosen.quote) usedQuotes.add(chosen.quote);
    }
    return { key, item, evidence: chosen };
  });
});

watch(activeArea, (area) => {
  if (area !== "interview") {
    stopListening();
    stopSpeaking();
  }
});

function radarPoint(score, angle, radius = 86) {
  const radians = (angle * Math.PI) / 180;
  const distance = (Math.max(0, Math.min(100, Number(score))) / 100) * radius;
  return `${130 + Math.cos(radians) * distance},${105 + Math.sin(radians) * distance}`;
}

function radarGridPoints(level) {
  return radarDimensions.map((item) => radarPoint(level, item.angle)).join(" ");
}

function dimensionLabel(key) {
  return { professional: "专业能力", logic: "逻辑结构", communication: "表达沟通" }[key] || key;
}

async function downloadReport() {
  if (!current.value || !report.value) return;
  clearMessage();
  loading.value = true;
  try {
    const response = await fetch(API_BASE.replace(/\/api$/, "") + "/api/sessions/" + current.value.id + "/report.pdf", { headers: authHeaders() });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || "PDF 导出失败");
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `ai_interview_report_${current.value.id}.pdf`;
    link.click();
    URL.revokeObjectURL(url);
    notice.value = "PDF 报告已生成并开始下载。";
  } catch (err) {
    error.value = err.message;
  } finally {
    loading.value = false;
  }
}

async function downloadSpreadsheet() {
  if (!current.value || !report.value) return;
  clearMessage();
  loading.value = true;
  try {
    const response = await fetch(API_BASE.replace(/\/api$/, "") + "/api/sessions/" + current.value.id + "/report.xlsx", { headers: authHeaders() });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || "Excel 导出失败");
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `ai_interview_report_${current.value.id}.xlsx`;
    link.click();
    URL.revokeObjectURL(url);
    notice.value = "Excel 报告已生成并开始下载。";
  } catch (err) {
    error.value = err.message;
  } finally {
    loading.value = false;
  }
}

function clearMessage() {
  notice.value = "";
  error.value = "";
}

function setupVoice() {
  if (typeof window === "undefined") return;
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  voiceInputSupported.value = Boolean(Recognition);
  voiceOutputSupported.value = "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;
  if (!Recognition) return;

  recognition = new Recognition();
  recognition.lang = "zh-CN";
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.maxAlternatives = 1;
  recognition.onstart = () => {
    isListening.value = true;
    voiceStatus.value = "正在听，请自然回答…";
  };
  recognition.onresult = (event) => {
    const transcript = Array.from(event.results)
      .map((result) => result[0]?.transcript || "")
      .join("")
      .trim();
    answerText.value = [voiceBaseText, transcript].filter(Boolean).join(" ").trim();
  };
  recognition.onerror = (event) => {
    isListening.value = false;
    if (event.error === "aborted") return;
    const messages = {
      "not-allowed": "麦克风权限被拒绝，请在浏览器地址栏允许麦克风。",
      "audio-capture": "没有检测到可用麦克风。",
      "no-speech": "没有听到声音，请再试一次。",
      network: "语音识别网络不可用，请检查网络后重试。",
    };
    voiceStatus.value = messages[event.error] || `语音输入失败：${event.error}`;
  };
  recognition.onend = () => {
    isListening.value = false;
    if (voiceStatus.value === "正在听，请自然回答…") {
      voiceStatus.value = answerText.value.trim() ? "语音已转成文字，可继续编辑。" : "";
    }
  };
}

function startListening() {
  if (!recognition || !isActive.value || isListening.value) return;
  clearMessage();
  voiceBaseText = answerText.value.trim();
  try {
    recognition.start();
  } catch (err) {
    if (err.name !== "InvalidStateError") voiceStatus.value = "无法启动语音输入，请重试。";
  }
}

function stopListening() {
  if (voiceMode.value === "websocket" && isListening.value) {
    stopWsVoice();
    return;
  }
  if (mediaRecorder && voiceMode.value === "server" && isListening.value) {
    mediaRecorder.stop();
    return;
  }
  if (recognition && isListening.value) recognition.stop();
  isListening.value = false;
  if (answerText.value.trim()) voiceStatus.value = "语音已转成文字，可继续编辑。";
}

async function toggleListening() {
  if (isListening.value) { stopListening(); return; }
  if (voiceMode.value === "websocket") {
    if (!current.value) return;
    clearMessage();
    voiceBaseText = answerText.value.trim();
    try {
      await recordViaWs();
    } catch (err) {
      isListening.value = false;
      serverTranscribing.value = false;
      cleanupWsRecording();
      voiceStatus.value = "无法使用 WS 实时识别（" + err.message + "），请允许麦克风或改用其他识别方式。";
    }
    return;
  }
  if (voiceMode.value === "server") {
    if (!current.value) return;
    clearMessage();
    voiceBaseText = answerText.value.trim();
    try {
      await recordViaServer();
    } catch (err) {
      isListening.value = false;
      serverTranscribing.value = false;
      voiceStatus.value = "无法使用服务端识别（" + err.message + "），请允许麦克风或改用浏览器识别。";
    }
    return;
  }
  startListening();
}

function stopSpeaking() {
  if (typeof window !== "undefined" && window.speechSynthesis) window.speechSynthesis.cancel();
  const audioElements = document.querySelectorAll("audio");
  audioElements.forEach((audio) => audio.pause());
  speakingMessageId.value = "";
}

function speakText(text, messageId = "manual") {
  if (!voiceOutputSupported.value || !text || typeof window === "undefined") return;
  stopSpeaking();
  const utterance = new window.SpeechSynthesisUtterance(text);
  utterance.lang = "zh-CN";
  utterance.rate = 1.02;
  utterance.pitch = 1;
  const chineseVoice = window.speechSynthesis.getVoices().find((voice) => /zh|cmn/i.test(voice.lang));
  if (chineseVoice) utterance.voice = chineseVoice;
  speakingMessageId.value = messageId;
  utterance.onend = () => {
    if (speakingMessageId.value === messageId) speakingMessageId.value = "";
  };
  utterance.onerror = () => {
    if (speakingMessageId.value === messageId) speakingMessageId.value = "";
  };
  window.speechSynthesis.speak(utterance);
}

function speakLatestAssistant() {
  const latest = [...currentMessages.value].reverse().find((item) => item.role === "assistant");
  if (!latest) return;
  if (voiceOutputMode.value === "server") {
    speakViaServer(latest.content);
  } else {
    speakText(latest.content, latest.id);
  }
}

function toggleSpeech(message) {
  if (speakingMessageId.value) stopSpeaking();
  else if (voiceOutputMode.value === "server") speakViaServer(message.content);
  else speakText(message.content, message.id);
}

function handleVoiceOutputToggle() {
  localStorage.setItem("ai_interview_voice_output", String(voiceOutputEnabled.value));
  if (voiceOutputEnabled.value) speakLatestAssistant();
  else stopSpeaking();
}

function handleVoiceModeChange() {
  localStorage.setItem("ai_interview_voice_mode", voiceMode.value);
  voiceStatus.value = voiceMode.value === "server" ? "已切换为服务端识别，点击语音输入开始。" : "";
}

function handleVoiceOutputModeChange() {
  localStorage.setItem("ai_interview_voice_output_mode", voiceOutputMode.value);
  if (voiceOutputEnabled.value) speakLatestAssistant();
}

async function speakViaServer(text) {
  if (!current.value) return;
  try {
    const data = await request("/sessions/" + current.value.id + "/voice/synthesize", {
      method: "POST",
      body: JSON.stringify({ content: text }),
    });
    speakingMessageId.value = "server";
    const audio = new Audio(API_BASE.replace(/\/api$/, "") + data.audio_url);
    audio.onended = () => { if (speakingMessageId.value === "server") speakingMessageId.value = ""; };
    audio.onerror = () => {
      speakingMessageId.value = "";
      voiceOutputMode.value = "browser";
      speakText(text);
    };
    await audio.play();
  } catch (err) {
    voiceStatus.value = "服务端合成失败，已改用浏览器朗读。";
    voiceOutputMode.value = "browser";
    speakText(text);
  }
}

async function transcribeViaServer(blob) {
  if (!current.value) return "";
  const body = new FormData();
  body.append("file", new File([blob], "answer.webm", { type: blob.type || "audio/webm" }));
  const data = await request("/sessions/" + current.value.id + "/voice/transcribe", { method: "POST", body });
  // 赛题三进阶 2：保存音频情绪，随下一次发送回答一起提交。
  pendingAudioEmotion = data.audio_emotion || null;
  if (pendingAudioEmotion) {
    voiceStatus.value = `声音状态：${pendingAudioEmotion.label}（${pendingAudioEmotion.score}）${pendingAudioEmotion.pace || ""}`;
  }
  return data.text || "";
}

function cleanupWsRecording() {
  if (wsRecorder && wsRecorder.state !== "inactive") {
    try { wsRecorder.stop(); } catch { /* already stopped */ }
  }
  wsRecorder = null;
  if (wsStream) {
    wsStream.getTracks().forEach((track) => track.stop());
    wsStream = null;
  }
}

function stopWsVoice() {
  // 停止录音后先发 stop 帧，让服务端触发整体转写；超时兜底直接关闭。
  if (wsVoice && wsVoice.readyState === WebSocket.OPEN) {
    try { wsVoice.send(JSON.stringify({ type: "stop", format: "webm" })); } catch { /* closed */ }
    setTimeout(() => {
      cleanupWsRecording();
      if (wsVoice) {
        try { wsVoice.close(); } catch { /* already closed */ }
        wsVoice = null;
      }
    }, 15000);
    return;
  }
  cleanupWsRecording();
  if (wsVoice) {
    try { wsVoice.close(); } catch { /* already closed */ }
    wsVoice = null;
  }
}

function recordViaWs() {
  // 进阶实时语音：录音分片通过 WebSocket 二进制帧推给后端（执行手册 4.2 WS）。
  return new Promise((resolve, reject) => {
    if (!token.value) { reject(new Error("请先登录")); return; }
    const wsBase = API_BASE.replace(/^http/, "ws").replace(/\/api$/, "");
    const ws = new WebSocket(`${wsBase}/ws/sessions/${current.value.id}`);
    let ready = false;
    ws.onopen = () => {
      ws.send(JSON.stringify({ token: token.value, mode: "transcribe" }));
    };
    ws.onmessage = (event) => {
      let payload;
      try { payload = JSON.parse(event.data); } catch { return; }
      if (payload.type === "ready") {
        ready = true;
        navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => {
          wsStream = stream;
          wsRecorder = new MediaRecorder(stream);
          wsProgressBytes.value = 0;
          wsRecorder.ondataavailable = (e) => {
            if (e.data.size && wsVoice && wsVoice.readyState === WebSocket.OPEN) {
              wsVoice.send(e.data);
              wsProgressBytes.value += e.data.size;
            }
          };
          wsRecorder.start(300);
          isListening.value = true;
          serverTranscribing.value = true;
          voiceStatus.value = "WS 实时识别中，再次点击结束录音。";
          resolve();
        }).catch((err) => {
          try { ws.close(); } catch { /* already closed */ }
          reject(err);
        });
        return;
      }
      if (payload.type === "progress") {
        voiceStatus.value = `已上传 ${(payload.received / 1024).toFixed(0)} KB…`;
        return;
      }
      if (payload.type === "transcript") {
        isListening.value = false;
        serverTranscribing.value = false;
        cleanupWsRecording();
        if (payload.text && payload.text !== "无人声") {
          answerText.value = [voiceBaseText, payload.text].filter(Boolean).join(" ").trim();
          voiceStatus.value = "WS 实时识别完成，可继续编辑。";
        } else {
          voiceStatus.value = payload.text === "无人声" ? "没有听到人声，请再试一次。" : "识别结果为空，请重试。";
        }
        try { ws.close(); } catch { /* already closed */ }
        return;
      }
      if (payload.type === "error") {
        isListening.value = false;
        serverTranscribing.value = false;
        cleanupWsRecording();
        voiceStatus.value = "WS 识别失败：" + payload.message + "，可改用文字输入。";
        try { ws.close(); } catch { /* already closed */ }
      }
    };
    ws.onerror = () => {
      if (!ready) reject(new Error("连接失败"));
      isListening.value = false;
      serverTranscribing.value = false;
      cleanupWsRecording();
    };
    ws.onclose = () => {
      cleanupWsRecording();
      if (wsVoice === ws) wsVoice = null;
    };
    wsVoice = ws;
  });
}

async function recordViaServer() {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  mediaChunks = [];
  mediaRecorder = new MediaRecorder(stream);
  mediaRecorder.ondataavailable = (event) => { if (event.data.size) mediaChunks.push(event.data); };
  mediaRecorder.onstop = async () => {
    stream.getTracks().forEach((track) => track.stop());
    isListening.value = false;
    serverTranscribing.value = false;
    voiceStatus.value = "正在识别…";
    try {
      const blob = new Blob(mediaChunks, { type: mediaRecorder.mimeType || "audio/webm" });
      const text = await transcribeViaServer(blob);
      if (text && text !== "无人声") {
        answerText.value = [voiceBaseText, text].filter(Boolean).join(" ").trim();
        voiceStatus.value = "服务端识别完成，可继续编辑。";
      } else {
        voiceStatus.value = text === "无人声" ? "没有听到人声，请再试一次。" : "识别结果为空，请重试。";
      }
    } catch (err) {
      voiceStatus.value = "服务端识别失败：" + err.message + "，可改用文字输入。";
    }
  };
  mediaRecorder.start();
  isListening.value = true;
  serverTranscribing.value = true;
  voiceStatus.value = "正在录音（服务端识别），再次点击结束。";
}

function authHeaders() {
  return token.value ? { Authorization: `Bearer ${token.value}` } : {};
}

async function request(path, options = {}) {
  const isFormData = options.body instanceof FormData;
  const headers = { ...(options.headers || {}), ...authHeaders() };
  const response = await fetch(API_BASE + path, {
    ...options,
    headers: isFormData ? headers : { "Content-Type": "application/json", ...headers },
  });
  const data = await response.json().catch(() => ({}));
  if (response.status === 401) {
    logout(false);
  }
  if (!response.ok) throw new Error(data.detail || data.error?.message || "请求失败");
  return data;
}

async function submitAuth() {
  clearMessage();
  if (!authForm.value.username.trim() || !authForm.value.password) {
    error.value = "请输入用户名和密码。";
    return;
  }
  loading.value = true;
  try {
    const data = await request(`/auth/${authMode.value}`, {
      method: "POST",
      body: JSON.stringify(authForm.value),
    });
    token.value = data.access_token;
    user.value = data.user;
    localStorage.setItem("ai_interview_token", token.value);
    localStorage.setItem("ai_interview_user", JSON.stringify(user.value));
    authForm.value.password = "";
    notice.value = authMode.value === "login" ? "登录成功。" : "注册成功，已自动登录。";
    await loadHistory();
  } catch (err) {
    error.value = err.message;
  } finally {
    loading.value = false;
  }
}

function logout(showNotice = true) {
  stopListening();
  stopSpeaking();
  token.value = "";
  user.value = null;
  sessions.value = [];
  current.value = null;
  report.value = null;
  localStorage.removeItem("ai_interview_token");
  localStorage.removeItem("ai_interview_user");
  if (showNotice) notice.value = "已退出登录。";
}

function chooseResume(event) {
  resumeFile.value = event.target.files?.[0] || null;
}

async function uploadResume() {
  if (!resumeFile.value) return;
  clearMessage();
  loading.value = true;
  try {
    const body = new FormData();
    body.append("file", resumeFile.value);
    resumeInfo.value = await request("/resumes/parse", { method: "POST", body });
    resumeConfirmed.value = {
      resume_text: resumeInfo.value.parsed.raw_text || "",
      education: resumeInfo.value.parsed.education || [],
      internships: resumeInfo.value.parsed.internships || [],
      projects: resumeInfo.value.parsed.projects || [],
      skills: resumeInfo.value.parsed.skills || [],
      tech_stack: resumeInfo.value.parsed.tech_stack || [],
    };
    form.value.resume_text = resumeConfirmed.value.resume_text;
    notice.value = "简历已解析为草稿，请检查并确认后再创建面试。";
  } catch (err) {
    error.value = err.message;
  } finally {
    loading.value = false;
  }
}

async function confirmResume() {
  if (!resumeInfo.value) return;
  clearMessage();
  loading.value = true;
  try {
    resumeInfo.value = await request("/resumes/" + resumeInfo.value.id, {
      method: "PUT",
      body: JSON.stringify(resumeConfirmed.value),
    });
    form.value.resume_text = resumeConfirmed.value.resume_text;
    notice.value = "简历已确认，面试官将使用这份内容提问。";
  } catch (err) {
    error.value = err.message;
  } finally {
    loading.value = false;
  }
}

function listToText(field) {
  return Array.isArray(resumeConfirmed.value[field]) ? resumeConfirmed.value[field].join("\n") : "";
}

function textToList(field, event) {
  resumeConfirmed.value[field] = event.target.value.split("\n").map((item) => item.trim()).filter(Boolean);
}

async function loadHistory() {
  try {
    sessions.value = await request("/history");
  } catch (err) {
    error.value = "历史记录暂时无法读取：" + err.message;
  }
}

async function createSession() {
  clearMessage();
  loading.value = true;
  try {
    const payload = {
      ...form.value,
      question_limit: Number(form.value.question_limit),
      time_limit_seconds: Number(form.value.time_limit_seconds),
      focus_skills: form.value.focus_skills.split(",").map((item) => item.trim()).filter(Boolean),
      resume_id: resumeInfo.value?.parse_status === "CONFIRMED" ? resumeInfo.value.id : null,
    };
    const created = await request("/sessions", { method: "POST", body: JSON.stringify(payload) });
    current.value = await request("/sessions/" + created.id);
    report.value = null;
    activeArea.value = "interview";
    notice.value = "会话已创建，面试官正在等待你的回答。";
    if (voiceOutputEnabled.value) speakLatestAssistant();
    await loadHistory();
  } catch (err) {
    error.value = err.message;
  } finally {
    loading.value = false;
  }
}

async function loadSession(id) {
  clearMessage();
  stopListening();
  stopSpeaking();
  loading.value = true;
  try {
    current.value = await request("/sessions/" + id);
    report.value = current.value.report;
    activeArea.value = isActive.value ? "interview" : "growth";
    if (voiceOutputEnabled.value && isActive.value) speakLatestAssistant();
  } catch (err) {
    error.value = err.message;
  } finally {
    loading.value = false;
  }
}

async function sendAnswer() {
  if (!current.value || !answerText.value.trim()) return;
  clearMessage();
  stopListening();
  loading.value = true;
  try {
    const result = await request("/sessions/" + current.value.id + "/messages", {
      method: "POST",
      body: JSON.stringify({
        content: answerText.value.trim(),
        audio_emotion: pendingAudioEmotion,
      }),
    });
    answerText.value = "";
    pendingAudioEmotion = null;
    current.value = await request("/sessions/" + current.value.id);
    if (result.termination.can_end_now) {
      stopSpeaking();
      notice.value = `已完成 ${current.value.question_limit} 轮回答，本次面试已自动结束。`;
    } else {
      if (voiceOutputEnabled.value) speakLatestAssistant();
      const cited = result.citations?.length
        ? `面试官参考了 ${result.citations.length} 道相关题库题。`
        : "";
      const emotion = result.emotion;
      const emotionTip = emotion ? `（本轮状态：${emotion.label}。${emotion.hint}）` : "";
      notice.value = result.memory.compressed
        ? `记忆管家已更新摘要。${cited}${emotionTip}`
        : `回答已保存。${cited}${emotionTip}`;
      if (result.termination.recommend_end) notice.value += " 本次面试接近结束，也可以提前结束。";
    }
    await loadHistory();
  } catch (err) {
    error.value = err.message;
  } finally {
    loading.value = false;
  }
}

async function endSession() {
  if (!current.value) return;
  clearMessage();
  stopListening();
  stopSpeaking();
  loading.value = true;
  try {
    await request("/sessions/" + current.value.id + "/end", {
      method: "POST",
      body: JSON.stringify({ reason: "user_clicked_end" }),
    });
    current.value = await request("/sessions/" + current.value.id);
    notice.value = "面试已结束，现在可以生成评估报告。";
    activeArea.value = "growth";
    await loadHistory();
  } catch (err) {
    error.value = err.message;
  } finally {
    loading.value = false;
  }
}

async function generateReport() {
  if (!current.value) return;
  clearMessage();
  loading.value = true;
  try {
    report.value = await request("/sessions/" + current.value.id + "/report", { method: "POST" });
    current.value.report = report.value;
    notice.value = "报告已生成，分数旁边保留了对应回答证据。";
    await loadHistory();
  } catch (err) {
    error.value = err.message;
  } finally {
    loading.value = false;
  }
}

async function deleteSession(id) {
  if (!confirm("确定删除这次面试及其报告吗？")) return;
  clearMessage();
  try {
    await request("/sessions/" + id, { method: "DELETE" });
    if (current.value?.id === id) {
      current.value = null;
      report.value = null;
      activeArea.value = "preparation";
    }
    notice.value = "记录已删除。";
    await loadHistory();
  } catch (err) {
    error.value = err.message;
  }
}

function formatDate(value) {
  if (!value) return "未记录时间";
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

function emotionBadge(emotion) {
  if (!emotion || !emotion.label) return "";
  return `${emotion.label} ${emotion.score}`;
}

function emotionColor(score) {
  if (score >= 72) return "#2d7958";
  if (score >= 55) return "#4d7a61";
  if (score >= 40) return "#a2773f";
  return "#ab665e";
}

const emotionTrendPoints = computed(() => {
  const timeline = report.value?.emotion?.timeline || [];
  if (timeline.length < 2) return "";
  const stepX = 220 / (timeline.length - 1);
  return timeline
    .map((item, index) => `${20 + index * stepX},${120 - (Number(item.score) / 100) * 95}`)
    .join(" ");
});

const graphView = computed(() => {
  const graph = report.value?.knowledge_graph;
  if (!graph || !graph.nodes?.length) return null;
  const center = { x: 160, y: 110 };
  const nodes = graph.nodes.map((node, index) => {
    const angle = (2 * Math.PI * index) / graph.nodes.length - Math.PI / 2;
    const radius = 42 + Math.min(34, node.mentions * 6);
    return {
      ...node,
      x: center.x + Math.cos(angle) * (radius + 30),
      y: center.y + Math.sin(angle) * (radius + 12),
      r: 5 + Math.min(9, node.mentions * 1.6),
    };
  });
  const byId = Object.fromEntries(nodes.map((node) => [node.id, node]));
  const edges = graph.edges
    .filter((edge) => byId[edge.source] && byId[edge.target])
    .map((edge) => ({
      ...edge,
      x1: byId[edge.source].x,
      y1: byId[edge.source].y,
      x2: byId[edge.target].x,
      y2: byId[edge.target].y,
    }));
  return { center, nodes, edges, meta: graph };
});

onMounted(async () => {
  setupVoice();
  if (!token.value) return;
  try {
    user.value = await request("/auth/me");
    localStorage.setItem("ai_interview_user", JSON.stringify(user.value));
    await loadHistory();
  } catch {
    logout(false);
  }
});

onBeforeUnmount(() => {
  stopListening();
  stopSpeaking();
});
</script>

<template>
  <div v-if="!user" class="auth-shell">
    <section class="auth-card">
      <div class="brand auth-brand"><div class="brand-mark">AI</div><div><p class="eyebrow">AGENT INTERVIEW STUDIO</p><h1>智能模拟面试系统</h1></div></div>
      <p class="auth-kicker">本地安全工作区</p>
      <h2>{{ authMode === 'login' ? '欢迎回来' : '创建你的面试空间' }}</h2>
      <p class="auth-help">账号只保存在本机数据库中，不同账号的面试记录、简历和报告彼此隔离。</p>
      <div v-if="notice" class="notice success">{{ notice }}</div><div v-if="error" class="notice error">{{ error }}</div>
      <form @submit.prevent="submitAuth">
        <label>用户名<input v-model="authForm.username" autocomplete="username" placeholder="2-40 个字符" /></label>
        <label>密码<input v-model="authForm.password" type="password" autocomplete="current-password" placeholder="至少 6 位" /></label>
        <button class="primary-button auth-submit" :disabled="loading">{{ loading ? '请稍候…' : (authMode === 'login' ? '登录' : '注册并登录') }}</button>
      </form>
      <button class="text-button auth-switch" @click="authMode = authMode === 'login' ? 'register' : 'login'; clearMessage()">{{ authMode === 'login' ? '还没有账号？注册一个' : '已有账号？返回登录' }}</button>
    </section>
  </div>
  <div v-else class="app-shell">
    <header class="topbar">
      <div class="brand">
        <div class="brand-mark">AI</div>
        <div><p class="eyebrow">AGENT INTERVIEW STUDIO</p><h1>智能模拟面试系统</h1></div>
      </div>
      <div class="user-area"><span class="status-pill"><span></span> 本地工作区</span><span class="user-name">{{ user.username }}</span><button class="text-button" @click="logout()">退出</button></div>
    </header>

    <main class="layout">
      <aside class="sidebar">
        <p class="side-caption">四个业务区域</p>
        <button v-for="(meta, key) in areaMeta" :key="key" class="area-nav" :class="{ active: activeArea === key }" @click="activeArea = key">
          <span class="area-number">{{ meta.icon }}</span>
          <span><strong>{{ meta.label }}</strong><small>{{ meta.hint }}</small></span>
        </button>
        <div class="side-note"><span class="note-dot"></span><p>文字和语音可以随时切换，回答始终会保留在同一份对话记录里。</p></div>
      </aside>

      <section class="content">
        <div v-if="notice" class="notice success">{{ notice }}</div>
        <div v-if="error" class="notice error">{{ error }}</div>

        <section v-if="activeArea === 'preparation'" class="hero-card">
          <div class="hero-copy">
            <p class="eyebrow accent">01 / 面试准备区</p>
            <h2>先让面试官了解你，<br /><em>再开始真正的追问。</em></h2>
            <p class="hero-text">填写目标岗位和简历要点。确认后的内容会进入面试官的系统提示词，帮助它围绕你的真实项目提问。</p>
          </div>
          <div class="form-card">
            <label>目标岗位<input v-model="form.target_role" placeholder="例如：Python 后端开发" /></label>
            <div class="two-cols"><label>难度<select v-model="form.difficulty"><option>基础</option><option>中等</option><option>困难</option></select></label><label>最多问几题<input v-model="form.question_limit" type="number" min="1" max="30" /></label></div>
            <label>重点方向<input v-model="form.focus_skills" placeholder="用逗号分隔，例如：数据库,系统设计" /></label>
            <label>上传简历（PDF / DOCX / TXT / MD）<input type="file" accept=".pdf,.docx,.txt,.md" @change="chooseResume" /></label>
            <div v-if="resumeFile" class="upload-actions"><span>{{ resumeFile.name }}</span><button type="button" class="outline-button" :disabled="loading" @click="uploadResume">解析简历</button></div>
            <div v-if="resumeInfo && resumeConfirmed" class="resume-confirm-card">
              <div class="resume-confirm-head">
                <strong>简历草稿{{ resumeInfo.parse_status === 'CONFIRMED' ? '（已确认）' : '（待确认）' }}</strong>
                <button v-if="resumeInfo.parse_status !== 'CONFIRMED'" type="button" class="outline-button small" :disabled="loading" @click="confirmResume">确认这份简历</button>
              </div>
              <label>简历全文（可编辑）<textarea v-model="resumeConfirmed.resume_text" rows="4"></textarea></label>
              <div class="two-cols">
                <label>教育经历<textarea :value="listToText('education')" rows="3" @change="textToList('education', $event)"></textarea></label>
                <label>项目经历<textarea :value="listToText('projects')" rows="3" @change="textToList('projects', $event)"></textarea></label>
              </div>
              <div class="two-cols">
                <label>技能（每行一条）<textarea :value="listToText('skills')" rows="3" @change="textToList('skills', $event)"></textarea></label>
                <label>技术栈（每行一条）<textarea :value="listToText('tech_stack')" rows="3" @change="textToList('tech_stack', $event)"></textarea></label>
              </div>
              <small class="resume-confirm-hint">确认后的内容才会进入面试官提示词；解析草稿不会直接使用。</small>
            </div>
            <label>简历/项目摘要<textarea v-model="form.resume_text" rows="6" placeholder="也可以直接粘贴简历或项目简介。"></textarea></label>
            <button class="primary-button" :disabled="loading" @click="createSession">{{ loading ? "正在创建..." : "创建面试会话 →" }}</button>
          </div>
        </section>

        <section v-else-if="activeArea === 'interview'" class="interview-section">
          <div class="section-heading"><div><p class="eyebrow accent">02 / 智能面试区</p><h2>让回答推动下一道问题</h2></div><div v-if="current" class="session-badge">{{ current.target_role }} · {{ current.difficulty }}</div></div>
          <div v-if="!current" class="empty-state"><strong>还没有进行中的面试</strong><p>先到“面试准备”创建一个会话。</p><button class="text-button" @click="activeArea = 'preparation'">去创建 →</button></div>
          <template v-else>
            <div class="chat-card">
              <div class="chat-head"><span>面试官对话</span><div class="chat-head-tools"><span>第 {{ current.turn_count }} / {{ current.question_limit }} 轮</span><select v-if="voiceOutputSupported || current.status !== 'ACTIVE'" v-model="voiceOutputMode" class="voice-mode-select" @change="handleVoiceOutputModeChange"><option value="browser">浏览器朗读</option><option value="server">服务端语音</option></select><button v-if="voiceOutputSupported || voiceOutputMode === 'server'" type="button" class="text-button voice-head-button" @click="speakingMessageId ? stopSpeaking() : speakLatestAssistant()">{{ speakingMessageId ? "停止朗读" : "朗读当前问题" }}</button><label v-if="voiceOutputSupported || voiceOutputMode === 'server'" class="voice-toggle"><input v-model="voiceOutputEnabled" type="checkbox" @change="handleVoiceOutputToggle" /> 自动朗读</label></div></div>
              <div class="messages">
                <div v-for="item in currentMessages" :key="item.id" class="message" :class="item.role"><div class="avatar">{{ item.role === "assistant" ? "AI" : "我" }}</div><div class="message-content"><small>{{ item.role === "assistant" ? "AI 面试官" : "你的回答" }}<span v-if="item.role === 'user' && item.metadata?.emotion" class="emotion-badge" :style="{ background: emotionColor(item.metadata.emotion.score) }">{{ emotionBadge(item.metadata.emotion) }}</span></small><p>{{ item.content }}</p><div v-if="item.role === 'assistant' && (item.metadata?.target_skill || item.question_id)" class="question-meta"><span v-if="item.metadata?.target_skill" class="meta-tag">考察：{{ item.metadata.target_skill }}</span><span v-if="item.question_id" class="meta-tag citation">题库引用：{{ item.question_id }}</span></div><div v-if="item.role === 'assistant' && item.citations?.length" class="citations-box"><small>参考题库候选：</small><span v-for="c in item.citations" :key="c.question_id" class="meta-tag citation">{{ c.question_id }}（{{ c.source === 'chroma_vector' ? '向量' : '关键词' }}）</span></div><button v-if="item.role === 'assistant' && (voiceOutputSupported || voiceOutputMode === 'server')" type="button" class="message-voice-button" @click="toggleSpeech(item)">{{ speakingMessageId ? "停止朗读" : "朗读这条" }}</button></div></div>
              </div>
              <div v-if="endRecommended && isActive" class="notice warn">面试官建议可以结束本次面试，但你仍可以继续回答。</div>
              <div v-if="isActive" class="answer-box"><div class="voice-input-toolbar"><button type="button" class="outline-button voice-button" :class="{ recording: isListening }" :disabled="loading || (!voiceInputSupported && voiceMode === 'browser')" @click="toggleListening">{{ isListening ? (serverTranscribing ? "识别中…" : "停止语音输入") : "语音输入" }}</button><select v-model="voiceMode" class="voice-mode-select" @change="handleVoiceModeChange"><option value="browser">浏览器识别</option><option value="server">服务端识别</option><option value="websocket">WS 实时识别</option></select><span>{{ voiceStatus || (voiceMode === 'server' ? "服务端识别：录音结束后由 AI 转成文字" : voiceMode === 'websocket' ? "WS 实时识别：音频流实时传给后端" : "可选：点击按钮，用中文直接回答") }}</span></div><textarea v-model="answerText" rows="4" placeholder="输入你的回答。试着说出技术选择、具体数字和你亲自负责的部分。" @keydown.ctrl.enter="sendAnswer"></textarea><div class="answer-actions"><span>Ctrl + Enter 发送</span><button class="primary-button small" :disabled="loading || !answerText.trim()" @click="sendAnswer">发送回答</button></div></div>
              <div v-else class="finished-bar">本次面试已结束。<button class="text-button" @click="activeArea = 'growth'">查看评估 →</button></div>
            </div>
            <div class="interview-bottom"><div class="memory-card"><div class="mini-title">记忆管家</div><p>摘要版本 {{ current.memory?.version || 0 }} · 已覆盖到第 {{ current.memory?.covered_turn || 0 }} 轮</p><small>{{ current.memory?.next_focus || "完成五轮后自动生成结构化摘要" }}</small></div><button v-if="isActive" class="outline-button danger" :disabled="loading" @click="endSession">结束面试</button></div>
          </template>
        </section>

        <section v-else-if="activeArea === 'growth'" class="growth-section">
          <div class="section-heading"><div><p class="eyebrow accent">03 / 评估成长区</p><h2>把每个分数讲出依据</h2></div></div>
          <div v-if="!current" class="empty-state"><strong>还没有可评估的面试</strong><p>结束一次面试后，这里会出现报告。</p></div>
          <template v-else>
            <div v-if="!report" class="empty-state report-empty"><strong>面试已结束，报告还没有生成</strong><p>系统会根据完整问答生成首版结构化报告。</p><button class="primary-button" :disabled="loading || isActive" @click="generateReport">生成评估报告</button></div>
            <div v-else class="report-grid">
              <div class="score-card"><p class="eyebrow">OVERALL SCORE</p><div class="score">{{ report.overall_score }}</div><span>本次面试综合表现</span><button class="primary-button small download-button" :disabled="loading" @click="downloadReport">下载 PDF 报告</button><button class="outline-button small download-button" :disabled="loading" @click="downloadSpreadsheet">下载 Excel 报告</button></div>
              <div class="radar-card"><div class="radar-title"><h3>能力雷达</h3><small>三项核心能力对比</small></div><svg class="radar-chart" viewBox="0 0 260 210" role="img" aria-label="能力雷达图"><polygon v-for="level in [25, 50, 75, 100]" :key="level" :points="radarGridPoints(level)" class="radar-grid" /><line v-for="item in radarDimensions" :key="item.key" x1="130" y1="105" :x2="radarPoint(100, item.angle).split(',')[0]" :y2="radarPoint(100, item.angle).split(',')[1]" class="radar-axis" /><polygon :points="radarPoints" class="radar-value" /><circle v-for="item in radarDimensions" :key="item.key" :cx="radarPoint(report.dimensions?.[item.key]?.score || 0, item.angle).split(',')[0]" :cy="radarPoint(report.dimensions?.[item.key]?.score || 0, item.angle).split(',')[1]" r="3.5" class="radar-dot" /><text v-for="item in radarDimensions" :key="item.key" :x="item.labelX" :y="item.labelY" class="radar-label">{{ item.label }}</text></svg></div>
               <div class="dimension-card"><div v-for="entry in displayDimensions" :key="entry.key" class="dimension-row"><div><strong>{{ dimensionLabel(entry.key) }}</strong><small>{{ entry.evidence?.quote || '暂无证据' }}</small></div><b>{{ entry.item.score }}</b></div></div>
              <div class="report-panel"><h3>表现亮点</h3><p v-for="item in report.highlights" :key="item">✦ {{ item }}</p><h3>改进建议</h3><p v-for="item in report.suggestions" :key="item">→ {{ item }}</p></div>
              <div class="report-panel"><h3>还可以更好</h3><p v-for="item in report.problems" :key="item">{{ item }}</p><div class="evidence-note">报告版本 {{ report.version }} · 已引用 {{ report.meta?.answer_count || 0 }} 条回答</div></div>
              <div v-if="report.emotion?.timeline?.length" class="report-panel emotion-card"><h3>情绪辅助分析</h3><p class="emotion-summary">平均 {{ report.emotion.average_score }} 分 · 主导状态「{{ report.emotion.dominant_label }}」· 趋势：{{ report.emotion.trend }}</p><svg v-if="emotionTrendPoints" class="emotion-chart" viewBox="0 0 260 150" role="img" aria-label="情绪轨迹图"><line v-for="y in [25, 50, 75, 100]" :key="y" x1="20" :y1="120 - y * 0.95" x2="240" :y2="120 - y * 0.95" class="emotion-grid" /><polyline :points="emotionTrendPoints" class="emotion-line" /><circle v-for="(item, index) in report.emotion.timeline" :key="item.turn" :cx="20 + index * (220 / (report.emotion.timeline.length - 1))" :cy="120 - (item.score / 100) * 95" r="3.5" :fill="emotionColor(item.score)" /><text v-for="(item, index) in report.emotion.timeline" :key="'t' + item.turn" :x="20 + index * (220 / (report.emotion.timeline.length - 1))" y="140" class="emotion-axis-label">{{ item.turn }}</text></svg><div class="emotion-turns"><span v-for="item in report.emotion.timeline" :key="'b' + item.turn" class="emotion-turn-chip" :style="{ borderColor: emotionColor(item.score) }">第{{ item.turn }}轮 {{ item.label }} {{ item.score }}</span></div><small class="evidence-note">情绪分来自回答文本的确定性信号（自信表述、不确定词、量化数据），仅供复盘参考。</small></div>
              <div v-if="graphView" class="report-panel graph-card"><h3>知识图谱</h3><p class="emotion-summary">本次回答覆盖 {{ graphView.nodes.length }} 个技能点<template v-if="graphView.meta.covered_focus?.length">，重点已覆盖：{{ graphView.meta.covered_focus.join("、") }}</template><template v-if="graphView.meta.missing_focus?.length">；重点未谈到：{{ graphView.meta.missing_focus.join("、") }}</template></p><svg class="graph-chart" viewBox="0 0 320 220" role="img" aria-label="技能知识图谱"><line v-for="(edge, index) in graphView.edges" :key="'e' + index" :x1="edge.x1" :y1="edge.y1" :x2="edge.x2" :y2="edge.y2" class="graph-edge" :style="{ opacity: Math.min(0.7, 0.25 + edge.weight * 0.15) }" /><circle v-for="node in graphView.nodes" :key="node.id" :cx="node.x" :cy="node.y" :r="node.r" :class="['graph-node', { focus: node.category === '重点' }]" ><title>{{ node.label }} · {{ node.category }} · 提及 {{ node.mentions }} 次（第 {{ node.turns.join('、') }} 轮）</title></circle><text v-for="node in graphView.nodes" :key="'l' + node.id" :x="node.x" :y="node.y - node.r - 4" class="graph-label">{{ node.label }}</text></svg><small class="evidence-note">节点大小 = 提及次数，连线 = 同一回答中共同出现；悬停节点可查看证据轮次。</small></div>
              <div v-if="report" class="report-panel echarts-panel"><h3>可视化看板（ECharts）</h3><ReportCharts :report="report" /><small class="evidence-note">雷达图、STAR 热力图、情绪时序图与技术栈气泡图均由 ECharts 渲染，支持缩放与悬停查看数据。</small></div>
            </div>
          </template>
        </section>

        <section v-else class="records-section">
          <div class="section-heading"><div><p class="eyebrow accent">04 / 记录交付区</p><h2>每一次练习都留下轨迹</h2></div><button class="outline-button" @click="loadHistory">刷新记录</button></div>
          <div v-if="!sessions.length" class="empty-state"><strong>还没有历史记录</strong><p>完成第一次面试后，记录会自动出现在这里。</p></div>
          <div v-else class="record-list"><article v-for="item in sessions" :key="item.id" class="record-item"><div class="record-main"><span class="record-status" :class="['active', 'completed'].includes(item.status.toLowerCase()) ? item.status.toLowerCase() : 'recommended'">{{ item.status === 'ACTIVE' ? '进行中' : item.status === 'END_RECOMMENDED' ? '建议结束' : '已结束' }}</span><h3>{{ item.target_role }}</h3><p>{{ item.difficulty }} · {{ item.turn_count }} 轮 · {{ formatDate(item.created_at) }}</p></div><div class="record-score">{{ item.report?.overall_score ?? "—" }}<small>综合分</small></div><div class="record-actions"><button class="text-button" @click="loadSession(item.id)">查看</button><button class="text-button danger-text" @click="deleteSession(item.id)">删除</button></div></article></div>
        </section>
      </section>
    </main>
  </div>
</template>
