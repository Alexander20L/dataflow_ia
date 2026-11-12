"use client";
import { useEffect, useRef } from "react";
import { init, use as registerECharts } from "echarts/core";
import {
  BarChart,
  HeatmapChart,
  LineChart,
  PieChart,
  ScatterChart,
} from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  VisualMapComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { EChartsCoreOption } from "echarts/core";
import { capDecimals, localeNumber } from "@/lib/numbers";

registerECharts([
  BarChart,
  LineChart,
  PieChart,
  ScatterChart,
  HeatmapChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  VisualMapComponent,
  CanvasRenderer,
]);
/** Valor de un tooltip con el formato «es-ES» y 3 decimales como mucho. */
export function chartValue(value: unknown): string {
  if (Array.isArray(value)) return value.map(chartValue).join(", ");
  if (typeof value === "number") return localeNumber(value);
  if (
    typeof value === "string" &&
    value.trim() !== "" &&
    Number.isFinite(Number(value))
  )
    return localeNumber(Number(capDecimals(value.trim())));
  return value == null ? "-" : String(value);
}

type Settings = Record<string, unknown>;
const isSettings = (value: unknown): value is Settings =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/** Ejes de valores sin `axisLabel.formatter` propio: 3 decimales como mucho. */
function capAxis(axis: unknown, type: string): unknown {
  if (Array.isArray(axis)) return axis.map((item) => capAxis(item, type));
  if (!isSettings(axis) || (axis.type ?? type) !== "value") return axis;
  const label = isSettings(axis.axisLabel) ? axis.axisLabel : {};
  if (label.formatter !== undefined) return axis;
  return {
    ...axis,
    axisLabel: { ...label, formatter: (v: number) => localeNumber(v) },
  };
}

/** Sólo presentación: los resultados se muestran con 3 decimales como mucho salvo que quien
 * llama haya fijado su propio formateador. Los datos de las series no cambian. */
function capDecimalsOption(option: EChartsCoreOption): EChartsCoreOption {
  const result: Settings = { ...option };
  const tooltip = option.tooltip;
  if (
    isSettings(tooltip) &&
    tooltip.formatter === undefined &&
    tooltip.valueFormatter === undefined
  )
    result.tooltip = { ...tooltip, valueFormatter: chartValue };
  // Tipos por defecto de ECharts: «category» en el eje X y «value» en el Y.
  if ("xAxis" in option) result.xAxis = capAxis(option.xAxis, "category");
  if ("yAxis" in option) result.yAxis = capAxis(option.yAxis, "value");
  return result as EChartsCoreOption;
}

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
    chart.setOption(capDecimalsOption(option));
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
      valueFormatter: chartValue,
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
        formatter: (v: number) =>
          v >= 1000 ? `${capDecimals(v / 1000)}k` : capDecimals(v),
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

// Fase 21: las etiquetas vienen del archivo; los tooltips nunca se tratan como HTML.
const SAFE_TOOLTIP = { renderMode: "richText" as const };

export function pieOption(
  labels: string[],
  values: number[],
): EChartsCoreOption {
  return {
    color: ["#6366f1", "#06b6d4", "#f59e0b", "#10b981", "#ef4444", "#8b5cf6"],
    tooltip: { ...SAFE_TOOLTIP, trigger: "item" },
    legend: { bottom: 0, textStyle: { color: "#94a3b8", fontSize: 11 } },
    series: [
      {
        type: "pie",
        radius: ["40%", "70%"],
        center: ["50%", "45%"],
        data: labels.map((name, index) => ({ name, value: values[index] })),
        label: { show: false },
      },
    ],
  };
}

export function heatmapOption(
  xs: string[],
  ys: string[],
  cells: [number, number, number][],
): EChartsCoreOption {
  const values = cells.map((cell) => cell[2]);
  return {
    tooltip: { ...SAFE_TOOLTIP, trigger: "item" },
    grid: { left: 80, right: 20, top: 10, bottom: 60 },
    xAxis: {
      type: "category",
      data: xs,
      axisLabel: { color: "#94a3b8", fontSize: 11 },
    },
    yAxis: {
      type: "category",
      data: ys,
      axisLabel: { color: "#94a3b8", fontSize: 11 },
    },
    visualMap: {
      min: Math.min(0, ...values),
      max: Math.max(1, ...values),
      calculable: false,
      orient: "horizontal",
      left: "center",
      bottom: 0,
      itemHeight: 120,
      inRange: { color: ["#e0e7ff", "#4338ca"] },
      textStyle: { color: "#94a3b8" },
      formatter: (v: number) => localeNumber(v),
    },
    series: [{ type: "heatmap", data: cells }],
  };
}
