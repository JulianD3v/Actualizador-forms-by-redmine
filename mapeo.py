"""Lógica de mapeo Excel (Redmine) -> campos del panel de soporte."""
import re
import unicodedata
from datetime import datetime, timedelta

import pandas as pd

# ---------- Opciones del formulario ----------
CLIENTES_FORM = [
    "ARATI", "ARESS", "ARGOS", "BECALL", "CEO", "COCOROLLO", "COLSUBSIDIO",
    "CREDIANTIOQUIA", "COMFENALCO ANTIOQUIA", "FOOD FAIR PLANTATION", "INGENEO",
    "HDI", "MADECENTRO", "NEUROLÓGICO", "OBAMA CARE - AVE FENIX", "OSH HOTELS",
    "POLI GRANCOLOMBIANO", "SERVICREDITO", "SMARTFIT", "SURA", "TAQUERO",
    "UNICEF", "WAKEUP", "WINGO",
]
HORARIOS = ["Laboral", "No laboral", "Fin de semana", "24 horas"]
TIPOS = ["General", "Incidencia", "Requerimiento", "Consulta"]
ESTADOS = ["En proceso", "Cerrado"]
RESPONSABLES = [
    "Milena Bedoya", "Maryeiny Losada", "Duban Ramirez", "Ronal Vargas",
    "Manuela Villa", "Santiago Barahona", "Jhon Osma", "Julian Quintero",
    "Miguel García",
]


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip().upper()


# Nombre en Redmine -> nombre en el form (solo los que cambian de nombre).
# Los que no estén aquí ni en CLIENTES_FORM caen en la regla INGENEO + campaña.
ALIAS_REDMINE_A_FORM = {
    "ARGOS PANAMA": "ARGOS",
    "BECALL GROUP": "BECALL OUTSOURCING SAS",
    "SURAMERICANA": "SURA",
    "U. POLITECNICO GRAN COLOMBIANO": "POLI GRANCOLOMBIANO",
}

# Nombre corto de la tabla -> texto con el que hay que buscarlo en el panel.
NOMBRE_EN_PANEL = {
    "MADECENTRO": "Madecentro Colombia SAS",
    "POLI GRANCOLOMBIANO": "Universidad Politécnico Gran Colombiano",
}

_FORM_NORM = {norm(c): c for c in CLIENTES_FORM}
_ALIAS_NORM = {norm(k): v for k, v in ALIAS_REDMINE_A_FORM.items()}
_PANEL_NORM = {norm(k): v for k, v in NOMBRE_EN_PANEL.items()}


def nombre_en_panel(cliente: str) -> str:
    """Nombre que hay que escribir en el buscador de clientes del panel."""
    return _PANEL_NORM.get(norm(cliente), str(cliente).strip())


RX_PROYECTO = re.compile(r"\[\s*(.*?)\s*-\s*Implementaci", re.I)
RX_PROYECTO_FALLBACK = re.compile(r"\[\s*(.*?)\s*-")
RX_ID = re.compile(r"#(\d+)")


def parsear_proyecto(texto: str):
    m = RX_PROYECTO.search(texto) or RX_PROYECTO_FALLBACK.search(texto)
    nombre = m.group(1).strip() if m else str(texto).strip()
    mid = RX_ID.search(texto)
    return nombre, (mid.group(1) if mid else "")


def mapear_cliente(nombre_redmine: str):
    """Devuelve (cliente_form, campaña)."""
    k = norm(nombre_redmine)
    destino = _ALIAS_NORM.get(k) or _FORM_NORM.get(k)
    if destino:
        return destino, destino
    return "INGENEO", nombre_redmine.strip()


def fmt_hhmm(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def construir_filas(df: pd.DataFrame, hora_inicio: str = "08:00",
                    horario="Laboral", tipo="General", estado="Cerrado"):
    """Convierte el Excel en filas listas para editar/enviar.

    Hora creación/cierre: por cada fecha, la primera actividad arranca a
    `hora_inicio` y cada una dura `Hora` (decimal, 8.4 = 8h24m); la siguiente
    empieza donde terminó la anterior.
    """
    filas = []
    cursor_por_fecha = {}
    h0, m0 = map(int, hora_inicio.split(":"))
    for _, r in df.iterrows():
        fecha = pd.to_datetime(r["Fecha"]).date()
        nombre, id_redmine = parsear_proyecto(r["Proyecto / Petición"])
        cliente, campana = mapear_cliente(nombre)

        inicio = cursor_por_fecha.get(
            fecha, datetime(fecha.year, fecha.month, fecha.day, h0, m0))
        fin = inicio + timedelta(hours=float(r["Hora"]))
        cursor_por_fecha[fecha] = fin

        filas.append({
            "Enviar": True,
            "Cliente": cliente,
            "Horario atención": horario,
            "Tipo": tipo,
            "Campaña": campana,
            "Descripción": str(r["Detalle"]).strip(),
            "Estado": estado,
            "Fecha creación": fecha,
            "Hora creación": fmt_hhmm(inicio),
            "Fecha cierre": fecha,
            "Hora cierre": fmt_hhmm(fin),
            "Ticket": "",
            "Observaciones": "",
            "Redmine #": id_redmine,
            "Horas": float(r["Hora"]),
            "Cliente en Redmine": nombre,
        })
    return filas


def clave_fila(f: dict) -> str:
    """Identificador estable para no reenviar filas ya cargadas."""
    return f'{f["Fecha creación"]}|{f["Redmine #"]}|{f["Horas"]}|{f["Descripción"][:40]}'
