# Redmine → Chattigo Support

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
streamlit run app.py
```

1. Sube el Excel → revisa la tabla (edita Estado, Ticket, horas, lo que quieras).
2. Escribe el usuario y la contraseña del panel. No se guardan en `cola.json`.
3. "Probar 1 fila" → se abre Chrome, inicia sesión, llena la primera fila y NO guarda.
4. "Guardar filas marcadas" → guarda una por una; las exitosas se anotan en `enviados.txt`
   y quedan desmarcadas si vuelves a subir el mismo Excel.

La fecha del caso es la fecha de creación. Horas, cierre y observaciones se ven en la tabla
y no se envían al panel.

Si falla alguna fila: captura en `errores/fila_N.png`.
Para cambiar nombres de clientes: `ALIAS_REDMINE_A_FORM` y `NOMBRE_EN_PANEL` en `mapeo.py`.

Una vez instalado todo, el comando de ejecución es: `streamlit run app.py`
