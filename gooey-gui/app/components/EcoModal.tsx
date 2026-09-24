import "./EcoModal.css";

import type {
  EcoLabelProps,
  EcoRegionProps,
} from "@gooey-types/eco_label_props";
import { useEffect, useRef, useState } from "react";
import ReactDOM from "react-dom";
import Tippy from "@tippyjs/react";
import { Author } from "./RunDebugInfo";
import {
  MIX_COLORS,
  MIX_LABELS,
  REASON_TEXT,
  RUN_STEPS,
  RUN_TICKS,
  carbonEquivalent,
  countryName,
  energyEquivalent,
  flagEmoji,
  formatGrams,
  formatMl,
  formatRuns,
  formatTokens,
  formatUsd,
  formatWh,
  gridNote,
  waterEquivalent,
} from "./ecoScale";

/**
 * A bar's cost readout when the run has eco figures: the cost (`children`),
 * then its CO2e, as one button that opens the impact modal. Shared by the top
 * bar and the editor run bar, which differ only in styling and cost markup.
 */
export function EcoCostButton({
  eco_cost,
  tooltip,
  className,
  children,
}: {
  eco_cost: EcoLabelProps;
  tooltip: string;
  className: string;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const co2e = formatGrams(eco_cost.co2e_grams);
  return (
    <>
      <button
        type="button"
        className={className}
        title="Run cost and environment impact"
        aria-label={`${tooltip}, ${co2e} CO2e. Open cost and environment impact`}
        aria-haspopup="dialog"
        onClick={() => setOpen(true)}
      >
        {children}
        <span className="gooey-eco-co2e">
          {co2e} CO<sub>2</sub>e
        </span>
      </button>
      {open && <EcoModal eco_cost={eco_cost} onClose={() => setOpen(false)} />}
    </>
  );
}

/**
 * "Run Cost & Environment Impact": the per-run figures the server sent,
 * scaled client-side by a slider so the comparisons stay readable from one
 * run to a million. Mounted under <body> like the other overlays.
 */
export function EcoModal({
  eco_cost,
  onClose,
}: {
  eco_cost: EcoLabelProps;
  onClose: () => void;
}) {
  const [stepIdx, setStepIdx] = useState(0);
  const runs = RUN_STEPS[stepIdx];
  const contentRef = useRef<HTMLDivElement>(null);
  useSwipeDownToClose(contentRef, onClose);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [onClose]);

  const g = eco_cost.co2e_grams * runs;
  const ml = eco_cost.water_ml * runs;
  const mlDataCenter = eco_cost.water_data_center_ml * runs;
  const wh = eco_cost.energy_wh * runs;
  const water = waterEquivalent(ml);
  const energy = energyEquivalent(wh);

  const modal = (
    <div
      className="modal show d-block gooey-eco-modal"
      tabIndex={-1}
      role="dialog"
      aria-modal="true"
      aria-labelledby="gooey-eco-modal-title"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="modal-dialog modal-dialog-centered modal-dialog-scrollable modal-lg">
        <div ref={contentRef} className="modal-content gooey-eco-modal-content">
          {/* the action sheet's grab handle; shown only while this is a sheet */}
          <div
            className="gooey-sheet-handle-wrap gooey-eco-sheet-handle"
            aria-hidden="true"
          >
            <div className="gooey-sheet-handle" />
          </div>
          <div className="gooey-eco-modal-head">
            <div>
              <h2 id="gooey-eco-modal-title" className="gooey-eco-modal-title">
                Run Cost &amp; Environment Impact
              </h2>
              <div className="gooey-eco-modal-sub">
                {eco_cost.run_by && (
                  <span>
                    Run by <Author author={eco_cost.run_by} fallback="" />
                  </span>
                )}
                {eco_cost.run_by && eco_cost.charged_to && (
                  <span className="gooey-eco-dot" />
                )}
                {eco_cost.charged_to && (
                  // the balance is the charged workspace's, so it stays on
                  // this line, dot and all, even where the other dots hide;
                  // a long name is cut with an ellipsis instead
                  <span>
                    Charged to{" "}
                    <Author author={eco_cost.charged_to} fallback="" />
                    {eco_cost.balance && eco_cost.balance_url && (
                      <>
                        <span className="gooey-eco-dot" />
                        <a
                          href={eco_cost.balance_url}
                          target="_blank"
                          rel="noreferrer"
                          className="gooey-eco-balance"
                        >
                          Balance: {eco_cost.balance}{" "}
                          <i className="fa-regular fa-arrow-up-right" />
                        </a>
                      </>
                    )}
                  </span>
                )}
              </div>
            </div>
            <button
              type="button"
              className="btn-close"
              aria-label="Close"
              onClick={onClose}
            />
          </div>

          <div className="gooey-eco-modal-body">
            <div className="gooey-eco-headline">
              <div className="gooey-eco-stat">
                <div className="gooey-eco-stat-label">Total cost</div>
                <div className="gooey-eco-stat-value">
                  {eco_cost.run_cost_usd == null
                    ? eco_cost.run_cost
                    : formatUsd(eco_cost.run_cost_usd * runs)}
                </div>
                {eco_cost.models.map((m) => (
                  <div key={m.model_id} className="gooey-eco-stat-model">
                    <div className="gooey-eco-stat-model-name">{m.label}</div>
                    <div className="gooey-eco-stat-model-tokens">
                      {formatTokens(m.input_tokens * runs)} in ·{" "}
                      {formatTokens(m.output_tokens * runs)} out tokens
                    </div>
                  </div>
                ))}
              </div>
              <div className="gooey-eco-stat">
                <div className="gooey-eco-stat-label">Eco cost</div>
                <div className="gooey-eco-stat-value gooey-eco-green">
                  {formatGrams(g)}{" "}
                  <span className="gooey-eco-unit">
                    CO<sub>2</sub>e
                  </span>
                </div>
                <div className="gooey-eco-stat-range">
                  range {formatGrams(eco_cost.co2e_min * runs)} –{" "}
                  {formatGrams(eco_cost.co2e_max * runs)}
                </div>
              </div>
            </div>

            <div className="gooey-eco-slider">
              <label htmlFor="gooey-eco-runs">
                <span className="gooey-eco-slider-unit">
                  Conversation turns
                </span>
                <HelpTip
                  content={<ScaleTable runs={runs} />}
                  label="What the scale counts"
                />
              </label>
              <div className="gooey-eco-slider-track">
                <input
                  id="gooey-eco-runs"
                  type="range"
                  min={0}
                  max={RUN_STEPS.length - 1}
                  step={1}
                  value={stepIdx}
                  onChange={(e) => setStepIdx(Number(e.target.value))}
                  aria-valuetext={`${formatRuns(runs)} conversation turns`}
                  // the page form re-submits on any change that bubbles to it
                  data-submit-disabled=""
                  style={
                    {
                      "--pct": `${stepFraction(runs) * 100}%`,
                    } as React.CSSProperties
                  }
                />
                <div className="gooey-eco-slider-ticks" aria-hidden="true">
                  {RUN_TICKS.map((n) => (
                    <span
                      key={n}
                      // centred under the thumb, which is 18px wide
                      style={{
                        left: `calc(9px + ${stepFraction(n) * 100}% - ${stepFraction(n) * 18}px)`,
                      }}
                    >
                      {formatRuns(n)}
                    </span>
                  ))}
                </div>
              </div>
              {/* Sized to the widest count so the track never resizes mid-drag. */}
              <output
                htmlFor="gooey-eco-runs"
                className="gooey-eco-slider-value"
              >
                <span aria-hidden="true" className="gooey-eco-slider-sizer">
                  500k
                </span>
                <span>{formatRuns(runs)}</span>
              </output>
            </div>

            <h3 className="gooey-eco-h3">Environmental impact</h3>
            <div className="gooey-eco-tiles">
              <Tile
                icon="fa-solid fa-cloud"
                tone="ink"
                value={formatGrams(g)}
                unit={
                  <>
                    CO<sub>2</sub>e
                  </>
                }
                line1={carbonEquivalent(g)}
              />
              <Tile
                icon="fa-solid fa-droplet"
                tone="blue"
                value={`≈ ${water.value}`}
                unit={water.unit}
                line1="estimated water footprint"
                line2={`${formatMl(mlDataCenter)} cooling · ${formatMl(ml - mlDataCenter)} power plants`}
              />
              <Tile
                icon="fa-solid fa-bolt"
                tone="amber"
                value={energy.value}
                unit={energy.unit}
                line1={energy.caption}
                line2={`${formatWh(wh)} at the meter`}
              />
            </div>

            {eco_cost.region && <RegionBlock region={eco_cost.region} />}

            <div className="gooey-eco-foot">
              {/* ecocost's reason codes, most important first */}
              <Tip
                content={
                  <>
                    <div className="gooey-eco-reasons-title">
                      Why the range is wide
                    </div>
                    <ul className="gooey-eco-reasons">
                      {eco_cost.reasons.map((r) => (
                        <li key={r}>{REASON_TEXT[r] ?? r}</li>
                      ))}
                    </ul>
                  </>
                }
                disabled={!eco_cost.reasons.length}
              >
                <span
                  className={`gooey-eco-pill gooey-eco-pill-${eco_cost.confidence}`}
                  tabIndex={eco_cost.reasons.length ? 0 : undefined}
                >
                  <i className="fa-regular fa-circle-info" />
                  <span>{eco_cost.confidence} confidence</span>
                </span>
              </Tip>
              <a
                href={eco_cost.methodology_url}
                target="_blank"
                rel="noreferrer"
                className="gooey-eco-card-link"
              >
                How this is estimated{" "}
                <i className="fa-regular fa-arrow-up-right" />
              </a>
            </div>
          </div>
        </div>
      </div>
    </div>
  );

  if (typeof document === "undefined") return null;
  return ReactDOM.createPortal(modal, document.body);
}

