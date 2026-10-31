"use client";
import { useEffect, useRef } from "react";
import { init, use as registerECharts } from "echarts/core";
import { BarChart, LineChart, PieChart, ScatterChart } from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { EChartsCoreOption } from "echarts/core";

registerECharts([
  BarChart,
  LineChart,
  PieChart,
  ScatterChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  CanvasRenderer,
]);
export function Chart({
  option,
  label,
  height = 260,
}: {
  option: EChartsCoreOption;
  label: string;
  height?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const chart = init(ref.current);
    chart.setOption(option);
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(ref.current);
    return () => {
      observer.disconnect();
      chart.dispose();
    };
  }, [option]);
  return (
    <div
      ref={ref}
      role="img"
      aria-label={label}
      style={{ height, width: "100%" }}
    />
  );
}

export function seriesOption(
  labels: string[],
  values: number[],
  type: "line" | "bar" = "line",
): EChartsCoreOption {
  return {
    color: ["#6366f1", "#06b6d4"],
    tooltip: {
      trigger: "axis",
      valueFormatter: (value: unknown) => Number(value).toLocaleString("es-ES"),
    },
    grid: { left: 50, right: 20, top: 20, bottom: 35 },
    xAxis: {
      type: "category",
      data: labels,
      boundaryGap: type === "bar",
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: "#94a3b8", fontSize: 11, margin: 16 },
    },
    yAxis: {
      type: "value",
      splitNumber: 4,
      axisLabel: {
        color: "#94a3b8",
        fontSize: 11,
        formatter: (v: number) => (v >= 1000 ? `${v / 1000}k` : String(v)),
      },
      splitLine: { lineStyle: { color: "#94a3b820", type: "dashed" } },
    },
    series: [
      {
        type,
        data: values,
        smooth: true,
        symbol: "circle",
        symbolSize: 7,
        showSymbol: false,
        barMaxWidth: 40,
        itemStyle: { borderRadius: type === "bar" ? [5, 5, 0, 0] : 0 },
        lineStyle: { width: 3 },
        areaStyle: type === "line" ? { color: "#6366f112" } : undefined,
      },
    ],
  };
}
