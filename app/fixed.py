import json
import re
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app import main as base

base.APP_VERSION = "render-light-1.0.9"

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
        raw_body = await request.body()
        payload = json.loads(raw_body.decode("utf-8") if raw_body else "{}")
    except Exception:
        return base.JSONResponse({"detail": "No pude leer el mensaje JSON."}, status_code=400)

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

PHONE_CONTROL_JS = r'''
function aiRxNorm(text){ return String(text||'').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').trim(); }
function aiRxPhoneAvailable(){ return !!(window.AIRX && typeof window.AIRX.runPhoneAction === 'function'); }
function aiRxRunPhone(action, payload){
  if(!aiRxPhoneAvailable()) return false;
  window.AIRX.runPhoneAction(action, JSON.stringify(payload || {}));
  return true;
}
function aiRxParseClock(text){
  const m = aiRxNorm(text).match(/(?:a las|alas|para las|alarma|despiertame|despiertame a las)\s*(\d{1,2})(?:[:\.](\d{1,2}))?/);
  if(!m) return null;
  let hour = parseInt(m[1],10);
  const minute = m[2] ? parseInt(m[2],10) : 0;
  if(/\bpm\b|tarde|noche/.test(aiRxNorm(text)) && hour < 12) hour += 12;
  if(hour < 0 || hour > 23 || minute < 0 || minute > 59) return null;
  return {hour, minute, label:'AI_RX'};
}
function aiRxParseDuration(text){
  const n = aiRxNorm(text);
  const m = n.match(/(\d+)\s*(hora|horas|minuto|minutos|min|segundo|segundos|seg)/);
  if(!m) return null;
  const value = parseInt(m[1],10);
  let seconds = value;
  if(m[2].startsWith('hora')) seconds = value * 3600;
  else if(m[2].startsWith('min')) seconds = value * 60;
  return {seconds, label:'AI_RX'};
}
function aiRxCommandReply(text){ add('bot', text); }
function aiRxHandlePhoneCommand(message){
  const n = aiRxNorm(message);
  if(!aiRxPhoneAvailable() && /(telefono|celular|calendario|reloj|alarma|temporizador|mensaje|sms|fotos|galeria|camara|contactos|ajustes|configuracion|wifi)/.test(n)){
    aiRxCommandReply('Señor, esa acción necesita abrirse desde la app Android de AI_RX en el teléfono.');
    return true;
  }
  if(/(lee|leer|muestra|mostrar).*mensajes|mensajes.*(privados|recibidos|inbox)|leer.*fotos|ver todas mis fotos/.test(n)){
    aiRxCommandReply('Por privacidad, señor, puedo abrir la app correspondiente para usted, pero no leer mensajes ni revisar fotos en secreto.');
    if(n.includes('mensaje')) aiRxRunPhone('sms', {});
    if(n.includes('foto')) aiRxRunPhone('photos', {});
    return true;
  }
  const alarm = aiRxParseClock(message);
  if(alarm && /(alarma|despiertame|despiértame)/.test(n)){
    aiRxRunPhone('set_alarm', alarm);
    aiRxCommandReply(`Con gusto, señor. Le preparé una alarma para ${String(alarm.hour).padStart(2,'0')}:${String(alarm.minute).padStart(2,'0')}. Revísela y confirme si el reloj se lo pide.`);
    return true;
  }
  const timer = aiRxParseDuration(message);
  if(timer && /(temporizador|timer|cronometro|cronómetro)/.test(n)){
    aiRxRunPhone('timer', timer);
    aiRxCommandReply('Desde luego, señor. Le abrí el temporizador para confirmarlo.');
    return true;
  }
  const sms = n.match(/(?:mensaje|sms|texto)\s+a\s+([^,\s]+)\s*(.*)/);
  if(sms){
    aiRxRunPhone('sms', {number:sms[1], text:sms[2] || ''});
    aiRxCommandReply('Le preparé el mensaje, señor. Revíselo antes de enviarlo.');
    return true;
  }
  const call = n.match(/(?:llama|llamar|telefono|marcar)\s+(?:a\s+)?([^,\s]+)/);
  if(call && !/(abre|abrir)/.test(n)){
    aiRxRunPhone('phone', {number:call[1]});
    aiRxCommandReply('Le abrí el teléfono con el número listo, señor. Usted confirma la llamada.');
    return true;
  }
  const openActions = [
    [/calendario|agenda/, 'calendar', 'Abriendo calendario, señor.'],
    [/reloj|alarmas/, 'clock', 'Abriendo reloj, señor.'],
    [/fotos|galeria|galería/, 'photos', 'Abriendo fotos, señor.'],
    [/camara|cámara/, 'camera', 'Abriendo cámara, señor.'],
    [/contactos/, 'contacts', 'Abriendo contactos, señor.'],
    [/wifi|wi-fi/, 'wifi', 'Abriendo ajustes de Wi‑Fi, señor.'],
    [/ajustes|configuracion|configuración/, 'settings', 'Abriendo ajustes, señor.'],
    [/telefono|teléfono|marcador/, 'phone', 'Abriendo teléfono, señor.']
  ];
  if(/abre|abrir|pon|ve a|ir a|muestrame|muéstrame/.test(n)){
    for(const [pattern, action, reply] of openActions){
      if(pattern.test(n)){
        aiRxRunPhone(action, {});
        aiRxCommandReply(reply);
        return true;
      }
    }
  }
  return false;
}
'''

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
    "if(!r.ok) throw new Error(j.detail||'No autorizado');",
    "if(!r.ok){ const msg = typeof j.detail === 'string' ? j.detail : 'Escribe un código autorizado.'; throw new Error(msg||'No autorizado'); }",
)
base.HTML = base.HTML.replace(
    "if(!r.ok) throw new Error(j.detail||'Error'); typing.remove(); add('bot',j.reply);",
    "if(!r.ok){ const msg = typeof j.detail === 'string' ? j.detail : 'No pude completar la petición.'; throw new Error(msg||'Error'); } typing.remove(); add('bot',j.reply);",
)
base.HTML = base.HTML.replace(
    "let token = localStorage.getItem('ai_rx_token') || '';\nlet history = [];",
    "let token = localStorage.getItem('ai_rx_token') || '';\nlet history = [];\n" + PHONE_CONTROL_JS,
)
base.HTML = base.HTML.replace(
    "add('user',msg); const typing=document.createElement('div');",
    "add('user',msg); if(aiRxHandlePhoneCommand(msg)) return; const typing=document.createElement('div');",
)
base.HTML = base.HTML.replace(
    "@media (max-width:640px) { .app{padding:10px;} #login{min-height:calc(100svh - 20px); display:flex; flex-direction:column; justify-content:center;} form{position:sticky;bottom:0;background:rgba(6,9,20,.94);backdrop-filter:blur(16px);} .msg{max-width:94%;} }",
    "@media (max-width:640px) { body{font-size:20px !important;} .app{padding:8px;min-height:100svh;width:100%;} .card{border-radius:26px;} .logo{width:76px;height:76px;font-size:38px;border-radius:22px;} h1{font-size:38px;line-height:1.05;} p{font-size:18px;line-height:1.35;} .tiny,.status{font-size:16px;line-height:1.25;} input{font-size:21px;min-height:70px;padding:18px;border-radius:20px;} button{font-size:19px;min-height:64px;border-radius:20px;padding:16px 18px;} #login{width:min(620px,100%);min-height:calc(100svh - 16px);padding:38px;display:flex;flex-direction:column;justify-content:center;} .row{gap:14px;margin-top:14px;} #enter{margin-top:14px !important;} #main{min-height:calc(100svh - 16px);max-height:calc(100svh - 16px);} header{flex:none;padding:20px;} header strong{font-size:22px;} #chat{font-size:20px;padding:20px;gap:18px;} .msg{max-width:95%;font-size:20px;line-height:1.5;padding:16px 18px;border-radius:22px;} form{position:sticky;bottom:0;background:rgba(6,9,20,.96);backdrop-filter:blur(16px);padding:18px;} textarea{font-size:20px !important;min-height:76px;} form button{font-size:19px;min-height:76px;width:128px;flex-basis:128px;} }",
)

app = base.app
