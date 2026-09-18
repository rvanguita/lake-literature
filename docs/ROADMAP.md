# Roadmap — lake-literature

Improvement backlog and strategic research agenda for the `lake-literature` medallion pipeline and analytical dashboard. See [`../README.md`](../README.md) for orientation, [`PRD.md`](PRD.md) for domain motivation, and [`SDD.md`](SDD.md) for architecture.

Every measurement below reflects the active corpus on **2026-09-17** (1,831 articles, 6,235 chunks, 100% embedded).

---

## 🏁 Completed Milestones

The following foundational items were implemented, tested (183 automated unit and integration tests passing across 22 test files), and verified in the live system:

- [x] **Item 1: Binary Embedding Storage** — Vectors migrated from heavy JSON strings (~50 MB, ~8 KB/vector) to native `LargeBinary` float32 BLOBs (~9 MB, ~1.5 KB/vector), with dual-write safety in `transform/embeddings.py` and zero-copy `np.frombuffer` reads in `semantics.py` and `search.py`.
- [x] **Item 2: Relevance Screening Calibration & Stratified Sampling** — Replaced circular pseudo-label evaluation with `transform/screening_calibration.py`, enabling stratified sample extraction across 4 margin strata and threshold tuning for target SLR recall ($\ge 98\%$).
- [x] **Item 3: Pipeline Execution Run History** — Persisted pipeline runs via `lit_pipeline_runs` table in Gold, capturing stage names, wall-clock start/finish timestamps, durations, structured execution metrics, and error traces across all 6 medallion stages; visualized in the "Camadas & Pipeline" dashboard.
- [x] **Item 4: Explicit Non-Article Flagging at Silver** — Automated tagging of front matter, prefaces, and book chapters (105 `incollection` + 3 `book`/`inbook` with missing or short abstracts < 50 chars) via `is_non_article` boolean flag carried into Gold.
- [x] **Item 5: Full-Text vs. Abstract Chunk Stratification** — Resolved coverage skew (96 PDF articles generating 70% of chunks) by segregating and disclosing chunk-type proportions in RAG quality metrics.
- [x] **Item 6: Abstract-less Record Segregation** — Title-only records (31 articles without abstract) marked with `⚠️ título-only` badges and excluded from relevance margin percentile distributions to prevent dilution of screening signals.
- [x] **Item 7: Auditability of Excluded Records** — Dropped bronze records lacking a valid DOI persisted into `silver.lit_rejected` with timestamps and rejection rationales, providing a complete audit trail for Systematic Literature Review (SLR) standards.
- [x] **Item 8: Automated Citation Enrichment via OpenAlex** — Implemented `ingest/openalex.py` querying public OpenAlex REST API to fetch citations and references without API keys, caching incrementally into `data/enrichment_cache.json`.
- [x] **Item 9: Core Test Gaps Closed & Expanded Suite** — 183 automated tests across 22 test files covering Airflow DAG imports (`test_dag_import.py`), additive schema bootstrap (`test_bootstrap.py`), semantics integration, heavy-tail statistics, machine learning forecasting, OpenAlex enrichment, screening calibration, dynamic c-TF-IDF, Zipf's law, network small-world/centralities, Isolation Forest anomaly detection, strategic scientometrics, advanced methodological synthesis, and technological frontiers/disruption.
- [x] **Item 10: Advanced Multi-Projection & Semantic Novelty (Trilha A)** — UMAP and PCA 2D projections alongside t-SNE with zero-copy caching; Cosine Outlier Factor / Novelty score measuring cosine distance to corpus centroid and k-NN local dispersion.
- [x] **Item 11: Zipf's Law & Bibliometric Triad (Trilha B)** — Power-law rank-frequency regression of vocabulary on log-log coordinates ($\gamma \approx -1$, $R^2$), completing the classic bibliometric triad (Lotka, Bradford, Zipf).
- [x] **Item 12: Complex Network Centralities & Small-World Topology (Trilha C)** — PageRank and Closeness centralities computed alongside Betweenness; Small-World coefficient $\sigma = \frac{C/C_{rand}}{L/L_{rand}}$ evaluating knowledge diffusion efficiency.
- [x] **Item 13: Dynamic Topic c-TF-IDF & Isolation Forest Anomaly Audit (Trilha D)** — Class-based dynamic TF-IDF tracking distinctive vocabulary per theme across chronological epochs; multi-dimensional Isolation Forest detecting bibliometric anomalies with explicit audit rationales.
- [x] **Item 14: Fast Vector Indexing (Trilha E)** — Modular vector retrieval engine (`build_vector_index`, `search_vector_index`) supporting Faiss L2/IP indexing with accelerated linear vector fallbacks.
- [x] **Item 15: Strategic Scientometrics & Epistemic Synthesis** — 11ª página do dashboard (`pages/strategic.py`) com 7 gráficos inéditos em 5 abas temáticas: Diagrama Estratégico de Callon (1991), Rede de Coocorrência de Palavras-Chave (Jaccard + Louvain), Proximidade Cosseno entre Centróides Temáticos ($8 \times 8$), Radar Multidimensional de Maturidade (5 eixos), Matriz de Correlações de Spearman, Entropia de Shannon / Gini-Simpson temporal e Paisagem de Colaboração Internacional.
- [x] **Item 16: Methodological Synthesis & Scientometric Maturity** — 12ª página do dashboard (`pages/synthesis.py`) ampliada para **8 abas analíticas completas** com 18+ gráficos e matrizes cruzadas: Paradigmas de Otimização e Espectro de Complexidade (MILP, SOCP, MINLP, Heurística, IA), Funções-Objetivo e Matriz de Co-Otimização (Custos, Perdas, Confiabilidade, Tensão, Descarbonização, Resiliência), Modelagem de Incerteza (Estocástica, Robusta, Fuzzy, DRO), Horizontes Temporais (Multi-Estágio vs. Co-Otimização com Dias Representativos vs. Estático), Benchmarks IEEE e Redes Reais, Ferramental Computacional e Solvers (GAMS, CPLEX, Gurobi, MATLAB, OpenDSS, Python), Liderança Científica e Carreira ($h$, $g$, $e$-index e $m$-quotient de Hirsch), e Longevidade Citacional (Meia-Vida, Artigos Evergreen, Estilometria Flesch-Kincaid / TTR).
- [x] **Item 17: Technological Frontiers, Scientometric Disruption & Open Access Dynamics** — 13ª página do dashboard (`pages/frontiers.py`) com 10 gráficos inéditos em 5 abas temáticas: Índice de Price (1965) da juventude da base de conhecimento por tema e série histórica; Belas Adormecidas na ciência (*Sleeping Beauties*, Ke et al. 2015 e van Raan 2004) com coeficiente de beleza $B$, lag de dormência e trajetórias de despertar; Índice de Disrupção Científica $CD$ (Wu, Wang & Evans, Nature 2019) e confirmação empírica de equipes pequenas vs grandes; Vantagem Citatória do Acesso Aberto (OACA) e dinâmica de licenciamento; e Algoritmo de Detecção de Rajadas Tecnológicas de Kleinberg (2002).
- [x] **Item 18: Revisão e Otimização Metodológica de 58+ Funções Analíticas** — Auditoria completa de todas as 64 funções em `analytics.py` e módulos auxiliares:
  - *Rigor Estatístico*: preenchimento de gaps temporais com zeros em trajetórias de autores (`author_productivity_trend`), incorporação de pesos em Louvain (`weight="weight"`), inversão semântica de pesos em centralidades de intermediação e proximidade ($d = 1/w$), regressão Poisson sem penalização enviesada, Mínimos Quadrados Ponderados (WLS) na Lei de Lotka, e vetorização matricial de similaridade de centroides ($C \cdot C^T$).
  - *Performance & Robustez*: vetorização de Mann-Kendall e Gini/Lorenz, pré-compilação de regex taxonômicos, `CountVectorizer` com vocabulário global para c-TF-IDF inter-épocas, e resolução de busca vetorial para colunas binárias (`embedding_bin`).
