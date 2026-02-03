# VejaPRO Backend (Core MVP)

## Įgyvendinimo žurnalas

- 2026-02-03: Sukurtas `backend/` stuburas ir pagrindinė struktūra.

## Struktūra

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── api/
│   │   ├── __init__.py
│   │   └── v1/
│   │       ├── __init__.py
│   │       └── projects.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   └── dependencies.py
│   ├── models/
│   │   ├── __init__.py
│   │   └── project.py
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── project.py
│   ├── services/
│   │   ├── __init__.py
│   │   └── project_service.py
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── logger.py
│   │   └── pdf_gen.py
│   └── migrations/
├── alembic.ini
├── requirements.txt
├── .env
└── .gitignore
```
