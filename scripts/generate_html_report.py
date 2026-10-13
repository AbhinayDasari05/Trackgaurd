import markdown
from pathlib import Path

# Source Markdown Path
md_path = Path("C:/Users/rahul/.gemini/antigravity/brain/c7e19a15-1c26-4bbb-bf91-068635ff84f6/TrackGuard_Comprehensive_Project_Report.md")
md_content = md_path.read_text(encoding="utf-8")

# Convert markdown to html with extra extensions
html_body = markdown.markdown(md_content, extensions=["extra", "codehilite", "tables", "toc"])

html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TrackGuard - Comprehensive Project Engineering & Security Report</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <script>mermaid.initialize({{startOnLoad: true, theme: 'dark'}});</script>
    <style>
        :root {{
            --bg: #0b0f19;
            --surface: #131b2e;
            --surface-border: #1e293b;
            --accent: #38bdf8;
            --accent-glow: rgba(56, 189, 248, 0.15);
            --danger: #ef4444;
            --success: #10b981;
            --text-main: #f1f5f9;
            --text-muted: #94a3b8;
            --code-bg: #070a13;
        }}
        @media print {{
            body {{ background: #fff !important; color: #111 !important; }}
            .no-print {{ display: none !important; }}
            .report-card {{ border: none !important; box-shadow: none !important; background: transparent !important; padding: 0 !important; }}
            pre, code {{ background: #f1f5f9 !important; color: #0f172a !important; border: 1px solid #cbd5e1 !important; }}
            table th {{ background: #e2e8f0 !important; color: #000 !important; }}
            table td {{ border-color: #cbd5e1 !important; color: #111 !important; }}
            h1, h2, h3, h4 {{ color: #000 !important; -webkit-text-fill-color: #000 !important; }}
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'Inter', -apple-system, sans-serif;
            background-color: var(--bg);
            color: var(--text-main);
            line-height: 1.65;
            padding: 40px 20px;
        }}
        .container {{
            max-width: 1040px;
            margin: 0 auto;
        }}
        .action-bar {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: var(--surface);
            border: 1px solid var(--surface-border);
            padding: 16px 24px;
            border-radius: 12px;
            margin-bottom: 30px;
            box-shadow: 0 8px 24px rgba(0,0,0,0.3);
        }}
        .badge {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: rgba(16, 185, 129, 0.15);
            color: #34d399;
            padding: 6px 14px;
            border-radius: 999px;
            font-size: 0.82rem;
            font-weight: 600;
            border: 1px solid rgba(52, 211, 153, 0.3);
        }}
        .pulse {{
            width: 8px;
            height: 8px;
            background: #10b981;
            border-radius: 50%;
            box-shadow: 0 0 10px #10b981;
            animation: pulse-dot 1.8s infinite;
        }}
        @keyframes pulse-dot {{
            0% {{ transform: scale(0.9); opacity: 0.7; }}
            50% {{ transform: scale(1.3); opacity: 1; }}
            100% {{ transform: scale(0.9); opacity: 0.7; }}
        }}
        .btn {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: #0284c7;
            color: #fff;
            padding: 10px 18px;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 600;
            font-size: 0.88rem;
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
        .btn-outline:hover {{ background: #1e293b; }}
        .report-card {{
            background: var(--surface);
            border: 1px solid var(--surface-border);
            border-radius: 16px;
            padding: 48px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.4);
        }}
        h1 {{
            font-size: 2.2rem;
            font-weight: 800;
            color: #fff;
            margin-bottom: 12px;
            background: linear-gradient(135deg, #38bdf8, #818cf8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        h2 {{
            font-size: 1.45rem;
            font-weight: 700;
            color: #e2e8f0;
            margin-top: 36px;
            margin-bottom: 16px;
            padding-bottom: 8px;
            border-bottom: 1px solid var(--surface-border);
        }}
        h3 {{
            font-size: 1.15rem;
            font-weight: 600;
            color: #38bdf8;
            margin-top: 24px;
            margin-bottom: 12px;
        }}
        h4 {{
            font-size: 1.0rem;
            font-weight: 600;
            color: #94a3b8;
            margin-top: 18px;
            margin-bottom: 8px;
        }}
        p {{ margin-bottom: 16px; color: #cbd5e1; }}
        ul, ol {{ margin-bottom: 16px; padding-left: 24px; color: #cbd5e1; }}
        li {{ margin-bottom: 6px; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 24px 0;
            font-size: 0.9rem;
            background: var(--code-bg);
            border-radius: 10px;
            overflow: hidden;
            border: 1px solid var(--surface-border);
        }}
        th {{
            background: #1e293b;
            color: #38bdf8;
            text-align: left;
            padding: 12px 16px;
            font-weight: 600;
        }}
        td {{
            padding: 12px 16px;
            border-top: 1px solid var(--surface-border);
            color: #cbd5e1;
        }}
        tr:hover td {{ background: rgba(56, 189, 248, 0.04); }}
        pre {{
            background: var(--code-bg);
            border: 1px solid var(--surface-border);
            border-radius: 10px;
            padding: 16px;
            overflow-x: auto;
            margin: 18px 0;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.86rem;
            color: #38bdf8;
        }}
        code {{
            font-family: 'JetBrains Mono', monospace;
            background: rgba(56, 189, 248, 0.1);
            color: #38bdf8;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 0.85em;
        }}
        pre code {{
            background: transparent;
            padding: 0;
            color: inherit;
        }}
        hr {{
            border: none;
            border-top: 1px solid var(--surface-border);
            margin: 36px 0;
        }}
        .mermaid {{
            background: var(--code-bg);
            border: 1px solid var(--surface-border);
            border-radius: 12px;
            padding: 20px;
            margin: 24px 0;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="action-bar no-print">
            <div style="display: flex; align-items: center; gap: 14px;">
                <span class="badge"><span class="pulse"></span> SYSTEM OPERATIONAL (100%)</span>
                <span style="font-size: 0.85rem; color: var(--text-muted);">TrackGuard Defense Platform</span>
            </div>
            <div style="display: flex; gap: 10px;">
                <button onclick="window.print()" class="btn">
                    🖨️ Print / Save as PDF
                </button>
                <a href="/download-report?format=markdown" class="btn btn-outline" download="TrackGuard_Comprehensive_Project_Report.md">
                    ⬇️ Download Markdown (.md)
                </a>
            </div>
        </div>

        <div class="report-card">
            {html_body}
        </div>
    </div>
</body>
</html>"""

# Output destinations
destinations = [
    Path("c:/Users/rahul/Downloads/TrackGuard_Comprehensive_Project_Report.html"),
    Path("c:/Users/rahul/Downloads/TrackGuard_Project/TrackGuard_Comprehensive_Project_Report.html"),
    Path("c:/Users/rahul/Downloads/TrackGuard_Project/TrackGuard/dashboard/static/reports/TrackGuard_Comprehensive_Project_Report.html"),
    Path("c:/Users/rahul/TrackGuard/dashboard/static/reports/TrackGuard_Comprehensive_Project_Report.html")
]

for d in destinations:
    d.parent.mkdir(parents=True, exist_ok=True)
    d.write_text(html_template, encoding="utf-8")

print("Generated HTML report across all destinations successfully.")
