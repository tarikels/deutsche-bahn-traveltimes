/**
 * Client-side logic for the interactive accessibility map UI.
 *
 * This file manages map initialization, tile and layer rendering, user
 * interactions, API requests, choropleth styling, tooltip content, legend
 * updates, and ranking table updates for the FastAPI + Leaflet frontend.
 */

const state = {
  period: "2026W09",
  day_type: "weekday",
  hour: 8,
  zone_id: null,
  metric: "travel_time",
  selectedLayer: null,
  zonesById: new Map(),
  zoneNamesById: new Map(),
};

let lastValues = {};
let lastMode = "od";
let lastDestStations = {};
let lastOriginStation = null;
let lastOriginStations = {};
let currentAbort = null;

const weekEl = document.getElementById("week");
const hourEl = document.getElementById("hour");
const hourLabelEl = document.getElementById("hourLabel");
const zoneEl = document.getElementById("zone");
const dayTypeTabs = document.querySelectorAll(".daytype-tab");
const metricRadios = document.querySelectorAll('input[name="metric"]');

function selectedStyle() {
  return { weight: 3, color: "#184e77", fillColor: "#2b8cbe", fillOpacity: 0.38 };
}

function defaultStyle() {
  return { weight: 1, color: "#4b5563", fillColor: "#bfdbfe", fillOpacity: 0.28 };
}

function highlightZone(zoneId) {
  if (state.selectedLayer && state.selectedLayer.length) {
    state.selectedLayer.forEach((l) => l.setStyle(styleForZone(String(state.zone_id || ""))));
    state.selectedLayer = null;
  }

  if (!zoneId) return;

  const layers = state.zonesById.get(String(zoneId));
  if (layers && layers.length) {
    layers.forEach((l) => l.setStyle(selectedStyle()));
    state.selectedLayer = layers;
  }
}

function setZone(zoneId) {
  state.zone_id = zoneId || null;
  lastMode = state.zone_id ? "od" : "origin_avg";
  zoneEl.value = state.zone_id || "";
  highlightZone(state.zone_id);
}

const map = L.map("map", {
  zoomAnimation: false,
  fadeAnimation: false,
  markerZoomAnimation: false
}).setView([51.1657, 10.4515], 6);

const legendControl = L.control({ position: "bottomright" });

legendControl.onAdd = function () {
  this._div = L.DomUtil.create("div", "legendControlHost");
  this._div.innerHTML = buildLegendHtml();
  return this._div;
};

legendControl.addTo(map);

function updateLegend() {
  if (legendControl && legendControl._div) {
    legendControl._div.innerHTML = buildLegendHtml();
  }
}

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap contributors",
  detectRetina: false,
  keepBuffer: 4,
  updateWhenZooming: false,
  updateWhenIdle: true
}).addTo(map);

async function buildWeekOptions() {
  const r = await fetch("/api/periods");
  const payload = await r.json();
  const periods = payload.periods || [];

  if (periods.length > 0) {
    state.period = periods[0];
    if (weekEl) weekEl.value = state.period;
  }
}

async function loadZoneIndex() {
  const r = await fetch("/api/zones/index");
  const zones = await r.json();

  for (const z of zones) {
    state.zoneNamesById.set(String(z.zone_id), z.zone_name);
    const opt = document.createElement("option");
    opt.value = z.zone_id;
    opt.textContent = `${z.zone_name} — ${z.zone_id}`;
    zoneEl.appendChild(opt);
  }
}

function colorForMinutesAvg(minutes) {
  if (minutes == null || !isFinite(minutes)) return "#e5e7eb";
  if (minutes <= 180) return "#1a9850";
  if (minutes <= 240) return "#66bd63";
  if (minutes <= 300) return "#a6d96a";
  if (minutes <= 360) return "#fee08b";
  if (minutes <= 420) return "#fdae61";
  if (minutes <= 480) return "#f46d43";
  return "#d73027";
}

