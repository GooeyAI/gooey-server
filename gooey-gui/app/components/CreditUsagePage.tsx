import "./CreditUsagePage.css";

import { Link, useNavigate } from "@remix-run/react";
import { useLayoutEffect, useRef, useState } from "react";

import type { CustomComponentProps } from "~/components";
import { lazyImport } from "~/lazyImports";
import type {
  CreditUsagePageProps,
  CreditUsageRangeOption,
  CreditUsageSeries,
} from "@gooey-types/credit_usage_props";

const Plot = lazyImport(
  () => import("react-plotly.js").then((mod) => mod.default)
  // @ts-ignore
).default;

// narrowest a month gets in the chart before it scrolls sideways
const MIN_MONTH_WIDTH = 44;
const TOOLTIP_WIDTH = 240;
const TOOLTIP_GAP = 8;
// recipes past the chart's palette fold into one grey "Other" series
const OTHER_COLOR = "#a3a29c";

type ChartHover = {
  index: number;
  band: { left: number; width: number; top: number; height: number };
  barTop: number;
  chartWidth: number;
  plotTop: number;
  plotBottom: number;
};

export function CreditUsagePage({
  title,
  workspace_name,
  months,
  series,
  billing_href,
  current_month,
  month_options,
  range_href,
  presets,
  chart,
}: CustomComponentProps & CreditUsagePageProps) {
  const monthTotals = months.map((_, i) =>
    series.reduce((sum, s) => sum + s.usd[i], 0)
  );
  const grandTotal = monthTotals.reduce((a, b) => a + b, 0);
  const rangeLabel = `${formatMonth(months[0])} – ${formatMonth(months[months.length - 1])}`;

  return (
    <div className="credit-usage my-4">
      <div className="d-flex flex-wrap align-items-center justify-content-between gap-3 mb-2">
        <h2 className="my-0">{title}</h2>
        <button
          type="button"
          className="btn btn-theme btn-secondary"
          disabled={!series.length}
          onClick={() => downloadCsv(workspace_name, months, series)}
        >
          <i className="fa-regular fa-download me-2" aria-hidden="true" />
          Download CSV
        </button>
      </div>
      <p className="text-muted mb-4">
        What <b>{workspace_name}</b> spent each month, by recipe, in USD. Months
        are in UTC. See <Link to={billing_href}>Billing</Link> for purchases and
        your balance.
      </p>

      <UsageRangeFilter
        months={months}
        monthOptions={month_options}
        rangeHref={range_href}
        presets={presets}
      />

      {series.length ? (
        <>
          <UsageStats
            months={months}
            currentMonth={current_month}
            monthTotals={monthTotals}
            grandTotal={grandTotal}
          />
          {chart && (
            <UsageChart
              chart={chart}
              months={months}
              series={series}
              monthTotals={monthTotals}
            />
          )}
          <UsageTable
            months={months}
            series={series}
            monthTotals={monthTotals}
            grandTotal={grandTotal}
          />
        </>
      ) : (
        <p className="text-muted">Nothing spent in {rangeLabel}.</p>
      )}
    </div>
  );
}

function UsageRangeFilter({
  months,
  monthOptions,
  rangeHref,
  presets,
}: {
  months: string[];
  monthOptions: string[];
  rangeHref: string;
  presets: CreditUsageRangeOption[];
}) {
  const navigate = useNavigate();
  const start = months[0];
  const end = months[months.length - 1];

  const setRange = (newStart: string, newEnd: string) => {
    const params = new URLSearchParams({ start: newStart, end: newEnd });
    navigate(`${rangeHref}?${params}`);
  };

  return (
    <div className="credit-usage-filter">
      <div
        className="credit-usage-presets"
        role="group"
        aria-label="Date range"
      >
        {presets.map((preset) => (
          <Link
            key={preset.title}
            to={preset.href}
            className={preset.active ? "active" : undefined}
            aria-current={preset.active ? "true" : undefined}
          >
            {preset.title}
          </Link>
        ))}
      </div>
      <div className="d-flex align-items-center gap-2">
        <MonthSelect
          label="From"
          value={start}
          options={monthOptions}
          onChange={(value) => setRange(value, end)}
        />
        <span className="text-muted">to</span>
        <MonthSelect
          label="To"
          value={end}
          options={monthOptions}
          onChange={(value) => setRange(start, value)}
        />
      </div>
    </div>
  );
}

function MonthSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  return (
    <select
      // navigates by url; keep the page's form from also submitting its state
      data-submit-disabled
      className="form-select form-select-sm"
      aria-label={label}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      {[...options].reverse().map((month) => (
        <option key={month} value={month}>
          {formatMonth(month)}
        </option>
      ))}
    </select>
  );
}

function UsageStats({
  months,
  currentMonth,
  monthTotals,
  grandTotal,
}: {
  months: string[];
  currentMonth: string;
  monthTotals: number[];
  grandTotal: number;
}) {
  const last = months.length - 1;
  const peak = monthTotals.indexOf(Math.max(...monthTotals));
  return (
    <div className="credit-usage-stats">
      <Stat
        label={`Total, ${months.length} ${months.length === 1 ? "month" : "months"}`}
        value={grandTotal}
      />
      <Stat label="Monthly average" value={grandTotal / months.length} />
      {months[last] === currentMonth ? (
        <Stat
          label={`${formatMonth(months[last])} so far`}
          value={monthTotals[last]}
        />
      ) : (
        <Stat
          label={`Peak month, ${formatMonth(months[peak])}`}
          value={monthTotals[peak]}
        />
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="credit-usage-stat">
      <div className="credit-usage-stat-label">{label}</div>
      <div className="credit-usage-stat-value">{formatUsd(value)}</div>
    </div>
  );
}

function UsageChart({
  chart,
  months,
  series,
  monthTotals,
}: {
  chart: Record<string, any>;
  months: string[];
  series: CreditUsageSeries[];
  monthTotals: number[];
}) {
  const [hover, setHover] = useState<ChartHover | null>(null);

  // plotly draws the bars; the band behind the hovered month and the tooltip
  // are ours, placed with the hovered point's axes
  const onHover = (event: any) => {
    const point = event.points?.[0];
    if (!point) return;
    const xa = point.xaxis;
    const ya = point.yaxis;
    const index = point.pointIndex;
    const center = xa._offset + xa.d2p(point.x);
    const slot = Math.abs(
      xa.d2p(nextMonth(months[index])) - xa.d2p(`${months[index]}-01`)
    );
    const graph = event.event?.target?.closest?.(".js-plotly-plot");
    setHover({
      index,
      band: {
        left: center - slot / 2,
        width: slot,
        top: ya._offset,
        height: ya._length,
      },
      barTop: ya._offset + ya.d2p(monthTotals[index]),
      chartWidth: graph?.offsetWidth ?? xa._offset + xa._length,
      plotTop: ya._offset,
      plotBottom: ya._offset + ya._length,
    });
  };

  return (
    <>
      <UsageLegend series={series} />
      {/* scrolls sideways on narrow screens rather than squeezing the bars */}
      <div className="credit-usage-chart-scroll">
        <div
          className="credit-usage-chart"
          style={{ minWidth: `${months.length * MIN_MONTH_WIDTH}px` }}
          onMouseLeave={() => setHover(null)}
        >
          {hover && (
            <div className="credit-usage-hover-band" style={hover.band} />
          )}
          <Plot
            data={chart.data}
            layout={chart.layout}
            style={{ width: "100%" }}
            config={{ displayModeBar: false }}
            onHover={onHover}
            onUnhover={() => setHover(null)}
          />
          {hover && (
            <UsageTooltip
              hover={hover}
              month={months[hover.index]}
              series={series}
              total={monthTotals[hover.index]}
            />
          )}
        </div>
      </div>
    </>
  );
}

function UsageLegend({ series }: { series: CreditUsageSeries[] }) {
  const items = series
    .filter((s) => s.color)
    .map((s) => ({ id: s.id, title: s.title, color: s.color! }));
  if (series.some((s) => !s.color)) {
    items.push({ id: "other", title: "Other", color: OTHER_COLOR });
  }
  return (
    <div className="credit-usage-legend">
      {items.map((item) => (
        <span key={item.id} className="credit-usage-legend-item">
          <span
            className="credit-usage-swatch"
            style={{ background: item.color }}
          />
          {item.title}
        </span>
      ))}
    </div>
  );
}

function UsageTooltip({
  hover,
  month,
  series,
  total,
}: {
  hover: ChartHover;
  month: string;
  series: CreditUsageSeries[];
  total: number;
}) {
  const i = hover.index;
  const rows = series
    .filter((s) => s.usd[i] > 0)
    .sort((a, b) => b.usd[i] - a.usd[i]);

  // beside the band, flipping to its left when there's no room on the right,
  // and level with the top of the bar where it fits
  const { band } = hover;
  const right = band.left + band.width + TOOLTIP_GAP;
  const left =
    right + TOOLTIP_WIDTH <= hover.chartWidth
      ? right
      : Math.max(0, band.left - TOOLTIP_GAP - TOOLTIP_WIDTH);
  // level with the top of the bar, but kept inside the plot so it never covers
  // the axis labels; the height is measured once the tooltip has rendered
  const ref = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState(0);
  useLayoutEffect(() => {
    setHeight(ref.current?.offsetHeight ?? 0);
  }, [i]);
  const top = Math.max(
    hover.plotTop,
    Math.min(hover.barTop, hover.plotBottom - height)
  );

  return (
    <div
      ref={ref}
      className="credit-usage-tooltip"
      style={{ left, top, width: TOOLTIP_WIDTH }}
    >
      <div className="credit-usage-tooltip-month">
        {formatMonth(month, true)}
      </div>
      <div className="credit-usage-tooltip-total">{formatUsd(total)}</div>
      <hr />
      {rows.map((s) => (
        <div key={s.id} className="credit-usage-tooltip-row">
          <span
            className="credit-usage-swatch"
            style={{ background: s.color ?? OTHER_COLOR }}
          />
          <span className="credit-usage-tooltip-name">{s.title}</span>
          <span>{formatUsd(s.usd[i])}</span>
        </div>
      ))}
    </div>
  );
}

function UsageTable({
  months,
  series,
  monthTotals,
  grandTotal,
}: {
  months: string[];
  series: CreditUsageSeries[];
  monthTotals: number[];
  grandTotal: number;
}) {
  return (
    <div className="table-responsive">
      <table className="table table-sm credit-usage-table">
        <thead>
          <tr>
            <th>Recipe</th>
            {months.map((m) => (
              <th key={m} className="text-end">
                {formatMonth(m)}
              </th>
            ))}
            <th className="text-end">Total</th>
          </tr>
        </thead>
        <tbody>
          {series.map((s) => (
            <tr key={s.id}>
              <td>{s.title}</td>
              {s.usd.map((c, i) => (
                <td key={months[i]} className="text-end">
                  {c ? formatUsd(c) : <span className="text-muted">–</span>}
                </td>
              ))}
              <td className="text-end fw-semibold">{formatUsd(sum(s.usd))}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="fw-semibold">
            <td>Total</td>
            {monthTotals.map((t, i) => (
              <td key={months[i]} className="text-end">
                {formatUsd(t)}
              </td>
            ))}
            <td className="text-end">{formatUsd(grandTotal)}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

function downloadCsv(
  workspaceName: string,
  months: string[],
  series: CreditUsageSeries[]
) {
  const escape = (value: string) => `"${value.replace(/"/g, '""')}"`;
  const rows = [
    ["Recipe", ...months, "Total"],
    ...series.map((s) => [
      escape(s.title),
      ...s.usd.map(toCsvUsd),
      toCsvUsd(sum(s.usd)),
    ]),
    [
      "Total",
      ...months.map((_, i) => toCsvUsd(sum(series.map((s) => s.usd[i])))),
      toCsvUsd(sum(series.flatMap((s) => s.usd))),
    ],
  ];
  const blob = new Blob([rows.map((r) => r.join(",")).join("\n")], {
    type: "text/csv",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${workspaceName} usage (USD) ${months[0]} to ${months[months.length - 1]}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

function nextMonth(month: string) {
  const [year, m] = month.split("-").map(Number);
  return m === 12
    ? `${year + 1}-01-01`
    : `${year}-${String(m + 1).padStart(2, "0")}-01`;
}

function formatMonth(month: string, long = false) {
  const [year, m] = month.split("-").map(Number);
  return new Date(Date.UTC(year, m - 1, 1)).toLocaleDateString("en-US", {
    month: long ? "long" : "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

function formatUsd(value: number) {
  return value.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

// plain numbers, so spreadsheets can sum them
function toCsvUsd(value: number) {
  return value.toFixed(2);
}

function sum(values: number[]) {
  return values.reduce((a, b) => a + b, 0);
}
