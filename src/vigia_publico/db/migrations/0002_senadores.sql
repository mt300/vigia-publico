-- Perfil atual do senador (1 linha por senador, sempre o mais recente).
-- So cobre quem esta na lista atual de exercicio (mesmo criterio ja usado
-- pra deputados) - a API de despesas (CEAPS) inclui codSenador de gente que
-- ja saiu (suplente trocado, etc.), esses ficam sem linha aqui de proposito.
CREATE TABLE senadores (
    id INTEGER PRIMARY KEY,          -- CodigoParlamentar/codSenador (mesmo id nas duas APIs do Senado)
    nome_civil TEXT,
    nome_parlamentar TEXT,
    sexo TEXT,
    email TEXT,
    url_foto TEXT,
    sigla_partido TEXT,
    sigla_uf TEXT,
    situacao TEXT,
    atualizado_em TEXT
);

-- Despesas CEAPS (Cota pra Exercicio da Atividade Parlamentar dos
-- Senadores) - equivalente Senado da CEAP da Camara (tabela `despesas`),
-- mas API/schema mais simples: um valor so (valorReembolsado, sem o split
-- documento/liquido/glosa que a Camara tem). A API de despesas devolve
-- codSenador de gente que ja nao esta mais na lista atual (suplente
-- trocado etc.) - esses registros sao filtrados NA INGESTAO (mesmo
-- criterio "so quem esta em exercicio agora" que a Camara ja usa), entao a
-- FK aqui fica igual a de `despesas.deputado_id` (nunca ha orfao em
-- producao, porque a ingestao so insere despesa de quem ja upsertou em
-- `senadores` antes).
CREATE TABLE despesas_senadores (
    uid TEXT PRIMARY KEY,             -- sha256, mesmo padrao de despesa_uid()
    senador_id INTEGER NOT NULL REFERENCES senadores(id),
    ano INTEGER,
    mes INTEGER,
    tipo_despesa TEXT,
    data_documento TEXT,
    nome_fornecedor TEXT,
    cnpj_cpf_fornecedor TEXT,
    tipo_documento TEXT,
    num_documento TEXT,
    detalhamento TEXT,
    valor_reembolsado REAL
);
CREATE INDEX idx_despesas_sen_periodo ON despesas_senadores(senador_id, ano, mes);

-- Generaliza `findings` pra caber achados de qualquer casa. SQLite nao tem
-- ALTER TABLE ... DROP CONSTRAINT, entao reconstroi a tabela (mesmo padrao
-- de `_reduzir_despesas()` em reporting/public_snapshot.py).
--
-- Decisao: a coluna continua se chamando `deputado_id` (nao virou
-- `parlamentar_id`) - um achado de Senado guarda o senador_id nessa mesma
-- coluna. Evita reescrever `analytics/queries.py::get_findings` e
-- `reporting/report_builder.py` (que ja tem SQL literal contra
-- "f.deputado_id") - so precisam de um `AND f.casa = 'camara'` a mais no
-- WHERE, pra nao juntar um achado de Senado com o deputado de ID numerico
-- coincidente (os dois namespaces de ID sao independentes). Ja existe
-- precedente pra essa reutilizacao "solta" de nome de coluna:
-- `ingest_state.deputado_id` ja e usado genericamente como "ID de quem for
-- o dono dessa unidade de trabalho", sem FK.
CREATE TABLE findings_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mes_referencia TEXT NOT NULL,
    casa TEXT NOT NULL DEFAULT 'camara',
    deputado_id INTEGER NOT NULL,
    tipo TEXT NOT NULL,
    severidade TEXT,
    descricao TEXT,
    dados_suporte TEXT,
    fonte_url TEXT,
    criado_em TEXT
);
INSERT INTO findings_new (id, mes_referencia, casa, deputado_id, tipo, severidade, descricao, dados_suporte, fonte_url, criado_em)
    SELECT id, mes_referencia, 'camara', deputado_id, tipo, severidade, descricao, dados_suporte, fonte_url, criado_em FROM findings;
DROP TABLE findings;
ALTER TABLE findings_new RENAME TO findings;
CREATE INDEX idx_findings_mes ON findings(mes_referencia, casa, deputado_id);
