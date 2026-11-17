"""
Monitor PNCP x DSPACE - 15ª Cia Inf Mtz

Abre o painel do Data Studio, filtra a UGA da OM, lê todos os processos,
identifica os que estão na falta (não encontrados no DSPACE), salva no
histórico (docs/historico.json) e envia e-mail quando houver falta.

Variáveis de ambiente:
  OM_NOME             nome da UGA no painel (padrão: 15ª Cia Inf Mtz)
  GMAIL_USER          conta Gmail que envia (ex.: conf15companhia@gmail.com)
  GMAIL_APP_PASSWORD  senha de app do Google dessa conta
  EMAIL_TO            destinatário(s), separados por vírgula
"""

from __future__ import annotations

import html
import json
import os
import re
import smtplib
import sys
import time
import unicodedata
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.sync_api import Page, sync_playwright

URL = (
    "https://datastudio.google.com/u/0/reporting/"
    "71a1b697-4dd9-428d-ba8c-c2f02491324a/page/p_n01n3pu72d"
)
OM = os.getenv("OM_NOME", "15ª Cia Inf Mtz")
EMAIL_TO = os.getenv("EMAIL_TO", "conf15companhia@gmail.com")
TZ = ZoneInfo("America/Sao_Paulo")

BASE = Path(__file__).resolve().parent
HIST_JSON = BASE / "docs" / "historico.json"
HIST_JS = BASE / "docs" / "historico.js"

# JS executado na página: lê cabeçalho, linhas e paginação de cada tabela.
JS_TABELAS = r"""
() => [...document.querySelectorAll('table-wrapper')].map(tw => {
  const header = [...tw.querySelectorAll('.headerRow .headerCell')]
      .map(c => (c.querySelector('.colName')?.innerText || '').replace(/[▲▼]/g, '').trim());
  const rows = [...tw.querySelectorAll('.centerColsContainer .row')].map(r =>
      [...r.querySelectorAll('.cell')].map(c => c.innerText.trim()));
  const label = tw.querySelector('.pageControl .pageLabel')
      || tw.parentElement?.parentElement?.querySelector('.pageControl .pageLabel');
  const pag = ((label?.innerText || '').match(/(\d+)\s*-\s*(\d+)\s*\/\s*(\d+)/) || []).slice(1).map(Number);
  return {header, rows, pag};
})
"""


# JS: traz o corpo da tabela de detalhamento para a tela e devolve um ponto visível dele.
JS_PONTO_TABELA = r"""
() => {
  const tw = [...document.querySelectorAll('table-wrapper')]
      .find(t => t.querySelector('.colName[title="PNCP_TITULO"]'));
  const body = tw && tw.querySelector('.tableBody');
  if (!body) return null;
  body.scrollIntoView({block: 'center', inline: 'center'});
  const r = body.getBoundingClientRect();
  const x0 = Math.max(r.left, 0), x1 = Math.min(r.right, innerWidth);
  const y0 = Math.max(r.top, 0), y1 = Math.min(r.bottom, innerHeight);
  if (x1 <= x0 || y1 <= y0) return null;
  return [(x0 + x1) / 2, (y0 + y1) / 2];
}
"""


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().upper()


def tabela(page: Page, coluna: str) -> dict | None:
    for t in page.evaluate(JS_TABELAS):
        if coluna in t["header"]:
            return t
    return None


def para_dict(t: dict, row: list[str]) -> dict:
    return {h or f"_{i}": (row[i] if i < len(row) else "") for i, h in enumerate(t["header"])}


def numero(s: str) -> float | None:
    s = (s or "").replace("%", "").replace(".", "").replace(",", ".").strip()
    try:
        v = float(s)
    except ValueError:
        return None
    return int(v) if v.is_integer() else v