- [x] **Item 19: Fronteiras Preditivas, Dinâmica Estrutural e Recuperação Avançada (Trilha F Concluída)** —
  - Detecção estatística de quebras estruturais e changepoints históricos via minimização de SSE e teste F de Chow (`detect_structural_breaks`).
  - Intervalos de confiança preditivos dinâmicos com variância expansiva por horizonte ($\sigma \sqrt{h}$) em `forecasting.py`.
  - Calibração Não-Linear contínua (NLS) da difusão tecnológica de Bass com bounds físicos (`fit_bass_diffusion_nls` via `scipy.optimize.curve_fit`).
  - Busca Híbrida Densa-Esparsa com Reciprocal Rank Fusion (`bm25_search`, `hybrid_search_rrf`) e alternador no dashboard de Qualidade & RAG.
  - Análise empírica de atipicidade e novidade conceitual de Brian Uzzi et al. (Science 2013) correlacionada com artigos hiper-citados top 5% (`conceptual_atypicality_analysis`).
  - Agrupamento ontológico e clustering semântico de periódicos em $\mathbb{R}^{384}$ (`venue_semantic_clusters`).

---

## 🚀 Trilha A — Metodologias Semânticas Avançadas e Análise do Espaço Vetorial

Ampliação metodológica da representação latente do corpus para extrair padrões conceituais além do mapa t-SNE 2D padrão.

