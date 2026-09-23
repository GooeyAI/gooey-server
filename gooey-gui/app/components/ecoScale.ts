/**
 * Formats one run's eco figures, scaled to N runs, and picks the comparison
 * that reads best at that size. Pure functions so the modal stays a thin view.
 *
 * Comparison constants and where they come from:
 *  - tree 0.060 tCO2 per year (urban tree, first 10 years, survival-weighted)
 *    and petrol car 393 gCO2e per mile (244 per km): EPA Greenhouse Gas
 *    Equivalencies,
 *    https://www.epa.gov/energy/greenhouse-gas-equivalencies-calculator-calculations-and-references
 *  - 10 W LED bulb (a typical 60 W-equivalent)
 *  - EU household electricity 3,600 kWh/yr (Eurostat)
 *  - glass of water 250 mL; bathtub 150 L; Olympic pool 2,500,000 L
 */

/** 1-5-10 steps per decade, so the slider moves in halves rather than tens. */
export const RUN_STEPS = [
  1, 5, 10, 50, 100, 500, 1_000, 5_000, 10_000, 50_000, 100_000, 500_000,
  1_000_000,
] as const;
/** Only the decades get a tick label; the 5s sit between them. */
export const RUN_TICKS = RUN_STEPS.filter((n) => Math.log10(n) % 1 === 0);

const YEAR_S = 365.25 * 24 * 3600;
const TREE_G_PER_S = 60_000 / YEAR_S;
const CAR_G_PER_KM = 244;
const LED_W = 10;
const HOME_W = 3_600_000 / (YEAR_S / 3600);
const GLASS_ML = 250;
const BATHTUB_ML = 150_000;
const POOL_ML = 2_500_000_000;

export type Amount = { value: string; unit: string };

export function formatRuns(n: number): string {
  if (n >= 1_000_000) return `${n / 1_000_000}M`;
  if (n >= 1_000) return `${n / 1_000}k`;
  return String(n);
}

export function formatUsd(usd: number): string {
  if (usd >= 1000)
    return `$${usd.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
  if (usd >= 1) return `$${usd.toFixed(2)}`;
  return `$${usd.toFixed(3)}`;
}

export function formatGrams(g: number): string {
  if (g >= 1_000_000) return `${sig(g / 1_000_000)} t`;
  if (g >= 1000) return `${sig(g / 1000, 3)} kg`;
  if (g >= 1) return `${sig(g)} g`;
  const mg = g * 1000;
  return mg >= 0.1 ? `${sig(mg)} mg` : "<0.1 mg";
}

export function formatWh(wh: number): string {
  if (wh >= 1_000_000) return `${sig(wh / 1_000_000, 3)} MWh`;
  if (wh >= 1000) return `${sig(wh / 1000, 3)} kWh`;
  if (wh >= 1) return `${sig(wh)} Wh`;
  return `${sig(wh * 1000)} mWh`;
}

export function formatMl(ml: number): string {
  if (ml >= 1_000_000) return `${sig(ml / 1_000_000, 3)} m³`;
  if (ml >= 1000) return `${sig(ml / 1000, 3)} L`;
  return `${sig(ml)} mL`;
}

function duration(s: number): Amount {
  if (s >= YEAR_S) return { value: sig(s / YEAR_S), unit: "yr" };
  if (s >= 86400) return { value: sig(s / 86400), unit: "days" };
  if (s >= 3600) return { value: sig(s / 3600), unit: "h" };
  if (s >= 60) return { value: sig(s / 60), unit: "min" };
  return { value: sig(s), unit: "s" };
}

/** Carbon as the time one tree takes to absorb it, then as driving once it
 * passes a kilogram, where tree-time stops being easy to picture. */
export function carbonEquivalent(g: number): string {
  if (g >= 1000) return `≈ driving a petrol car ${sig(g / CAR_G_PER_KM)} km`;
  const t = duration(Math.max(g / TREE_G_PER_S, 1));
  return `≈ ${t.value} ${t.unit} of a tree's CO₂ uptake`;
}

/** Energy as time an average EU home runs on it, or an LED bulb when that's
 * under a minute. */
export function energyEquivalent(wh: number): Amount & { caption: string } {
  const homeS = (wh / HOME_W) * 3600;
  return homeS >= 60
    ? { ...duration(homeS), caption: "of an EU home's electricity" }
    : { ...duration((wh / LED_W) * 3600), caption: "of a 10 W LED bulb" };
}

/** Water as glasses, bathtubs or pools. */
export function waterEquivalent(ml: number): Amount {
  if (ml >= POOL_ML / 2)
    return { value: sig(ml / POOL_ML), unit: "Olympic pools" };
  if (ml >= BATHTUB_ML / 2)
    return { value: sig(ml / BATHTUB_ML), unit: "bathtubs" };
  const glasses = ml / GLASS_ML;
  if (glasses >= 0.5)
    return { value: sig(glasses), unit: glasses < 1.5 ? "glass" : "glasses" };
  return { value: sig(ml), unit: "mL" };
}

/** Flag emoji from an ISO 3166-1 alpha-2 code; empty for anything else. */
export function flagEmoji(cc: string): string {
  if (!/^[A-Za-z]{2}$/.test(cc)) return "";
  return String.fromCodePoint(
    ...[...cc.toUpperCase()].map((c) => 0x1f1e6 + c.charCodeAt(0) - 65)
  );
}

export function gridNote(gPerKwh: number): string {
  if (gPerKwh < 100)
    return "Very low-carbon grid: mostly hydro, nuclear or geothermal.";
  if (gPerKwh < 300) return "Relatively low-carbon grid.";
  if (gPerKwh < 500) return "Average grid intensity, gas-heavy.";
  return "High-carbon grid, coal-heavy.";
}

export const MIX_LABELS: Record<string, string> = {
  nuclear: "Nuclear",
  hydro: "Hydro",
  wind: "Wind",
  solar: "Solar",
  geothermal: "Geothermal",
  biomass: "Biomass",
  gas: "Natural gas",
  coal: "Coal",
  oil: "Oil",
  other: "Other",
};

export const MIX_COLORS: Record<string, string> = {
  nuclear: "#7c6cf0",
  hydro: "#3b8fe0",
  wind: "#39b98a",
  solar: "#f2c14e",
  geothermal: "#d97a3a",
  biomass: "#8ab04a",
  gas: "#e8a838",
  coal: "#6b6b6b",
  oil: "#9a8f80",
  other: "#c4c4c4",
};

/** Short nouns for the confidence tooltip: "Assumed: serving site, PUE". */
export const REASON_LABELS: Record<string, string> = {
  provider_unknown_fallback: "provider",
  provider_inferred_from_model: "provider",
  region_inferred: "serving site",
  hardware_assumed: "chip type",
  active_params_undisclosed: "model size",
  active_params_estimated: "model size",
  pue_assumed: "PUE",
  wue_assumed: "cooling water",
  utilization_assumed: "GPU utilization",
  serving_overhead_assumed: "server overhead",
  grid_intensity_national_average: "grid average",
  embodied_carbon_default: "hardware lifetime",
};

/** Two significant figures, plain digits, thousands separators above 999. */
function sig(x: number, digits = 2): string {
  if (!isFinite(x) || x === 0) return "0";
  const rounded = Number(x.toPrecision(digits));
  return rounded >= 1000
    ? rounded.toLocaleString("en-US", { maximumFractionDigits: 0 })
    : String(rounded);
}
