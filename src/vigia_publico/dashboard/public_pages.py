"""Paginas publicas de apoio ao painel (dashboard/views.py): inicio (landing)
e tutorial/documentacao. So usadas pelo app publico (`app_public.py`) - o
dashboard local (`app.py`) continua single-page, sem essas paginas.
"""

from __future__ import annotations

import streamlit as st

from vigia_publico.dashboard import data
from vigia_publico.detection.neutral_copy import GLOSSARIO_ESTATISTICO, TIPO_EXPLICACAO_PUBLICO, TIPO_LABEL_PUBLICO


def render_home() -> None:
    st.title("Vigia Público")
    st.subheader("Monitor independente de deputados federais brasileiros, com dados 100% públicos.")

    st.markdown(
        "O Vigia Público acompanha gastos, presença em votações e discursos dos deputados "
        "federais em exercício, usando exclusivamente a API de Dados Abertos da Câmara dos "
        "Deputados (`dadosabertos.camara.leg.br`). Ele compara cada deputado com o próprio "
        "histórico e com colegas de partido/estado, e destaca **padrões estatísticos que fogem "
        "do comum** - não acusações, não conclusões. São sinais para você (ou para o jornalismo, "
        "ou para o próprio deputado) investigar mais a fundo."
    )

    meses = data.listar_meses_disponiveis()
    if meses:
        ultimo_mes = meses[-1]
        deputados = data.listar_deputados()
        achados_ultimo_mes = data.get_findings(ultimo_mes, ultimo_mes)

        c1, c2, c3 = st.columns(3)
        c1.metric("Deputados monitorados", len(deputados))
        c2.metric("Meses de histórico", len(meses))
        c3.metric(f"Achados em {ultimo_mes}", len(achados_ultimo_mes))

    st.divider()

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### 📊 Painel")
        st.markdown(
            "Explore os dados com filtros por partido, estado, deputado e período - gastos, "
            "presença em votações, discursos e os achados estatísticos de cada um. "
            "*(menu **Painel** na barra lateral)*"
        )
    with c2:
        st.markdown("### 📖 Como funciona")
        st.markdown(
            "Não entendeu um termo como 'desvio-padrão' ou o que significa cada tipo de achado? "
            "O tutorial explica tudo em linguagem simples, sem jargão. "
            "*(menu **Como funciona** na barra lateral)*"
        )

    st.divider()
    st.caption(
        "Achados aqui são sinais estatísticos automáticos, não veredito nem acusação - sempre "
        "exigem verificação humana. Código-fonte aberto: "
        "[github.com/mt300/vigia-publico](https://github.com/mt300/vigia-publico)."
    )
    st.caption("Desenvolvido por [MWebS](https://www.mwebs.com.br).")


def render_tutorial() -> None:
    st.title("Como funciona o Vigia Público")

    st.markdown(
        "## De onde vêm os dados\n"
        "Tudo vem da API pública e oficial da Câmara dos Deputados "
        "(`dadosabertos.camara.leg.br`) - a mesma base que qualquer pessoa pode consultar. "
        "Não há dado privado, vazado ou obtido por fora dos canais oficiais. O universo "
        "coberto é o dos deputados **em exercício agora**, com o histórico completo de seus "
        "mandatos anteriores."
    )

    st.markdown(
        "## O que os achados NÃO são\n"
        "Cada achado é o resultado de uma **regra estatística simples** (comparação de um "
        "número com uma média histórica ou de colegas). Isso **não é** uma investigação, "
        "**não é** uma acusação e **não prova** irregularidade - é um sinal de que algo foge "
        "do padrão habitual e merece um olhar mais de perto. Muitas vezes há explicação "
        "legítima (por exemplo: um gasto alto pode ser uma viagem oficial pontual)."
    )

    st.markdown("## Tipos de achado")
    for tipo, explicacao in TIPO_EXPLICACAO_PUBLICO.items():
        with st.expander(f"**{TIPO_LABEL_PUBLICO.get(tipo, tipo)}**"):
            st.write(explicacao)

    st.markdown("## Termos estatísticos")
    for termo, explicacao in GLOSSARIO_ESTATISTICO.items():
        with st.expander(f"**{termo}**"):
            st.write(explicacao)

    st.markdown(
        "## Como usar os filtros\n"
        "No menu lateral do Painel: escolha o **período** (mês inicial/final), e opcionalmente "
        "**partido**, **estado (UF)** e um **deputado específico**. Os filtros se combinam - "
        "por exemplo, partido + estado mostra só deputados daquele partido naquele estado. Sem "
        "nenhum deputado escolhido, as abas mostram dados agregados de todo o filtro; escolhendo "
        "um deputado, a aba **Perfil** mostra o histórico individual completo dele."
    )

    st.markdown(
        "## Limitações conhecidas\n"
        "- A API não expõe o motivo formal de uma ausência em votação - é inferido por "
        "exclusão (deputado não aparece entre os votos registrados).\n"
        "- Fornecedor usado por poucos deputados é, na maioria das vezes, só um fornecedor "
        "regional/local - não uma empresa de fachada. Confirmar isso exigiria dados externos "
        "(Receita Federal), fora do escopo atual.\n"
        "- O projeto está em fase inicial (Câmara dos Deputados apenas - o Senado pode entrar "
        "no escopo no futuro)."
    )

    st.divider()
    st.caption(
        "Código-fonte aberto, incluindo os limiares exatos de cada regra: "
        "[github.com/mt300/vigia-publico](https://github.com/mt300/vigia-publico)."
    )
    st.caption("Desenvolvido por [MWebS](https://www.mwebs.com.br).")
