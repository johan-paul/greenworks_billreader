"""Serialize extraction results as JSON, CSV or standalone HTML."""

import csv
import html
import io
import json


def render_export(result: dict, name: str, kind: str):
    if kind == "json":
        body = json.dumps(result, indent=2)
        mime = "application/json"
        extension = "json"
    elif kind == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["page", "status", "field", "value", "unit", "evidence"])

        def safe(value):
            value = str(value)
            return (
                "'" + value
                if value.startswith(("=", "+", "-", "@", "\t", "\r"))
                else value
            )

        for page in result["pages"]:
            if page["status"] == "error":
                writer.writerow(
                    [page["page"], "error", "error", safe(page["error"]), "", ""]
                )
            for field, value in page.get("data", {}).items():
                if value is None or field == "notes":
                    continue
                cells = (
                    [value.get("value"), value.get("unit"), value.get("quote")]
                    if isinstance(value, dict)
                    else [value, "", ""]
                )
                writer.writerow(
                    [page["page"], page["status"], field, *map(safe, cells)]
                )
            for field, value in page.get("derived", {}).items():
                writer.writerow(
                    [
                        page["page"],
                        "derived",
                        field,
                        value["value"],
                        value["unit"],
                        safe(value["formula"]),
                    ]
                )
        body = output.getvalue()
        mime = "text/csv"
        extension = "csv"
    elif kind == "html":
        esc = lambda v: html.escape(str(v))
        body = f"""<!doctype html>
<meta charset="utf-8">
<title>Greenworks bill report</title>
<style>
body {{font:16px/1.6 system-ui;max-width:1000px;margin:40px auto;
       padding:20px;color:#173e35}}
table {{border-collapse:collapse;width:100%}}
td,th {{text-align:left;padding:10px;border-bottom:1px solid #ddd}}
code {{white-space:pre-wrap}}
section {{break-inside:avoid;margin-bottom:40px}}
</style>
<h1>Greenworks · Bill report</h1>
<p>{esc(name)}</p>
<p>Processed {result['processed_pages']} of {result['page_count']} pages.
Review required; no cross-page totals are assumed.</p>"""
        for page in result["pages"]:
            body += f'<section><h2>Page {page["page"]} · {esc(page["status"])}</h2>'
            if page["status"] == "error":
                body += f'<p>{esc(page["error"])}</p>'
            body += "<table><tr><th>Field</th><th>Value</th><th>Evidence</th></tr>"
            for field, value in page.get("data", {}).items():
                if value is None or field == "notes":
                    continue
                display = (
                    f'{value["value"]:,.3f} {value["unit"]}'
                    if isinstance(value, dict)
                    else value
                )
                quote = value.get("quote", "") if isinstance(value, dict) else ""
                body += f"<tr><td>{esc(field)}</td><td>{esc(display)}</td><td>{esc(quote)}</td></tr>"
            body += "</table>"
            for field, value in page.get("derived", {}).items():
                body += f'<p><b>{esc(field)}: {value["value"]:,.3f} {esc(value["unit"])}</b> — {esc(value["formula"])}. {esc(value["warning"])}</p>'
            body += (
                "<ul>"
                + "".join(
                    f"<li>{esc(issue)}</li>"
                    for issue in page.get("issues", [])
                    + page.get("data", {}).get("notes", [])
                )
                + "</ul></section>"
            )
        body += "<p>Savings and emissions cannot be established from an unreconciled bill alone. Use reviewed delivered energy, costs, tariffs and sourced emission factors.</p>"
        mime = "text/html"
        extension = "html"
    else:
        raise ValueError("Unsupported report format")
    return body, mime, extension
