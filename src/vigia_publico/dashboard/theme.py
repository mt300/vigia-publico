"""Paleta de cores e polimento visual do Vigia Publico.

Cores vem do skill de dataviz (paleta categorica de 8 tons, ordem fixa,
validada contra CVD/contraste - ver `node scripts/validate_palette.js
"<hexs>" --mode light`, PASS). Dois principios do skill guiam o uso aqui:

- "Color follows the entity, never its rank": cada TIPO de achado tem uma
  cor fixa (COR_POR_TIPO_ACHADO), a mesma independente de quais outros
  tipos estao visiveis no filtro atual.
- Severidade e um conceito de STATUS (bom/alerta/critico), nao uma
  categoria arbitraria - usa a paleta de status fixa do skill, nunca
  tematizada.
"""

from __future__ import annotations

import streamlit as st

from vigia_publico.detection.neutral_copy import TIPO_LABEL_PUBLICO

# --- paleta categorica (ordem fixa, validada) --------------------------------

AZUL = "#2a78d6"
VERDE = "#008300"
MAGENTA = "#e87ba4"
AMARELO = "#eda100"
AGUA = "#1baf7a"
LARANJA = "#eb6834"
VIOLETA = "#4a3aa7"
VERMELHO = "#e34948"

COR_PRIMARIA = AZUL  # serie unica (linhas de gasto/presenca no tempo)

# Um tipo de achado = uma cor, sempre a mesma. So usa 6 dos 8 slots (todos
# os tipos publicos existentes) - saltando magenta/agua deliberadamente
# reservados caso outro tipo de achado seja adicionado no futuro.
COR_POR_TIPO_ACHADO: dict[str, str] = {
    "GASTO_OUTLIER": AZUL,
    "GASTO_OUTLIER_VS_PARES": VERDE,
    "VALOR_REPETIDO_SUSPEITO": AMARELO,
    "FORNECEDOR_POUCO_COMUM": LARANJA,
    "FORNECEDOR_CONCENTRADO": VIOLETA,
    "TAXA_AUSENCIA_ALTA": VERMELHO,
}

# Mesmo mapa, mas com a chave sendo o ROTULO amigavel (o que o modo publico
# efetivamente mostra no eixo do grafico) - gerado a partir do mapa acima
# pra nao ter duas fontes de verdade sobre qual cor e de qual tipo.
COR_POR_CATEGORIA_LABEL: dict[str, str] = {
    TIPO_LABEL_PUBLICO[tipo]: cor for tipo, cor in COR_POR_TIPO_ACHADO.items()
}

# --- paleta de status (fixa, nunca tematizada) -------------------------------

STATUS_BOM = "#0ca30c"
STATUS_ALERTA = "#fab219"
STATUS_SERIO = "#ec835a"
STATUS_CRITICO = "#d03b3b"

COR_POR_SEVERIDADE: dict[str, str] = {
    "baixa": STATUS_BOM,
    "media": STATUS_ALERTA,
    "alta": STATUS_CRITICO,
}

# Destaque de "proximo de eleicao" no grafico de presenca: e um aviso de
# CONTEXTO temporal, nao um alarme - usar vermelho/crimson passaria a
# mensagem errada (contradiz o texto ao lado, que explica que isso NAO e
# por si so irregularidade). Amber a baixa opacidade sinaliza "atencao ao
# contexto" sem ler como "algo errado".
COR_DESTAQUE_ELEICAO = STATUS_ALERTA


_CSS = """
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
div[data-testid="stToolbarActions"] {display: none;}
</style>
"""


def injetar_css() -> None:
    """Esconde o chrome padrao do Streamlit (menu hamburguer, rodape 'Made
    with Streamlit', botao de deploy) - nao agrega nada pro visitante de um
    app publico e destoa de um produto com identidade propria."""
    st.markdown(_CSS, unsafe_allow_html=True)