def raspar() -> dict:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": 1600, "height": 1000},
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
        )
        page.goto(URL, wait_until="domcontentloaded", timeout=120_000)
        botao_uga = page.locator("button.lego-control", has_text="UGA").first
        botao_uga.wait_for(timeout=120_000)
        page.locator("table-wrapper .centerColsContainer .row").first.wait_for(timeout=120_000)
        time.sleep(3)

        # --- filtra a UGA ---------------------------------------------------
        botao_uga.click()
        busca = page.locator("md-virtual-repeat-container, .md-virtual-repeat-scroller").first
        busca.wait_for(timeout=30_000)
        campo = page.locator("input[type=text]:visible").first
        if campo.count():
            campo.fill(OM)
            time.sleep(1.5)
        item = page.locator(f'div.item:has(md-checkbox[aria-label="{OM}"])').first
        item.wait_for(timeout=30_000)
        item.hover()
        item.locator("span.only").click()
        page.keyboard.press("Escape")

        # espera o ranking mostrar só a OM
        ranking = None
        for _ in range(60):
            time.sleep(1)
            ranking = tabela(page, "Publicados no PNCP")
            if ranking and len(ranking["rows"]) == 1 and OM in ranking["rows"][0]:
                break
        else:
            raise RuntimeError(f"Filtro da UGA '{OM}' não foi aplicado no ranking.")
        r = para_dict(ranking, ranking["rows"][0])

        # --- lê todas as linhas do detalhamento (tabela virtualizada) --------
        linhas: dict[str, dict] = {}
        total = None
        for _ in range(40):
            det = tabela(page, "PNCP_TITULO")
            if det and det["rows"] and all(OM in (row[1] if len(row) > 1 else "") for row in det["rows"]):
                if det["pag"]:
                    a, b, _tot = det["pag"]
                    total = b - a + 1
                for row in det["rows"]:
                    linhas[row[0]] = para_dict(det, row)
                if total is not None and len(linhas) >= total:
                    break
            # a tabela tem rolagem própria e só responde à roda real do mouse:
            # posiciona o mouse sobre a parte visível dela e rola
            ponto = page.evaluate(JS_PONTO_TABELA)
            if ponto:
                page.mouse.move(ponto[0], ponto[1])
                page.mouse.wheel(0, 600)
            time.sleep(1)
        if total is None or len(linhas) < total:
            raise RuntimeError(f"Leitura incompleta do detalhamento: {len(linhas)} de {total} linhas.")

        texto = page.inner_text("body")
        m = re.search(r"(?:última atualização|atualizados pela última vez):\s*([\d/]+ [\d:]+)", texto)
        browser.close()

    processos = [
        {
            "modalidade": l.get("MODALIDADE", ""),
            "titulo": l.get("PNCP_TITULO", ""),
            "link_pncp": l.get("LINK_PNCP", ""),
            "dspace": l.get("DSPACE_ENCONTRADO", ""),
            "link_dspace": l.get("LINK_DSPACE", ""),
            "status": l.get("STATUS", ""),
        }
        for _, l in sorted(linhas.items(), key=lambda kv: numero(kv[0]) or 0)
    ]
    falta = [p for p in processos if norm(p["status"]) != "ENCONTRADO"]
    return {
        "publicados_pncp": numero(r.get("Publicados no PNCP", "")),
        "no_dspace": numero(r.get("Processos no DSPACE", "")),
        "percentual": r.get("%", ""),
        "total_processos": len(processos),
        "qtd_falta": len(falta),
        "falta": [{k: p[k] for k in ("modalidade", "titulo", "link_pncp", "status")} for p in falta],
        "atualizacao_painel": m.group(1) if m else "",
    }


# --- histórico ------------------------------------------------------------------
def carregar_historico() -> list:
    if HIST_JSON.exists():
        return json.loads(HIST_JSON.read_text(encoding="utf-8") or "[]")
    return []


def salvar_historico(hist: list) -> None:
    HIST_JSON.parent.mkdir(parents=True, exist_ok=True)
    dados = json.dumps(hist, ensure_ascii=False, indent=2)
    HIST_JSON.write_text(dados + "\n", encoding="utf-8")
    HIST_JS.write_text(f"window.HISTORICO = {dados};\n", encoding="utf-8")


