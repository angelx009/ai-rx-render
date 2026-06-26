import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

APP_VERSION = "render-light-1.0.0"
STARTED_AT = time.time()
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "ai_rx.db"
SESSION_DURATION = timedelta(hours=12)
SESSIONS: dict[str, tuple[str, datetime, str]] = {}


class Settings(BaseModel):
    ai_name: str = "AI_RX"
    access_codes: tuple[str, ...] = ("codigo_0000", "ambu_perro")
    owner_code: str = "codigo_0000"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash-lite"
    system_prompt: str = "Eres AI_RX, una asistente util, rapida y clara. Responde siempre en el idioma del usuario."


def get_settings() -> Settings:
    codes = tuple(code.strip() for code in os.getenv("ACCESS_CODES", "codigo_0000,ambu_perro").split(",") if code.strip())
    return Settings(
        ai_name=os.getenv("AI_NAME", "AI_RX").strip() or "AI_RX",
        access_codes=codes,
        owner_code=os.getenv("OWNER_CODE", "codigo_0000").strip() or "codigo_0000",
        gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite").strip() or "gemini-2.5-flash-lite",
        system_prompt=os.getenv("SYSTEM_PROMPT", "Eres AI_RX, una asistente util, rapida y clara. Responde siempre en el idioma del usuario.").strip(),
    )


def owner_hash(code: str, settings: Settings) -> str:
    role = "owner" if hmac.compare_digest(code, settings.owner_code) else "user"
    return hashlib.sha256(f"{role}:{code}".encode()).hexdigest()


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH, timeout=5) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_hash TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(owner_hash, content)
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)


def valid_code(code: str, settings: Settings) -> bool:
    return any(hmac.compare_digest(code, item) for item in settings.access_codes)


def require_session(x_access_code: str | None = Header(default=None, alias="X-Access-Code"), settings: Settings = Depends(get_settings)) -> str:
    now = datetime.now(ZoneInfo("America/Chicago"))
    if not x_access_code:
        raise HTTPException(status_code=401, detail="Sesion no autorizada.")
    session = SESSIONS.get(x_access_code)
    if not session or session[1] <= now:
        SESSIONS.pop(x_access_code, None)
        raise HTTPException(status_code=401, detail="Sesion expirada o no autorizada.")
    return session[0]


def local_time() -> dict:
    now = datetime.now(ZoneInfo("America/Chicago"))
    return {
        "iso": now.isoformat(),
        "date": now.date().isoformat(),
        "time": now.strftime("%H:%M:%S"),
        "timezone": "America/Chicago",
        "readable": now.strftime("%A %d %B %Y, %I:%M:%S %p"),
    }


def add_memory(owner: str, content: str) -> bool:
    content = content.strip()[:500]
    if not content:
        return False
    with sqlite3.connect(DB_PATH, timeout=5) as db:
        cur = db.execute("INSERT OR IGNORE INTO memories(owner_hash, content) VALUES(?, ?)", (owner, content))
        return cur.rowcount > 0


def list_memories(owner: str, limit: int = 20) -> list[str]:
    with sqlite3.connect(DB_PATH, timeout=5) as db:
        rows = db.execute(
            "SELECT content FROM memories WHERE owner_hash = ? ORDER BY id DESC LIMIT ?",
            (owner, limit),
        ).fetchall()
    return [row[0] for row in rows]


def remember_from_message(message: str) -> str | None:
    lowered = message.lower().strip()
    triggers = ("recuerda que", "acuérdate que", "acuerdate que", "guarda que")
    for trigger in triggers:
        if lowered.startswith(trigger):
            return message[len(trigger):].strip(" :.-")
    return None


class AuthRequest(BaseModel):
    code: str = Field(min_length=1, max_length=100)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    history: list[dict] = Field(default_factory=list, max_length=12)


class MemoryRequest(BaseModel):
    content: str = Field(min_length=1, max_length=500)


app = FastAPI(title="AI_RX")


@app.on_event("startup")
def startup() -> None:
    init_db()


async def ask_gemini(message: str, history: list[dict], memories: list[str], settings: Settings) -> str:
    if not settings.gemini_api_key:
        raise HTTPException(status_code=503, detail="Falta GEMINI_API_KEY en Render.")
    time_info = local_time()
    system_text = (
        f"{settings.system_prompt}\n\n"
        f"Fecha y hora real del servidor: {time_info['readable']} ({time_info['timezone']}).\n"
        "Si el usuario pregunta por hoy, manana, ayer, fecha u hora, usa ese dato."
    )
    if memories:
        system_text += "\n\nRecuerdos guardados del usuario:\n" + "\n".join(f"- {m}" for m in memories[:12])
    contents = []
    for item in history[-8:]:
        role = "model" if item.get("role") == "assistant" else "user"
        text = str(item.get("content", "")).strip()
        if text:
            contents.append({"role": role, "parts": [{"text": text[:4000]}]})
    contents.append({"role": "user", "parts": [{"text": message}]})
    payload = {
        "systemInstruction": {"parts": [{"text": system_text}]},
        "contents": contents,
        "generationConfig": {"temperature": 0.45, "maxOutputTokens": 768},
    }
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent",
            params={"key": settings.gemini_api_key},
            json=payload,
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="Gemini no respondio correctamente. Revisa GEMINI_API_KEY.")
    data = response.json()
    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    reply = "".join(str(part.get("text", "")) for part in parts).strip()
    if not reply:
        raise HTTPException(status_code=502, detail="Gemini devolvio una respuesta vacia.")
    return reply


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return HTML


