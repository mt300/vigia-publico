# Vigia Público

*Desenvolvido por [MWebS](https://www.mwebs.com.br).*

Monitor mensal de gastos, presenca e discursos dos deputados federais brasileiros,
usando a API publica de Dados Abertos da Camara dos Deputados
(`dadosabertos.camara.leg.br`). Detecta padroes suspeitos (outliers de gasto,
incoerencia entre discurso e voto, discursos com possivel conteudo contra o
interesse publico) e gera um relatorio Markdown por mes.

> Escopo atual: Camara dos Deputados (nao o Senado) - o nome "Vigia Público"
> foi escolhido de propósito pra nao ficar preso a uma casa legislativa so,
> caso o Senado (ou outras esferas) entre no escopo no futuro. O diretorio no
> disco ainda se chama `senado-sentinel` por legado (nome interno anterior);
> o pacote Python e o nome do projeto ja sao `vigia_publico`/`vigia-publico`.

## Setup

```
uv sync
copy .env.example .env      REM preencha ANTHROPIC_API_KEY para a analise de discursos
```

## Uso

```
uv run python -m vigia_publico.cli backfill              # ingestao inicial (demorado, rode uma vez)
uv run python -m vigia_publico.cli backfill --limite 5    # so 5 deputados, para testar
uv run python -m vigia_publico.cli run-all                # update + detect + report do mes anterior
uv run python -m vigia_publico.cli report --mes-referencia 2024-03
```

Sem `ANTHROPIC_API_KEY` configurada, o pipeline roda normalmente mas pula a
analise de discursos via LLM (so as regras estatisticas de gasto/faltas/troca
de partido rodam).

## Dashboard

```
uv run streamlit run src/vigia_publico/dashboard/app.py
```

Abre um dashboard local no navegador (`scripts\run_dashboard.bat` faz o mesmo).
Filtros por periodo, partido, UF e deputado na barra lateral; abas para
achados, gastos, presenca/votos e perfil do deputado.

## Agendamento mensal (Windows Task Scheduler)

```
schtasks /Create /SC MONTHLY /D 5 /TN "VigiaPublico_Mensal" /TR "\"D:\projects\MWEBS-AUTOMATION\claude-project\senado-sentinel\scripts\run_monthly.bat\"" /ST 03:00
```

Isso roda `scripts\run_monthly.bat` todo dia 5 do mes as 03:00, processando o
mes anterior (ja fechado). Teste o `.bat` manualmente antes de agendar.

## Escopo e limitacoes conhecidas

- Universo de dados: os deputados EM EXERCICIO agora, com o historico completo
  de TODOS os mandatos federais anteriores deles (nao o histórico de todo
  mundo que ja passou pela Camara).
- A API nao expoe um campo formal de motivo de ausencia por votacao - a
  ausencia e inferida por exclusao (deputado nao aparece entre os votos
  registrados de uma votacao nominal), cruzada com o status oficial do
  deputado na data (falta durante "Licenca" registrada nao conta pro
  alerta). Ainda assim e uma aproximacao para casos-limite. Ver
  `detection/statistical.py`.
- Achados gerados por LLM sao sinais heuristicos para revisao humana, nunca
  veredito ou acusacao.
- Fase 2 (redes sociais) ainda nao implementada - os links ja sao coletados e
  armazenados em `deputado_redes_sociais` para uso futuro.

## Ideias futuras (precisam de dados externos)

Analises que agregariam bastante mas exigem importar uma base de dados nova,
fora do escopo atual (so API da Camara):

- **CNPJ do fornecedor x Receita Federal**: idade da empresa, capital social,
  quadro societario - para detectar fornecedor "de fachada" recem-aberto ou
  com socios em comum entre varios fornecedores usados pelo mesmo deputado.
- **Doacoes de campanha (TSE)**: cruzar doador de campanha x fornecedor de
  despesa parlamentar x tema de voto - provavelmente a analise mais reveladora
  de todas, mas exige importar e casar uma base de dados totalmente nova
  (prestacao de contas eleitorais do TSE).
- **Proposicoes/projetos de lei**: nao e um dado externo de verdade (vem da
  mesma API da Camara, endpoint `/proposicoes`, so ainda nao foi ingerido) -
  mas exige uma nova tabela e pipeline de ingestao. Mediria producao
  legislativa alem de discurso/voto, e permitiria cruzar tema das
  proposicoes com tema dos discursos e com fornecedores de despesa do mesmo
  setor.

---

Desenvolvido por [MWebS](https://www.mwebs.com.br).