# --- e-mail ---------------------------------------------------------------------
def enviar_email(assunto: str, corpo_html: str) -> bool:
    user = os.getenv("GMAIL_USER", "").strip()
    senha = os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    if not user or not senha:
        print("AVISO: GMAIL_USER/GMAIL_APP_PASSWORD não configurados; e-mail não enviado.")
        return False
    destinos = [e.strip() for e in EMAIL_TO.split(",") if e.strip()]
    msg = MIMEMultipart("alternative")
    msg["Subject"] = assunto
    msg["From"] = user
    msg["To"] = ", ".join(destinos)
    msg.attach(MIMEText(corpo_html, "html", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=60) as s:
        s.login(user, senha)
        s.sendmail(user, destinos, msg.as_string())
    print(f"E-mail enviado para {', '.join(destinos)}")
    return True


def email_falta(reg: dict) -> tuple[str, str]:
    linhas = "".join(
        f"<tr><td>{i}</td><td>{html.escape(p['modalidade'])}</td>"
        f"<td>{html.escape(p['titulo'])}</td>"
        f"<td><a href=\"{html.escape(p['link_pncp'])}\">Abrir no PNCP</a></td>"
        f"<td>{html.escape(p['status'])}</td></tr>"
        for i, p in enumerate(reg["falta"], 1)
    )
    assunto = f"[PNCP x DSPACE] {OM}: {reg['qtd_falta']} processo(s) na falta - {reg['data_hora_fmt']}"
    corpo = f"""
<div style="font-family:Arial,sans-serif;font-size:14px;color:#222">
  <h2 style="color:#b42318">Processos na falta no DSPACE - {html.escape(OM)}</h2>
  <p>Consulta de <b>{reg['data_hora_fmt']}</b>
     (dados do painel: {html.escape(reg.get('atualizacao_painel') or 'n/d')}).</p>
  <ul>
    <li>Processos da OM no painel: <b>{reg['total_processos']}</b></li>
    <li>Publicados no PNCP: <b>{fmt(reg['publicados_pncp'])}</b> |
        Encontrados no DSPACE: <b>{fmt(reg['no_dspace'])}</b> ({html.escape(reg['percentual'])})</li>
    <li>Na falta: <b style="color:#b42318">{reg['qtd_falta']}</b></li>
  </ul>
  <table cellpadding="6" cellspacing="0" border="1" style="border-collapse:collapse;border-color:#ddd">
    <tr style="background:#f2f2f2"><th>#</th><th>Modalidade</th><th>Título no PNCP</th><th>Link</th><th>Status</th></tr>
    {linhas}
  </table>
  <p style="margin-top:16px">Painel: <a href="{URL}">PNCP x DSPACE 2026</a></p>
</div>"""
    return assunto, corpo


def fmt(v) -> str:
    return "n/d" if v is None else (str(int(v)) if float(v).is_integer() else str(v))


# --- principal ------------------------------------------------------------------
def main() -> int:
    agora = datetime.now(TZ)
    reg: dict = {
        "data_hora": agora.isoformat(timespec="seconds"),
        "data_hora_fmt": agora.strftime("%d/%m/%Y %H:%M"),
        "om": OM,
    }
    erro = None
    for tentativa in range(1, 4):
        try:
            reg.update(raspar())
            erro = None
            break
        except Exception as e:  # noqa: BLE001
            erro = f"{type(e).__name__}: {e}"
            print(f"Tentativa {tentativa} falhou: {erro}")
            time.sleep(20)

    reg["erro"] = erro
    reg["email_enviado"] = False
    try:
        if erro:
            reg["email_enviado"] = enviar_email(
                f"[PNCP x DSPACE] Falha na consulta de {reg['data_hora_fmt']}",
                f"<p>Não foi possível ler o painel para <b>{html.escape(OM)}</b>.</p>"
                f"<p>Erro: <code>{html.escape(erro)}</code></p>"
                f"<p>Confira manualmente: <a href=\"{URL}\">PNCP x DSPACE 2026</a></p>",
            )
        elif reg["qtd_falta"] > 0:
            reg["email_enviado"] = enviar_email(*email_falta(reg))
    except Exception as e:  # noqa: BLE001
        print(f"ERRO ao enviar e-mail: {e}")
        reg["erro_email"] = str(e)

    hist = carregar_historico()
    hist.append(reg)
    salvar_historico(hist)

    print(json.dumps(reg, ensure_ascii=False, indent=2))
    return 1 if erro or reg.get("erro_email") else 0


if __name__ == "__main__":
    sys.exit(main())
