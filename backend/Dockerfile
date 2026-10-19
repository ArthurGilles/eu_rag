FROM python:3.12-slim

# 1. Récupération du binaire uv
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /uvx /bin/

WORKDIR /app

# 2. Variables d'environnement pour Python et uv
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Force uv à copier les fichiers plutôt que d'utiliser des hard links (évite les bugs sous Docker)
    UV_LINK_MODE=copy \
    # Précompile le bytecode lors de l'installation pour un démarrage plus rapide
    UV_COMPILE_BYTECODE=1

# 3. Copie des fichiers de définition des dépendances
COPY pyproject.toml uv.lock ./

# 4. Installation des dépendances avec uv sync
# - --locked : échoue si uv.lock n'est pas à jour avec pyproject.toml
# - --no-install-project : installe uniquement les paquets externes, pas votre propre code
# - --mount=type=cache : conserve le cache des wheels entre deux builds Docker
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project

# 5. Place le virtualenv créé par uv (/app/.venv) en priorité dans le PATH
ENV PATH="/app/.venv/bin:$PATH"

# 6. Copie du code source
COPY . .

# 7. Finalisation de la synchro pour installer l'application courante
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

EXPOSE 8000

CMD ["fastapi", "run", "src/backend/main.py", "--host", "0.0.0.0", "--port", "8000"]