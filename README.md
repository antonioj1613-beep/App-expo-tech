# Learning Skills — Django

Aplicación web para practicar inglés: escucha, lectura, escritura, vocabulario y conversación por voz con tutores de IA (Miles y Maya).

## Inicio rápido (un solo comando)

```powershell
cd learning-skills-restored
.\start.ps1
```

Abre **http://127.0.0.1:8000/** — inicia sesión y entra en **Speaking** desde el menú lateral o en **Levels → Speaking**.

La primera ejecución instala las dependencias de Python automáticamente. Después, `start.ps1` tarda solo unos segundos.

### Qué hace `start.ps1`

1. Instala las dependencias de Django con tu Python del sistema  
2. Aplica las migraciones de la base de datos  
3. Arranca Django en el **puerto 8000** — Speaking está en `/speaking/`  

## Inicio manual

```powershell
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_skills
python manage.py runserver
```

## Panel de administración

```powershell
python manage.py createsuperuser
```

http://127.0.0.1:8000/admin/

Desde el admin puedes ver y editar usuarios, perfiles, habilidades, progreso por habilidad y sesiones de Speaking.

## Base de datos y progreso

El panel y las estadísticas leen datos reales de SQLite:

| Dato | Origen |
|------|--------|
| XP total, precisión media, horas de estudio | `UserProfile` (actualizado al guardar sesiones de Speaking) |
| Progreso por habilidad | `UserSkillProgress` (Listening, Reading, Writing, Vocabulary, Speaking) |
| Sesiones de voz | `SpeakingSession` (transcripción, XP, duración) |

Tras migrar, ejecuta una vez:

```powershell
python manage.py seed_skills
```

## Ollama (opcional — respuestas más naturales del tutor)

```powershell
ollama pull llama3.2
```

Si Ollama está instalado y en marcha (`http://127.0.0.1:11434`), Speaking usa el modelo local. Si no, funciona con preguntas integradas.

## Navegador

Usa **Chrome o Edge** en la página de Speaking (grabación y transcripción de voz).

## Estructura del proyecto

```
learning-skills-restored/
├── start.ps1                 ← ejecutar esto
├── dev.ps1                   ← alias de start.ps1
├── requirements.txt
├── scripts/
│   ├── save-to-github.ps1    ← guarda cambios en GitHub
│   └── setup-scheduled-save.ps1  ← programar guardado diario 17:00
├── app/
│   ├── models.py             ← User, UserProfile, Skill, progreso, sesiones
│   ├── stats_service.py
│   ├── speaking_views.py
│   └── templates/
└── lisa/                     ← configuración Django
```

## Guardado automático en GitHub

Para subir cambios **de lunes a viernes a las 17:00** (hora local de tu PC):

```powershell
.\scripts\setup-scheduled-save.ps1
```

Para guardar manualmente en cualquier momento:

```powershell
.\scripts\save-to-github.ps1
```

Repositorio: [App-expo-tech](https://github.com/antonioj1613-beep/App-expo-tech)

## Despliegue

Consulta `PRODUCTION.md` para producción.
