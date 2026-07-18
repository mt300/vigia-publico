"""Reescreve achados em linguagem neutra para superficies publicas (dashboard
publico, carrossel de redes sociais).

`findings.descricao` (ver `detection/statistical.py`) e escrita com cuidado
pra um relatorio PESSOAL/interno, mas ainda carrega linguagem interpretativa
("possivel fracionamento", "requer verificacao manual") apropriada pra quem
ja entende que sao sinais heuristicos, nao veredito. Conteudo publico exige
um padrao mais estrito: so numero e comparacao, sem nenhuma palavra que
sugira irregularidade, fraude ou necessidade de investigacao - o leitor tira
as proprias conclusoes.

Por isso os renderers aqui NUNCA leem `descricao` - so os campos estruturados
de `dados_suporte`, que sao so numeros/nomes/datas.
"""

from __future__ import annotations

# Tipos de achado elegiveis pra superficie publica: so os puramente
# estatisticos/baseados em regra, cujo dados_suporte reduz a uma frase
# factual sem perda de sentido. Achados derivados de LLM (analise de
# discurso) e o sinal combinado BAIXA_ATIVIDADE_GERAL (cuja propria natureza
# e "parece estranho, precisa checar") ficam de fora do MVP publico - so
# aparecem no relatorio/dashboard interno.
TIPOS_PUBLICOS = frozenset(
    {
        "GASTO_OUTLIER",
        "GASTO_OUTLIER_VS_PARES",
        "VALOR_REPETIDO_SUSPEITO",
        "FORNECEDOR_POUCO_COMUM",
        "FORNECEDOR_CONCENTRADO",
        "TAXA_AUSENCIA_ALTA",
    }
)


def _gasto_outlier(d: dict) -> str:
    return (
        f"Gastou R$ {d['valor_mes']:,.2f} em '{d['tipo_despesa']}' no mes - "
        f"{d['zscore']:.1f} desvios-padrao acima da propria media historica "
        f"(R$ {d['media_historica']:,.2f})."
    )


def _gasto_outlier_vs_pares(d: dict) -> str:
    return (
        f"Gastou R$ {d['valor_mes']:,.2f} em '{d['tipo_despesa']}' no mes - "
        f"{d['zscore']:.1f} desvios-padrao acima da media de {d['n_pares']} colegas "
        f"de {d['grupo_comparado']} ({d['grupo_valor']}) na mesma categoria "
        f"(R$ {d['media_pares']:,.2f})."
    )


def _valor_repetido(d: dict) -> str:
    return (
        f"Mesmo valor de R$ {d['valor_unitario']:,.2f} registrado {d['repeticoes']}x "
        f"no mesmo dia ({d['data']}) com o fornecedor '{d['fornecedor']}' em "
        f"'{d['tipo_despesa']}' - total R$ {d['total']:,.2f}."
    )


def _fornecedor_pouco_comum(d: dict) -> str:
    return (
        f"Gasto de R$ {d['valor_mes']:,.2f} com '{d['fornecedor']}', fornecedor "
        f"usado por {d['n_deputados_historico']} deputado(s) em todo o historico "
        f"registrado."
    )


def _fornecedor_concentrado(d: dict) -> str:
    return (
        f"{d['fracao']:.0%} do gasto do mes (R$ {d['total_mes']:,.2f}) concentrado "
        f"num unico fornecedor: {d['fornecedor']}."
    )


def _taxa_ausencia_alta(d: dict) -> str:
    return (
        f"Sem voto registrado em {d['taxa_ausencia_sem_justificativa']:.0%} das "
        f"{d['votacoes_no_mes']} votacoes nominais do Plenario no mes, fora de "
        f"licenca oficial."
    )


_RENDERERS = {
    "GASTO_OUTLIER": _gasto_outlier,
    "GASTO_OUTLIER_VS_PARES": _gasto_outlier_vs_pares,
    "VALOR_REPETIDO_SUSPEITO": _valor_repetido,
    "FORNECEDOR_POUCO_COMUM": _fornecedor_pouco_comum,
    "FORNECEDOR_CONCENTRADO": _fornecedor_concentrado,
    "TAXA_AUSENCIA_ALTA": _taxa_ausencia_alta,
}


def render(tipo: str, dados_suporte: dict) -> str:
    """Frase neutra para o achado, a partir so de `dados_suporte`.

    Levanta `KeyError`/`ValueError` se `tipo` nao estiver em `TIPOS_PUBLICOS`
    (verificar com `tipo in TIPOS_PUBLICOS` antes de chamar) ou se
    `dados_suporte` nao tiver os campos esperados.
    """
    if tipo not in _RENDERERS:
        raise ValueError(f"tipo '{tipo}' nao e elegivel para superficie publica (ver TIPOS_PUBLICOS)")
    return _RENDERERS[tipo](dados_suporte)