function colorForTransfersAvg(x) {
  if (x == null || !isFinite(x)) return "#e5e7eb";
  if (x <= 1.2) return "#1a9850";
  if (x <= 1.6) return "#66bd63";
  if (x <= 2.0) return "#a6d96a";
  if (x <= 2.4) return "#fee08b";
  if (x <= 2.8) return "#fdae61";
  return "#d73027";
}

function legendItemsForCurrentMetric() {
  if (state.metric === "travel_time" || state.metric === "car_travel_time") {
    if (lastMode === "origin_avg") {
      return {
        title: state.metric === "travel_time" ? "Ø Reisezeit Zug (min)" : "Ø Reisezeit Auto (min)",
        items: [
          ["#1a9850", "≤ 180"],
          ["#66bd63", "181–240"],
          ["#a6d96a", "241–300"],
          ["#fee08b", "301–360"],
          ["#fdae61", "361–420"],
          ["#f46d43", "421–480"],
          ["#d73027", "> 480"],
          ["#e5e7eb", "Keine Daten"],
        ],
      };
    }

    return {
      title: state.metric === "travel_time" ? "Reisezeit Zug (min)" : "Reisezeit Auto (min)",
      items: [
        ["#1a9850", "≤ 90"],
        ["#66bd63", "91–150"],
        ["#a6d96a", "151–210"],
        ["#fee08b", "211–270"],
        ["#fdae61", "271–330"],
        ["#f46d43", "331–390"],
        ["#d73027", "> 390"],
        ["#e5e7eb", "Keine Daten"],
      ],
    };
  }

  if (state.metric === "transfers") {
    if (lastMode === "origin_avg") {
      return {
        title: "Ø Umstiege Zug",
        items: [
          ["#1a9850", "≤ 1.0"],
          ["#66bd63", "≤ 1.5"],
          ["#a6d96a", "≤ 2.0"],
          ["#fee08b", "≤ 2.5"],
          ["#fdae61", "≤ 3.0"],
          ["#f46d43", "≤ 3.5"],
          ["#d73027", "> 3.5"],
          ["#e5e7eb", "Keine Daten"],
        ],
      };
    }

    return {
      title: "Umstiege Zug",
      items: [
        ["#1a9850", "0"],
        ["#66bd63", "1"],
        ["#a6d96a", "2"],
        ["#fee08b", "3"],
        ["#fdae61", "4"],
        ["#d73027", "≥ 5"],
        ["#e5e7eb", "Keine Daten"],
      ],
    };
  }

  return {
    title: "ÖPNV/MIV Verhältnis",
    items: [
      ["#1a9850", "≤ 1.00x"],
      ["#66bd63", "≤ 1.25x"],
      ["#a6d96a", "≤ 1.50x"],
      ["#fee08b", "≤ 2.00x"],
      ["#fdae61", "≤ 3.00x"],
      ["#f46d43", "≤ 4.00x"],
      ["#d73027", "> 4.00x"],
      ["#e5e7eb", "Keine Daten"],
    ],
  };
}

function buildLegendHtml() {
  const cfg = legendItemsForCurrentMetric();
  const rows = cfg.items.map(([color, label]) => `
    <div class="legend-item">
      <span class="legend-swatch" style="background:${color};"></span>
      <span>${label}</span>
    </div>
  `).join("");

  return `
    <div class="legend">
      <div class="legend-title">${cfg.title}</div>
      ${rows}
    </div>
  `;
}

function formatDuration(seconds) {
  if (seconds == null || !isFinite(seconds)) return "Keine Daten vorhanden";

  const totalSeconds = Math.max(0, Math.round(seconds));
  const mins = Math.floor(totalSeconds / 60);
  const hrs = Math.floor(mins / 60);
  const remMins = mins % 60;

  if (hrs <= 0) return `${mins} min`;
  if (remMins === 0) return `${hrs} h`;
  return `${hrs} h ${remMins} min`;
}