@app.get("/install", response_class=HTMLResponse)
def install() -> str:
    return HTML


@app.get("/api/health")
def health(settings: Settings = Depends(get_settings)) -> dict:
    return {
        "status": "ok",
        "ai_name": settings.ai_name,
        "provider": "gemini",
        "model": settings.gemini_model,
        "configured": bool(settings.gemini_api_key),
        "version": APP_VERSION,
        "uptime_seconds": int(time.time() - STARTED_AT),
    }


@app.get("/api/time")
def api_time() -> dict:
    return local_time()


@app.post("/api/auth")
def auth(payload: AuthRequest, settings: Settings = Depends(get_settings)) -> dict:
    if not valid_code(payload.code, settings):
        raise HTTPException(status_code=401, detail="Codigo de acceso incorrecto.")
    now = datetime.now(ZoneInfo("America/Chicago"))
    token = secrets.token_urlsafe(32)
    role = "owner" if hmac.compare_digest(payload.code, settings.owner_code) else "user"
    SESSIONS[token] = (owner_hash(payload.code, settings), now + SESSION_DURATION, role)
    return {"authenticated": True, "token": token, "role": role, "expires_in_seconds": int(SESSION_DURATION.total_seconds())}


@app.get("/api/memories")
def get_memories(owner: str = Depends(require_session)) -> dict:
    return {"memories": list_memories(owner)}


@app.post("/api/memories")
def post_memory(payload: MemoryRequest, owner: str = Depends(require_session)) -> dict:
    created = add_memory(owner, payload.content)
    return {"created": created, "memories": list_memories(owner)}


@app.post("/api/chat")
async def chat(payload: ChatRequest, owner: str = Depends(require_session), settings: Settings = Depends(get_settings)) -> dict:
    remembered = remember_from_message(payload.message)
    memory_saved = add_memory(owner, remembered) if remembered else False
    memories = list_memories(owner)
    reply = await ask_gemini(payload.message, payload.history, memories, settings)
    with sqlite3.connect(DB_PATH, timeout=5) as db:
        db.execute("INSERT INTO messages(owner_hash, role, content) VALUES(?, 'user', ?)", (owner, payload.message))
        db.execute("INSERT INTO messages(owner_hash, role, content) VALUES(?, 'assistant', ?)", (owner, reply))
    return {"reply": reply, "provider": "gemini", "model": settings.gemini_model, "memory_saved": memory_saved}