### [x] A.1 Multi-Projeção Dimensional Comparativa (t-SNE vs. UMAP vs. PCA 2D)
- **Status**: Concluído e integrado ao dashboard (`semantics.py`).
- **Motivação**: O t-SNE preserva vizinhanças locais bem, mas distorce distâncias globais e não permite projeção paramétrica de novos artigos fora da amostra (`out-of-sample transform`).
- **Ação**: Implementado em `loaders.py` (`alternative_projections`) e `semantics.py` com seletor interativo dinâmico (t-SNE, PCA 2D, UMAP) e cache zero-copy.

### [x] A.2 Topologia de Bacias de Pesquisa e Vazios Científicos (KDE 2D)
- **Status**: Concluído e integrado ao dashboard (`pages/semantics.py`).
- **Motivação**: Scatter plots sofrem de sobreposição em regiões densas e não quantificam a probabilidade de densidade conceitual.
- **Ação**: Implementados contornos de densidade bidimensional por Kernel Density Estimation (`go.Histogram2dContour`) sobre o mapa semântico, destacando bacias temáticas consolidadas e vazios conceituais.

### [x] A.3 Trajetórias Temporais e Deriva Semântica (*Thematic Semantic Drift*)
- **Status**: Concluído e integrado ao dashboard (`transform/semantics.py`, `pages/semantics.py`).
- **Motivação**: O mapa estático não revela como as áreas de pesquisa evoluíram conceitualmente ao longo das décadas.
- **Ação**: Implementado `compute_temporal_drift` calculando o centróide vetorial de cada cluster temático em janelas temporais de 5 anos, traçando trajetórias de velocidade e direção da evolução científica na distribuição de energia.

### [x] A.4 Métrica de Novidade Semântica e Interdisciplinaridade
- **Status**: Concluído e integrado ao dashboard (`loaders.py`, `semantics.py`).
- **Motivação**: Identificar artigos pioneiros que transpõem fronteiras temáticas tradicionais.
- **Ação**: Implementado cálculo de distância cosseno ao centróide global do corpus e distância média aos 10 vizinhos mais próximos no espaço $\mathbb{R}^{384}$, com painel dedicado de dispersão e ranking dos top 20 artigos singulares/interdisciplinares.

### [x] A.5 Agrupamento Semântico de Periódicos e Ontologia de Palavras-Chave
- **Status**: Concluído (`analytics.py`, `pages/topics.py`).
- **Motivação**: Revistas e termos são agrupados por strings literais, mascarando sinonímias e afinidades epistemológicas.
- **Ação**: Implementado `venue_semantic_clusters` projetando periódicos no espaço vetorial a partir da média dos artigos que publicam e agrupando-os por k-means em clusters ontológicos.

