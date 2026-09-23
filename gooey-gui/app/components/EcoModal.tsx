import "./EcoModal.css";

import type {
  EcoLabelProps,
  EcoRegionProps,
} from "@gooey-types/eco_label_props";
import { useEffect, useState } from "react";
import ReactDOM from "react-dom";
import Tippy from "@tippyjs/react";
import { Author } from "./RunDebugInfo";
import {
  MIX_COLORS,
  MIX_LABELS,
  REASON_LABELS,
  RUN_STEPS,
  RUN_TICKS,
  carbonEquivalent,
  energyEquivalent,
  flagEmoji,
  formatGrams,
  formatMl,
  formatRuns,
  formatUsd,
  formatWh,
  gridNote,
  waterEquivalent,
} from "./ecoScale";

/**
 * "Run Cost & Environment Impact": the per-run figures the server sent,
 * scaled client-side by a slider so the comparisons stay readable from one
 * run to a million. Mounted under <body> like the other overlays.
 */
export function EcoModal({
  eco,
  onClose,
}: {
  eco: EcoLabelProps;
  onClose: () => void;
}) {
  const [stepIdx, setStepIdx] = useState(0);
  const runs = RUN_STEPS[stepIdx];

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

  const g = eco.co2e_grams * runs;
  const ml = eco.water_ml * runs;
  const mlOnsite = eco.water_onsite_ml * runs;
  const wh = eco.energy_wh * runs;
  const water = waterEquivalent(ml);
  const energy = energyEquivalent(wh);
  const assumed = [...new Set(eco.reasons.map((r) => REASON_LABELS[r] ?? r))];

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
        <div className="modal-content gooey-eco-modal-content">
          <div className="gooey-eco-modal-head">
            <div>
              <h2 id="gooey-eco-modal-title" className="gooey-eco-modal-title">
                Run Cost &amp; Environment Impact
              </h2>
              <div className="gooey-eco-modal-sub">
                {eco.run_by && (
                  <span>
                    Run by <Author author={eco.run_by} fallback="" />
                  </span>
                )}
                {eco.run_by && eco.charged_to && (
                  <span className="gooey-eco-dot" />
                )}
                {eco.charged_to && (
                  <span>
                    Billed to <Author author={eco.charged_to} fallback="" />
                  </span>
                )}
                {eco.balance_url && (
                  <>
                    <span className="gooey-eco-dot" />
                    <a href={eco.balance_url} target="_blank" rel="noreferrer">
                      View balance{" "}
                      <i className="fa-regular fa-arrow-up-right" />
                    </a>
                  </>
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
                  {eco.run_cost_usd == null
                    ? eco.run_cost
                    : formatUsd(eco.run_cost_usd * runs)}
                </div>
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
                  range {formatGrams(eco.co2e_min * runs)} –{" "}
                  {formatGrams(eco.co2e_max * runs)}
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
                line2={`${formatMl(mlOnsite)} cooling · ${formatMl(ml - mlOnsite)} power plants`}
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

            {eco.region && <RegionBlock region={eco.region} />}

            <div className="gooey-eco-foot">
              <span
                className={`gooey-eco-pill gooey-eco-pill-${eco.confidence}`}
                title={
                  assumed.length ? `Assumed: ${assumed.join(", ")}` : undefined
                }
              >
                <i className="fa-regular fa-circle-info" />
                <span>{eco.confidence} confidence</span>
              </span>
              <a
                href={eco.methodology_url}
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

/** Where a count sits along the slider, 0..1. */
function stepFraction(n: number): number {
  return (
    RUN_STEPS.indexOf(n as (typeof RUN_STEPS)[number]) / (RUN_STEPS.length - 1)
  );
}

/** The slider's tooltip: the count read as a month of traffic, assuming 30
 * days and about 10 messages per active user. Eco cost only shows on the
 * Agent page (the one layout-v2 recipe), where a run is one conversation turn. */
function ScaleTable({ runs }: { runs: number }) {
  const approx = (n: number) =>
    n < 1 ? "< 1" : `≈ ${Number(n.toPrecision(2)).toLocaleString("en-US")}`;
  const rows: [string, string][] = [
    ["Messages", runs.toLocaleString("en-US")],
    ["Daily messages", approx(runs / 30)],
    ["Monthly active users", approx(Math.max(runs / 10, 1))],
  ];
  return (
    <dl className="gooey-eco-help-table">
      {rows.map(([k, v]) => (
        <div key={k}>
          <dt>{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
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
            <span>{region.label}</span>
            {region.assumption && (
              <HelpTip content={region.assumption} label="What's assumed" />
            )}
          </div>
          <div className="gooey-eco-place-note">
            {gridNote(region.gco2e_per_kwh)}
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
            {mix.slice(0, 5).map(([k, v]) => (
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

/** The modal body scrolls, so an in-place tooltip would be clipped; this one
 * mounts under <body> like the modal itself. */
function HelpTip({
  content,
  label,
}: {
  content: React.ReactNode;
  label: string;
}) {
  return (
    <Tippy
      content={<div className="gooey-eco-help">{content}</div>}
      placement="top"
      maxWidth={320}
      animation="scale"
      duration={80}
      delay={100}
      appendTo={() => document.body}
    >
      <i
        role="button"
        tabIndex={0}
        aria-label={label}
        className="fa-regular fa-circle-info gooey-eco-help-icon"
      />
    </Tippy>
  );
}
