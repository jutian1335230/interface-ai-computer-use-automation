from __future__ import annotations

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse

app = FastAPI(title="Legacy Member Console")

MEMBERS = {
    "12345": {"name": "Jamie Rivera", "balance": "$1,250.00", "status": "Active"},
    "24680": {"name": "Morgan Lee", "balance": "$82.14", "status": "Restricted"},
}


def page(content: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Member Services Terminal</title>
<style>
body {{ margin: 0; background: #d6d9cf; color: #111; font: 16px 'Courier New', monospace; }}
.top {{ background: #173b31; color: #f4f1d0; padding: 14px 24px; border-bottom: 5px solid #c6a94c; }}
.shell {{ width: min(760px, calc(100% - 28px)); margin: 30px auto; background: #eef0e8; border: 2px solid #49564e; box-shadow: 8px 8px 0 #89938b; }}
.bar {{ background: #49564e; color: white; padding: 8px 12px; }}
.content {{ padding: 24px; }} table {{ width: 100%; border-collapse: collapse; }}
td, th {{ border: 1px solid #69746d; padding: 10px; text-align: left; }}
input {{ width: min(320px, 90%); padding: 9px; font: inherit; border: 2px inset #aaa; }}
button, a.button {{ display: inline-block; padding: 9px 16px; color: #111; background: #d8d8ce; border: 2px outset #fff; font: bold 15px inherit; text-decoration: none; cursor: pointer; }}
.error {{ border: 2px solid #9f2d22; background: #fff0eb; padding: 12px; }}
.status {{ color: #315b34; font-weight: bold; }}
</style></head><body><div class="top"><b>NORTHSTAR CORE / MEMBER SERVICES</b></div>
<main class="shell"><div class="bar">SESSION: TRAINING-ONLY</div><div class="content">{content}</div></main>
</body></html>"""


@app.get("/legacy", response_class=HTMLResponse)
def home() -> str:
    return page("""
<h1>Member Lookup</h1>
<form method="post" action="/legacy/search">
<table><tr><td><label for="member-number">Member number</label></td>
<td><input id="member-number" name="member_id" autocomplete="off" required pattern="[0-9]{5}"></td></tr></table>
<p><button type="submit">Find member</button></p>
</form><small>Training records: 12345 and 24680</small>
""")


@app.post("/legacy/search", response_class=HTMLResponse)
def search(member_id: str = Form()) -> str:
    if member_id == "99999":
        return page("""<h1>Session expired</h1><div class="error" role="alert">
Your training session expired. Sign in again or request operator assistance.</div>
<p><a class="button" href="/legacy">Return to lookup</a></p>""")
    member = MEMBERS.get(member_id)
    if member is None:
        return page("""<h1>Search result</h1><div class="error" role="alert">No member found</div>
<p><a class="button" href="/legacy">New lookup</a></p>""")
    return page(f"""<h1>Member Detail</h1><p class="status">Record loaded</p>
<table aria-label="Member account summary">
<tr><th>Member number</th><td>{member_id}</td></tr>
<tr><th>Name</th><td>{member['name']}</td></tr>
<tr><th>Savings balance</th><td>{member['balance']}</td></tr>
<tr><th>Status</th><td>{member['status']}</td></tr></table>
<p><a class="button" href="/legacy">New lookup</a></p>""")