---

## 📊 Trilha B — Estatística Rigorosa de Caudas Pesadas e Cienciometria

Superação de estatísticas descritivas ingênuas através de modelos probabilísticos formais adequados aos dados bibliométricos.

### [x] B.1 Modelagem de Caudas Pesadas de Citações (Power-Law vs. Log-Normal)
- **Status**: Concluído e integrado ao dashboard (`highlights.py`, `analytics.py`).
- **Motivação**: Citações em literatura científica não seguem distribuições normais; médias aritméticas são inflacionadas por papers outliers.
- **Ação**: Ajustados modelos de cauda pesada (Power-Law, Log-Normal e Exponencial) via MLE com teste de Kolmogorov-Smirnov.

### [x] B.2 Indicadores de Citação Normalizados por Idade e Campo (*Age-Normalized Metrics*)
- **Status**: Concluído e integrado ao dashboard (`highlights.py`, `analytics.py`).
- **Motivação**: Artigos publicados há 15 anos acumulam mais citações brutas do que artigos de 2024, criando viés retrospectivo.
- **Ação**: Calculada a Taxa Anualizada de Citações e $z$-score por coorte anual de publicação.

### [x] B.3 Testes Não-Paramétricos de Tendência (Mann-Kendall e Estimador de Sen)
- **Status**: Concluído e integrado ao dashboard (`topics.py`, `analytics.py`).
- **Motivação**: A classificação atual de tendências de autores e termos usa limiares empíricos arbitrários ($\pm 0.15$ artigos/ano em OLS linear).
- **Ação**: Implementado teste de Mann-Kendall ($S, \tau, z, p$) com estimador de inclinação de Sen.

### [x] B.4 Validação Empírica de Leis Bibliométricas Clássicas
- **Status**: Concluído e integrado ao dashboard (`topics.py`, `analytics.py`).
- **Motivação**: Avaliar se o corpus adere aos princípios fundamentais da cienciometria.
- **Ação**:
  - **Lei de Lotka**: Modelada produtividade de autores com teste $\chi^2$.
  - **Lei de Bradford**: Particionamento em zonas concêntricas ($1 : n : n^2$).
  - **Lei de Zipf**: Implementada em `analytics.py` (`zipf_law_analysis`) e sub-aba dedicada em `topics.py` com gráfico log-log e coeficientes de regressão ($\gamma \approx -1$, $R^2$).

### [x] B.5 Modelagem Econométrica de Determinantes de Citação (GLM de Contagem)
- **Status**: Concluído e integrado ao dashboard (`highlights.py`, `analytics.py`).
- **Motivação**: Compreender quais atributos de um artigo impulsionam seu impacto científico.
- **Ação**: Ajustado GLM Poisson para citações com cálculo de Incidência de Razão de Taxas (IRR) para referências, ano, número de autores e prestígio.

---

## 🕸️ Trilha C — Ciência de Redes e Grafos Complexos de Colaboração

Análise estrutural da topologia das redes de coautoria e citação.

### [x] C.1 Detecção de Comunidades de Pesquisa via Algoritmo de Louvain
- **Status**: Concluído e integrado ao dashboard (`researchers.py`, `analytics.py`).
- **Motivação**: A rede de coautoria circular atual não revela colégios invisíveis ou grupos cooperativos independentes.
- **Ação**: Implementado algoritmo de maximização de modularidade de Louvain em `networkx` com coloração por comunidade.

### [x] C.2 Bateria Completa de Centralidades Estruturais
- **Status**: Concluído e integrado ao dashboard (`researchers.py`, `analytics.py`).
- **Motivação**: O grau simples (número de conexões) não captura pesquisadores que atuam como pontes interdisciplinares.
- **Ação**: Calculadas Centralidades de Intermediação (*Betweenness*), Centralidade de Autovetor / PageRank e Centralidade de Proximidade (*Closeness*), exibidas na tabela analítica de pesquisadores.

