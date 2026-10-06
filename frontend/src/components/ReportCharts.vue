<script setup>
// 赛题三功能 9：ECharts 可视化看板（雷达图 / STAR 热力图 / 情绪时序图 / 技术栈气泡图）。
import * as echarts from "echarts";
import { onBeforeUnmount, onMounted, ref, watch } from "vue";

const props = defineProps({ report: { type: Object, required: true } });
const radarRef = ref(null);
const starRef = ref(null);
const trendRef = ref(null);
const bubbleRef = ref(null);
let charts = [];

function render(el, option) {
  if (!el) return null;
  const chart = echarts.init(el);
  chart.setOption(option);
  return chart;
}

function disposeAll() {
  charts.forEach((chart) => chart.dispose());
  charts = [];
}

function renderAll() {
  disposeAll();
  const report = props.report;
  if (!report) return;

  const dimensionKeys = ["professional", "logic", "communication"];
  const dimensionLabels = ["专业能力", "逻辑结构", "表达沟通"];
  render(
    radarRef.value,
    {
      tooltip: {},
      radar: {
        indicator: dimensionLabels.map((name) => ({ name, max: 100 })),
        radius: "62%",
        splitNumber: 4,
        axisName: { color: "#52525b", fontSize: 11 },
        splitLine: { lineStyle: { color: "#e4e4e7" } },
        splitArea: { areaStyle: { color: ["#fafafa", "#f4f4f5"] } },
      },
      series: [
        {
          type: "radar",
          data: [
            {
              value: dimensionKeys.map((key) => Number(report.dimensions?.[key]?.score) || 0),
              name: "能力得分",
              areaStyle: { opacity: 0.25 },
              lineStyle: { width: 2, color: "#3f3f46" },
              itemStyle: { color: "#18181b" },
            },
          ],
        },
      ],
    }
  );

  const star = report.star || { turns: [], dimensions: [], cells: [] };
  if (star.turns?.length) {
    render(
      starRef.value,
      {
        tooltip: {
          position: "top",
          formatter: (params) => `第 ${star.turns[params.value[0]]} 轮<br/>${star.dimensions[params.value[1]]}：${params.value[2]}`,
        },
        grid: { height: "52%", top: 16, left: 90, right: 16 },
        xAxis: {
          type: "category",
          data: star.turns.map((turn) => `第${turn}轮`),
          splitArea: { show: true },
          axisLabel: { fontSize: 10 },
        },
        yAxis: {
          type: "category",
          data: star.dimensions,
          axisLabel: { fontSize: 10 },
        },
        visualMap: {
          min: 0,
          max: 1,
          calculable: true,
          orient: "horizontal",
          left: "center",
          bottom: 0,
          inRange: { color: ["#f4f4f5", "#a1a1aa", "#18181b"] },
          textStyle: { fontSize: 10 },
        },
        series: [
          {
            type: "heatmap",
            label: { show: true, fontSize: 9, formatter: (params) => (params.value[2] > 0 ? params.value[2] : "") },
            data: star.cells,
          },
        ],
      }
    );
  }

  const timeline = report.emotion?.timeline || [];
  if (timeline.length) {
    render(
      trendRef.value,
      {
        tooltip: { trigger: "axis" },
        grid: { left: 34, right: 14, top: 18, bottom: 24 },
        xAxis: {
          type: "category",
          data: timeline.map((item) => `第${item.turn}轮`),
          axisLabel: { fontSize: 10 },
        },
        yAxis: { type: "value", max: 100, axisLabel: { fontSize: 10 } },
        series: [
          {
            type: "line",
            smooth: true,
            name: "情绪分",
            data: timeline.map((item) => item.score),
            areaStyle: { opacity: 0.15 },
            lineStyle: { width: 2, color: "#4d7a61" },
            itemStyle: { color: "#2d7958" },
            markLine: {
              silent: true,
              symbol: "none",
              data: [{ yAxis: 55, name: "平稳线" }],
              lineStyle: { type: "dashed", color: "#a2773f" },
              label: { formatter: "平稳线", fontSize: 9 },
            },
          },
        ],
      }
    );
  }

  const graph = report.knowledge_graph;
  if (graph?.nodes?.length) {
    const focusSet = new Set(graph.covered_focus || []);
    const isV2 = graph.graph_version === 2;
    const typeColors = { 岗位: "#18181b", 面试题: "#a1a1aa" };
    render(
      bubbleRef.value,
      {
        tooltip: {
          formatter: (params) => {
            if (params.dataType === "edge") {
              const edge = graph.edges.find((item) => item.source === params.data.source && item.target === params.data.target);
              return edge?.relation ? `关系：${edge.relation}` : "";
            }
            const node = graph.nodes.find((item) => item.id === params.name);
            return node
              ? `${params.name}<br/>${node.type || node.category || "技能"}<br/>提及 ${node.mentions} 次${node.turns?.length ? `（第 ${node.turns.join("、")} 轮）` : ""}${node.similarity ? `<br/>相似度 ${node.similarity}` : ""}`
              : params.name;
          },
        },
        legend: isV2
          ? {
              data: ["岗位", "面试题"],
              textStyle: { fontSize: 10 },
              selectedMode: false,
              bottom: 0,
            }
          : undefined,
        series: [
          {
            type: "graph",
            layout: "force",
            roam: true,
            label: { show: true, fontSize: 10 },
            force: { repulsion: 140, gravity: 0.12, edgeLength: 60 },
            data: graph.nodes.map((node) => ({
              name: node.id,
              symbolSize: node.type === "岗位" ? 34 : 12 + Math.min(24, node.mentions * 6),
              itemStyle: {
                color: typeColors[node.type] || (focusSet.has(node.id) || node.category === "重点" ? "#a2773f" : "#3f3f46"),
              },
            })),
            links: (graph.edges || [])
              .filter((edge) => graph.nodes.some((node) => node.id === edge.source) && graph.nodes.some((node) => node.id === edge.target))
              .map((edge) => ({
                source: edge.source,
                target: edge.target,
                lineStyle: {
                  width: Math.min(4, 0.8 + edge.weight),
                  opacity: 0.4,
                  color: "#a1a1aa",
                  type: edge.relation === "考察" ? "dashed" : "solid",
                },
              })),
          },
        ],
      }
    );
  }
}

