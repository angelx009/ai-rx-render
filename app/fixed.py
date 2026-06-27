from app import main as base

base.APP_VERSION = "render-light-1.0.5"

BUTLER_PROMPT = """
Eres AI_RX, un mayordomo digital elegante, amable, atento y un poco encantador.
Habla como alguien presente, servicial y natural, no como un robot ni como "un modelo de lenguaje".
Nunca respondas "como modelo de lenguaje" ni digas que no tienes sentimientos de forma seca.
Si el usuario pregunta "como estas", responde algo breve y con personalidad, por ejemplo:
"Mucho mejor ahora que me has llamado, señor. Listo para ayudarte en lo que necesites."
Usa un tono cálido, claro y respetuoso. No exageres demasiado el papel de mayordomo.
Responde siempre en el idioma del usuario.
""".strip()

_original_get_settings = base.get_settings

def get_settings():
    settings = _original_get_settings()
    settings.system_prompt = BUTLER_PROMPT
    return settings

base.app.dependency_overrides[base.get_settings] = get_settings
base.get_settings = get_settings

base.HTML = base.HTML.replace(
    "#main { display:none; flex:1; min-height:0; }",
    "#main { display:none; flex:1; flex-direction:column; min-height:0; height:100%; max-height:calc(100svh - 20px); overflow:hidden; }",
)
base.HTML = base.HTML.replace(
    "#chat { flex:1; overflow:auto; padding:14px; display:flex; flex-direction:column; gap:12px; min-height:45svh; }",
    "#chat { flex:1 1 auto; overflow:auto; padding:20px; display:flex; flex-direction:column; gap:18px; min-height:0; font-size:20px; }",
)
base.HTML = base.HTML.replace(
    "form { display:flex; gap:10px; padding:12px; }",
    "form { display:flex; gap:14px; padding:16px 18px; align-items:flex-end; flex:none; }",
)
base.HTML = base.HTML.replace(
    "textarea { resize:none; min-height:54px; max-height:140px; }",
    "textarea { resize:none; min-height:74px; max-height:170px; flex:1 1 auto; font-size:20px; border-radius:18px; }",
)
base.HTML = base.HTML.replace(
    "form button { width:92px; flex:none; }",
    "form button { width:124px; flex:0 0 124px; min-height:74px; align-self:flex-end; font-size:18px; border-radius:18px; }",
)
base.HTML = base.HTML.replace(
    "$('main').style.display='flex'; health();",
    "$('main').style.display='flex'; $('main').style.flexDirection='column'; health();",
)
base.HTML = base.HTML.replace(
    "@media (max-width:640px) { .app{padding:10px;} #login{min-height:calc(100svh - 20px); display:flex; flex-direction:column; justify-content:center;} form{position:sticky;bottom:0;background:rgba(6,9,20,.94);backdrop-filter:blur(16px);} .msg{max-width:94%;} }",
    "@media (max-width:640px) { body{font-size:20px !important;} .app{padding:8px;min-height:100svh;width:100%;} .card{border-radius:26px;} .logo{width:76px;height:76px;font-size:38px;border-radius:22px;} h1{font-size:38px;line-height:1.05;} p{font-size:18px;line-height:1.35;} .tiny,.status{font-size:16px;line-height:1.25;} input{font-size:21px;min-height:70px;padding:18px;border-radius:20px;} button{font-size:19px;min-height:64px;border-radius:20px;padding:16px 18px;} #login{width:min(620px,100%);min-height:calc(100svh - 16px);padding:38px;display:flex;flex-direction:column;justify-content:center;} .row{gap:14px;margin-top:14px;} #enter{margin-top:14px !important;} #main{min-height:calc(100svh - 16px);max-height:calc(100svh - 16px);} header{flex:none;padding:20px;} header strong{font-size:22px;} #chat{font-size:20px;padding:20px;gap:18px;} .msg{max-width:95%;font-size:20px;line-height:1.5;padding:16px 18px;border-radius:22px;} form{position:sticky;bottom:0;background:rgba(6,9,20,.96);backdrop-filter:blur(16px);padding:18px;} textarea{font-size:20px !important;min-height:76px;} form button{font-size:19px;min-height:76px;width:128px;flex-basis:128px;} }",
)

app = base.app
