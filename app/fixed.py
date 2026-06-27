from app import main as base

base.APP_VERSION = "render-light-1.0.1"

base.HTML = base.HTML.replace(
    "#main { display:none; flex:1; min-height:0; }",
    "#main { display:none; flex:1; flex-direction:column; min-height:0; height:100%; max-height:calc(100svh - 20px); overflow:hidden; }",
)
base.HTML = base.HTML.replace(
    "#chat { flex:1; overflow:auto; padding:14px; display:flex; flex-direction:column; gap:12px; min-height:45svh; }",
    "#chat { flex:1 1 auto; overflow:auto; padding:14px; display:flex; flex-direction:column; gap:12px; min-height:0; }",
)
base.HTML = base.HTML.replace(
    "form { display:flex; gap:10px; padding:12px; }",
    "form { display:flex; gap:10px; padding:12px; align-items:flex-end; flex:none; }",
)
base.HTML = base.HTML.replace(
    "textarea { resize:none; min-height:54px; max-height:140px; }",
    "textarea { resize:none; min-height:54px; max-height:140px; flex:1 1 auto; }",
)
base.HTML = base.HTML.replace(
    "form button { width:92px; flex:none; }",
    "form button { width:92px; flex:0 0 92px; min-height:54px; align-self:flex-end; }",
)
base.HTML = base.HTML.replace(
    "$('main').style.display='flex'; health();",
    "$('main').style.display='flex'; $('main').style.flexDirection='column'; health();",
)
base.HTML = base.HTML.replace(
    "@media (max-width:640px) { .app{padding:10px;} #login{min-height:calc(100svh - 20px); display:flex; flex-direction:column; justify-content:center;} form{position:sticky;bottom:0;background:rgba(6,9,20,.94);backdrop-filter:blur(16px);} .msg{max-width:94%;} }",
    "@media (max-width:640px) { .app{padding:10px;min-height:100svh;} #login{min-height:calc(100svh - 20px); display:flex; flex-direction:column; justify-content:center;} #main{min-height:calc(100svh - 20px);} header{flex:none;} form{position:sticky;bottom:0;background:rgba(6,9,20,.94);backdrop-filter:blur(16px);} .msg{max-width:94%;} }",
)

app = base.app