onMounted(renderAll);
watch(() => props.report, renderAll, { deep: true });
window.addEventListener("resize", handleResize);
function handleResize() {
  charts.forEach((chart) => chart.resize());
}
onBeforeUnmount(() => {
  window.removeEventListener("resize", handleResize);
  disposeAll();
});
</script>

<template>
  <div class="charts-grid">
    <div class="chart-card">
      <h3>能力雷达（ECharts）</h3>
      <div ref="radarRef" class="chart-box"></div>
    </div>
    <div class="chart-card" :class="{ span2: (report.star?.turns?.length || 0) > 0 }">
      <h3>STAR 表现热力图</h3>
      <div v-if="report.star?.turns?.length" ref="starRef" class="chart-box wide"></div>
      <p v-else class="chart-empty">暂无回答数据，无法绘制 STAR 热力图。</p>
    </div>
    <div class="chart-card">
      <h3>情绪时序（ECharts）</h3>
      <div v-if="report.emotion?.timeline?.length" ref="trendRef" class="chart-box"></div>
      <p v-else class="chart-empty">暂无情绪轨迹数据。</p>
    </div>
    <div class="chart-card">
      <h3>技术栈气泡（ECharts）</h3>
      <div v-if="report.knowledge_graph?.nodes?.length" ref="bubbleRef" class="chart-box"></div>
      <p v-else class="chart-empty">暂无技能图谱数据。</p>
    </div>
  </div>
</template>

<style scoped>
.charts-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px; }
.chart-card { padding: 16px; border: 1px solid #e4e4e7; border-radius: 14px; background: #fff; }
.chart-card.span2 { grid-column: span 2; }
.chart-card h3 { margin: 0 0 8px; font-size: 13px; color: #18181b; }
.chart-box { width: 100%; height: 240px; }
.chart-box.wide { height: 260px; }
.chart-empty { margin: 0; padding: 40px 0; color: #a1a1aa; font-size: 12px; text-align: center; }
@media (max-width: 760px) { .chart-card.span2 { grid-column: span 1; } }
</style>
