# ReadyLab — Instrucciones

## Instalación (una sola vez)

Abre la terminal y ejecuta estos comandos uno por uno:

```bash
unzip readylab_final.zip
cd readylab
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py shell < lab/seed.py
```

En Windows cambia `source venv/bin/activate` por `venv\Scripts\activate`.

---

## Arrancar el servidor

Cada vez que quieras usar ReadyLab:

```bash
cd readylab
source venv/bin/activate
python manage.py runserver
```

Abre http://localhost:8000 en tu navegador. Eso es todo.

---

## Configurar WhatsApp

Edita el archivo `readylab/settings.py` y busca esta línea:

```python
READYLAB_MESSAGING = "twilio"
```

Opciones:
- `"console"` → los mensajes solo se muestran en la terminal (para probar sin WhatsApp)
- `"twilio"` → envía WhatsApp real (necesitas cuenta de Twilio)
- `"whatsapp_link"` → abre WhatsApp Web con el mensaje listo para enviar

Si usas Twilio, pega tu Auth Token en la línea que dice:
```python
TWILIO_AUTH_TOKEN = ""   # ← PEGA TU AUTH TOKEN AQUÍ
```

---

## Hacer el demo en vivo

### Terminal 1 — Servidor (déjalo corriendo)

```bash
python manage.py runserver
```

### Terminal 2 — Crear el demo

```bash
python manage.py demo_protocol --name "María García" --phone "+51987379193"
```

Eso es todo. No necesitas hacer nada más.

### Qué pasa automáticamente

El sistema envía los mensajes solo. Tú solo miras:

| Tiempo | Qué pasa |
|--------|----------|
| Ahora | Se envía: "👋 ¡Bienvenido a ReadyLab!" |
| +2 min | Se envía: "🍽️ ¿Ya almorzaste?" con 3 opciones |
| +4 min | Se envía: "🌙 ¿Ya cenaste?" con 3 opciones |
| +6 min | Se envía: "⏰ Tu ayuno está por comenzar" |

Los mensajes aparecen en la terminal del servidor.
El dashboard (http://localhost:8000) se actualiza solo.

### Cómo responder como paciente

El comando `demo_protocol` te imprime links como estos:

```
http://localhost:8000/meal-check/TOKEN/?response=light
http://localhost:8000/meal-check/TOKEN/?response=normal
http://localhost:8000/meal-check/TOKEN/?response=high_fat
```

Abre uno de esos links en tu navegador o celular. La respuesta se registra automáticamente en el sistema y el dashboard se actualiza.

Si respondes "high_fat" en la cena:
- El ayuno sube de 12h a 14h
- El riesgo cambia a Elevated
- Todo se ve en el dashboard al instante

---

## Si algo no funciona

| Problema | Solución |
|----------|----------|
| "No module named django" | Activa el entorno virtual: `source venv/bin/activate` |
| Dashboard vacío | Carga datos: `python manage.py shell < lab/seed.py` |
| WhatsApp no llega | Verifica que enviaste el código al sandbox de Twilio |
| Links no abren desde celular | Usa `python manage.py runserver 0.0.0.0:8000` y abre con la IP de tu computadora |
| Quiero empezar de cero | `rm db.sqlite3` y repite desde `python manage.py migrate` |