function formatMetricValue(v) {
  if (v == null || !isFinite(v)) return "—";

  if (state.metric === "travel_time" || state.metric === "car_travel_time") {
    return formatDuration(v);
  }

  if (state.metric === "pt_car_ratio") {
    return `${Number(v).toFixed(2)}x`;
  }

  if (state.metric === "transfers" && lastMode === "origin_avg") {
    return Number(v).toFixed(1);
  }

  return String(v);
}

function buildRankingTable(rows) {
  if (!rows.length) {
    return `<div class="ranking-empty">Keine Daten vorhanden</div>`;
  }

  const body = rows.map((r, i) => `
      <tr>
        <td>${i + 1}.</td>
        <td>${r.zone_name}</td>
        <td>${formatMetricValue(r.value)}</td>
      </tr>
    `).join("");

  return `
      <table class="ranking-table">
        <tbody>
          ${body}
        </tbody>
      </table>
    `;
}

function colorForMinutes(minutes) {
  if (minutes == null || !isFinite(minutes)) return "#e5e7eb";
  if (minutes <= 90) return "#1a9850";
  if (minutes <= 150) return "#66bd63";
  if (minutes <= 210) return "#a6d96a";
  if (minutes <= 270) return "#fee08b";
  if (minutes <= 330) return "#fdae61";
  if (minutes <= 390) return "#f46d43";
  return "#d73027";
}

function colorForTransfers(x) {
  if (x == null || !isFinite(x)) return "#e5e7eb";
  if (x === 0) return "#1a9850";
  if (x === 1) return "#66bd63";
  if (x === 2) return "#a6d96a";
  if (x === 3) return "#fee08b";
  if (x === 4) return "#fdae61";
  return "#d73027";
}

function colorForRatio(x) {
  if (x == null || !isFinite(x)) return "#e5e7eb";
  if (x <= 1.0) return "#1a9850";
  if (x <= 1.25) return "#66bd63";
  if (x <= 1.5) return "#a6d96a";
  if (x <= 2.0) return "#fee08b";
  if (x <= 3.0) return "#fdae61";
  if (x <= 4.0) return "#f46d43";
  return "#d73027";
}

function styleForZone(zid) {
  const style = defaultStyle();

  if (!zid) return style;

  const v = lastValues ? lastValues[zid] : null;

  if (state.metric === "travel_time" || state.metric === "car_travel_time") {
    const minutes = v == null ? null : v / 60.0;
    style.fillColor = lastMode === "origin_avg"
      ? colorForMinutesAvg(minutes)
      : colorForMinutes(minutes);
  } else if (state.metric === "pt_car_ratio") {
    style.fillColor = lastMode === "origin_avg"
      ? colorForRatio(v)
      : colorForRatio(v);
  } else {
    style.fillColor = lastMode === "origin_avg"
      ? colorForTransfersAvg(v)
      : colorForTransfers(v);
  }

  style.fillOpacity = 0.55;
  return style;
}

function applyChoropleth(valuesByZoneId, destStationsByZoneId, originStation) {
  lastValues = valuesByZoneId || {};
  lastDestStations = destStationsByZoneId || {};
  lastOriginStation = originStation || null;

  for (const [zid, layers] of state.zonesById.entries()) {
    layers.forEach((l) => l.setStyle(styleForZone(zid)));
  }
  highlightZone(state.zone_id);
}

async function loadMetricAndRender() {
  if (currentAbort) currentAbort.abort();
  currentAbort = new AbortController();

  const url = new URL("/api/od/metric", window.location.origin);
  url.searchParams.set("period", state.period);
  url.searchParams.set("day_type", state.day_type);
  url.searchParams.set("hour", String(state.hour));
  url.searchParams.set("metric", state.metric);

  if (state.zone_id) {
    url.searchParams.set("origin_zone_id", state.zone_id);
  }

  const r = await fetch(url.toString(), { signal: currentAbort.signal });
  if (!r.ok) return;

  const payload = await r.json();
  lastMode = payload.mode || "od";

  if (lastMode === "od") {
    lastOriginStations = {};
  } else {
    lastOriginStations = payload.origin_stations || {};
  }

  applyChoropleth(
    payload.values || {},
    payload.dest_stations || {},
    payload.origin_station || null
  );
  updateRankings(payload.values || {});
  updateLegend();
}

