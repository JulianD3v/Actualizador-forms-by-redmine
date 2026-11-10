"""Entra al panel de Chattigo y guarda un caso por fila.

Uso (lo lanza app.py, pero también sirve a mano):
    python runner.py cola.json --form-url <URL> [--dry-run]

Usuario y contraseña van por el entorno: SOPORTE_USUARIO y SOPORTE_CLAVE.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

from mapeo import norm, nombre_en_panel

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ENVIADOS = Path("enviados.txt")
ERRORES = Path("errores")


def formulario_alta(page):
    return page.locator("form").filter(
        has=page.get_by_role("button", name=re.compile(r"^Guardar caso$"))
    ).first


def iniciar_sesion(page, usuario, clave):
    page.locator('input[type="email"]').fill(usuario)
    page.locator('input[type="password"]').fill(clave)
    page.get_by_role("button", name="INGRESAR AL PANEL").click()
    handle = page.wait_for_function(
        """() => {
            const swal = document.querySelector('.swal2-popup');
            if (swal && /incorrectos/i.test(swal.innerText || '')) return 'bad';
            const ok = [...document.querySelectorAll('h2')].some(
                n => (n.textContent || '').trim() === 'Nuevo caso');
            return ok ? 'ok' : false;
        }""",
        timeout=60_000,
    )
    return handle.json_value() == "ok"


def abrir_formulario(page, url, usuario, clave):
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_selector('input[type="email"], h2', timeout=30_000)
    if page.locator('input[type="email"]').is_visible():
        if not iniciar_sesion(page, usuario, clave):
            return False
    page.get_by_role("heading", name="Nuevo caso").wait_for(timeout=30_000)
    popup = page.locator(".swal2-container")
    if popup.count() and popup.is_visible():
        try:
            popup.wait_for(state="hidden", timeout=5_000)
        except PWTimeout:
            page.keyboard.press("Escape")
    return True


def elegir_cliente(page, form, nombre):
    nombre = str(nombre).strip()
    busqueda = nombre_en_panel(nombre)
    if len(busqueda) < 3:
        raise RuntimeError(f"cliente '{nombre}' tiene menos de 3 caracteres")
    campo = form.locator(".client-field input").first
    campo.click()
    campo.fill(busqueda)
    if campo.input_value().strip() != busqueda:
        campo.press("Control+A")
        campo.press_sequentially(busqueda, delay=25)
    form.locator(".client-menu").wait_for(state="visible", timeout=8_000)
    page.wait_for_function(
        """() => {
            const form = [...document.querySelectorAll('form')].find(f =>
                [...f.querySelectorAll('button')].some(b =>
                    /Guardar caso|Guardando/.test(b.textContent || '')));
            if (!form) return false;
            const menu = form.querySelector('.client-menu');
            if (!menu) return false;
            const t = menu.innerText || '';
            if (t.includes('Buscando')) return false;
            if (t.includes('Escribe al menos 3')) return false;
            return true;
        }""",
        timeout=10_000,
    )
    if form.locator(".client-hint", has_text="Sin resultados").is_visible():
        raise RuntimeError(f"sin cliente '{busqueda}' en el panel")

    objetivo = norm(busqueda)
    opciones = form.locator(".client-option")
    candidatos = []
    vistos = []
    for i in range(opciones.count()):
        op = opciones.nth(i)
        principal = op.locator("span").first.inner_text().strip()
        vistos.append(principal)
        corto = ""
        muted = op.locator("span.text-muted")
        if muted.count():
            corto = muted.first.inner_text().replace("·", "").strip()
        if norm(principal) == objetivo or (corto and norm(corto) == objetivo):
            candidatos.append((op.locator(".inactive-tag").count() > 0, i))
    if not candidatos:
        raise RuntimeError(
            f"ninguna opción coincide con '{busqueda}' (vi: {', '.join(vistos[:8])})")
    candidatos.sort(key=lambda item: item[0])
    opciones.nth(candidatos[0][1]).click()
    form.locator(".client-menu").wait_for(state="hidden", timeout=3_000)


def llenar(page, form, f, responsable):
    elegir_cliente(page, form, f["cliente"])
    form.get_by_placeholder("Campaña o cola").fill(str(f["campana"]))
    form.locator('input[type="date"]').fill(f["fecha_creacion"])
    form.locator('input[list="support-schedules"]').fill(f["horario"])
    form.locator('input[list="support-types"]').fill(f["tipo"])
    form.locator("select").select_option(label=responsable)
    ticket = str(f.get("ticket") or "").strip()
    if ticket:
        form.get_by_placeholder("Si ya existe un ticket").fill(ticket)
    form.locator("textarea").fill(str(f["descripcion"]))
    form.locator("button.status-pick").filter(
        has_text=re.compile(rf"^{re.escape(f['estado'])}$")
    ).click()


def guardar(page, form):
    alerta = page.locator(".alert-success")
    previo = alerta.first.inner_text().strip() if alerta.count() else ""
    form.locator("button.save-btn").click()
    handle = page.wait_for_function(
        """(prev) => {
            const btn = document.querySelector('form button.save-btn');
            if (btn && /Guardando/.test(btn.textContent || '')) return false;
            const ok = document.querySelector('.alert-success');
            const okText = ok ? ok.textContent.trim() : '';
            if (okText && okText !== prev) return 'ok';
            const alta = document.querySelector('form');
            const err = alta
                ? [...alta.querySelectorAll('.invalid-feedback')]
                    .map(e => e.textContent.trim()).filter(Boolean)
                : [];
            const danger = document.querySelector('.alert-danger');
            const dangerText = danger ? danger.textContent.trim() : '';
            if (err.length || dangerText) return 'err:' + (dangerText || err.join('; '));
            return false;
        }""",
        arg=previo,
        timeout=30_000,
    )
    resultado = handle.json_value()
    if resultado != "ok":
        raise RuntimeError((resultado[4:] or "el panel no confirmó el guardado")[:200])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cola")
    ap.add_argument("--form-url", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    usuario = os.environ.get("SOPORTE_USUARIO", "").strip()
    clave = os.environ.get("SOPORTE_CLAVE", "")
    if not usuario or not clave:
        print("ERROR: faltan usuario y contraseña (SOPORTE_USUARIO / SOPORTE_CLAVE).",
              flush=True)
        return 1

    data = json.loads(Path(args.cola).read_text(encoding="utf-8"))
    responsable = data["responsable"]
    filas = data["filas"]
    if args.dry_run:
        filas = filas[:1]
    ERRORES.mkdir(exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="chrome",
            headless=False,
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
        )
        ctx = browser.new_context(no_viewport=True)
        page = ctx.new_page()
        ok = fail = 0
        try:
            for i, f in enumerate(filas, 1):
                etiqueta = f'{i}/{len(filas)} {f["cliente"]} {f["fecha_creacion"]}'
                try:
                    if not abrir_formulario(page, args.form_url, usuario, clave):
                        print("ERROR login: usuario o contraseña incorrectos.", flush=True)
                        print(f"FIN ok={ok} error={fail}", flush=True)
                        return 1
                    form = formulario_alta(page)
                    form.scroll_into_view_if_needed()
                    llenar(page, form, f, responsable)
                    if args.dry_run:
                        print(f"DRY-RUN {etiqueta}: formulario llenado, NO guardado. "
                              "Revisa la ventana (20 s).", flush=True)
                        page.wait_for_timeout(20_000)
                        continue
                    guardar(page, form)
                    with ENVIADOS.open("a", encoding="utf-8") as fh:
                        fh.write(f["clave"] + "\n")
                    ok += 1
                    print(f"OK {etiqueta}", flush=True)
                except Exception as e:
                    fail += 1
                    shot = ERRORES / f"fila_{i}.png"
                    try:
                        page.screenshot(path=str(shot), full_page=True)
                    except Exception:
                        pass
                    print(f"ERROR {etiqueta}: {type(e).__name__}: {str(e)[:200]} "
                          f"(captura: {shot})", flush=True)
        finally:
            ctx.close()
            browser.close()
    print(f"FIN ok={ok} error={fail}", flush=True)
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
