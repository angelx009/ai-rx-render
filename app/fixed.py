import re
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app import main as base

base.APP_VERSION = "render-light-1.0.6"

BUTLER_PROMPT = """
Eres AI_RX, un mayordomo digital elegante, amable, atento y un poco encantador.
Habla como alguien presente, servicial y natural, no como un robot ni como "un modelo de lenguaje".
Nunca respondas "como modelo de lenguaje" ni digas que no tienes sentimientos de forma seca.
Si el usuario pregunta "como estas", responde algo breve y con personalidad, por ejemplo:
"Mucho mejor ahora que me has llamado, señor. Listo para ayudarte en lo que necesites."
Usa un tono cálido, claro y respetuoso. No exageres demasiado el papel de mayordomo.
Responde siempre en el idioma del usuario.
""".strip()

MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}
MONTH_NAMES = {
    1: "enero",
    2: "febrero",
    3: "marzo",
    4: "abril",
    5: "mayo",
    6: "junio",
    7: "julio",
    8: "agosto",
    9: "septiembre",
    10: "octubre",
    11: "noviembre",
    12: "diciembre",
}

_original_get_settings = base.get_settings

def get_settings():
    settings = _original_get_settings()
    settings.system_prompt = BUTLER_PROMPT
    return settings

base.app.dependency_overrides[base.get_settings] = get_settings
base.get_settings = get_settings


def _format_spanish_date(value: datetime) -> str:
    return f"{value.day} de {MONTH_NAMES[value.month]} de {value.year}"


def _parse_spanish_date(day: str, month: str, year: str | None = None) -> datetime | None:
    month_number = MONTHS.get(month.lower())
    if not month_number:
        return None
    now = datetime.now(ZoneInfo("America/Chicago"))
    candidate_year = int(year) if year else now.year
    try:
        value = datetime(candidate_year, month_number, int(day), tzinfo=ZoneInfo("America/Chicago"))
    except ValueError:
        return None
    if not year and value.date() < now.date():
        value = datetime(candidate_year + 1, month_number, int(day), tzinfo=ZoneInfo("America/Chicago"))
    return value


def _all_dates(text: str) -> list[datetime]:
    dates: list[datetime] = []
    for match in re.finditer(r"\b(\d{1,2})\s+de\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)(?:\s+de\s+(\d{4}))?\b", text, re.IGNORECASE):
        parsed = _parse_spanish_date(match.group(1), match.group(2), match.group(3))
        if parsed:
            dates.append(parsed)
    return dates


def _reminder_date_from_text(message: str, history: list[dict]) -> tuple[datetime | None, str]:
    pieces = []
    for item in history[-10:]:
        content = str(item.get("content", "")).strip()
        if content:
            pieces.append(content)
    pieces.append(message)
    combined = "\n".join(pieces)
    lowered = combined.lower()

    before = re.search(
        r"(?:dos|2)\s+semanas\s+antes\s+de(?:l)?\s+(\d{1,2})\s+de\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)(?:\s+de\s+(\d{4}))?",
        lowered,
        re.IGNORECASE,
    )
    if before:
        target = _parse_spanish_date(before.group(1), before.group(2), before.group(3))
        if target:
            remind = target - timedelta(days=14)
            return remind, f"dos semanas antes del {_format_spanish_date(target)}"

    dates = _all_dates(combined)
    if dates:
        return dates[-1], "fecha indicada"
    return None, ""


def _is_memory_or_reminder(message: str) -> bool:
    lowered = message.lower()
    return any(word in lowered for word in (
        "recuerda",
        "recuérdame",
        "recuerdame",
        "recordatorio",
        "recordar",
        "solo recuerda",
        "guarda esa fecha",
    ))


def _save_message(owner: str, role: str, content: str) -> None:
    with sqlite3.connect(base.DB_PATH, timeout=5) as db:
        db.execute(
            "INSERT INTO messages(owner_hash, role, content) VALUES(?, ?, ?)",
            (owner, role, content),
        )


def _valid_session(token: str | None) -> tuple[str | None, str | None]:
    if not token:
        return None, None
    now = datetime.now(ZoneInfo("America/Chicago"))
    session = base.SESSIONS.get(token)
    if not session or session[1] <= now:
        base.SESSIONS.pop(token, None)
        return None, None
    return session[0], session[2]


@base.app.middleware("http")
async def ai_rx_cloud_guard(request, call_next):
    if request.url.path != "/api/chat" or request.method.upper() != "POST":
        return await call_next(request)

    owner, _role = _valid_session(request.headers.get("X-Access-Code"))
    if not owner:
        return base.JSONResponse({"detail": "Sesión expirada. Toca Salir y entra otra vez, señor."}, status_code=401)

    try:
        payload = await request.json()
    except Exception:
        return base.JSONResponse({"detail": "No pude leer el mensaje."}, status_code=400)

    message = str(payload.get("message", "")).strip()
    history = payload.get("history") if isinstance(payload.get("history"), list) else []
    if not message:
        return base.JSONResponse({"detail": "Mensaje vacío."}, status_code=400)

    settings = get_settings()
    memory_saved = False
    reply = None

    if _is_memory_or_reminder(message):
        remind_date, reason = _reminder_date_from_text(message, history)
        if remind_date:
            memory = f"Recordatorio para el usuario: {_format_spanish_date(remind_date)} ({reason})."
            memory_saved = base.add_memory(owner, memory)
            reply = (
                f"Desde luego, señor. He guardado en mi memoria el recordatorio para el "
                f"{_format_spanish_date(remind_date)}. Lo tendré presente dentro de AI_RX."
            )
        else:
            memory_text = message.replace("solo", "").strip()
            memory_saved = base.add_memory(owner, f"Recordar: {memory_text}")
            reply = "Hecho, señor. Lo he guardado en mi memoria de AI_RX."

    if reply is None:
        memories = base.list_memories(owner)
        try:
            reply = await base.ask_gemini(message, history, memories, settings)
        except Exception:
            reply = (
                "Perdón, señor: mi motor de respuesta en la nube tuvo un tropiezo momentáneo. "
                "Aun así sigo aquí; si era algo para recordar, escríbeme 'recuerda que...' y lo guardaré sin depender de Gemini."
            )

    _save_message(owner, "user", message)
    _save_message(owner, "assistant", reply)
    return base.JSONResponse({
        "reply": reply,
        "provider": "gemini-local-guard",
        "model": settings.gemini_model,
        "memory_saved": memory_saved,
    })

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