### [x] C.3 Métricas de Topologia de Rede e Índice de Pequeno Mundo (*Small-World*)
- **Status**: Concluído e integrado ao dashboard (`researchers.py`, `analytics.py`).
- **Motivação**: Determinar a eficiência de difusão de ideias na comunidade de planejamento de distribuição de energia.
- **Ação**: Calculados o Coeficiente Médio de Aglomeração ($C$), Comprimento Médio do Caminho Mais Curto ($L$) e o coeficiente de Pequeno Mundo $\sigma = \frac{C / C_{\text{rand}}}{L / L_{\text{rand}}}$, exibido em card de métrica de destaque.

### [x] C.4 Distância Cognitiva nas Equipes e Impacto Bibliométrico
- **Status**: Concluído e integrado ao dashboard (`pages/researchers.py`).
- **Motivação**: Investigar o benefício da diversidade interdisciplinar em publicações de engenharia.
- **Ação**: Calculada a distância cosseno par a par entre os perfis semânticos históricos dos coautores de cada artigo, avaliando a correlação de Pearson e Spearman com a taxa de citação e scatter plot interativo.

---

## 🤖 Trilha D — Machine Learning, Active Learning e Modelagem Preditiva

Aplicação de técnicas modernas de aprendizado de máquina para extrair inteligência do corpus.

### [x] D.1 Triagem Assistida por Active Learning (*Uncertainty Sampling*)
- **Status**: Concluído e integrado ao dashboard (`semantics.py`, `transform/screening_calibration.py`).
- **Motivação**: A triagem manual de centenas de artigos em uma Revisão Sistemática da Literatura (SLR) é custosa.
- **Ação**: Implementada amostragem por incerteza baseada na margem de relevância ($|\Delta| \approx 0$) com calibração estratificada.

### [x] D.2 Modelagem Dinâmica de Tópicos (c-TF-IDF / DTM)
- **Status**: Concluído e integrado ao dashboard (`topics.py`, `analytics.py`).
- **Motivação**: O K-Means define clusters estáticos e não modela a evolução semântica do vocabulário dentro de cada tópico através do tempo.
- **Ação**: Implementado `dynamic_topic_ctfidf` em `analytics.py` e sub-aba dedicada em `topics.py` permitindo acompanhar termos distintivos por tema em épocas temporais históricas.

### [x] D.3 Previsão Probabilística por Regressão Quantílica e Difusão de Bass
- **Status**: Concluído e integrado ao dashboard (`trends.py`, `forecasting.py`).
- **Motivação**: A regressão linear gaussiana assume variância residual constante e simétrica, irrealista para contagens de publicações.
- **Ação**: Implementada Regressão Quantílica (P10, P50 mediana, P90) para intervalos empíricos de confiança e o Modelo de Difusão de Bass para estimar o ciclo de vida e pico de adoção.

### [x] D.4 Detecção de Anomalias Bibliométricas via *Isolation Forest*
- **Status**: Concluído e integrado ao dashboard (`quality.py`, `analytics.py`).
- **Motivação**: Identificar metadados inconsistentes, padrões anômalos de citação ou artigos atípicos.
- **Ação**: Implementado `detect_bibliometric_anomalies` utilizando `sklearn.ensemble.IsolationForest` treinado em características multidimensionais (ano, citações, referências, autores, score de relevância, status de PDF), com geração de justificativas textuais explícitas e aba de auditoria no dashboard.

---

## 💾 Trilha E — Engenharia de Dados, Integração Externa e Escalabilidade

Modernização da infraestrutura de dados e fontes externas.

### [x] E.1 Enriquecimento Automatizado de Metadados via APIs Públicas (OpenAlex & Crossref)
- **Status**: Concluído (`ingest/openalex.py`, `bronze_articles.py`).
- **Motivação**: A base Elsevier dependia de dados bibliográficos com citações parciais.
- **Ação**: Implementado cliente OpenAlex com resolução de DOIs, normalização de métricas e cache incremental em `data/enrichment_cache.json`.

