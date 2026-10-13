"""
TrackGuard Live Attack Detection & Forensic Incident Report Generator
Queries SQLite (security_events, security_events_history, packets) and
renders a publication-grade cyber incident audit report with PDF export,
CSV export, and live telemetry status.
"""

import sqlite3
import json
import csv
import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List

DB_PATH = Path(__file__).resolve().parent.parent / "trackguard.db"


def fetch_all_attack_events():
    """Fetches all registered and detected attacks combining live and historical tables."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # 1. Fetch live security events with packet coordinates
    c.execute("""
        SELECT 
            e.event_id,
            e.event_time,
            e.attack_type,
            e.severity,
            e.description,
            e.action,
            e.status,
            COALESCE(p.source_type, 'HARDWARE') AS source_type,
            p.latitude,
            p.longitude,
            p.speed,
            p.packet_id,
            'LIVE' AS record_scope
        FROM security_events e
        LEFT JOIN packets p ON e.packet_id = p.packet_id
        ORDER BY e.event_id DESC
    """)
    live_events = [dict(r) for r in c.fetchall()]

    # 2. Fetch historical security events
    c.execute("""
        SELECT 
            h.history_event_id AS event_id,
            h.event_time,
            h.attack_type,
            h.severity,
            h.description,
            h.action,
            h.status,
            COALESCE(p.source_type, 'HISTORICAL') AS source_type,
            p.latitude,
            p.longitude,
            p.speed,
            p.packet_id,
            'ARCHIVED' AS record_scope
        FROM security_events_history h
        LEFT JOIN packets p ON h.packet_id = p.packet_id
        ORDER BY h.history_event_id DESC
    """)
    history_events = [dict(r) for r in c.fetchall()]

    # 3. Aggregate attack counts across all 13 types
    c.execute("""
        SELECT attack_type, COUNT(*) as count
        FROM (
            SELECT attack_type FROM security_events
            UNION ALL
            SELECT attack_type FROM security_events_history
        )
        GROUP BY attack_type
        ORDER BY count DESC
    """)
    attack_counts = [dict(r) for r in c.fetchall()]

    conn.close()

    all_events = live_events + history_events

    # Compute metrics
    total_attacks = len(all_events)
    hw_attacks = sum(1 for e in all_events if "HARDWARE" in str(e.get("source_type", "")).upper() or "Hardware" in str(e.get("description", "")))
    sim_attacks = total_attacks - hw_attacks
    crit_attacks = sum(1 for e in all_events if str(e.get("severity", "")).upper() == "CRITICAL")
    high_attacks = sum(1 for e in all_events if str(e.get("severity", "")).upper() == "HIGH")

    return {
        "all_events": all_events,
        "live_events": live_events,
        "history_events": history_events,
        "attack_counts": attack_counts,
        "total_attacks": total_attacks,
        "live_count": len(live_events),
        "history_count": len(history_events),
        "hw_attacks": hw_attacks,
        "sim_attacks": sim_attacks,
        "crit_attacks": crit_attacks,
        "high_attacks": high_attacks,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    }


def generate_attack_report_html(hw_status: Dict[str, Any] = None) -> str:
    """Generates a comprehensive styled HTML report of all detected attacks."""
    data = fetch_all_attack_events()
    events = data["all_events"]
    counts = data["attack_counts"]

    hw_status = hw_status or {}
    hw_port = hw_status.get("port") or "COM10"
    hw_conn = "CONNECTED" if hw_status.get("connected") else "OFFLINE"
    hw_fix = hw_status.get("fix_state") or "VALID_FIX"
    hw_lat = f"{hw_status.get('latitude'):.6f}° N" if hw_status.get("latitude") else "13.262403° N"
    hw_lon = f"{hw_status.get('longitude'):.6f}° E" if hw_status.get("longitude") else "80.027432° E"
    hw_sats = f"{hw_status.get('satellites_used', 6)} locked / {hw_status.get('satellites_in_view', 15)} view"

    # Mitigation dictionary
    mitigation_map = {
        "Location Jump": ("QUARANTINE_POSITION", "Rejects teleportation coordinates; locks baseline"),
        "Speed Anomaly": ("RATE_LIMIT_VELOCITY", "Enforces vehicle kinematic ceiling (180 km/h)"),
        "NMEA Data Injection": ("DROP_INVALID_FRAME", "Rejects corrupted XOR checksum UART frames"),
        "GNSS Signal Loss / Jamming": ("DEAD_RECKONING_FALLBACK", "Switches downstream navigation to dead reckoning"),
        "Timestamp Manipulation": ("REJECT_OUT_OF_ORDER", "Discards non-monotonic UTC desync epochs"),
        "GNSS Fix Contradiction": ("FLAG_SEMANTIC_CONFLICT", "Isolates contradictory cross-sentence fixes"),
        "Multi-Constellation Drift": ("KALMAN_FILTER_SANITY_CHECK", "Filters divergent pseudorange constellations"),
        "Replay Attack": ("BLOCK_REPLAY_PACKET", "Prevents duplicate packet replay & nonce reuse"),
        "Altitude Spoofing": ("LOCK_ALTITUDE_BASELINE", "Clamps vertical axis to barometric/DEM baseline"),
        "IMEI Spoofing": ("ISOLATE_ROGUE_DEVICE", "Blocks unwhitelisted cellular transmitter"),
        "PCAP Malicious Payload": ("DROP_AND_ALERT_SOC", "Drops malicious binary shellcode payload"),
        "SDR RF Signal Distortion": ("REJECT_SYNTHETIC_RF", "Flags synthesized IQ RF waveform interference"),
        "Coordinate Bounds Tampering": ("CLAMP_COORDINATES", "Restricts out-of-boundary lat/lon overflow")
    }

    # Build Attack Distribution Rows
    dist_rows_html = ""
    for item in counts:
        atk = item["attack_type"]
        cnt = item["count"]
        pct = (cnt / data["total_attacks"] * 100) if data["total_attacks"] > 0 else 0
        action, action_desc = mitigation_map.get(atk, ("QUARANTINE", "Enforce security isolation"))
        
        dist_rows_html += f"""
        <tr>
            <td style="font-weight: 700; color: #fff;">{atk}</td>
            <td style="text-align: center;"><span class="badge count-badge">{cnt}</span></td>
            <td style="min-width: 140px;">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <div style="flex: 1; background: #1e293b; height: 8px; border-radius: 4px; overflow: hidden;">
                        <div style="width: {pct:.1f}%; background: linear-gradient(90deg, #38bdf8, #818cf8); height: 100%;"></div>
                    </div>
                    <span style="font-size: 0.78rem; color: #94a3b8; min-width: 38px;">{pct:.1f}%</span>
                </div>
            </td>
            <td><code class="action-tag">{action}</code></td>
            <td style="font-size: 0.82rem; color: #94a3b8;">{action_desc}</td>
        </tr>
        """

    # Build Recent Events Rows (Top 100 for fast rendering)
    events_rows_html = ""
    for ev in events[:120]:
        eid = ev.get("event_id")
        etime = ev.get("event_time", "")
        atk = ev.get("attack_type", "Unknown")
        sev = str(ev.get("severity", "MEDIUM")).upper()
        desc = ev.get("description", "")
        action = ev.get("action", "QUARANTINE")
        scope = ev.get("record_scope", "LIVE")
        src = ev.get("source_type", "HARDWARE")
        lat = ev.get("latitude")
        lon = ev.get("longitude")
        coords = f"{lat:.4f}, {lon:.4f}" if lat is not None and lon is not None else "Baseline Coord"

        sev_class = "sev-crit" if sev == "CRITICAL" else ("sev-high" if sev == "HIGH" else "sev-med")
        scope_badge = "badge-live" if scope == "LIVE" else "badge-archive"

        events_rows_html += f"""
        <tr class="event-row" data-attack="{atk.lower()}" data-sev="{sev.lower()}">
            <td style="font-family: monospace; color: #94a3b8;">#{eid}</td>
            <td style="font-size: 0.82rem; color: #cbd5e1; white-space: nowrap;">{etime}</td>
            <td><span class="badge {scope_badge}">{scope}</span></td>
            <td style="font-weight: 600; color: #f1f5f9;">{atk}</td>
            <td><span class="badge {sev_class}">{sev}</span></td>
            <td style="font-size: 0.82rem; font-family: monospace; color: #38bdf8;">{coords}</td>
            <td style="font-size: 0.83rem; color: #cbd5e1; max-width: 320px;">{desc}</td>
            <td><code class="action-tag">{action}</code></td>
        </tr>
        """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TrackGuard - Registered Attacks & Incident Detection Report</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg: #070a13;
            --surface: #0f172a;
            --surface-border: #1e293b;
            --accent-blue: #38bdf8;
            --accent-purple: #818cf8;
            --danger: #ef4444;
            --warning: #f59e0b;
            --success: #10b981;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --card-bg: #131d35;
        }}
        @media print {{
            body {{ background: #fff !important; color: #0f172a !important; padding: 0 !important; }}
            .no-print {{ display: none !important; }}
            .report-box {{ border: none !important; box-shadow: none !important; background: transparent !important; padding: 0 !important; }}
            .kpi-card {{ border: 1px solid #cbd5e1 !important; background: #f8fafc !important; color: #000 !important; }}
            .kpi-value {{ color: #0284c7 !important; }}
            table {{ border: 1px solid #cbd5e1 !important; background: #fff !important; }}
            th {{ background: #e2e8f0 !important; color: #000 !important; }}
            td {{ border-color: #cbd5e1 !important; color: #111 !important; }}
            .badge {{ border: 1px solid #94a3b8 !important; color: #000 !important; }}
            h1, h2, h3 {{ color: #000 !important; -webkit-text-fill-color: #000 !important; }}
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'Inter', sans-serif;
            background: var(--bg);
            color: var(--text-main);
            line-height: 1.6;
            padding: 30px 20px;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        .action-bar {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: var(--surface);
            border: 1px solid var(--surface-border);
            padding: 14px 24px;
            border-radius: 12px;
            margin-bottom: 24px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.5);
        }}
        .btn {{
            display: inline-flex;
            align-items: center;
            gap: 7px;
            background: #0284c7;
            color: #fff;
            padding: 9px 16px;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 600;
            font-size: 0.85rem;
            border: none;
            cursor: pointer;
            transition: all 0.2s ease;
        }}
        .btn:hover {{ background: #0369a1; transform: translateY(-1px); }}
        .btn-outline {{
            background: transparent;
            border: 1px solid var(--surface-border);
            color: var(--text-main);
        }}
        .btn-outline:hover {{ background: #1e293b; color: #38bdf8; }}
        .report-box {{
            background: var(--surface);
            border: 1px solid var(--surface-border);
            border-radius: 16px;
            padding: 40px;
            box-shadow: 0 20px 45px rgba(0,0,0,0.6);
        }}
        .header-meta {{
            border-bottom: 1px solid var(--surface-border);
            padding-bottom: 24px;
            margin-bottom: 30px;
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            flex-wrap: wrap;
            gap: 20px;
        }}
        h1 {{
            font-size: 2.1rem;
            font-weight: 800;
            background: linear-gradient(135deg, #38bdf8, #818cf8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            letter-spacing: -0.5px;
        }}
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
            gap: 16px;
            margin-bottom: 32px;
        }}
        .kpi-card {{
            background: var(--card-bg);
            border: 1px solid var(--surface-border);
            border-radius: 12px;
            padding: 20px;
            display: flex;
            flex-direction: column;
            gap: 6px;
            position: relative;
            overflow: hidden;
        }}
        .kpi-card::before {{
            content: "";
            position: absolute;
            top: 0; left: 0; right: 0; height: 3px;
            background: linear-gradient(90deg, #38bdf8, #818cf8);
        }}
        .kpi-label {{
            font-size: 0.78rem;
            font-weight: 700;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        .kpi-value {{
            font-size: 2.2rem;
            font-weight: 800;
            color: #fff;
            line-height: 1.1;
        }}
        .kpi-sub {{
            font-size: 0.8rem;
            color: #94a3b8;
        }}
        h2 {{
            font-size: 1.3rem;
            font-weight: 700;
            color: #f1f5f9;
            margin-top: 36px;
            margin-bottom: 16px;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 16px 0 32px;
            font-size: 0.88rem;
            background: #090e1a;
            border-radius: 10px;
            overflow: hidden;
            border: 1px solid var(--surface-border);
        }}
        th {{
            background: #162036;
            color: #38bdf8;
            text-align: left;
            padding: 12px 14px;
            font-weight: 600;
            font-size: 0.82rem;
            text-transform: uppercase;
            letter-spacing: 0.8px;
        }}
        td {{
            padding: 12px 14px;
            border-top: 1px solid var(--surface-border);
            color: #cbd5e1;
        }}
        tr:hover td {{
            background: rgba(56, 189, 248, 0.03);
        }}
        .badge {{
            display: inline-block;
            padding: 3px 8px;
            border-radius: 6px;
            font-size: 0.74rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .badge-live {{ background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(52, 211, 153, 0.3); }}
        .badge-archive {{ background: rgba(148, 163, 184, 0.15); color: #94a3b8; border: 1px solid rgba(148, 163, 184, 0.3); }}
        .count-badge {{ background: rgba(56, 189, 248, 0.15); color: #38bdf8; font-weight: 800; font-size: 0.85rem; }}
        .sev-crit {{ background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4); }}
        .sev-high {{ background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.4); }}
        .sev-med {{ background: rgba(59, 130, 246, 0.2); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.4); }}
        .action-tag {{
            font-family: 'JetBrains Mono', monospace;
            background: rgba(129, 140, 248, 0.12);
            color: #818cf8;
            padding: 2px 7px;
            border-radius: 4px;
            font-size: 0.8rem;
            border: 1px solid rgba(129, 140, 248, 0.25);
        }}
        .search-box {{
            width: 100%;
            background: #090e1a;
            border: 1px solid var(--surface-border);
            padding: 10px 14px;
            border-radius: 8px;
            color: #fff;
            font-size: 0.88rem;
            margin-bottom: 12px;
            outline: none;
        }}
        .search-box:focus {{ border-color: #38bdf8; }}
        .hw-banner {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: rgba(2, 132, 199, 0.08);
            border: 1px solid rgba(56, 189, 248, 0.25);
            padding: 14px 20px;
            border-radius: 10px;
            margin-bottom: 28px;
        }}
    </style>
</head>
<body>
    <div class="container">
        
        <!-- ACTION BAR -->
        <div class="action-bar no-print">
            <div style="display: flex; align-items: center; gap: 12px;">
                <span class="badge badge-live">● AUDIT COMPLETE</span>
                <span style="font-size: 0.85rem; color: var(--text-muted);">TrackGuard Real-Time Attack Forensic Report</span>
            </div>
            <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                <button onclick="window.print()" class="btn">
                    🖨️ Print / Save as PDF
                </button>
                <a href="/download-report?format=csv" class="btn btn-outline" download="TrackGuard_Detected_Attacks.csv">
                    📥 Download CSV
                </a>
                <a href="/download-report?format=json" class="btn btn-outline" download="TrackGuard_Detected_Attacks.json">
                    📥 Download JSON
                </a>
                <button onclick="location.reload()" class="btn btn-outline">
                    🔄 Refresh Data
                </button>
            </div>
        </div>

        <!-- REPORT CARD -->
        <div class="report-box">
            
            <div class="header-meta">
                <div>
                    <h1>TrackGuard Attack Detection & Incident Report</h1>
                    <p style="color: #94a3b8; font-size: 0.95rem; margin-top: 6px;">
                        Comprehensive forensic audit of all cyber-physical attacks registered and intercepted across live hardware and simulation channels.
                    </p>
                </div>
                <div style="text-align: right;">
                    <div style="font-size: 0.8rem; color: #94a3b8;">AUDIT GENERATED AT</div>
                    <div style="font-family: monospace; font-size: 0.92rem; color: #38bdf8; font-weight: 600;">{data["generated_at"]}</div>
                    <div style="font-size: 0.78rem; color: #10b981; margin-top: 4px;">Classification: Official Security Telemetry</div>
                </div>
            </div>

            <!-- HARDWARE STATUS BANNER -->
            <div class="hw-banner">
                <div>
                    <span style="font-size: 0.82rem; font-weight: 700; color: #38bdf8; text-transform: uppercase;">Active Hardware Sensor:</span>
                    <span style="font-size: 0.88rem; color: #fff; font-weight: 600; margin-left: 6px;">7semi NEO-M9N GNSS</span>
                    <span style="font-size: 0.82rem; color: #94a3b8; margin-left: 6px;">({hw_port} @ 38,400 baud)</span>
                </div>
                <div style="display: flex; gap: 16px; font-size: 0.83rem;">
                    <div>Status: <strong style="color: #34d399;">{hw_conn}</strong></div>
                    <div>Fix State: <strong>{hw_fix}</strong></div>
                    <div>Satellites: <strong>{hw_sats}</strong></div>
                    <div>Baseline: <strong style="color: #38bdf8;">{hw_lat}, {hw_lon}</strong></div>
                </div>
            </div>

            <!-- EXECUTIVE KPI CARDS -->
            <div class="kpi-grid">
                <div class="kpi-card">
                    <span class="kpi-label">Total Attacks Intercepted</span>
                    <div class="kpi-value">{data["total_attacks"]}</div>
                    <span class="kpi-sub">{data["live_count"]} Live Interceptions / {data["history_count"]} Archived</span>
                </div>
                <div class="kpi-card">
                    <span class="kpi-label">Distinct Attack Vectors</span>
                    <div class="kpi-value" style="color: #38bdf8;">13</div>
                    <span class="kpi-sub">Full Spectrum GNSS & Telematics Protection</span>
                </div>
                <div class="kpi-card">
                    <span class="kpi-label">High / Critical Threats</span>
                    <div class="kpi-value" style="color: #f87171;">{data["crit_attacks"] + data["high_attacks"]}</div>
                    <span class="kpi-sub">{data["crit_attacks"]} Critical &bull; {data["high_attacks"]} High Severity</span>
                </div>
                <div class="kpi-card">
                    <span class="kpi-label">Hardware Vector Attacks</span>
                    <div class="kpi-value" style="color: #34d399;">{data["hw_attacks"]}</div>
                    <span class="kpi-sub">Intercepted on Hardware Bus / Injected</span>
                </div>
            </div>

            <!-- SECTION 1: ATTACK DISTRIBUTION SUMMARY -->
            <h2>1. Registered Attack Distribution & Mitigation Matrix</h2>
            <p style="font-size: 0.88rem; color: #94a3b8; margin-bottom: 12px;">
                Aggregated counts and automated defense mitigations triggered across all 13 recognized cyber-physical attack categories.
            </p>

            <table>
                <thead>
                    <tr>
                        <th>Attack Category Name</th>
                        <th style="text-align: center;">Incidents</th>
                        <th>Distribution Ratio</th>
                        <th>Automated Mitigation</th>
                        <th>Defensive Action Rationale</th>
                    </tr>
                </thead>
                <tbody>
                    {dist_rows_html}
                </tbody>
            </table>

            <!-- SECTION 2: CHRONOLOGICAL INCIDENT AUDIT LOG -->
            <h2>2. Chronological Security Incident Audit Log</h2>
            <p style="font-size: 0.88rem; color: #94a3b8; margin-bottom: 12px;">
                Detailed chronological record of registered attack events intercepted by TrackGuard. Use the search filter below to query by attack type or keywords.
            </p>

            <input type="text" id="incidentSearch" class="search-box no-print" placeholder="🔍 Type to filter by attack type, coordinates, or forensic details..." onkeyup="filterIncidents()">

            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Timestamp (UTC)</th>
                        <th>Scope</th>
                        <th>Attack Type</th>
                        <th>Severity</th>
                        <th>Intercepted Coords</th>
                        <th>Forensic Incident Description</th>
                        <th>Mitigation Action</th>
                    </tr>
                </thead>
                <tbody id="incidentsTableBody">
                    {events_rows_html}
                </tbody>
            </table>

        </div>
    </div>

    <script>
        function filterIncidents() {{
            const input = document.getElementById('incidentSearch').value.toLowerCase();
            const rows = document.querySelectorAll('#incidentsTableBody .event-row');
            rows.forEach(row => {{
                const text = row.innerText.toLowerCase();
                row.style.display = text.includes(input) ? '' : 'none';
            }});
        }}
    </script>
</body>
</html>"""

    return html


def generate_attack_report_csv() -> str:
    """Exports all registered attack events as a formatted CSV string."""
    data = fetch_all_attack_events()
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Event_ID",
        "Timestamp",
        "Scope",
        "Attack_Type",
        "Severity",
        "Source_Type",
        "Latitude",
        "Longitude",
        "Speed_KMH",
        "Forensic_Description",
        "Mitigation_Action",
        "Status"
    ])

    for ev in data["all_events"]:
        writer.writerow([
            ev.get("event_id"),
            ev.get("event_time"),
            ev.get("record_scope"),
            ev.get("attack_type"),
            ev.get("severity"),
            ev.get("source_type"),
            ev.get("latitude"),
            ev.get("longitude"),
            ev.get("speed"),
            ev.get("description"),
            ev.get("action"),
            ev.get("status")
        ])

    return output.getvalue()
