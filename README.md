# AI 模拟面试系统

基于 AI Agent 的智能模拟面试系统（Vue 3 + FastAPI + LangChain + 百炼 qwen-plus）。

用户上传简历并配置面试岗位与难度后，AI 面试官结合简历与上下文进行多轮追问；支持语音交互（浏览器/服务端/WebSocket 三通道）；面试结束后生成带回答证据的 ECharts 可视化评估报告，支持 PDF/Excel 导出与历史管理。

## 功能

- 简历解析：PDF/DOCX/TXT/MD 上传 → 结构化字段 → 编辑确认
- Agent 面试：动态系统提示词、回答驱动追问、已问题目去重
- Function Call：题库检索（ChromaDB 向量检索）、学习资源爬虫推荐
- 记忆压缩：每 5 轮生成结构化摘要，控制 Token 消耗
- 语音：ASR/TTS 双通道（浏览器 Web Speech / 服务端 qwen3-omni-flash），WebSocket 实时分片识别
- 评估报告：总分 + 三维度（证据引用经防幻觉校验）+ 亮点/问题/建议
- 可视化：ECharts 雷达图、STAR 热力图、情绪时序图、技术栈气泡图
- 情绪分析：文本规则打分 + 音频情绪推理
- 知识图谱：岗位—技能—面试题三层关系网络
- 导出与管理：PDF（reportlab）/ Excel，历史记录增删查

## 快速开始

```powershell
# 1. 后端
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy .env.example .env        # 填入 DASHSCOPE_API_KEY
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 2. 前端（新终端）
cd frontend
npm install
npm run dev
```

或直接双击 `启动项目.bat`（自动启动前后端并打开浏览器）。

- 页面：http://127.0.0.1:5173
- 接口文档：http://127.0.0.1:8000/docs

## 环境变量

`backend/.env`（参考 `.env.example`）：

```
DASHSCOPE_API_KEY=sk-xxx
```

未配置密钥时系统进入本地降级模式（规则追问/规则报告），页面功能不瘫痪。

## 项目结构

```
frontend/            Vue 3 + Vite + ECharts
backend/app/         FastAPI 入口、路由、SQLite 数据层
backend/app/ai/      AI 能力层（面试官/记忆管家/检索/爬虫/情绪/图谱/报告/语音）
data/                运行数据（SQLite、ChromaDB、上传与导出文件），已 gitignore
```

## License

MIT