### [x] E.2 Indexação Vetorial de Alta Velocidade (FAISS / HNSW)
- **Status**: Concluído (`search.py`, `data.py`).
- **Motivação**: A busca vetorial por produto interno em numpy ($O(N)$) atende bem volumes moderados, mas degrada para grandes acervos textuais.
- **Ação**: Implementados construtor de índice vetorial (`build_vector_index`) e motor de busca acelerado (`search_vector_index`) com suporte nativo a índices Faiss (IndexFlatIP) e fallback vetorizado contínuo.

### E.3 Mecanismo Persistente de Resolução e Fusão de Quase-Duplicatas
- **Motivação**: 18 pares de quase-duplicatas são identificados em `lit_duplicate_pairs`, mas o dashboard é estritamente read-only.
- **Ação**: Criar CLI ou interface de aprovação para registrar pares validados em tabela de overrides `lit_duplicate_overrides`.

---

## 🔮 Trilha F — Fronteiras Preditivas, Dinâmica Estrutural e Recuperação Avançada

Planos estratégicos e aprofundamentos metodológicos derivados da revisão global de 2026-09-18.

### [x] F.1 Detecção de Rupturas Estruturais e Changepoints Temporais
- **Status**: Concluído e integrado ao dashboard (`analytics.py`, `pages/topics.py`).
- **Motivação**: Séries bibliométricas sofrem quebras estruturais induzidas por eventos exógenos (marcos regulatórios, novas normas IEEE, Acordo de Paris 2015). A regressão contínua mascara essas transições de regime.
- **Ação**: Implementado algoritmo de detecção de pontos de mudança via minimização de SSE e teste F de Chow (`detect_structural_breaks`), identificando transições de regime estatisticamente significantes com visualização gráfica dedicada.

### [x] F.2 Modelagem Preditiva de Contagem com Incerteza Dinâmica
- **Status**: Concluído (`forecasting.py`).
- **Motivação**: A regressão linear gaussiana assume variância homocedástica constante ao longo dos horizontes $h \in \{1, 2\}$, desconsiderando que a incerteza estatística se expande com o tempo.
- **Ação**: Incorporadas bandas de incerteza preditivas com variância expansiva por horizonte temporal ($\text{margin} = 1.96 \cdot \sigma \cdot \sqrt{h}$).

### [x] F.3 Calibração Não-Linear (NLS) da Difusão Tecnológica de Bass
- **Status**: Concluído e integrado ao dashboard (`forecasting.py`, `pages/forecasting.py`).
- **Motivação**: A formulação discreta OLS de Bass frequentemente sofre de multicolinearidade entre $Y_{t-1}$ e $Y_{t-1}^2$, gerando parâmetros não-físicos ($\beta_2 > 0$).
- **Ação**: Implementado `fit_bass_diffusion_nls` ajustando a curva contínua cumulativa diretamente via `scipy.optimize.curve_fit` com restrições de limites de parâmetros ($p, q > 0, m \ge \max(Y)$).

### [x] F.4 Busca Híbrida Densa-Esparsa com Reciprocal Rank Fusion (BM25 + BGE-Small RRF)
- **Status**: Concluído e integrado ao dashboard (`search.py`, `pages/quality.py`).
- **Motivação**: Embeddings densos capturam proximidade semântica ampla, mas falham em acrônimos técnicos exatos ou especificações numéricas de redes (ex.: "IEEE 33-bus", "SOCP", "MILP", "OPF").
- **Ação**: Implementado BM25 Okapi puro (`bm25_search`) associado a embeddings densos via Reciprocal Rank Fusion (`hybrid_search_rrf`), com seletor interativo no dashboard de Qualidade & RAG.

### [x] F.5 Análise de Atipicidade Conceitual e Impacto Citacional (Uzzi et al., Science 2013)
- **Status**: Concluído e integrado ao dashboard (`analytics.py`, `pages/topics.py`).
- **Motivação**: Investigar se combinações conceituais incomuns de palavras-chave e temas produzem probabilidade desproporcional de artigos altamente citados (top 5% do corpus).
- **Ação**: Implementado `conceptual_atypicality_analysis` computando o score de atipicidade combinatória para pares de palavras-chave contra modelo nulo randomizado, correlacionando com taxa de sucesso em citações no percentil 95.


