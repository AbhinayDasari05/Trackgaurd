<script>
"use strict";

/* ═══════════════════════════════════════════════════════════════
   SIDEBAR / TAB NAVIGATION
═══════════════════════════════════════════════════════════════ */
const TAB_TITLES = {
    overview: "System Overview",
    gnss:     "Live GNSS Monitor",
    packets:  "Live Telemetry Stream",
    events:   "Security Events",
    history:  "Forensic Archive",
    devices:  "Registered Devices",
    lab:      "Attack Simulation Lab",
    pcap:     "PCAP / Wireshark",
    sdr:      "SDR Forensics"
};

function showTab(id, btn) {
    document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
    document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));
    const panel = document.getElementById("tab-" + id);
    if (panel) panel.classList.add("active");
    if (btn)  btn.classList.add("active");
    document.getElementById("topbarTitle").textContent = TAB_TITLES[id] || id;

    // init map if switching to gnss tab
    if (id === "gnss" && !map) {
        initMap(13.0827, 80.2707);
    }
}

function toggleSidebar() {
    document.getElementById("sidebar").classList.toggle("open");
}

/* ═══════════════════════════════════════════════════════════════
   TOAST NOTIFICATIONS
═══════════════════════════════════════════════════════════════ */
function showToast(type, title, msg, durationMs = 4000) {
    const icons = { success: "fa-circle-check", error: "fa-circle-xmark", warn: "fa-triangle-exclamation", info: "fa-circle-info" };
    const colors = { success: "var(--accent-green)", error: "var(--accent-red)", warn: "var(--accent-yellow)", info: "var(--accent-blue)" };
    const toast = document.createElement("div");
    toast.className = "toast " + type;
    toast.innerHTML = `
        <i class="fa ${icons[type] || icons.info} toast-icon" style="color:${colors[type]}"></i>
        <div class="toast-content">
            <div class="toast-title">${title}</div>
            ${msg ? `<div class="toast-msg">${msg}</div>` : ""}
        </div>
        <span class="toast-close" onclick="this.parentElement.remove()"><i class="fa fa-xmark"></i></span>`;
    document.getElementById("toast-container").appendChild(toast);
    setTimeout(() => toast.remove(), durationMs);
}

/* ═══════════════════════════════════════════════════════════════
   MAP SETUP
═══════════════════════════════════════════════════════════════ */
let map = null;
let hwMarker = null;
let simMarker = null;
let trackPolyline = null;
let trackPoints = [];
const TRACK_MAX = 50;

const hwIcon = L.divIcon({
    className: "",
    html: `<div style="width:14px;height:14px;border-radius:50%;background:#22c55e;border:3px solid white;box-shadow:0 0 0 3px rgba(34,197,94,0.3);"></div>`,
    iconAnchor: [7,7]
});
const simIcon = L.divIcon({
    className: "",
    html: `<div style="width:14px;height:14px;border-radius:50%;background:#ef4444;border:3px solid white;box-shadow:0 0 0 3px rgba(239,68,68,0.3);"></div>`,
    iconAnchor: [7,7]
});

function initMap(lat, lon) {
    if (map) return;
    map = L.map("gnssMap", { zoomControl: true }).setView([lat || 13.0827, lon || 80.2707], 13);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: "© <a href='https://openstreetmap.org'>OpenStreetMap</a> contributors"
    }).addTo(map);
    trackPolyline = L.polyline([], { color: "#14b8a6", weight: 3, opacity: 0.7 }).addTo(map);
    if (lat && lon) updateMapHW(lat, lon);
}

function updateMapHW(lat, lon) {
    if (!map) return;
    if (!hwMarker) {
        hwMarker = L.marker([lat, lon], { icon: hwIcon }).addTo(map);
    } else {
        hwMarker.setLatLng([lat, lon]);
    }
    // add to trail
    trackPoints.push([lat, lon]);
    if (trackPoints.length > TRACK_MAX) trackPoints.shift();
    trackPolyline.setLatLngs(trackPoints);
}

function centerMapOnHW() {
    if (lastHWLat != null && lastHWLon != null) {
        flyToCoordinate(lastHWLat, lastHWLon, "7semi NEO-M9N Hardware Fix", 0, "NORMAL");
    } else {
        showToast("info", "Hardware Coordinate", "Waiting for physical GNSS fix to lock coordinates.");
    }
}

