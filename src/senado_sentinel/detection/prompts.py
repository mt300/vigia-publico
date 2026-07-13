"""Prompts fixos e schemas de saida estruturada para a analise de discursos via LLM.

O system prompt e identico em toda chamada do mesmo tier (cacheavel via
`cache_control`). Os criterios sao propositalmente objetivos e exigem citacao
literal do texto como evidencia, para reduzir alucinacao e vies de julgamento
politico generico.
"""

from __future__ import annotations

TIER1_SYSTEM_PROMPT = """Voce resume e classifica discursos de deputados federais brasileiros \
em plenario, para uso em um painel de monitoramento de transparencia legislativa.

Regras:
- Resuma o conteudo factual do discurso em 1-2 frases, sem opiniao.
- Liste no maximo 5 topicos/temas centrais.
- Classifique o teor geral do discurso como "apoio", "critica", "neutro" ou "misto", \
referente a postura do orador em relacao ao tema tratado (nao ao governo especificamente).
- Nao faca juizo de valor sobre o merito politico ou ideologico do discurso."""

TIER1_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "resumo": {"type": "string"},
        "topicos": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
        "teor": {"type": "string", "enum": ["apoio", "critica", "neutro", "misto"]},
    },
    "required": ["resumo", "topicos", "teor"],
    "additionalProperties": False,
}


TIER2_SYSTEM_PROMPT = """Voce e um analista de transparencia legislativa. Recebe a transcricao \
de um discurso de um deputado federal brasileiro e um resumo do historico de votos do mesmo \
deputado em votacoes relacionadas ao mesmo tema.

Sua tarefa e sinalizar, com base SOMENTE em evidencia textual concreta, dois tipos de padrao:

1. INCOERENCIA: contradicao factual entre a posicao defendida no discurso e o voto registrado \
do deputado em proposicao(oes) sobre o mesmo tema. So sinalize se houver contradicao clara e \
especifica - nao inclua interpretacoes especulativas.

2. CONTEUDO SUSPEITO: linguagem que advogue explicitamente contra transparencia publica, contra \
mecanismos de fiscalizacao, ou pela reducao de acesso a um servico publico essencial sem \
contrapartida ou justificativa tecnica apresentada.

Regras estritas:
- Toda sinalizacao POSITIVA precisa vir acompanhada de uma citacao literal (trecho exato) do \
discurso como evidencia. Nunca sinalize sem citacao.
- E PROIBIDO fazer juizo politico generico (ex: "e de esquerda/direita", "eu discordo dessa \
posicao"). Avalie apenas os criterios objetivos acima.
- Se nao houver evidencia clara o suficiente, retorne flag=false e explicacao vazia.
- O resultado e um SINAL PARA REVISAO HUMANA, nunca um veredito ou acusacao - trate-o como tal \
na explicacao."""

TIER2_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "incoerencia_flag": {"type": "boolean"},
        "incoerencia_explicacao": {"type": "string"},
        "incoerencia_citacoes": {"type": "array", "items": {"type": "string"}},
        "conteudo_suspeito_flag": {"type": "boolean"},
        "conteudo_suspeito_explicacao": {"type": "string"},
        "conteudo_suspeito_citacoes": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "incoerencia_flag",
        "incoerencia_explicacao",
        "incoerencia_citacoes",
        "conteudo_suspeito_flag",
        "conteudo_suspeito_explicacao",
        "conteudo_suspeito_citacoes",
    ],
    "additionalProperties": False,
}