function updateRankings(valuesByZoneId) {
  const topEl = document.getElementById("top3Table");
  const worstEl = document.getElementById("worst3Table");

  if (!topEl || !worstEl) return;

  const entries = Object.entries(valuesByZoneId || {})
    .filter(([zid, v]) => v != null && isFinite(v))
    .filter(([zid]) => !state.zone_id || String(zid) !== String(state.zone_id))
    .map(([zid, v]) => ({
      zone_id: String(zid),
      zone_name: state.zoneNamesById.get(String(zid)) || String(zid),
      value: Number(v),
    }));

  if (!entries.length) {
    topEl.innerHTML = `<div class="ranking-empty">Keine Daten vorhanden</div>`;
    worstEl.innerHTML = `<div class="ranking-empty">Keine Daten vorhanden</div>`;
    return;
  }

  const sortedAsc = [...entries].sort((a, b) => a.value - b.value);
  const sortedDesc = [...entries].sort((a, b) => b.value - a.value);

  const top3 = sortedAsc.slice(0, 3);
  const worst3 = sortedDesc.slice(0, 3);

  topEl.innerHTML = buildRankingTable(top3);
  worstEl.innerHTML = buildRankingTable(worst3);
}

async function loadZonesGeoJSON() {
  state.zonesById.clear();
  state.selectedLayer = null;
  const r = await fetch("/api/zones/geojson");
  const gj = await r.json();

  const layer = L.geoJSON(gj, {
    style: defaultStyle,
    onEachFeature: function (feature, lyr) {
      const zid = feature?.properties?.zone_id;
      const zname = feature?.properties?.zone_name || "";

      if (!zid) return;

      const zidStr = String(zid);
      const arr = state.zonesById.get(zidStr) || [];
      arr.push(lyr);
      state.zonesById.set(zidStr, arr);

      lyr.on("click", async () => {
        if (String(state.zone_id || "") === zidStr) {
          setZone(null);
          if (zoneEl) zoneEl.value = "";
        } else {
          setZone(zidStr);
          if (zoneEl) zoneEl.value = zidStr;
        }
        await loadMetricAndRender();
      });

      lyr.on("mouseover", (e) => {
        lyr.setStyle({ weight: 2 });

        if (!state.zone_id) {
          const v = lastValues ? lastValues[zidStr] : null;
          const title = zname ? `${zname} — ${zidStr}` : `${zidStr}`;
          const os = lastOriginStations ? lastOriginStations[zidStr] : null;
          const originStopTxt = os ? (os.stop_name || "—") : "—";

          let metricLabel = "";
          let metricValue = "";

          if (state.metric === "travel_time") {
            metricLabel = "Ø Reisezeit mit dem Zug zu allen Zonen";
            metricValue = formatDuration(v);
          } else if (state.metric === "car_travel_time") {
            metricLabel = "Ø Reisezeit mit dem Auto zu allen Zonen";
            metricValue = formatDuration(v);
          } else if (state.metric === "pt_car_ratio") {
            metricLabel = "Ø ÖPNV/MIV Reisezeitverhältnis zu allen Zonen";
            metricValue = (v == null || !isFinite(v)) ? "Keine Fahrten zu dieser Stunde" : `${Number(v).toFixed(2)}x`;
          } else {
            metricLabel = "Ø Umstiege mit dem Zug zu allen Zonen";
            metricValue = (v == null || !isFinite(v)) ? "Keine Fahrten zu dieser Stunde" : Number(v).toFixed(1);
          }

          const html = `<div style="font-size:14px; line-height:1.2;">
            <div style="font-weight:600; margin-bottom:4px;">${title}</div>
            <div>Zonen-Starthaltestelle: <b>${originStopTxt}</b></div>
            <div>${metricLabel}: <b>${metricValue}</b></div>
          </div>`;

          lyr
            .bindTooltip(html, {
              sticky: true,
              direction: "auto",
              opacity: 0.95,
              className: "tt-tooltip",
            })
            .openTooltip(e.latlng);

          return;
        }

        const v = lastValues ? lastValues[zidStr] : null;
        const isOrigin = String(state.zone_id) === zidStr;
        const title = zname ? `${zname} — ${zidStr}` : `${zidStr}`;

        let metricLabel = "";
        let metricValue = "";

        if (state.metric === "travel_time") {
          metricLabel = "Reisezeit Zug";
          metricValue = isOrigin ? "0 min" : formatDuration(v);
        } else if (state.metric === "car_travel_time") {
          metricLabel = "Reisezeit Auto";
          metricValue = isOrigin ? "0 min" : formatDuration(v);
        } else if (state.metric === "pt_car_ratio") {
          metricLabel = "ÖPNV/MIV Reisezeitverhältnis";
          metricValue = isOrigin ? "—" : ((v == null || !isFinite(v)) ? "Keine Fahrten zu dieser Stunde" : `${Number(v).toFixed(2)}x`);
        } else {
          metricLabel = "Umstiege";
          metricValue = (v == null || !isFinite(v)) ? "Keine Fahrten zu dieser Stunde" : String(v);
        }

        const originTxt = lastOriginStation
          ? `${lastOriginStation.stop_name}`
          : "—";

        const ds = lastDestStations ? lastDestStations[zidStr] : null;
        const destTxt = ds ? `${ds.stop_name}` : "—";

        const html = `<div style="font-size:14px; line-height:1.2;">
          <div style="font-weight:600; margin-bottom:4px;">${title}</div>
          <div>Start-Station: <b>${originTxt}</b></div>
          <div>Ziel-Station: <b>${destTxt}</b></div>
          <div>${metricLabel}: <b>${metricValue}</b></div>
        </div>`;

        lyr
          .bindTooltip(html, {
            sticky: true,
            direction: "auto",
            opacity: 0.95,
            className: "tt-tooltip",
          })
          .openTooltip(e.latlng);
      });

      lyr.on("mouseout", () => {
        lyr.closeTooltip();
        if (state.selectedLayer && state.selectedLayer.includes(lyr)) return;
        lyr.setStyle(styleForZone(zidStr));
      });
    },
  }).addTo(map);

  try {
    map.fitBounds(layer.getBounds(), { padding: [10, 10] });
  } catch (_) {}
}

if (weekEl) {
  weekEl.addEventListener("change", () => {
    state.period = weekEl.value;
    loadMetricAndRender();
  });
}

dayTypeTabs.forEach((btn) => {
  btn.addEventListener("click", () => {
    dayTypeTabs.forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    state.day_type = btn.dataset.value;
    loadMetricAndRender();
  });
});

metricRadios.forEach((r) => {
  r.addEventListener("change", () => {
    if (r.checked) state.metric = r.value;
    loadMetricAndRender();
  });
});

hourEl.addEventListener("input", () => {
  state.hour = parseInt(hourEl.value, 10);
  hourLabelEl.textContent = String(state.hour);
  loadMetricAndRender();
});

zoneEl.addEventListener("change", () => {
  setZone(zoneEl.value ? String(zoneEl.value) : null);
  loadMetricAndRender();
});

(async function boot() {
  hourLabelEl.textContent = String(state.hour);
  await buildWeekOptions();
  await loadZoneIndex();
  await loadZonesGeoJSON();
  await loadMetricAndRender();
})();