let lastHWLat = null;
let lastHWLon = null;
let inspectionMarker = null;

function flyToCoordinate(lat, lon, label, isSim = 0, status = "NORMAL") {
    // Switch to Overview tab if not already on it
    const overviewBtn = document.querySelector(".nav-item:first-of-type");
    showTab("overview", overviewBtn);

    if (!map) {
        initMap(lat, lon);
    }
    if (!map) return;

    setTimeout(() => {
        map.invalidateSize();
        map.flyTo([lat, lon], 12, { duration: 1.2 });

        if (isSim) {
            if (simMarker) {
                simMarker.setLatLng([lat, lon]);
            } else {
                simMarker = L.marker([lat, lon], { icon: simIcon }).addTo(map);
            }
            simMarker.bindPopup(`
                <div style="font-family:sans-serif; font-size:12px; color:#111;">
                    <b style="color:#ef4444;">🚨 [SIMULATION / FALSE COORDINATE]</b><br>
                    <b>Label:</b> ${label}<br>
                    <b>Coordinates:</b> ${Number(lat).toFixed(5)}°, ${Number(lon).toFixed(5)}°<br>
                    <b>Validation:</b> <span style="color:#ef4444; font-weight:700;">${status}</span>
                </div>
            `).openPopup();
        } else {
            if (inspectionMarker) {
                inspectionMarker.setLatLng([lat, lon]);
            } else {
                inspectionMarker = L.marker([lat, lon], { icon: hwIcon }).addTo(map);
            }
            inspectionMarker.bindPopup(`
                <div style="font-family:sans-serif; font-size:12px; color:#111;">
                    <b style="color:#22c55e;">📡 [TELEMETRY PACKET]</b><br>
                    <b>Label:</b> ${label}<br>
                    <b>Coordinates:</b> ${Number(lat).toFixed(5)}°, ${Number(lon).toFixed(5)}°<br>
                    <b>Validation:</b> <span style="color:#22c55e; font-weight:700;">${status}</span>
                </div>
            `).openPopup();
        }
    }, 150);
}

/* ═══════════════════════════════════════════════════════════════
   SPARKLINE / CHART SETUP
═══════════════════════════════════════════════════════════════ */
let sparkChart = null;
let speedChart = null;
let sparkData  = Array(10).fill(0);
let speedData  = Array(20).fill(0);
let speedLabels= Array(20).fill("");

function initCharts() {
    // Packet sparkline
    const sc = document.getElementById("spark-packets");
    if (sc) {
        sparkChart = new Chart(sc, {
            type: "line",
            data: { labels: sparkData.map((_,i) => i), datasets: [{
                data: sparkData, borderColor: "#3b82f6",
                borderWidth: 2, pointRadius: 0, fill: true,
                backgroundColor: "rgba(59,130,246,0.08)"
            }]},
            options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
                scales: { x: { display: false }, y: { display: false } },
                animation: { duration: 300 } }
        });
    }
    // Speed history chart
    const spd = document.getElementById("speedChart");
    if (spd) {
        speedChart = new Chart(spd, {
            type: "line",
            data: { labels: speedLabels, datasets: [{
                label: "Speed km/h",
                data: speedData, borderColor: "#14b8a6",
                borderWidth: 2, pointRadius: 2, fill: true,
                backgroundColor: "rgba(20,184,166,0.08)",
                tension: 0.4
            }]},
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { display: false },
                    y: { display: true, ticks: { color: "#4a5d80", font: { size: 10 } },
                         grid: { color: "rgba(31,46,80,0.5)" } }
                },
                animation: { duration: 300 }
            }
        });
    }
}

function pushSparkValue(v) {
    sparkData.push(v);
    if (sparkData.length > 10) sparkData.shift();
    if (sparkChart) {
        sparkChart.data.datasets[0].data = sparkData;
        sparkChart.update("none");
    }
}

function pushSpeedValue(v, label) {
    speedData.push(v);
    speedLabels.push(label || "");
    if (speedData.length > 20)  { speedData.shift();  }
    if (speedLabels.length > 20){ speedLabels.shift(); }
    if (speedChart) {
        speedChart.data.labels = speedLabels;
        speedChart.data.datasets[0].data = speedData;
        speedChart.update("none");
    }
}

