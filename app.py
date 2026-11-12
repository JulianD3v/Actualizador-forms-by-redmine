"""Interfaz local: sube el Excel de Redmine, revisa/edita y envía al panel de Chattigo.

    streamlit run app.py
"""
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

import mapeo

FORM_URL_DEFAULT = "https://chattigosupport.ingeneo.co/soporte"

st.set_page_config(page_title="Redmine → Chattigo", layout="wide")
st.title("Cargue masivo Redmine → Chattigo")

with st.sidebar:
    st.header("Configuración")
    form_url = st.text_input("URL del panel", FORM_URL_DEFAULT)
    usuario = st.text_input("Usuario", placeholder="admin@ingeneo.com.co")
    clave = st.text_input("Contraseña", type="password")
    responsable = st.selectbox("Responsable", mapeo.RESPONSABLES,
                               index=mapeo.RESPONSABLES.index("Julian Quintero"))
    hora_inicio = st.text_input("Hora de inicio de jornada (HH:MM, 24h)", "08:00")
    horario = st.selectbox("Horario atención por defecto", mapeo.HORARIOS)
    tipo = st.selectbox("Tipo por defecto", mapeo.TIPOS)
    estado = st.selectbox("Estado por defecto", mapeo.ESTADOS, index=1)

archivo = st.file_uploader("Excel de Redmine (hoja 'Formato Cargue')", type=["xlsx"])
if not archivo:
    st.info("Sube el archivo para ver la vista previa.")
    st.stop()

df = pd.read_excel(archivo, sheet_name="Formato Cargue").dropna(subset=["Proyecto / Petición"])
try:
    filas = mapeo.construir_filas(df, hora_inicio, horario, tipo, estado)
except ValueError as e:
    st.error(str(e))
    st.stop()

enviados = set()
if Path("enviados.txt").exists():
    enviados = set(Path("enviados.txt").read_text(encoding="utf-8").splitlines())
for f in filas:
    if mapeo.clave_fila(f) in enviados:
        f["Enviar"] = False
        f["Ya enviado"] = True
    else:
        f["Ya enviado"] = False

tabla = pd.DataFrame(filas)
n_ing = (tabla["Cliente"] == "INGENEO").sum()
st.caption(f"{len(tabla)} filas · {n_ing} caen en la regla INGENEO + campaña "
           f"· {int(tabla['Ya enviado'].sum())} ya enviadas antes (desmarcadas).")

editada = st.data_editor(
    tabla,
    use_container_width=True,
    hide_index=True,
    num_rows="fixed",
    height=520,
    column_config={
        "Enviar": st.column_config.CheckboxColumn(width="small"),
        "Cliente": st.column_config.SelectboxColumn(options=mapeo.CLIENTES_FORM, required=True),
        "Horario atención": st.column_config.SelectboxColumn(options=mapeo.HORARIOS, required=True),
        "Tipo": st.column_config.SelectboxColumn(options=mapeo.TIPOS, required=True),
        "Estado": st.column_config.SelectboxColumn(options=mapeo.ESTADOS, required=True),
        "Descripción": st.column_config.TextColumn(width="large"),
        "Fecha creación": st.column_config.DateColumn(format="DD/MM/YYYY"),
        "Fecha cierre": st.column_config.DateColumn(format="DD/MM/YYYY"),
        "Hora creación": st.column_config.TextColumn(help="HH:MM en 24 h", width="small"),
        "Hora cierre": st.column_config.TextColumn(help="HH:MM en 24 h", width="small"),
        "Ticket": st.column_config.TextColumn(help="Solo si el caso fue escalado"),
        "Redmine #": st.column_config.TextColumn(disabled=True, width="small"),
        "Horas": st.column_config.NumberColumn(disabled=True, width="small"),
        "Cliente en Redmine": st.column_config.TextColumn(disabled=True),
        "Ya enviado": st.column_config.CheckboxColumn(disabled=True, width="small"),
    },
)

st.markdown(
    "La **fecha del caso** es la fecha de creación. "
    "Horas, cierre y observaciones quedan en la tabla y no se envían al panel."
)


def a_cola(df_: pd.DataFrame):
    out = []
    for _, r in df_.iterrows():
        if not r["Enviar"]:
            continue
        f = r.to_dict()
        out.append({
            "clave": mapeo.clave_fila(f),
            "cliente": r["Cliente"], "horario": r["Horario atención"], "tipo": r["Tipo"],
            "campana": r["Campaña"], "descripcion": r["Descripción"], "estado": r["Estado"],
            "fecha_creacion": pd.to_datetime(r["Fecha creación"]).date().isoformat(),
            "hora_creacion": r["Hora creación"],
            "fecha_cierre": pd.to_datetime(r["Fecha cierre"]).date().isoformat(),
            "hora_cierre": r["Hora cierre"],
            "ticket": r["Ticket"] or "", "observaciones": r["Observaciones"] or "",
        })
    return out


c1, c2 = st.columns(2)
prueba = c1.button("Probar 1 fila (llena el caso, NO guarda)")
enviar = c2.button("Guardar filas marcadas", type="primary")

if prueba or enviar:
    if not usuario.strip() or not clave:
        st.warning("Escribe el usuario y la contraseña del panel.")
        st.stop()
    cola = a_cola(editada)
    if not cola:
        st.warning("No hay filas marcadas para enviar.")
        st.stop()
    Path("cola.json").write_text(
        json.dumps({"responsable": responsable, "filas": cola}, ensure_ascii=False),
        encoding="utf-8")
    cmd = [sys.executable, "-u", "runner.py", "cola.json", "--form-url", form_url]
    if prueba:
        cmd.append("--dry-run")
    log = st.empty()
    lineas = []
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
           "SOPORTE_USUARIO": usuario.strip(), "SOPORTE_CLAVE": clave}
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace", env=env)
    for linea in proc.stdout:
        lineas.append(linea.rstrip())
        log.code("\n".join(lineas[-30:]))
    proc.wait()
    st.success("Proceso terminado. Revisa el log; las filas OK quedan registradas en enviados.txt.")
