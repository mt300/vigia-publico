# senado-sentinel

Monitor mensal de gastos, presenca e discursos dos deputados federais brasileiros,
usando a API publica de Dados Abertos da Camara dos Deputados
(`dadosabertos.camara.leg.br`). Detecta padroes suspeitos (outliers de gasto,
incoerencia entre discurso e voto, discursos com possivel conteudo contra o
interesse publico) e gera um relatorio Markdown por mes.

> Apesar do nome do diretorio, o escopo e a Camara dos Deputados (nao o Senado).

## Setup

```
uv sync
copy .env.example .env      REM preencha ANTHROPIC_API_KEY para a analise de discursos
```

## Uso

```
uv run python -m senado_sentinel.cli backfill              # ingestao inicial (demorado, rode uma vez)
uv run python -m senado_sentinel.cli backfill --limite 5    # so 5 deputados, para testar
uv run python -m senado_sentinel.cli run-all                # update + detect + report do mes anterior
uv run python -m senado_sentinel.cli report --mes-referencia 2024-03
```

Sem `ANTHROPIC_API_KEY` configurada, o pipeline roda normalmente mas pula a
analise de discursos via LLM (so as regras estatisticas de gasto/faltas/troca
de partido rodam).

## Dashboard

```
uv run streamlit run src/senado_sentinel/dashboard/app.py
```

Abre um dashboard local no navegador (`scripts\run_dashboard.bat` faz o mesmo).
Filtros por periodo, partido, UF e deputado na barra lateral; abas para
achados, gastos, presenca/votos e perfil do deputado.

## Agendamento mensal (Windows Task Scheduler)

```
schtasks /Create /SC MONTHLY /D 5 /TN "SenadoSentinel_Mensal" /TR "\"D:\projects\MWEBS-AUTOMATION\claude-project\senado-sentinel\scripts\run_monthly.bat\"" /ST 03:00
```

Isso roda `scripts\run_monthly.bat` todo dia 5 do mes as 03:00, processando o
mes anterior (ja fechado). Teste o `.bat` manualmente antes de agendar.

## Escopo e limitacoes conhecidas

- Universo de dados: os deputados EM EXERCICIO agora, com o historico completo
  de TODOS os mandatos federais anteriores deles (nao o histórico de todo
  mundo que ja passou pela Camara).
- A API nao expoe o motivo de uma falta (justificada/injustificada) em
  votacoes - a ausencia e inferida por exclusao (deputado nao aparece entre os
  votos registrados de uma votacao nominal). Ver `detection/statistical.py`.
- Achados gerados por LLM sao sinais heuristicos para revisao humana, nunca
  veredito ou acusacao.
- Fase 2 (redes sociais) ainda nao implementada - os links ja sao coletados e
  armazenados em `deputado_redes_sociais` para uso futuro.