/* ═══════════════════════════════════════════════════════════════
   POLLING LOOP — /api/live-data (every 2s)
═══════════════════════════════════════════════════════════════ */
async function updateDashboard() {
    try {
        const resp = await fetch("/api/live-data", { cache: "no-store" });
        if (!resp.ok) return;
        const data = await resp.json();

        // ── Stats cards ──
        const tp = data.total_packets || 0;
        document.getElementById("totalPackets").textContent = tp;
        document.getElementById("normalPackets").textContent = data.normal_packets || 0;
        document.getElementById("anomalyPackets").textContent = data.anomaly_packets || 0;
        document.getElementById("totalEvents").textContent   = data.total_events || 0;
        document.getElementById("historyTotalPackets").textContent = data.history_total_packets || 0;
        document.getElementById("historyTotalEvents").textContent  = data.history_total_events || 0;
        pushSparkValue(tp);

        // ── Nav event badge ──
        const evBadge = document.getElementById("navEventsBadge");
        evBadge.textContent = data.total_events || 0;
        evBadge.style.display = (data.total_events > 0) ? "inline-flex" : "none";

        // ── GNSS hardware status ──
        const hw = data.gnss_status || {};
        document.getElementById("cardFixState").textContent = hw.fix_state || "DISCONNECTED";
        document.getElementById("cardSats").textContent = (hw.satellites_used || 0) + " / " + (hw.satellites_in_view || 0);

        // HW badge in topbar - live if connected, or if fix is valid, or if data is recent (<10s)
        const isLive = hw.connected || hw.fix_valid || (hw.data_age_seconds != null && hw.data_age_seconds < 10);
        const hwBadge = document.getElementById("hwStatusBadge");
        const hwText  = document.getElementById("hwBadgeText");
        if (isLive) {
            hwBadge.className = "hw-badge live";
            hwText.textContent = "GNSS LIVE — " + (hw.port || "CONNECTED");
        } else {
            hwBadge.className = "hw-badge disconnected";
            hwText.textContent = "GNSS HARDWARE DISCONNECTED";
        }

        // Nav fix badge
        const nfb = document.getElementById("navFixBadge");
        const effectiveFixState = hw.fix_state || (hw.fix_valid ? "VALID_FIX" : "DISCONNECTED");
        nfb.textContent = effectiveFixState.replace("_", " ");
        nfb.className = "nav-badge " + (effectiveFixState === "VALID_FIX" ? "green" : (effectiveFixState === "STALE_FIX" ? "orange" : ""));

        // Fix state pill helper
        function applyFixPill(el) {
            if (!el) return;
            el.textContent = effectiveFixState;
            el.className = "fix-pill " + (effectiveFixState === "VALID_FIX" ? "fix-valid" : effectiveFixState === "STALE_FIX" ? "fix-stale" : "fix-none");
        }
        applyFixPill(document.getElementById("fixStatePill"));
        applyFixPill(document.getElementById("fixStatePill2"));

        // Port / source
        const portEl = document.getElementById("gnssPortLabel");
        if (portEl) portEl.textContent = hw.port || "Auto-detect";
        const srcEl = document.getElementById("gnssSourceLabel");
        if (srcEl) srcEl.textContent = hw.source || "–";

        // GNSS metric tiles — sync all instances
        function setText(id, val) {
            [id, id+"2"].forEach(eid => {
                const el = document.getElementById(eid);
                if (el && val !== undefined) el.textContent = val;
            });
        }
        if (hw.latitude  != null) setText("gnssLat",  hw.latitude.toFixed(6));
        if (hw.longitude != null) setText("gnssLon",  hw.longitude.toFixed(6));
        if (hw.speed_kmh != null) {
            setText("gnssSpeed", hw.speed_kmh + " km/h");
            pushSpeedValue(hw.speed_kmh, new Date().toLocaleTimeString());
        }
        if (hw.altitude_m != null) setText("gnssAlt",  hw.altitude_m + " m");
        if (hw.hdop != null)       setText("gnssHdop", hw.hdop);
        setText("gnssSatsDetail", (hw.satellites_used || 0) + " / " + (hw.satellites_in_view || 0));
        setText("gnssAge",        hw.data_age_seconds != null ? hw.data_age_seconds + "s" : "--");

        const fqMap = { 0: "No Fix", 1: "GPS SPS", 2: "DGPS" };
        const fqText = fqMap[hw.fix_quality] || ("Q=" + hw.fix_quality);
        setText("gnssQuality", fqText);

        // Map update
        if (hw.latitude != null && hw.longitude != null) {
            lastHWLat = hw.latitude;
            lastHWLon = hw.longitude;
            if (!map) {
                initMap(hw.latitude, hw.longitude);
            }
            if (map) updateMapHW(hw.latitude, hw.longitude);
        }

        // ── Packets table ──
        const packetTable = document.getElementById("packetTable");
        if (data.packets && data.packets.length > 0) {
            packetTable.innerHTML = data.packets.slice(0, 15).map(p => {
                const isSimBadge = p.is_simulation
                    ? '<span class="badge badge-sim">SIMULATED</span>'
                    : '<span class="badge badge-hw">HARDWARE</span>';
                const valBadge = p.validation_status === "ANOMALY_DETECTED"
                    ? '<span class="badge badge-high"><i class="fa fa-triangle-exclamation"></i> ANOMALY</span>'
                    : '<span class="badge badge-normal"><i class="fa fa-check"></i> NORMAL</span>';
                    const hasCoords = p.latitude != null && p.longitude != null;
                    const actionCell = hasCoords 
                        ? `<td><button class="btn btn-ghost btn-sm" onclick="flyToCoordinate(${p.latitude}, ${p.longitude}, 'Packet #${p.packet_id} (${p.imei || p.device_id || "Dev"})', ${p.is_simulation ? 1 : 0}, '${p.validation_status || "NORMAL"}')" title="Open coordinates on Overview map"><i class="fa fa-map-pin" style="color:${p.is_simulation ? 'var(--accent-red)' : 'var(--accent-teal)'};"></i> View</button></td>`
                        : `<td>–</td>`;
                    return `<tr class="${rowClass}">
                        <td><strong>#${p.packet_id}</strong></td>
                        <td><code>${p.imei || p.device_id || "–"}</code></td>
                        <td>${isSimBadge}</td>
                        <td>${p.protocol || "–"}</td>
                        <td>${p.latitude != null ? p.latitude.toFixed(5) : "–"}</td>
                        <td>${p.longitude != null ? p.longitude.toFixed(5) : "–"}</td>
                        <td>${p.speed != null ? Number(p.speed).toFixed(1) + " km/h" : "–"}</td>
                        <td>${p.satellites_used || "–"}</td>
                        <td>${valBadge}</td>
                        <td style="color:var(--text-muted)">${p.received_at || "–"}</td>
                        ${actionCell}
                    </tr>`;
            }).join("");
        }

        // ── Events table ──
        const eventTable = document.getElementById("eventTable");
        if (data.events && data.events.length > 0) {
            eventTable.innerHTML = data.events.slice(0, 15).map(e => {
                const sev = e.severity;
                const sevClass = sev === "HIGH" ? "badge-high" : (sev === "MEDIUM" ? "badge-medium" : "badge-low");
                const rowClass = sev === "HIGH" ? "row-anomaly" : "";
                return `<tr class="${rowClass}">
                    <td><strong>#${e.event_id}</strong></td>
                    <td>${e.packet_id || "–"}</td>
                    <td><code>${e.imei}</code></td>
                    <td style="color:var(--accent-red);font-weight:600">${e.attack_type}</td>
                    <td><span class="badge ${sevClass}">${sev}</span></td>
                    <td style="max-width:250px;white-space:normal;color:var(--text-muted)">${e.description}</td>
                    <td><span class="badge badge-gray">${e.action}</span></td>
                    <td>${e.status}</td>
                    <td style="color:var(--text-muted)">${e.event_time}</td>
                </tr>`;
            }).join("");
        }

    } catch (err) {
        console.warn("Polling error:", err);
    }
}

