"""Rellena y envía el Google Form con Playwright, una fila a la vez.

Uso (lo lanza app.py, pero también sirve a mano):
    python runner.py cola.json --form-url <URL> [--dry-run]
"""
import argparse
import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ENVIADOS = Path("enviados.txt")
ERRORES = Path("errores")


def bloque(page, titulo):
    return (page.locator('div[role="listitem"]')
            .filter(has_text=re.compile(rf"^\s*{re.escape(titulo)}")).first)


def texto(page, titulo, valor):
    if valor == "" or valor is None:
        return
    bloque(page, titulo).locator("input[type=text], textarea").first.fill(str(valor))


def dropdown(page, titulo_o_bloque, valor, intentos=3):
    nombre = titulo_o_bloque if isinstance(titulo_o_bloque, str) else "desplegable"
    b = bloque(page, titulo_o_bloque) if isinstance(titulo_o_bloque, str) else titulo_o_bloque
    for _ in range(intentos):
        b.scroll_into_view_if_needed()
        b.locator('[role="listbox"]').first.click()
        opcion = b.locator(f'[role="option"][data-value="{valor}"]:visible').first
        opcion.wait_for(state="visible", timeout=5_000)
        page.wait_for_timeout(300)          # deja terminar la animación del popup
        opcion.click()
        page.wait_for_timeout(300)
        elegida = b.locator('[role="option"][aria-selected="true"]').first
        if elegida.count() and elegida.get_attribute("data-value") == valor:
            return
    print(f"AVISO: no pude confirmar '{valor}' en {nombre}", flush=True)


def fecha(page, titulo, iso):
    bloque(page, titulo).locator('input[type="date"]').fill(iso)


def hora(page, titulo, hhmm):
    h24, mm = map(int, hhmm.split(":"))
    ampm = "AM" if h24 < 12 else "PM"
    h12 = h24 % 12 or 12
    b = bloque(page, titulo)
    inputs = b.locator("input")
    inputs.nth(0).fill(str(h12))
    inputs.nth(1).fill(f"{mm:02d}")
    dropdown(page, b, ampm)


def llenar(page, f, responsable):
    dropdown(page, "Cliente", f["cliente"])
    dropdown(page, "Horario atención", f["horario"])
    dropdown(page, "Tipo", f["tipo"])
    texto(page, "Campaña", f["campana"])
    texto(page, "Descripción", f["descripcion"])
    dropdown(page, "Responsable", responsable)
    dropdown(page, "Estado", f["estado"])
    fecha(page, "Fecha de creación", f["fecha_creacion"])
    hora(page, "Hora de creación", f["hora_creacion"])
    if f["estado"] == "Cerrado":
        fecha(page, "Fecha de cierre", f["fecha_cierre"])
        hora(page, "Hora de cierre", f["hora_cierre"])
    texto(page, "Ticket", f["ticket"])
    texto(page, "Observaciones", f["observaciones"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cola")
    ap.add_argument("--form-url", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data = json.loads(Path(args.cola).read_text(encoding="utf-8"))
    responsable = data["responsable"]
    filas = data["filas"]
    if args.dry_run:
        filas = filas[:1]
    ERRORES.mkdir(exist_ok=True)

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir="./google_session",
            channel="chrome",          # Chrome real: Google bloquea menos el login
            headless=False,
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
            no_viewport=True,
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(args.form_url)
        print("Si Google pide login, inicia sesión en la ventana (tienes 5 min)...", flush=True)
        page.wait_for_selector('div[role="listitem"]', timeout=300_000)

        ok = fail = 0
        for i, f in enumerate(filas, 1):
            etiqueta = f'{i}/{len(filas)} {f["cliente"]} {f["fecha_creacion"]}'
            try:
                page.goto(args.form_url)
                page.wait_for_selector('div[role="listitem"]')
                llenar(page, f, responsable)
                if args.dry_run:
                    print(f"DRY-RUN {etiqueta}: formulario llenado, NO enviado. "
                          "Revisa la ventana (20 s).", flush=True)
                    page.wait_for_timeout(20_000)
                    continue
                page.get_by_role("button", name=re.compile("^(Enviar|Submit)$")).click()
                page.wait_for_url("**/formResponse*", timeout=30_000)
                with ENVIADOS.open("a", encoding="utf-8") as fh:
                    fh.write(f["clave"] + "\n")
                ok += 1
                print(f"OK {etiqueta}", flush=True)
            except Exception as e:  # sigue con la siguiente fila
                fail += 1
                shot = ERRORES / f"fila_{i}.png"
                try:
                    page.screenshot(path=str(shot), full_page=True)
                except Exception:
                    pass
                print(f"ERROR {etiqueta}: {type(e).__name__}: {str(e)[:200]} (captura: {shot})",
                      flush=True)
        print(f"FIN ok={ok} error={fail}", flush=True)
        ctx.close()


if __name__ == "__main__":
    sys.exit(main())
