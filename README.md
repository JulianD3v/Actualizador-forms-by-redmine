# Redmine → Google Forms

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1

playwright install chromium     # (usa Chrome instalado; esto es el respaldo)
streamlit run app.py
```

1. Sube el Excel → revisa la tabla (edita Estado, Ticket, horas, lo que quieras).
2. "Probar 1 fila" → se abre Chrome, llena la primera fila y NO envía.
   La primera vez inicia sesión con tu cuenta @ingeneo (queda guardada en `google_session/`).
3. "Enviar filas marcadas" → envía una por una; las exitosas se anotan en `enviados.txt`
   y quedan desmarcadas si vuelves a subir el mismo Excel.

Si falla alguna fila: captura en `errores/fila_N.png`.
Para cambiar nombres de clientes: `ALIAS_REDMINE_A_FORM` en `mapeo.py`.

python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt || pip install pandas openpyxl playwright streamlit
playwright install chromium
streamlit run app.py

Una vez instalado todo el comando de ejecución es: streamlit run app.py