HTML = r'''
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover,interactive-widget=overlays-content" />
  <title>AI_RX</title>
  <style>
    :root { color-scheme: dark; --bg:#060914; --card:#11172a; --line:#263055; --text:#f4f7ff; --muted:#9da8c7; --accent:#7657ff; --accent2:#16d4ff; --bad:#ff5d7a; }
    * { box-sizing:border-box; }
    body { margin:0; min-height:100svh; font-family:system-ui,-apple-system,Segoe UI,sans-serif; background:radial-gradient(circle at top,#172142,#060914 55%); color:var(--text); display:flex; }
    .app { width:min(920px,100%); min-height:100svh; margin:auto; display:flex; flex-direction:column; padding:clamp(12px,3vw,24px); gap:12px; }
    .card { background:rgba(17,23,42,.86); border:1px solid rgba(255,255,255,.09); border-radius:24px; box-shadow:0 22px 80px rgba(0,0,0,.36); }
    #login { margin:auto; width:min(460px,100%); padding:28px; text-align:center; }
    .logo { width:54px; height:54px; margin:auto; border-radius:16px; display:grid; place-items:center; background:linear-gradient(135deg,var(--accent),var(--accent2)); font-weight:900; font-size:26px; }
    h1 { margin:14px 0 4px; font-size:28px; }
    p { color:var(--muted); }
    input, textarea, button { width:100%; border:0; border-radius:16px; font:inherit; }
    input, textarea { background:#080d1d; color:var(--text); border:1px solid #35406e; padding:15px; outline:none; }
    button { cursor:pointer; color:white; background:linear-gradient(135deg,var(--accent),#5848ef); padding:14px 16px; font-weight:800; }
    button.secondary { background:#18213d; border:1px solid #35406e; }
    .row { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-top:10px; }
    .error { color:var(--bad); min-height:24px; }
    #main { display:none; flex:1; min-height:0; }
    header { display:flex; align-items:center; justify-content:space-between; padding:14px 16px; gap:10px; }
    .status { color:var(--muted); font-size:13px; }
    #chat { flex:1; overflow:auto; padding:14px; display:flex; flex-direction:column; gap:12px; min-height:45svh; }
    .msg { max-width:88%; padding:12px 14px; border-radius:18px; line-height:1.45; white-space:pre-wrap; }
    .user { align-self:flex-end; background:linear-gradient(135deg,#7157ff,#4d46e9); }
    .bot { align-self:flex-start; background:#121a31; border:1px solid #263055; }
    form { display:flex; gap:10px; padding:12px; }
    textarea { resize:none; min-height:54px; max-height:140px; }
    form button { width:92px; flex:none; }
    .tiny { font-size:12px; color:var(--muted); padding:0 14px 12px; }
    @media (max-width:640px) { .app{padding:10px;} #login{min-height:calc(100svh - 20px); display:flex; flex-direction:column; justify-content:center;} form{position:sticky;bottom:0;background:rgba(6,9,20,.94);backdrop-filter:blur(16px);} .msg{max-width:94%;} }
  </style>
</head>
<body>
  <div class="app">
    <section id="login" class="card">
      <div class="logo">RX</div>
      <h1>AI_RX</h1>
      <p>Acceso requerido. Usa un codigo autorizado.</p>
      <input id="code" placeholder="codigo_0000" autocomplete="off" />
      <div class="row">
        <button id="owner" type="button">Dueno</button>
        <button id="user" type="button" class="secondary">Usuario</button>
      </div>
      <button id="enter" type="button" style="margin-top:10px">Entrar</button>
      <div id="login-error" class="error"></div>
    </section>
    <section id="main" class="card">
      <header>
        <div><strong id="name">AI_RX</strong><div class="status" id="status">Conectando...</div></div>
        <button id="logout" class="secondary" style="width:auto">Salir</button>
      </header>
      <div class="tiny" id="clock"></div>
      <main id="chat"></main>
      <form id="form">
        <textarea id="prompt" placeholder="Escribe algo para AI_RX..."></textarea>
        <button>Enviar</button>
      </form>
      <div class="tiny">Tip: escribe "recuerda que ..." para guardar memoria.</div>
    </section>
  </div>
<script>
const $ = id => document.getElementById(id);
let token = localStorage.getItem('ai_rx_token') || '';
let history = [];
function add(role, text){ const d=document.createElement('div'); d.className='msg '+(role==='user'?'user':'bot'); d.textContent=text; $('chat').appendChild(d); $('chat').scrollTop=$('chat').scrollHeight; history.push({role:role==='bot'?'assistant':'user', content:text}); history=history.slice(-10); }
async function health(){ try{ const r=await fetch('/api/health'); const j=await r.json(); $('name').textContent=j.ai_name; $('status').textContent=j.configured?'Lista · Gemini · Render':'Falta GEMINI_API_KEY en Render'; }catch{$('status').textContent='Servidor sin conexion';} }
async function tick(){ try{ const r=await fetch('/api/time'); const j=await r.json(); $('clock').textContent='Hora real: '+j.readable; }catch{} }
function showMain(){ $('login').style.display='none'; $('main').style.display='flex'; health(); tick(); setInterval(tick,1000); if(!$('chat').children.length)add('bot','Hola, soy AI_RX. Ya estoy en Render Free.'); }
async function login(code){ $('login-error').textContent=''; try{ const r=await fetch('/api/auth',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code})}); const j=await r.json(); if(!r.ok) throw new Error(j.detail||'No autorizado'); token=j.token; localStorage.setItem('ai_rx_token',token); showMain(); }catch(e){ $('login-error').textContent=e.message; } }
$('owner').onclick=()=>{ $('code').value='codigo_0000'; login('codigo_0000'); };
$('user').onclick=()=>{ $('code').value='ambu_perro'; login('ambu_perro'); };
$('enter').onclick=()=>login($('code').value.trim());
$('logout').onclick=()=>{ localStorage.removeItem('ai_rx_token'); location.reload(); };
$('form').onsubmit=async e=>{ e.preventDefault(); const msg=$('prompt').value.trim(); if(!msg)return; $('prompt').value=''; add('user',msg); const typing=document.createElement('div'); typing.className='msg bot'; typing.textContent='Pensando...'; $('chat').appendChild(typing); try{ const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json','X-Access-Code':token},body:JSON.stringify({message:msg,history})}); const j=await r.json(); if(!r.ok) throw new Error(j.detail||'Error'); typing.remove(); add('bot',j.reply); }catch(err){ typing.textContent='Error: '+err.message; } };
if(token) showMain(); else health();
</script>
</body>
</html>
'''
