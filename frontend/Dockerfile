FROM node:24-alpine

WORKDIR /app

# 1. Activation de pnpm via Corepack
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
RUN corepack enable

# 2. Copie des manifestes et du lockfile pnpm
COPY package.json pnpm-lock.yaml ./

# 3. Installation stricte avec cache BuildKit
# --frozen-lockfile équivaut au --frozen d'uv : refuse l'install si le lockfile n'est pas à jour
RUN --mount=type=cache,id=pnpm,target=/pnpm/store \
    pnpm install --frozen-lockfile

# 4. Copie du code source
COPY . .

EXPOSE 5173

# 5. Lancement avec écoute sur toutes les interfaces (0.0.0.0)
CMD ["pnpm", "run", "dev", "--host", "0.0.0.0"]