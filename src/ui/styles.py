CSS = """
<style>
:root { --panel:#101727; --border:#27324a; --muted:#9aa6ba; --text:#e6eaf2; }
.stApp { background:radial-gradient(circle at 12% 0%,#18213a 0,#0b1020 34%,#080c17 100%); color:var(--text); }
[data-testid="stHeader"] { background:rgba(8,12,23,.78); }
section[data-testid="stMain"] [data-testid="stMainBlockContainer"] { padding-top:calc(2.1rem + 28px) !important; padding-bottom:2rem; max-width:1280px; }
[data-testid="stVerticalBlock"] { gap:.7rem; }
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap:.45rem; }
.hero { padding:1.15rem 1.35rem; border:1px solid var(--border); border-radius:16px; background:linear-gradient(135deg,rgba(29,39,65,.88),rgba(13,18,34,.92)); margin:0 0 .55rem; }
.hero h1 { margin:.12rem 0 0; font-size:1.9rem; letter-spacing:-.04em; }
.hero p { color:#a9b4c9; margin:.3rem 0 0; }
.badge,.eyebrow { display:inline-block; color:#a9c7ff; font-size:.72rem; font-weight:700; letter-spacing:.08em; }
.badge { padding:.25rem .58rem; border-radius:999px; background:#222c48; border:1px solid #39496f; }
.summary-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(145px,1fr)); gap:.55rem; margin:.15rem 0 .85rem; }
.summary-card { padding:.72rem .8rem; border-radius:11px; border:1px solid var(--border); background:rgba(16,23,39,.88); min-width:0; }
.summary-card span,.approval-facts span,.decision-facts span,.reason-box span { display:block; color:var(--muted); font-size:.74rem; margin-bottom:.16rem; }
.summary-card strong { display:block; font-size:.91rem; overflow-wrap:anywhere; }
.step-card,.trace-row,.approval-history { display:flex; align-items:flex-start; justify-content:space-between; gap:1rem; padding:.68rem .8rem; margin:.32rem 0; background:var(--panel); border:1px solid var(--border); border-radius:10px; }
.step-card p,.trace-row p,.approval-history p { color:var(--muted); font-size:.82rem; line-height:1.35; margin:.16rem 0 0; }
.step-tool { display:inline-block; margin-left:.48rem; padding:.08rem .4rem; border-radius:5px; background:#1c263d; color:#9fb4d8; font-size:.7rem; font-family:monospace; }
.status-badge { display:inline-block; white-space:nowrap; padding:.19rem .5rem; border-radius:999px; border:1px solid #46536a; background:#20283a; color:#cbd4e4; font-size:.7rem; font-weight:700; }
.status-completed,.status-approved { color:#8ee0bd; border-color:#27664f; background:#102b24; }
.status-waiting_for_approval,.status-pending,.status-ready { color:#f2c77c; border-color:#715323; background:#2a2112; }
.status-failed,.status-rejected { color:#f3a0a5; border-color:#71343b; background:#2c171c; }
.status-running { color:#9fc3ff; border-color:#345f9c; background:#132642; }
.status-skipped { color:#aeb8c8; }
.trace-meta { display:flex; flex-direction:column; align-items:flex-end; gap:.22rem; color:var(--muted); font-size:.7rem; }
.approval-card,.decision-card { padding:1rem; border:1px solid #6c5429; background:linear-gradient(145deg,#211b13,#151923); border-radius:13px; margin:.55rem 0 .7rem; }
.decision-card { border-color:var(--border); background:var(--panel); }
.card-heading,.detail-heading { display:flex; align-items:flex-start; justify-content:space-between; gap:1rem; }
.card-heading h3,.decision-card h3,.response-heading h3,.detail-heading h2 { margin:.1rem 0 .65rem; }
.approval-facts,.decision-facts { display:grid; grid-template-columns:repeat(auto-fit,minmax(130px,1fr)); gap:.55rem; }
.approval-facts div,.decision-facts div { padding:.52rem .6rem; background:rgba(5,9,17,.32); border-radius:8px; }
.reason-box { margin-top:.65rem; padding:.58rem .65rem; border-top:1px solid rgba(167,118,42,.35); }
.reason-box p { margin:.1rem 0; color:#d8deea; font-size:.88rem; }
.request-card { padding:.78rem .9rem; border-left:3px solid #5577c9; background:var(--panel); border-radius:0 9px 9px 0; color:#dce3ef; }
.approval-history span { color:var(--muted); font-size:.72rem; }
.detail-heading { margin:.9rem 0 .45rem; }
.response-heading { margin:.25rem 0; }
.muted { color:var(--muted); }
div.stButton > button,div.stDownloadButton > button { border-radius:8px; border:1px solid #3c4c70; min-height:2.4rem; }
[data-testid="stExpander"] { border-color:var(--border); background:rgba(12,18,31,.5); }
[data-baseweb="tab-list"] { gap:.15rem; border-bottom:1px solid var(--border); }
[data-baseweb="tab"] { height:2.65rem; padding:0 .75rem; }
hr { margin:.65rem 0 !important; border-color:var(--border) !important; }
@media (max-width:700px) { .summary-grid { grid-template-columns:repeat(2,minmax(0,1fr)); } .step-card,.trace-row { gap:.5rem; } }
</style>
"""