/* ═══════════════════════════════════════════════════════════════
   ATTACK LAB
═══════════════════════════════════════════════════════════════ */
async function runSingleScenario(id, forceRandom = false) {
    const btn = document.querySelector(`#labCard-${id} button`);
    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fa fa-spinner fa-spin"></i> Running…'; }
    const resultEl = document.getElementById("labResult-" + id);

    let payload = {};
    if (id === "1") {
        const select = document.getElementById("spoofLocationSelect");
        if (select && select.value !== "RANDOM" && !forceRandom) {
            try {
                payload.target_location = JSON.parse(select.value);
            } catch(e) {}
        }
    }

    try {
        const resp = await fetch("/api/simulation/run/" + id, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const res = await resp.json();
        if (res.status === "success") {
            const r = res.result;
            const isPass = r.pass_fail === "PASS";
            const locName = r.location_name || (r.evidence && r.evidence.location_name) || "";
            
            if (resultEl) {
                resultEl.innerHTML = `<span class="badge ${isPass ? 'badge-pass' : 'badge-fail'}">${r.pass_fail}</span>
                    <span style="color:var(--text-muted);font-size:10px;">${locName ? '📍 ' + locName : (r.observed || "")}</span>`;
            }

            // Plot spoofed coordinate on Leaflet map if available
            const coords = r.target_coordinates || (r.evidence && r.evidence.injected_coordinates) || (r.evidence && r.evidence.jump_position ? {lat: r.evidence.jump_position[0], lon: r.evidence.jump_position[1]} : null);
            if (coords && typeof coords.lat === "number" && typeof coords.lon === "number") {
                plotSpoofedLocationOnMap(coords.lat, coords.lon, locName || "Spoofed Position", r.evidence && r.evidence.haversine_distance_km);
            }

            const toastTitle = `Scenario ${id}: ${r.pass_fail}${locName ? ' → ' + locName : ''}`;
            const toastMsg = r.description || `${r.observed || ''}${r.severity ? ' — Severity: ' + r.severity : ''}`;
            showToast(isPass ? "success" : "error", toastTitle, toastMsg, 5000);
            
            refreshSimulationTable();
            updateDashboard();
        } else {
            if (resultEl) resultEl.innerHTML = '<span class="badge badge-high">ERROR</span>';
            showToast("error", "Simulation Error", res.message || "Unknown error");
        }
    } catch (e) {
        showToast("error", "Scenario Failed", String(e));
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fa fa-play"></i> Run'; }
    }
}

function plotSpoofedLocationOnMap(lat, lon, label, distanceKm) {
    if (!map) initMap(13.0827, 80.2707);
    if (!map) return;
    
    if (simMarker) {
        simMarker.setLatLng([lat, lon]);
    } else {
        simMarker = L.marker([lat, lon], { icon: simIcon }).addTo(map);
    }
    
    const distText = distanceKm ? `<br><b>Displacement:</b> ${Math.round(distanceKm)} km from Chennai` : '';
    simMarker.bindPopup(`
        <div style="font-family:sans-serif; font-size:12px; color:#111;">
            <b style="color:#ef4444;">🚨 [SIMULATION] GNSS Spoofed Position</b><br>
            <b>Target:</b> ${label}<br>
            <b>Coordinates:</b> ${lat.toFixed(4)}°, ${lon.toFixed(4)}°
            ${distText}
        </div>
    `).openPopup();
    
    // Zoom or pan to show spoofed point
    map.setView([lat, lon], Math.min(map.getZoom(), 8));
}

async function runAllSimulationScenarios() {
    const progressWrap = document.getElementById("labProgressWrap");
    const fill  = document.getElementById("labProgressFill");
    const label = document.getElementById("labProgressLabel");
    progressWrap.classList.add("visible");
    fill.style.width = "0%";
    label.textContent = "Running all 12 scenarios…";

    // Run sequentially to animate progress
    for (let i = 1; i <= 12; i++) {
        const pct = Math.round((i - 1) / 12 * 100);
        fill.style.width = pct + "%";
        label.textContent = `Running scenario ${i} of 12…`;
        try {
            await fetch("/api/simulation/run/" + i, { method: "POST" });
        } catch(e) { /* continue */ }
    }
    fill.style.width = "100%";
    label.textContent = "All 12 scenarios complete!";
    setTimeout(() => progressWrap.classList.remove("visible"), 3000);
    showToast("success", "Lab Complete", "All 12 scenarios executed through the live detection engine.");
    refreshSimulationTable();
    updateDashboard();
}

async function refreshSimulationTable() {
    try {
        const resp = await fetch("/api/simulation/runs");
        const runs = await resp.json();
        const tbody = document.getElementById("simTableBody");
        if (!runs || runs.length === 0) return;
        tbody.innerHTML = runs.map(r => {
            const sevClass  = r.severity === "HIGH" ? "badge-high" : (r.severity === "MEDIUM" ? "badge-medium" : "badge-low");
            const passClass = r.pass_fail === "PASS" ? "badge-pass" : "badge-fail";
            const rowClass  = r.pass_fail === "FAIL" ? "row-anomaly" : "";

            // Also update inline lab card results
            const labRes = document.getElementById("labResult-" + r.scenario_id);
            if (labRes) {
                labRes.innerHTML = `<span class="badge ${passClass}">${r.pass_fail}</span>`;
            }

            return `<tr class="${rowClass}">
                <td><strong>#${r.run_id}</strong></td>
                <td><span class="badge badge-gray">${r.scenario_id}</span></td>
                <td style="font-weight:600;color:var(--text-primary)">${r.scenario_name}</td>
                <td style="color:var(--text-muted);max-width:180px;white-space:normal">${r.expected_detection}</td>
                <td style="color:var(--text-muted);max-width:180px;white-space:normal">${r.observed_detection}</td>
                <td><span class="badge ${sevClass}">${r.severity}</span></td>
                <td><span class="badge badge-gray">${r.mitigation_action}</span></td>
                <td><span class="badge ${passClass}">${r.pass_fail}</span></td>
                <td style="color:var(--text-muted)">${r.executed_at}</td>
            </tr>`;
        }).join("");
    } catch (err) {
        console.error("Failed to refresh simulation table:", err);
    }
}

async function clearSimulationResults() {
    await fetch("/api/simulation/clear", { method: "POST" });
    // Reset all lab cards
    for (let i = 1; i <= 12; i++) {
        const el = document.getElementById("labResult-" + i);
        if (el) el.innerHTML = '<span class="badge badge-gray">NOT RUN</span>';
    }
    refreshSimulationTable();
    showToast("info", "Lab Cleared", "All simulation log entries have been cleared.");
}

/* ═══════════════════════════════════════════════════════════════
   GNSS SERIAL PORT CONFIG
═══════════════════════════════════════════════════════════════ */
async function reconfigureSerialPort() {
    const port = document.getElementById("serialPortInput").value.trim();
    if (!port) return;
    try {
        const resp = await fetch("/api/gnss/config", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ port: port, baud: 38400 })
        });
        const res = await resp.json();
        showToast("success", "Port Reconfigured", "Now listening on " + (res.port || port));
        updateDashboard();
    } catch (e) {
        showToast("error", "Port Config Failed", String(e));
    }
}

