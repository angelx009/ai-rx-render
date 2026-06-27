from app import main as base

base.APP_VERSION = "render-light-1.0.2"

base.HTML = base.HTML.replace(
    "#main { display:none; flex:1; min-height:0; }",
    "#main { display:none; flex:1; flex-direction:column; min-height:0; height:100%; max-height:calc(100svh - 20px); overflow:hidden; }",
)
base.HTML = base.HTML.replace(
    "#chat { flex:1; overflow:auto; padding:14px; display:flex; flex-direction:column; gap:12px; min-height:45svh; }",
    "#chat { flex:1 1 auto; overflow:auto; padding:16px; display:flex; flex-direction:column; gap:14px; min-height:0; font-size:17px; }",
)
base.HTML = base.HTML.replace(
    "form { display:flex; gap:10px; padding:12px; }",
    "form { display:flex; gap:12px; padding:14px; align-items:flex-end; flex:none; }",
)
base.HTML = base.HTML.replace(
    "textarea { resize:none; min-height:54px; max-height:140px; }",
    "textarea { resize:none; min-height:60px; max-height:150px; flex:1 1 auto; font-size:17px; }",
)
base.HTML = base.HTML.replace(
    "form button { width:92px; flex:none; }",
    "form button { width:104px; flex:0 0 104px; min-height:60px; align-self:flex-end; font-size:16px; }",
)
base.HTML = base.HTML.replace(
    "$('main').style.display='flex'; health();",
    "$('main').style.display='flex'; $('main').style.flexDirection='column'; health();",
)
base.HTML = base.HTML.replace(
    "@media (max-width:640px) { .app{padding:10px;} #login{min-height:calc(100svh - 20px); display:flex; flex-direction:column; justify-content:center;} form{position:sticky;bottom:0;background:rgba(6,9,20,.94);backdrop-filter:blur(16px);} .msg{max-width:94%;} }",
    "@media (max-width:640px) { body{font-size:17px;} .app{padding:10px;min-height:100svh;} .logo{width:62px;height:62px;font-size:30px;} h1{font-size:31px;} p,.tiny,.status{font-size:14px;} input{font-size:17px;min-height:56px;} button{font-size:16px;min-height:50px;} #login{width:min(520px,100%);min-height:calc(100svh - 20px);padding:30px;display:flex;flex-direction:column;justify-content:center;} #main{min-height:calc(100svh - 20px);} header{flex:none;padding:16px;} header strong{font-size:18px;} form{position:sticky;bottom:0;background:rgba(6,9,20,.94);backdrop-filter:blur(16px);} .msg{max-width:94%;font-size:17px;} }",
)

app = base.app