const SWIPE_MS = 200;

/**
 * The sheet follows a finger pulling it down and closes past a quarter of its
 * height. A pull only starts with the sheet's content scrolled to the top, so
 * it never takes over scrolling back up.
 */
function useSwipeDownToClose(
  contentRef: React.RefObject<HTMLDivElement>,
  onClose: () => void
) {
  useEffect(() => {
    const content = contentRef.current;
    const sheet = content?.closest<HTMLElement>(".modal-dialog");
    const handle = content?.querySelector<HTMLElement>(
      ".gooey-eco-sheet-handle"
    );
    if (!content || !sheet || !handle) return;

    let startX = 0;
    let startY: number | null = null;
    let dy = 0;
    let closing = false;

    const onStart = (e: TouchEvent) => {
      // a touch during the slide down would pull the sheet back up
      if (closing) return;
      // only while the modal is a sheet, which is when its grab handle shows
      if (getComputedStyle(handle).display === "none") return;
      if (content.scrollTop > 0) return;
      // the runs slider is dragged sideways and must keep its touches
      if ((e.target as Element).closest("input[type=range]")) return;
      startX = e.touches[0].clientX;
      startY = e.touches[0].clientY;
      dy = 0;
    };
    const onMove = (e: TouchEvent) => {
      if (startY === null) return;
      const { clientX, clientY } = e.touches[0];
      // a gesture that starts sideways is not a pull
      if (!dy && Math.abs(clientX - startX) > Math.abs(clientY - startY)) {
        startY = null;
        return;
      }
      dy = Math.max(0, clientY - startY);
      if (!dy) {
        sheet.style.transform = "";
        return;
      }
      // the pull moves the sheet, not the content under the finger
      e.preventDefault();
      sheet.style.transition = "none";
      sheet.style.transform = `translateY(${dy}px)`;
    };
    const onEnd = (e: TouchEvent) => {
      if (startY === null) return;
      startY = null;
      const reduceMotion = window.matchMedia(
        "(prefers-reduced-motion: reduce)"
      ).matches;
      sheet.style.transition = reduceMotion
        ? "none"
        : `transform ${SWIPE_MS}ms ease-out`;
      // an interrupted touch is not a release, so it never closes the sheet
      if (e.type === "touchcancel" || dy < sheet.offsetHeight / 4) {
        sheet.style.transform = "";
        return;
      }
      closing = true;
      if (reduceMotion) {
        onClose();
        return;
      }
      sheet.style.transform = "translateY(100%)";
      window.setTimeout(onClose, SWIPE_MS);
    };

    content.addEventListener("touchstart", onStart);
    // not passive, so a pull can stop the content scrolling
    content.addEventListener("touchmove", onMove, { passive: false });
    content.addEventListener("touchend", onEnd);
    content.addEventListener("touchcancel", onEnd);
    return () => {
      content.removeEventListener("touchstart", onStart);
      content.removeEventListener("touchmove", onMove);
      content.removeEventListener("touchend", onEnd);
      content.removeEventListener("touchcancel", onEnd);
    };
  }, [contentRef, onClose]);
}