/* ═══════════════════════════════════════════════════════════════
   SESSION CONTROLS
═══════════════════════════════════════════════════════════════ */
async function clearRecentPackets() {
    if (!confirm("Archive active live session to History and reset live packet counters?")) return;
    await fetch("/clear", { method: "POST" });
    document.getElementById("clearBanner").style.display = "block";
    setTimeout(() => { document.getElementById("clearBanner").style.display = "none"; }, 5000);
    showToast("success", "Session Cleared", "Live packets archived to forensic history.");
    updateDashboard();
}

async function clearAllHistory() {
    if (!confirm("Permanently wipe ALL historical archives? This cannot be undone.")) return;
    await fetch("/clear-history", { method: "POST" });
    showToast("warn", "History Wiped", "All forensic archives permanently deleted.");
    updateDashboard();
}

/* ═══════════════════════════════════════════════════════════════
   INITIALISE
═══════════════════════════════════════════════════════════════ */
window.addEventListener("DOMContentLoaded", () => {
    // Immediately initialize tactical map on Overview page
    initMap(13.0827, 80.2707);
    initCharts();
    // Load initial simulation results into lab cards
    refreshSimulationTable();
    // Start polling
    setInterval(updateDashboard, 2000);
    updateDashboard();
});
</script>

</body>
</html>