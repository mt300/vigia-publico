# Imagem do dashboard PUBLICO (Vigia Publico) - so o que app_public.py precisa.
# Nao inclui anthropic/httpx/tenacity (ver src/vigia_publico/dashboard/requirements.txt)
# nem ANTHROPIC_API_KEY - fisicamente incapaz de rodar ingestao/analise LLM.
FROM python:3.12-slim

WORKDIR /app

RUN groupadd -r app && useradd -r -g app app

# So src/ - nao precisa de pyproject.toml/README.md (requirements.txt nao
# pip-instala o pacote local, ver comentario nele) - e requirements.txt
# primeiro (muda pouco) pra cachear a camada de pip install; public_data
# (muda todo mes) entra por ultimo.
COPY src ./src

RUN pip install --no-cache-dir -r src/vigia_publico/dashboard/requirements.txt

# .streamlit/config.toml (tema) - Streamlit le do cwd (WORKDIR /app), sem
# isso o container sobe com o tema azul/branco padrao em vez da marca.
COPY .streamlit ./.streamlit
COPY public_data ./public_data

RUN chown -R app:app /app
USER app
# `useradd -r` (sistema) nao cria /home/app - sem isso, o Streamlit tenta
# escrever config/telemetria (~/.streamlit/credentials.toml) num diretorio
# que nao existe/nao e gravavel e falha com PermissionError em runtime (so
# aparece nos logs, o healthcheck HTTP nao pega). /app ja e do usuario app.
ENV HOME=/app

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1

ENTRYPOINT ["streamlit", "run", "src/vigia_publico/dashboard/app_public.py", "--server.port=8501", "--server.address=0.0.0.0"]
