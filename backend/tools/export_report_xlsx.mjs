import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

function artifactToolPath() {
  const candidates = [];
  if (process.env.ARTIFACT_TOOL_ROOT) {
    candidates.push(process.env.ARTIFACT_TOOL_ROOT);
  }
  const home = process.env.USERPROFILE || process.env.HOME;
  if (home) {
    candidates.push(
      path.join(
        home,
        ".cache",
        "codex-runtimes",
        "codex-primary-runtime",
        "dependencies",
        "node",
        "node_modules",
        "@oai",
        "artifact-tool",
      ),
    );
  }
  candidates.push(path.resolve(path.dirname(fileURLToPath(import.meta.url)), "node_modules/@oai/artifact-tool"));
  return candidates.find((item) => item && item.length > 0);
}

const root = artifactToolPath();
if (!root) throw new Error("未找到 @oai/artifact-tool");
const { SpreadsheetFile, Workbook } = await import(
  pathToFileURL(path.join(root, "dist", "artifact_tool.mjs")).href
);

const [, , inputPath, outputPath] = process.argv;
if (!inputPath || !outputPath) throw new Error("缺少输入或输出路径");
const payload = JSON.parse(await fs.readFile(inputPath, "utf8"));
const report = payload.report || {};
const session = payload.session || {};
const workbook = Workbook.create();

const colors = {
  green: "#173F35",
  lightGreen: "#EDF5EF",
  border: "#DBE6DF",
  text: "#365146",
  muted: "#6F8479",
};
const font = "Arial";

function styleRange(range, options = {}) {
  range.format.font = { name: font, size: options.size || 10, color: options.color || colors.text, bold: Boolean(options.bold) };
  range.format.verticalAlignment = "center";
  if (options.fill) range.format.fill = options.fill;
  if (options.wrap) range.format.wrapText = true;
  if (options.borders) range.format.borders = { preset: "all", style: "thin", color: colors.border };
}

function title(sheet, text) {
  sheet.getRange("A1:D1").merge();
  sheet.getRange("A1").values = [[text]];
  styleRange(sheet.getRange("A1:D1"), { size: 16, bold: true, color: colors.green });
  sheet.getRange("A1:D1").format.rowHeight = 28;
}

function header(sheet, address) {
  styleRange(sheet.getRange(address), { bold: true, color: "#FFFFFF", fill: colors.green, wrap: true, borders: true });
}

function setWidths(sheet, widths) {
  widths.forEach(([column, width]) => {
    sheet.getRange(`${column}:${column}`).format.columnWidth = width;
  });
}

const summary = workbook.worksheets.add("评估总览");
summary.showGridLines = false;
title(summary, "AI 模拟面试评估总览");
summary.getRange("A3:B5").values = [
  ["目标岗位", session.target_role || "未填写"],
  ["面试难度", session.difficulty || "未填写"],
  ["综合评分", Number(report.overall_score || 0)],
];
styleRange(summary.getRange("A3:A5"), { bold: true, fill: colors.lightGreen, borders: true });
styleRange(summary.getRange("B3:B5"), { borders: true });
summary.getRange("B5").format.numberFormat = "0";
summary.getRange("A7:C7").values = [["评估维度", "分数", "证据摘要"]];
header(summary, "A7:C7");
const dimensionLabels = { professional: "专业能力", logic: "逻辑结构", communication: "表达沟通" };
const dimensionRows = ["professional", "logic", "communication"].map((key) => {
  const item = report.dimensions?.[key] || {};
  const evidence = (item.evidence || []).slice(0, 2).map((entry) => `第 ${entry.turn} 轮：${entry.quote || ""}`).join("；");
  return [dimensionLabels[key], Number(item.score || 0), evidence || "暂无可引用证据"];
});
summary.getRange("A8:C10").values = dimensionRows;
styleRange(summary.getRange("A8:C10"), { wrap: true, borders: true });
summary.getRange("B8:B10").format.numberFormat = "0";
summary.getRange("A12:B14").values = [
  ["回答数量", Number(report.meta?.answer_count || 0)],
  ["报告模式", report.meta?.mode || "unknown"],
  ["报告版本", Number(report.version || 1)],
];
styleRange(summary.getRange("A12:A14"), { bold: true, fill: colors.lightGreen, borders: true });
styleRange(summary.getRange("B12:B14"), { borders: true });
setWidths(summary, [["A", 18], ["B", 18], ["C", 72], ["D", 3]]);
summary.getRange("A1:C14").format.autofitRows();

const evidence = workbook.worksheets.add("证据明细");
evidence.showGridLines = false;
title(evidence, "面试回答证据明细");
evidence.getRange("A3:E3").values = [["评估维度", "回答轮次", "维度分数", "引用回答", "证据说明"]];
header(evidence, "A3:E3");
const evidenceRows = [];
for (const key of ["professional", "logic", "communication"]) {
  const item = report.dimensions?.[key] || {};
  for (const entry of item.evidence || []) {
    evidenceRows.push([
      dimensionLabels[key],
      Number(entry.turn || 0),
      Number(item.score || 0),
      entry.quote || "",
      `该证据来自用户第 ${entry.turn} 轮回答`,
    ]);
  }
}
if (!evidenceRows.length) evidenceRows.push(["暂无", "", "", "暂无证据", ""]);
evidence.getRange(`A4:E${evidenceRows.length + 3}`).values = evidenceRows;
styleRange(evidence.getRange(`A4:E${evidenceRows.length + 3}`), { wrap: true, borders: true });
setWidths(evidence, [["A", 18], ["B", 12], ["C", 14], ["D", 70], ["E", 30]]);
evidence.getRange(`A1:E${evidenceRows.length + 3}`).format.autofitRows();
evidence.freezePanes.freezeRows(3);

const review = workbook.worksheets.add("复盘建议");
review.showGridLines = false;
title(review, "面试复盘建议");
review.getRange("A3:B3").values = [["类型", "内容"]];
header(review, "A3:B3");
const reviewRows = [];
for (const value of report.highlights || []) reviewRows.push(["表现亮点", value]);
for (const value of report.problems || []) reviewRows.push(["还可以更好", value]);
for (const value of report.suggestions || []) reviewRows.push(["改进建议", value]);
if (!reviewRows.length) reviewRows.push(["暂无", "暂无复盘内容"]);
review.getRange(`A4:B${reviewRows.length + 3}`).values = reviewRows;
styleRange(review.getRange(`A4:B${reviewRows.length + 3}`), { wrap: true, borders: true });
setWidths(review, [["A", 18], ["B", 105], ["C", 3], ["D", 3]]);
review.getRange(`A1:B${reviewRows.length + 3}`).format.autofitRows();
review.freezePanes.freezeRows(3);

workbook.recalculate();
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
