-- Catalogo de legislaturas (permite navegar mandatos anteriores)
CREATE TABLE legislaturas (
    id INTEGER PRIMARY KEY,
    data_inicio TEXT,
    data_fim TEXT
);

-- Perfil atual do deputado (1 linha por deputado, sempre a mais recente)
CREATE TABLE deputados (
    id INTEGER PRIMARY KEY,
    nome_civil TEXT,
    nome_eleitoral TEXT,
    cpf TEXT,
    data_nascimento TEXT,
    uf_naturalidade TEXT,
    municipio_naturalidade TEXT,
    sexo TEXT,
    escolaridade TEXT,
    url_foto TEXT,
    sigla_partido TEXT,
    sigla_uf TEXT,
    situacao TEXT,
    condicao_eleitoral TEXT,
    email TEXT,
    gabinete_sala TEXT,
    gabinete_predio TEXT,
    gabinete_andar TEXT,
    gabinete_telefone TEXT,
    legislatura_atual_id INTEGER REFERENCES legislaturas(id),
    atualizado_em TEXT
);

-- Links de redes sociais do perfil (coletado agora, usado na Fase 2)
CREATE TABLE deputado_redes_sociais (
    deputado_id INTEGER NOT NULL REFERENCES deputados(id),
    rede TEXT,
    url TEXT NOT NULL,
    PRIMARY KEY (deputado_id, url)
);

-- Timeline de mudancas de partido/situacao (multi-legislatura)
CREATE TABLE deputado_historico (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deputado_id INTEGER NOT NULL REFERENCES deputados(id),
    legislatura_id INTEGER NOT NULL REFERENCES legislaturas(id),
    data_hora TEXT NOT NULL,
    situacao TEXT,
    condicao_eleitoral TEXT,
    sigla_partido TEXT,
    descricao_status TEXT,
    UNIQUE (deputado_id, legislatura_id, data_hora, sigla_partido)
);

-- Despesas da cota parlamentar (CEAP)
CREATE TABLE despesas (
    uid TEXT PRIMARY KEY,
    deputado_id INTEGER NOT NULL REFERENCES deputados(id),
    ano INTEGER,
    mes INTEGER,
    tipo_despesa TEXT,
    data_documento TEXT,
    nome_fornecedor TEXT,
    cnpj_cpf_fornecedor TEXT,
    tipo_documento TEXT,
    num_documento TEXT,
    cod_documento TEXT,
    valor_documento REAL,
    valor_liquido REAL,
    valor_glosa REAL,
    num_ressarcimento TEXT,
    cod_lote TEXT,
    parcela INTEGER,
    url_documento TEXT
);
CREATE INDEX idx_despesas_dep_periodo ON despesas(deputado_id, ano, mes);

-- Discursos em plenario. A propria API retorna a transcricao completa
-- (campo "transcricao"), entao nao ha necessidade de raspar o urlTexto.
CREATE TABLE discursos (
    uid TEXT PRIMARY KEY,
    deputado_id INTEGER NOT NULL REFERENCES deputados(id),
    data_hora_inicio TEXT,
    data_hora_fim TEXT,
    tipo_discurso TEXT,
    sumario TEXT,
    url_texto TEXT,
    keywords TEXT,
    fase_evento TEXT,
    transcricao TEXT
);
CREATE INDEX idx_discursos_dep_data ON discursos(deputado_id, data_hora_inicio);


-- Votacoes e votos individuais (fonte real de presenca/falta)
CREATE TABLE votacoes (
    id TEXT PRIMARY KEY,
    data TEXT,
    sigla_orgao TEXT,
    id_orgao INTEGER,
    descricao TEXT,
    aprovacao INTEGER
);
CREATE TABLE votos (
    votacao_id TEXT NOT NULL REFERENCES votacoes(id),
    deputado_id INTEGER NOT NULL REFERENCES deputados(id),
    voto TEXT,
    motivo_ausencia TEXT,
    PRIMARY KEY (votacao_id, deputado_id)
);
CREATE INDEX idx_votos_dep ON votos(deputado_id);

-- Controle de ingestao incremental/resumivel.
-- deputado_id usa o sentinel 0 (nao NULL) quando a unidade de trabalho nao e
-- por deputado (ex: votacoes de uma legislatura/ano): SQLite trata colunas
-- NULL como sempre distintas numa PRIMARY KEY composta, o que quebraria o
-- ON CONFLICT DO UPDATE (cada rodada inseriria uma linha nova em vez de
-- atualizar a existente).
CREATE TABLE ingest_state (
    entidade TEXT NOT NULL,
    deputado_id INTEGER NOT NULL DEFAULT 0,
    chave TEXT NOT NULL,
    status TEXT NOT NULL,
    tentativas INTEGER NOT NULL DEFAULT 0,
    erro_msg TEXT,
    atualizado_em TEXT,
    PRIMARY KEY (entidade, deputado_id, chave)
);

-- Cache de discursos ja processados por LLM (evita reprocessar/pagar de novo)
CREATE TABLE llm_discurso_cache (
    discurso_uid TEXT NOT NULL REFERENCES discursos(uid),
    prompt_version TEXT NOT NULL,
    resultado_json TEXT NOT NULL,
    modelo TEXT,
    processado_em TEXT,
    PRIMARY KEY (discurso_uid, prompt_version)
);

-- Achados/alertas gerados mensalmente
CREATE TABLE findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mes_referencia TEXT NOT NULL,
    deputado_id INTEGER NOT NULL REFERENCES deputados(id),
    tipo TEXT NOT NULL,
    severidade TEXT,
    descricao TEXT,
    dados_suporte TEXT,
    fonte_url TEXT,
    criado_em TEXT
);
CREATE INDEX idx_findings_mes ON findings(mes_referencia, deputado_id);
