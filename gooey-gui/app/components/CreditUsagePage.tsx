import "./CreditUsagePage.css";

import { Link, useNavigate } from "@remix-run/react";

import type { CustomComponentProps } from "~/components";
import { RenderedChildren } from "~/renderer";
import type {
  CreditUsagePageProps,
  CreditUsageRangeOption,
  CreditUsageSeries,
} from "@gooey-types/credit_usage_props";

// narrowest a month gets in the chart before it scrolls sideways
const MIN_MONTH_WIDTH = 44;

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
  children,
  onChange,
  state,
}: CustomComponentProps & CreditUsagePageProps) {
  const monthTotals = months.map((_, i) =>
    series.reduce((sum, s) => sum + s.credits[i], 0)
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
        Credits spent by <b>{workspace_name}</b> each month, by recipe. Months
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
          {/* the plotly chart from the server; scrolls sideways on narrow
              screens rather than squeezing the bars */}
          <div className="credit-usage-chart-scroll">
            <div style={{ minWidth: `${months.length * MIN_MONTH_WIDTH}px` }}>
              <RenderedChildren
                children={children}
                onChange={onChange}
                state={state}
              />
            </div>
          </div>
          <UsageTable
            months={months}
            series={series}
            monthTotals={monthTotals}
            grandTotal={grandTotal}
          />
        </>
      ) : (
        <p className="text-muted">No credits spent in {rangeLabel}.</p>
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
      <Stat
        label="Monthly average"
        value={Math.round(grandTotal / months.length)}
      />
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
      <div className="credit-usage-stat-value">
        {formatCredits(value)}{" "}
        <span className="fs-6 text-muted fw-normal">Cr</span>
      </div>
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
              {s.credits.map((c, i) => (
                <td key={months[i]} className="text-end">
                  {c ? formatCredits(c) : <span className="text-muted">–</span>}
                </td>
              ))}
              <td className="text-end fw-semibold">
                {formatCredits(sum(s.credits))}
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="fw-semibold">
            <td>Total</td>
            {monthTotals.map((t, i) => (
              <td key={months[i]} className="text-end">
                {formatCredits(t)}
              </td>
            ))}
            <td className="text-end">{formatCredits(grandTotal)}</td>
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
      ...s.credits.map(String),
      String(sum(s.credits)),
    ]),
    [
      "Total",
      ...months.map((_, i) => String(sum(series.map((s) => s.credits[i])))),
      String(sum(series.flatMap((s) => s.credits))),
    ],
  ];
  const blob = new Blob([rows.map((r) => r.join(",")).join("\n")], {
    type: "text/csv",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${workspaceName} credit usage ${months[0]} to ${months[months.length - 1]}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

function formatMonth(month: string) {
  const [year, m] = month.split("-").map(Number);
  return new Date(Date.UTC(year, m - 1, 1)).toLocaleDateString("en-US", {
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

function formatCredits(value: number) {
  return value.toLocaleString("en-US");
}

function sum(values: number[]) {
  return values.reduce((a, b) => a + b, 0);
}