/** Where a count sits along the slider, 0..1. */
function stepFraction(n: number): number {
  return (
    RUN_STEPS.indexOf(n as (typeof RUN_STEPS)[number]) / (RUN_STEPS.length - 1)
  );
}

const DAYS_PER_MONTH = 30;
const MESSAGES_PER_USER_PER_MONTH = 8;

/** The slider's tooltip: the count read as a month of traffic, assuming each
 * user sends about 8 messages a month. Eco cost only shows on the Agent page
 * (the one layout-v2 recipe), where a run is one conversation turn. */
function ScaleTable({ runs }: { runs: number }) {
  const approx = (n: number) =>
    n < 1 ? "< 1" : `≈ ${Number(n.toPrecision(2)).toLocaleString("en-US")}`;
  const rows: [string, string][] = [
    ["Messages / month", runs.toLocaleString("en-US")],
    ["Daily messages", approx(runs / DAYS_PER_MONTH)],
    ["Users / month", approx(runs / MESSAGES_PER_USER_PER_MONTH)],
  ];
  return (
    <>
      <dl className="gooey-eco-help-table">
        {rows.map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
      <p className="gooey-eco-help-note">
        Assumes {MESSAGES_PER_USER_PER_MONTH} messages a month per user.
      </p>
    </>
  );
}

function RegionBlock({ region }: { region: EcoRegionProps }) {
  const flag = flagEmoji(region.country_code);
  const mix = Object.entries(region.mix);
  const color = (source: string) => MIX_COLORS[source] ?? MIX_COLORS.other;
  return (
    <>
      <h3 className="gooey-eco-h3">Region and grid mix</h3>
      <div className="gooey-eco-location">
        <div className="gooey-eco-place">
          <div className="gooey-eco-place-name">
            {flag && <span className="gooey-eco-flag">{flag}</span>}
            <span>{countryName(region.country_code)}</span>
            {region.assumption && (
              <HelpTip content={region.assumption} label="What's assumed" />
            )}
          </div>
          <div className="gooey-eco-place-note">
            {gridNote(region.gco2e_per_kwh, region.mix)}
          </div>
          <div className="gooey-eco-place-grid">
            {Math.round(region.gco2e_per_kwh)} gCO<sub>2</sub>e per kWh{" "}
            <span className="gooey-eco-muted">
              ({Math.round(region.gco2e_per_kwh_min)}–
              {Math.round(region.gco2e_per_kwh_max)})
            </span>
          </div>
        </div>
        <div className="gooey-eco-mix">
          <div className="gooey-eco-mix-title">Grid energy mix</div>
          <div className="gooey-eco-mix-bar" aria-hidden="true">
            {mix.map(([k, v]) => (
              <span
                key={k}
                style={{ width: `${v * 100}%`, background: color(k) }}
              />
            ))}
          </div>
          <ul className="gooey-eco-mix-list">
            {mix.map(([k, v]) => (
              <li key={k}>
                <span
                  className="gooey-eco-swatch"
                  style={{ background: color(k) }}
                />
                <span>{MIX_LABELS[k] ?? k}</span>
                <span className="gooey-eco-mix-pct">
                  {Math.round(v * 100)}%
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </>
  );
}

function Tile({
  icon,
  tone,
  value,
  unit,
  line1,
  line2,
}: {
  icon: string;
  tone: "ink" | "blue" | "amber";
  value: string;
  unit: React.ReactNode;
  line1: string;
  line2?: string;
}) {
  return (
    <div className="gooey-eco-tile">
      <i className={`${icon} gooey-eco-tile-icon gooey-eco-tone-${tone}`} />
      <div className="gooey-eco-tile-value">
        {value} <span className="gooey-eco-tile-unit">{unit}</span>
      </div>
      <div className="gooey-eco-tile-line1">{line1}</div>
      {line2 && <div className="gooey-eco-tile-line2">{line2}</div>}
    </div>
  );
}

/** An ⓘ that explains the thing beside it. */
function HelpTip({
  content,
  label,
}: {
  content: React.ReactNode;
  label: string;
}) {
  return (
    <Tip content={content}>
      <i
        role="button"
        tabIndex={0}
        aria-label={label}
        className="fa-regular fa-circle-info gooey-eco-help-icon"
      />
    </Tip>
  );
}

/** The modal's tooltip, on hover, focus or tap. The modal body scrolls, so an
 * in-place tooltip would be clipped; this one mounts under <body> like the
 * modal itself. */
function Tip({
  content,
  disabled,
  children,
}: {
  content: React.ReactNode;
  disabled?: boolean;
  children: React.ReactElement;
}) {
  return (
    <Tippy
      content={<div className="gooey-eco-help">{content}</div>}
      disabled={disabled}
      // a tap is a click; hiding on it would close the tip it just opened
      hideOnClick={false}
      placement="top"
      maxWidth={320}
      animation="scale"
      duration={80}
      appendTo={() => document.body}
    >
      {children}
    </Tippy>
  );
}
