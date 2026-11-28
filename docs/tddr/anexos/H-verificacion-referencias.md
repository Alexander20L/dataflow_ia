# Anexo H — Revisión de literatura y verificación de referencias

Fecha de verificación: 2026-11-20. Cada referencia se comprobó resolviendo su DOI en la API de Crossref
(`https://api.crossref.org/works/<DOI>`: título, autores, año, revista/actas, volumen y páginas) o, cuando
no tiene DOI de editor, en la página del editor indicada. Las cifras de la columna «Métrica principal» se
tomaron **sólo** del resumen (abstract) publicado, leído vía Crossref, Semantic Scholar
(`api.semanticscholar.org`), ACL Anthology o NeurIPS Proceedings; cuando el resumen no da cifra, la métrica
se nombra sin cifra.

Convenciones: los números entre corchetes remiten a la lista de referencias (§2). En la columna
«Limitación», el texto sin marca es una limitación que el propio trabajo declara en su resumen; «(obs.)»
indica una observación nuestra respecto al alcance de DataFlow AI, no declarada por los autores.

## 1. Estado del arte (2021–2026)

| Ref                              | Año  | Tipo de solución                                         | Técnica/Tecnología                                                                                                     | Dataset/Contexto                                                                                | Métrica principal                                                                             | Limitación reportada                                                                                                                                 |
| -------------------------------- | ---- | -------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| [15] Lux                         | 2021 | EDA automático / recomendación de visualizaciones        | Recomendación «siempre activa» al imprimir un dataframe de pandas; lenguaje de alto nivel; 3 optimizaciones de sistema | Cuadernos Jupyter; datasets del repositorio UCI; entrevistas a usuarios tempranos               | Sobrecarga ≤ 2 s sobre pandas en más del 98 % de los datasets UCI                             | (obs.) Depende de que el analista programe en un cuaderno e interprete las sugerencias; una sola tabla                                               |
| [16] DataPrep.EDA                | 2021 | EDA automático orientado a tareas                        | API declarativa en Python sobre Dask                                                                                   | Comparación con Pandas-profiling                                                                | Velocidad y experiencia de usuario frente a Pandas-profiling (sin cifra en el resumen)        | Señala que las bibliotecas EDA existentes son de nivel demasiado bajo o alto; (obs.) requiere que el usuario especifique la tarea                    |
| [17] MetaInsight                 | 2021 | Descubrimiento automático de _insights_                  | Patrones homogéneos, «comunalidades y excepciones», función de puntuación y ranking                                    | Datos multidimensionales reales; estudios con expertos y no expertos                            | Efectividad y eficiencia; estudios de usuario (sin cifra en el resumen)                       | Motivación: los patrones aislados de sistemas previos están desorganizados; (obs.) sin control de comparaciones múltiples declarado                  |
| [18] Auto-Validate               | 2021 | Validación automática de datos                           | Inferencia de patrones de dominio a partir de un corpus (data lake)                                                    | Datos de producción en data lakes; parte se distribuye en Azure Purview                         | Falsos positivos frente a problemas detectados (sin cifra en el resumen)                      | Los enfoques previos dan muchos falsos positivos en columnas de texto; (obs.) se centra en datos de texto generados por máquinas                     |
| [19] Valentine                   | 2021 | Banco de pruebas de _schema matching_                    | Suite abierta con métodos clásicos reimplementados; fabricación de datasets con verdad de referencia                   | Descubrimiento de datasets en data lakes; 4 escenarios de matching                              | Efectividad y eficiencia de los métodos de matching (sin cifra en el resumen)                 | Los métodos de descubrimiento usan el matching de forma ad hoc por falta de verdad de referencia                                                     |
| [20] Calliope                    | 2021 | Historias de datos automáticas                           | Búsqueda en árbol Monte Carlo orientada a la lógica; importancia por teoría de la información; leyendas generadas      | Hojas de cálculo; 3 historias de ejemplo, 2 experimentos controlados, entrevistas a 10 expertos | Eficiencia en la generación de historias (sin cifra en el resumen)                            | (obs.) Requiere un editor para revisar la historia; no aplica pruebas de significancia declaradas                                                    |
| [23] AutoML to Date and Beyond   | 2022 | Revisión de AutoML                                       | Taxonomía de 7 niveles de autonomía                                                                                    | Canalización de ML de extremo a extremo                                                         | Sin métrica (revisión)                                                                        | El proceso «todavía requiere intervención humana» en pasos vitales (entender los atributos, definir el problema, crear el conjunto de entrenamiento) |
| [26] KG4Vis                      | 2022 | Recomendación de visualizaciones explicable              | Grafo de conocimiento + embeddings TransE                                                                              | Pares dataset–visualización existentes; estudios de caso y entrevistas a expertos               | Comparaciones cuantitativas (sin cifra en el resumen)                                         | Las reglas manuales son tediosas y los modelos de ML son cajas negras (motivación)                                                                   |
| [27] ncNet                       | 2022 | Lenguaje natural a visualización (NL2VIS)                | Transformer secuencia a secuencia con _attention forcing_ y plantilla de gráfico opcional                              | Benchmark nvBench; estudio de usuario                                                           | Precisión en nvBench (sin cifra en el resumen)                                                | Los enfoques previos (NL4DV, FlowSense) no son de extremo a extremo; (obs.) depende de la consulta del usuario                                       |
| [28] Ehrlinger y Wöß             | 2022 | Revisión de herramientas de calidad de datos             | Búsqueda sistemática y catálogo de requisitos (perfilado, métricas, monitorización)                                    | 667 herramientas identificadas, 13 analizadas en detalle                                        | 13 herramientas evaluadas (8 comerciales, 5 abiertas)                                         | Métricas de calidad aceptadas en investigación apenas implementadas en las herramientas                                                              |
| [29] Auto-BI                     | 2023 | Construcción automática de modelos BI (varias tablas)    | Predicción local de joins + grafo global de esquema (k-Min-Cost-Arborescence)                                          | Más de 100K modelos BI reales y 4 benchmarks TPC                                                | F1 > 0,9 en benchmarks reales y sintéticos; latencia inferior a 1 s con cerca de 100 tablas   | k-MCA es intratable e inaproximable en general (resuelto de forma óptima en la práctica)                                                             |
| [30] DeepJoin                    | 2023 | Descubrimiento de tablas combinables (joins)             | Modelo de lenguaje preentrenado + búsqueda aproximada de vecinos                                                       | Data lakes reales                                                                               | Hasta dos órdenes de magnitud más rápido que soluciones existentes (con GPU)                  | Diseñado para atributos de texto con cardinalidad bastante pequeña                                                                                   |
| [31] Starmie                     | 2023 | Descubrimiento de datasets (unión de tablas)             | Aprendizaje contrastivo de codificadores de columnas; índice HNSW                                                      | Benchmarks reales de _table union search_                                                       | +6,8 en MAP y recall; 3.000× frente al escaneo lineal                                         | (obs.) Unión de tablas, no relaciones clave–clave foránea                                                                                            |
| [32] Pollock                     | 2023 | Benchmark de carga de CSV no estándar                    | Modelo formal de problemas y «contaminación» sistemática de dialectos                                                  | Miles de CSV públicos estudiados; 16 sistemas evaluados                                         | Puntuación de robustez de carga de 16 sistemas (sin cifra global en el resumen)               | El formato CSV flexible obliga a pasos de preparación engorrosos                                                                                     |
| [33] Auto-Tables                 | 2023 | Reestructuración automática de tablas a forma relacional | Síntesis de canalizaciones de transformación de varios pasos sin ejemplos                                              | 244 casos reales de hojas de cálculo y foros                                                    | Más del 70 % de los casos resueltos, a velocidad interactiva                                  | Más del 30 % de las tablas reales no son relacionales (motivación); (obs.) cerca del 30 % de casos sin resolver                                      |
| [34] LSM                         | 2023 | _Schema matching_ con modelos de lenguaje                | Modelo preentrenado + aprendizaje activo                                                                               | Esquemas reales de clientes                                                                     | Hasta 81 % de ahorro en coste de etiquetado                                                   | Necesita etiquetado del usuario (aprendizaje activo); sin acceso a los datos de origen                                                               |
| [36] Chat2VIS                    | 2023 | Visualización desde lenguaje natural con LLM             | Ingeniería de prompts sobre GPT-3, Codex y ChatGPT; el LLM genera código                                               | Estudios de caso comparativos                                                                   | Comparación cualitativa por casos (sin cifra en el resumen)                                   | Ambigüedad del lenguaje natural y consultas mal especificadas; (obs.) el LLM genera el código que calcula                                            |
| [37] ¿Es GPT-4 un buen analista? | 2023 | LLM como analista de datos de extremo a extremo          | Prompts diseñados; comparación con analistas profesionales                                                             | Bases de datos de varios dominios                                                               | Rendimiento «comparable» al humano (sin cifra en el resumen)                                  | Los autores piden más estudios antes de concluir que puede sustituir a los analistas                                                                 |
| [38] BIRD                        | 2023 | Benchmark de texto a SQL sobre bases grandes             | 12.751 pares pregunta–SQL, 95 bases (33,4 GB), 37 dominios                                                             | Bases de datos con contenido sucio y conocimiento externo                                       | Exactitud de ejecución de GPT-4: 54,89 % frente a 92,96 % humana                              | Los modelos deben entender los valores de la base, no sólo el análisis semántico                                                                     |
| [41] DAIL-SQL                    | 2024 | Texto a SQL con LLM                                      | Evaluación sistemática de prompts; selección y organización de ejemplos; ajuste fino                                   | Spider                                                                                          | Exactitud de ejecución del 86,6 % en Spider                                                   | Faltaba un benchmark sistemático; coste en tokens como criterio                                                                                      |
| [42] Table-GPT                   | 2024 | LLM ajustado para tareas de tablas                       | «Table fine-tuning» con tareas sintetizadas de tablas reales                                                           | Transformación, limpieza, perfilado, imputación y QA de tablas                                  | Supera a GPT-3.5 y ChatGPT (sin cifra en el resumen)                                          | Los LLM son subóptimos en tablas por preentrenarse en texto unidimensional                                                                           |
| [43] Gu et al.                   | 2024 | Verificación humana de análisis generados por IA         | Sonda de diseño con explicaciones, código, visualizaciones y tablas                                                    | Estudio cualitativo con 22 analistas                                                            | Comportamientos de verificación (estudio cualitativo, n = 22)                                 | Respuestas de IA «aparentemente correctas» pueden llevar a conclusiones incorrectas                                                                  |
| [44] Kazemitabaar et al.         | 2024 | Dirección y verificación de análisis con LLM             | Descomposición por pasos (Stepwise) y por fases (Phasewise)                                                            | Estudio formativo (n = 15) y experimento controlado (n = 18)                                    | Mayor control percibido, significativo frente a la línea base conversacional                  | Retos serios para verificar resultados generados por IA y dirigir la IA                                                                              |
| [40] Data Formulator             | 2023 | Autoría de visualizaciones con agente de IA              | «Concept binding»: el agente transforma los datos                                                                      | Estudio de usuario con 10 participantes                                                         | Capacidad de crear visualizaciones con transformaciones complejas (sin cifra de rendimiento)  | (obs.) El agente de IA transforma los datos; el autor debe inspeccionar el resultado                                                                 |
| [45] QuanTemp                    | 2024 | Verificación de afirmaciones numéricas                   | Descomposición de afirmaciones; modelos NLI numéricos                                                                  | Dataset multidominio de afirmaciones numéricas reales                                           | Macro-F1 de 58,32 de la mejor línea base                                                      | Las afirmaciones numéricas reales son complejas y carecen de información precisa                                                                     |
| [46] DataNarrative               | 2024 | Historias de datos con LLM                               | Marco multiagente: un agente redacta y otro verifica cada paso                                                         | Benchmark de 1.449 historias                                                                    | Supera a líneas base no agénticas en evaluación por modelo y humana (sin cifra en el resumen) | Los autores señalan retos propios de la tarea                                                                                                        |
| [47] Chen et al.                 | 2024 | Revisión de herramientas de visualización narrativa      | 6 géneros y 4 tipos de herramientas según nivel de automatización                                                      | 105 artículos y herramientas                                                                    | Sin métrica (revisión)                                                                        | Problemas de investigación abiertos en cada categoría                                                                                                |
| [48] Magneto                     | 2025 | _Schema matching_ con modelos pequeños y LLM             | Recuperación con SLM + reordenación con LLM                                                                            | Nuevo benchmark biomédico y benchmarks existentes                                               | Alta precisión y escalabilidad (sin cifra en el resumen)                                      | Los SLM necesitan datos de entrenamiento costosos; los LLM, mucho cómputo y ventana de contexto limitada                                             |

## 2. Referencias (IEEE)

[1] Y. Benjamini and Y. Hochberg, "Controlling the false discovery rate: A practical and powerful approach to multiple testing," _J. Roy. Statist. Soc. Ser. B (Methodol.)_, vol. 57, no. 1, pp. 289–300, 1995, doi: 10.1111/j.2517-6161.1995.tb02031.x.

[2] W. H. Kruskal and W. A. Wallis, "Use of ranks in one-criterion variance analysis," _J. Amer. Statist. Assoc._, vol. 47, no. 260, pp. 583–621, 1952, doi: 10.1080/01621459.1952.10483441.

[3] K. Pearson, "On the criterion that a given system of deviations from the probable in the case of a correlated system of variables is such that it can be reasonably supposed to have arisen from random sampling," _London, Edinburgh, Dublin Philos. Mag. J. Sci._, vol. 50, no. 302, pp. 157–175, 1900, doi: 10.1080/14786440009463897.

[4] J. Brooke, "SUS: A 'quick and dirty' usability scale," in _Usability Evaluation in Industry_, P. W. Jordan, B. Thomas, I. L. McClelland, and B. Weerdmeester, Eds. CRC Press, 1996, pp. 207–212, doi: 10.1201/9781498710411-35.

[5] _Systems and Software Engineering — Systems and Software Quality Requirements and Evaluation (SQuaRE) — Product Quality Model_, ISO/IEC 25010:2023, 2023. [Online]. Available: https://www.iso.org/standard/78176.html

[6] M. Herschel, R. Diestelkämper, and H. Ben Lahmar, "A survey on provenance: What for? What form? What from?," _VLDB J._, vol. 26, no. 6, pp. 881–906, 2017, doi: 10.1007/s00778-017-0486-1.

[7] S. Schelter, D. Lange, P. Schmidt, M. Celikel, F. Biessmann, and A. Grafberger, "Automating large-scale data quality verification," _Proc. VLDB Endow._, vol. 11, no. 12, pp. 1781–1794, 2018, doi: 10.14778/3229863.3229867.

[8] Z. Zhao, L. De Stefani, E. Zgraggen, C. Binnig, E. Upfal, and T. Kraska, "Controlling false discoveries during interactive data exploration," in _Proc. ACM SIGMOD Int. Conf. Manage. Data_, 2017, pp. 527–540, doi: 10.1145/3035918.3064019.

[9] E. Zgraggen, Z. Zhao, R. Zeleznik, and T. Kraska, "Investigating the effect of the multiple comparisons problem in visual analysis," in _Proc. CHI Conf. Human Factors Comput. Syst._, 2018, pp. 1–12, doi: 10.1145/3173574.3174053.

[10] S. Jo, I. Trummer, W. Yu, X. Wang, C. Yu, D. Liu, and N. Mehta, "Verifying text summaries of relational data sets," in _Proc. ACM SIGMOD Int. Conf. Manage. Data_, 2019, pp. 299–316, doi: 10.1145/3299869.3300074.

[11] R. Ding, S. Han, Y. Xu, H. Zhang, and D. Zhang, "QuickInsights: Quick and automatic discovery of insights from multi-dimensional data," in _Proc. ACM SIGMOD Int. Conf. Manage. Data_, 2019, pp. 317–332, doi: 10.1145/3299869.3314037.

[12] M. Vartak, S. Rahman, S. Madden, A. Parameswaran, and N. Polyzotis, "SeeDB: Efficient data-driven visualization recommendations to support visual analytics," _Proc. VLDB Endow._, vol. 8, no. 13, pp. 2182–2193, 2015, doi: 10.14778/2831360.2831371.

[13] L. Jiang and F. Naumann, "Holistic primary key and foreign key detection," _J. Intell. Inf. Syst._, vol. 54, no. 3, pp. 439–461, 2020, doi: 10.1007/s10844-019-00562-z.

[14] G. J. J. van den Burg, A. Nazábal, and C. Sutton, "Wrangling messy CSV files by detecting row and type patterns," _Data Min. Knowl. Discov._, vol. 33, no. 6, pp. 1799–1820, 2019, doi: 10.1007/s10618-019-00646-y.

[15] D. J.-L. Lee _et al._, "Lux: Always-on visualization recommendations for exploratory dataframe workflows," _Proc. VLDB Endow._, vol. 15, no. 3, pp. 727–738, 2021, doi: 10.14778/3494124.3494151.

[16] J. Peng _et al._, "DataPrep.EDA: Task-centric exploratory data analysis for statistical modeling in Python," in _Proc. Int. Conf. Manage. Data (SIGMOD)_, 2021, pp. 2271–2280, doi: 10.1145/3448016.3457330.

[17] P. Ma, R. Ding, S. Han, and D. Zhang, "MetaInsight: Automatic discovery of structured knowledge for exploratory data analysis," in _Proc. Int. Conf. Manage. Data (SIGMOD)_, 2021, pp. 1262–1274, doi: 10.1145/3448016.3457267.

[18] J. Song and Y. He, "Auto-Validate: Unsupervised data validation using data-domain patterns inferred from data lakes," in _Proc. Int. Conf. Manage. Data (SIGMOD)_, 2021, pp. 1678–1691, doi: 10.1145/3448016.3457250.

[19] C. Koutras _et al._, "Valentine: Evaluating matching techniques for dataset discovery," in _Proc. IEEE 37th Int. Conf. Data Eng. (ICDE)_, 2021, pp. 468–479, doi: 10.1109/ICDE51399.2021.00047.

[20] D. Shi, X. Xu, F. Sun, Y. Shi, and N. Cao, "Calliope: Automatic visual data story generation from a spreadsheet," _IEEE Trans. Vis. Comput. Graphics_, vol. 27, no. 2, pp. 453–463, 2021, doi: 10.1109/TVCG.2020.3030403.

[21] A. Narechania, A. Srinivasan, and J. Stasko, "NL4DV: A toolkit for generating analytic specifications for data visualization from natural language queries," _IEEE Trans. Vis. Comput. Graphics_, vol. 27, no. 2, pp. 369–379, 2021, doi: 10.1109/TVCG.2020.3030378.

[22] X. He, K. Zhao, and X. Chu, "AutoML: A survey of the state-of-the-art," _Knowl.-Based Syst._, vol. 212, Art. no. 106622, 2021, doi: 10.1016/j.knosys.2020.106622.

[23] S. K. Karmaker ("Santu"), M. M. Hassan, M. J. Smith, L. Xu, C. Zhai, and K. Veeramachaneni, "AutoML to date and beyond: Challenges and opportunities," _ACM Comput. Surv._, vol. 54, no. 8, pp. 1–36, 2022, doi: 10.1145/3470918.

[24] T. De Bie, L. De Raedt, J. Hernández-Orallo, H. H. Hoos, P. Smyth, and C. K. I. Williams, "Automating data science," _Commun. ACM_, vol. 65, no. 3, pp. 76–87, 2022, doi: 10.1145/3495256.

[25] A. Wu _et al._, "AI4VIS: Survey on artificial intelligence approaches for data visualization," _IEEE Trans. Vis. Comput. Graphics_, vol. 28, no. 12, pp. 5049–5070, 2022, doi: 10.1109/TVCG.2021.3099002.

[26] H. Li, Y. Wang, S. Zhang, Y. Song, and H. Qu, "KG4Vis: A knowledge graph-based approach for visualization recommendation," _IEEE Trans. Vis. Comput. Graphics_, vol. 28, no. 1, pp. 195–205, 2022, doi: 10.1109/TVCG.2021.3114863.

[27] Y. Luo, N. Tang, G. Li, J. Tang, C. Chai, and X. Qin, "Natural language to visualization by neural machine translation," _IEEE Trans. Vis. Comput. Graphics_, vol. 28, no. 1, pp. 217–226, 2022, doi: 10.1109/TVCG.2021.3114848.

[28] L. Ehrlinger and W. Wöß, "A survey of data quality measurement and monitoring tools," _Front. Big Data_, vol. 5, Art. no. 850611, 2022, doi: 10.3389/fdata.2022.850611.

[29] Y. Lin, Y. He, and S. Chaudhuri, "Auto-BI: Automatically build BI-models leveraging local join prediction and global schema graph," _Proc. VLDB Endow._, vol. 16, no. 10, pp. 2578–2590, 2023, doi: 10.14778/3603581.3603596.

[30] Y. Dong, C. Xiao, T. Nozawa, M. Enomoto, and M. Oyamada, "DeepJoin: Joinable table discovery with pre-trained language models," _Proc. VLDB Endow._, vol. 16, no. 10, pp. 2458–2470, 2023, doi: 10.14778/3603581.3603587.

[31] G. Fan, J. Wang, Y. Li, D. Zhang, and R. J. Miller, "Semantics-aware dataset discovery from data lakes with contextualized column-based representation learning," _Proc. VLDB Endow._, vol. 16, no. 7, pp. 1726–1739, 2023, doi: 10.14778/3587136.3587146.

[32] G. Vitagliano, M. Hameed, L. Jiang, L. Reisener, E. Wu, and F. Naumann, "Pollock: A data loading benchmark," _Proc. VLDB Endow._, vol. 16, no. 8, pp. 1870–1882, 2023, doi: 10.14778/3594512.3594518.

[33] P. Li, Y. He, C. Yan, Y. Wang, and S. Chaudhuri, "Auto-Tables: Synthesizing multi-step transformations to relationalize tables without using examples," _Proc. VLDB Endow._, vol. 16, no. 11, pp. 3391–3403, 2023, doi: 10.14778/3611479.3611534.

[34] Y. Zhang, A. Floratou, J. Cahoon, S. Krishnan, A. C. Müller, D. Banda, F. Psallidas, and J. M. Patel, "Schema matching using pre-trained language models," in _Proc. IEEE 39th Int. Conf. Data Eng. (ICDE)_, 2023, pp. 1558–1571, doi: 10.1109/ICDE55515.2023.00123.

[35] V. Dibia, "LIDA: A tool for automatic generation of grammar-agnostic visualizations and infographics using large language models," in _Proc. 61st Annu. Meeting Assoc. Comput. Linguistics (Vol. 3: System Demonstrations)_, 2023, pp. 113–126, doi: 10.18653/v1/2023.acl-demo.11.

[36] P. Maddigan and T. Susnjak, "Chat2VIS: Generating data visualizations via natural language using ChatGPT, Codex and GPT-3 large language models," _IEEE Access_, vol. 11, pp. 45181–45193, 2023, doi: 10.1109/ACCESS.2023.3274199.

[37] L. Cheng, X. Li, and L. Bing, "Is GPT-4 a good data analyst?," in _Findings Assoc. Comput. Linguistics: EMNLP 2023_, 2023, pp. 9496–9514, doi: 10.18653/v1/2023.findings-emnlp.637.

[38] J. Li _et al._, "Can LLM already serve as a database interface? A BIg bench for large-scale database grounded text-to-SQLs," in _Adv. Neural Inf. Process. Syst. (NeurIPS), Datasets and Benchmarks Track_, vol. 36, 2023, pp. 42330–42357, doi: 10.52202/075280-1835. [Online]. Available: https://proceedings.neurips.cc/paper_files/paper/2023/hash/83fc8fab1710363050bbd1d4b8cc0021-Abstract-Datasets_and_Benchmarks.html

[39] Z. Ji _et al._, "Survey of hallucination in natural language generation," _ACM Comput. Surv._, vol. 55, no. 12, pp. 1–38, 2023, doi: 10.1145/3571730.

[40] C. Wang, J. Thompson, and B. Lee, "Data Formulator: AI-powered concept-driven visualization authoring," _IEEE Trans. Vis. Comput. Graphics_, 2023 (early access, pp. 1–11), doi: 10.1109/TVCG.2023.3326585.

[41] D. Gao _et al._, "Text-to-SQL empowered by large language models: A benchmark evaluation," _Proc. VLDB Endow._, vol. 17, no. 5, pp. 1132–1145, 2024, doi: 10.14778/3641204.3641221.

[42] P. Li _et al._, "Table-GPT: Table fine-tuned GPT for diverse table tasks," _Proc. ACM Manage. Data_, vol. 2, no. 3, pp. 1–28, 2024, doi: 10.1145/3654979.

[43] K. Gu, R. Shang, T. Althoff, C. Wang, and S. M. Drucker, "How do analysts understand and verify AI-assisted data analyses?," in _Proc. CHI Conf. Human Factors Comput. Syst._, 2024, pp. 1–22, doi: 10.1145/3613904.3642497.

[44] M. Kazemitabaar _et al._, "Improving steering and verification in AI-assisted data analysis with interactive task decomposition," in _Proc. 37th Annu. ACM Symp. User Interface Softw. Technol. (UIST)_, 2024, pp. 1–19, doi: 10.1145/3654777.3676345.

[45] V. Venktesh, A. Anand, A. Anand, and V. Setty, "QuanTemp: A real-world open-domain benchmark for fact-checking numerical claims," in _Proc. 47th Int. ACM SIGIR Conf. Res. Develop. Inf. Retrieval_, 2024, pp. 650–660, doi: 10.1145/3626772.3657874.

[46] M. S. Islam, M. T. R. Laskar, M. R. Parvez, E. Hoque, and S. Joty, "DataNarrative: Automated data-driven storytelling with visualizations and texts," in _Proc. Conf. Empirical Methods Natural Lang. Process. (EMNLP)_, 2024, pp. 19253–19286, doi: 10.18653/v1/2024.emnlp-main.1073.

[47] Q. Chen, S. Cao, J. Wang, and N. Cao, "How does automation shape the process of narrative visualization: A survey of tools," _IEEE Trans. Vis. Comput. Graphics_, vol. 30, no. 8, pp. 4429–4448, 2024, doi: 10.1109/TVCG.2023.3261320.

[48] Y. Liu, E. H. M. Pena, A. Santos, E. Wu, and J. Freire, "Magneto: Combining small and large language models for schema matching," _Proc. VLDB Endow._, vol. 18, no. 8, pp. 2681–2694, 2025, doi: 10.14778/3742728.3742757.

[49] Z. Hong _et al._, "Next-generation database interfaces: A survey of LLM-based text-to-SQL," _IEEE Trans. Knowl. Data Eng._, vol. 37, no. 12, pp. 7328–7345, 2025, doi: 10.1109/TKDE.2025.3609486.

[50] L. Huang _et al._, "A survey on hallucination in large language models: Principles, taxonomy, challenges, and open questions," _ACM Trans. Inf. Syst._, vol. 43, no. 2, pp. 1–55, 2025, doi: 10.1145/3703155.

[51] K. Hu, M. A. Bakker, S. Li, T. Kraska, and C. Hidalgo, "VizML: A machine learning approach to visualization recommendation," in _Proc. CHI Conf. Human Factors Comput. Syst._, 2019, pp. 1–12, doi: 10.1145/3290605.3300358.

Notas de formato: autores, volumen, número y páginas se tomaron de Crossref; se omite el dato cuando
Crossref no lo da (p. ej., las actas de conferencias no tienen volumen). [40] figura en Crossref sólo como
_early access_ de 2023; conviene completar su volumen y número definitivos desde la página del DOI.

## 3. Venue, tipo, nivel y verificación de cada referencia

Nivel: «A\* (CORE2023)» se comprobó en el portal CORE (`portal.core.edu.au/conf-ranks/?search=<siglas>&source=CORE2023`):
SIGMOD, VLDB, ICDE, CHI, UIST, SIGIR, ACL, EMNLP y NeurIPS figuran como A\*. Para PVLDB y PACMMOD se usa
el rango de su conferencia (VLDB y SIGMOD), de las que son las actas. SCImago (scimagojr.com) devolvió
HTTP 403; los cuartiles de TVCG y ACM Computing Surveys se confirmaron en el listado SJR 2024 mostrado por
el buscador web (Q1). Los demás cuartiles quedan como «no verificado».

| Ref  | Venue                                        | Tipo                   | Nivel                                              | Verificación                                                                                            |
| ---- | -------------------------------------------- | ---------------------- | -------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| [1]  | J. Roy. Statist. Soc. B                      | journal                | no verificado (fundacional)                        | api.crossref.org/works/10.1111/j.2517-6161.1995.tb02031.x                                               |
| [2]  | J. Amer. Statist. Assoc.                     | journal                | no verificado (fundacional)                        | api.crossref.org/works/10.1080/01621459.1952.10483441                                                   |
| [3]  | Philosophical Magazine                       | journal                | no verificado (fundacional, 1900)                  | api.crossref.org/works/10.1080/14786440009463897                                                        |
| [4]  | Usability Evaluation in Industry (CRC Press) | capítulo de libro      | no aplica                                          | api.crossref.org/works/10.1201/9781498710411-35                                                         |
| [5]  | ISO/IEC                                      | norma                  | no aplica                                          | iso.org/standard/78176.html (confirmada vía buscador; la página directa pide verificación de navegador) |
| [6]  | The VLDB Journal                             | journal                | no verificado                                      | api.crossref.org/works/10.1007/s00778-017-0486-1                                                        |
| [7]  | PVLDB                                        | journal (actas VLDB)   | A\* (CORE2023, VLDB)                               | api.crossref.org/works/10.14778/3229863.3229867                                                         |
| [8]  | ACM SIGMOD 2017                              | conference             | A\* (CORE2023)                                     | api.crossref.org/works/10.1145/3035918.3064019                                                          |
| [9]  | ACM CHI 2018                                 | conference             | A\* (CORE2023)                                     | api.crossref.org/works/10.1145/3173574.3174053                                                          |
| [10] | ACM SIGMOD 2019                              | conference             | A\* (CORE2023)                                     | api.crossref.org/works/10.1145/3299869.3300074                                                          |
| [11] | ACM SIGMOD 2019                              | conference             | A\* (CORE2023)                                     | api.crossref.org/works/10.1145/3299869.3314037                                                          |
| [12] | PVLDB                                        | journal (actas VLDB)   | A\* (CORE2023, VLDB)                               | api.crossref.org/works/10.14778/2831360.2831371                                                         |
| [13] | J. Intell. Inf. Syst.                        | journal                | no verificado                                      | api.crossref.org/works/10.1007/s10844-019-00562-z                                                       |
| [14] | Data Min. Knowl. Discov.                     | journal                | no verificado                                      | api.crossref.org/works/10.1007/s10618-019-00646-y                                                       |
| [15] | PVLDB                                        | journal (actas VLDB)   | A\* (CORE2023, VLDB)                               | api.crossref.org/works/10.14778/3494124.3494151                                                         |
| [16] | ACM SIGMOD 2021                              | conference             | A\* (CORE2023)                                     | api.crossref.org/works/10.1145/3448016.3457330                                                          |
| [17] | ACM SIGMOD 2021                              | conference             | A\* (CORE2023)                                     | api.crossref.org/works/10.1145/3448016.3457267                                                          |
| [18] | ACM SIGMOD 2021                              | conference             | A\* (CORE2023)                                     | api.crossref.org/works/10.1145/3448016.3457250                                                          |
| [19] | IEEE ICDE 2021                               | conference             | A\* (CORE2023)                                     | api.crossref.org/works/10.1109/ICDE51399.2021.00047                                                     |
| [20] | IEEE TVCG                                    | journal                | Q1 (SJR 2024)                                      | api.crossref.org/works/10.1109/TVCG.2020.3030403                                                        |
| [21] | IEEE TVCG                                    | journal                | Q1 (SJR 2024)                                      | api.crossref.org/works/10.1109/TVCG.2020.3030378                                                        |
| [22] | Knowledge-Based Systems                      | journal                | no verificado                                      | api.crossref.org/works/10.1016/j.knosys.2020.106622                                                     |
| [23] | ACM Computing Surveys                        | journal                | Q1 (SJR 2024)                                      | api.crossref.org/works/10.1145/3470918                                                                  |
| [24] | Communications of the ACM                    | journal (revista)      | no verificado                                      | api.crossref.org/works/10.1145/3495256                                                                  |
| [25] | IEEE TVCG                                    | journal                | Q1 (SJR 2024)                                      | api.crossref.org/works/10.1109/TVCG.2021.3099002                                                        |
| [26] | IEEE TVCG                                    | journal                | Q1 (SJR 2024)                                      | api.crossref.org/works/10.1109/TVCG.2021.3114863                                                        |
| [27] | IEEE TVCG                                    | journal                | Q1 (SJR 2024)                                      | api.crossref.org/works/10.1109/TVCG.2021.3114848                                                        |
| [28] | Frontiers in Big Data                        | journal                | no verificado                                      | api.crossref.org/works/10.3389/fdata.2022.850611                                                        |
| [29] | PVLDB                                        | journal (actas VLDB)   | A\* (CORE2023, VLDB)                               | api.crossref.org/works/10.14778/3603581.3603596                                                         |
| [30] | PVLDB                                        | journal (actas VLDB)   | A\* (CORE2023, VLDB)                               | api.crossref.org/works/10.14778/3603581.3603587                                                         |
| [31] | PVLDB                                        | journal (actas VLDB)   | A\* (CORE2023, VLDB)                               | api.crossref.org/works/10.14778/3587136.3587146                                                         |
| [32] | PVLDB                                        | journal (actas VLDB)   | A\* (CORE2023, VLDB)                               | api.crossref.org/works/10.14778/3594512.3594518                                                         |
| [33] | PVLDB                                        | journal (actas VLDB)   | A\* (CORE2023, VLDB)                               | api.crossref.org/works/10.14778/3611479.3611534                                                         |
| [34] | IEEE ICDE 2023                               | conference             | A\* (CORE2023)                                     | api.crossref.org/works/10.1109/icde55515.2023.00123                                                     |
| [35] | ACL 2023, System Demonstrations              | conference (demo)      | no contabilizado (A\* es la conferencia principal) | api.crossref.org/works/10.18653/v1/2023.acl-demo.11; aclanthology.org/2023.acl-demo.11                  |
| [36] | IEEE Access                                  | journal                | no verificado                                      | api.crossref.org/works/10.1109/ACCESS.2023.3274199                                                      |
| [37] | Findings of EMNLP 2023                       | conference (Findings)  | no contabilizado (A\* es la conferencia principal) | api.crossref.org/works/10.18653/v1/2023.findings-emnlp.637; aclanthology.org/2023.findings-emnlp.637    |
| [38] | NeurIPS 2023 (Datasets and Benchmarks)       | conference             | A\* (CORE2023, NeurIPS)                            | Crossref DOI 10.52202/075280-1835; proceedings.neurips.cc (página del artículo)                         |
| [39] | ACM Computing Surveys                        | journal                | Q1 (SJR 2024)                                      | api.crossref.org/works/10.1145/3571730                                                                  |
| [40] | IEEE TVCG                                    | journal                | Q1 (SJR 2024)                                      | api.crossref.org/works/10.1109/TVCG.2023.3326585                                                        |
| [41] | PVLDB                                        | journal (actas VLDB)   | A\* (CORE2023, VLDB)                               | api.crossref.org/works/10.14778/3641204.3641221                                                         |
| [42] | PACMMOD (SIGMOD)                             | journal (actas SIGMOD) | A\* (CORE2023, SIGMOD)                             | api.crossref.org/works/10.1145/3654979                                                                  |
| [43] | ACM CHI 2024                                 | conference             | A\* (CORE2023)                                     | api.crossref.org/works/10.1145/3613904.3642497                                                          |
| [44] | ACM UIST 2024                                | conference             | A\* (CORE2023)                                     | api.crossref.org/works/10.1145/3654777.3676345                                                          |
| [45] | ACM SIGIR 2024                               | conference             | A\* (CORE2023)                                     | api.crossref.org/works/10.1145/3626772.3657874                                                          |
| [46] | EMNLP 2024 (main)                            | conference             | A\* (CORE2023)                                     | Crossref (búsqueda bibliográfica); aclanthology.org/2024.emnlp-main.1073                                |
| [47] | IEEE TVCG                                    | journal                | Q1 (SJR 2024)                                      | api.crossref.org/works/10.1109/tvcg.2023.3261320                                                        |
| [48] | PVLDB                                        | journal (actas VLDB)   | A\* (CORE2023, VLDB)                               | api.crossref.org/works/10.14778/3742728.3742757                                                         |
| [49] | IEEE TKDE                                    | journal                | no verificado                                      | api.crossref.org/works/10.1109/tkde.2025.3609486                                                        |
| [50] | ACM Trans. Inf. Syst.                        | journal                | no verificado                                      | api.crossref.org/works/10.1145/3703155                                                                  |
| [51] | ACM CHI 2019                                 | conference             | A\* (CORE2023)                                     | api.crossref.org/works/10.1145/3290605.3300358                                                          |

## 4. Mapa de gaps

Grupos: **G1** AutoML / ciencia de datos automática [22]–[24]; **G2** EDA e _insights_ automáticos [11],
[12], [15]–[17]; **G3** recomendación de gráficos y NL2VIS [21], [25]–[27], [35], [36], [40], [51];
**G4** calidad, validación y carga [7], [14], [18], [28], [32], [33]; **G5** claves, joins y _schema
matching_ [13], [19], [29]–[31], [34], [48]; **G6** LLM para análisis y texto a SQL [37], [38], [41]–[44],
[49]; **G7** narrativas e informes automáticos [20], [46], [47]; **G8** verificación de cifras y falsos
descubrimientos [8]–[10], [45].

Criterio: ✓ = el grupo lo cubre según los resúmenes revisados; parcial = lo cubre algún trabajo del grupo
o sólo en parte; ✗ = no consta en los trabajos revisados (no significa que sea imposible con ellos).
La última columna describe el diseño de DataFlow AI, no una evaluación externa.

| Aspecto                                                         | G1                                               | G2                                                | G3                                                                | G4                                                        | G5                                                            | G6                                                                                 | G7                                               | G8                                                                  | DataFlow AI (diseño)                          |
| --------------------------------------------------------------- | ------------------------------------------------ | ------------------------------------------------- | ----------------------------------------------------------------- | --------------------------------------------------------- | ------------------------------------------------------------- | ---------------------------------------------------------------------------------- | ------------------------------------------------ | ------------------------------------------------------------------- | --------------------------------------------- |
| Automatización de extremo a extremo sin intervención            | parcial ([23]: aún requiere intervención humana) | parcial (descubre _insights_, el usuario explora) | ✗ (guiado por consulta o autoría)                                 | parcial ([33] sin entrada del usuario, sólo reestructura) | parcial ([29] predice el modelo BI; [34] requiere etiquetado) | ✗ (guiado por pregunta)                                                            | parcial ([20] automático con editor de revisión) | ✗                                                                   | ✓                                             |
| Múltiples tablas relacionadas                                   | ✗                                                | ✗ (datos multidimensionales de una tabla)         | ✗                                                                 | ✗                                                         | ✓ ([13], [29])                                                | ✓ ([38]: 95 bases de datos)                                                        | ✗                                                | parcial ([10]: conjuntos relacionales)                              | ✓ (`relations-v1`)                            |
| LLM que no calcula cifras / cifras trazables                    | ✗                                                | parcial (cifras del motor, sin LLM)               | ✗ ([35], [36], [40]: el LLM genera el código o la transformación) | ✗                                                         | ✗                                                             | parcial (SQL generado y ejecutado por el motor; verificación humana en [43], [44]) | parcial ([46]: agente verificador)               | parcial ([10] contrasta afirmaciones con los datos; [45] benchmark) | ✓ (`{{evidence:id}}`)                         |
| Pruebas estadísticas con corrección por comparaciones múltiples | ✗                                                | ✗                                                 | ✗                                                                 | ✗                                                         | ✗                                                             | ✗                                                                                  | ✗                                                | ✓ ([8] control de FDR; [9] mide el problema)                        | ✓ (chi², Kruskal-Wallis, Benjamini-Hochberg)  |
| Trazabilidad / linaje e inmutabilidad                           | ✗                                                | ✗                                                 | ✗                                                                 | parcial ([7] validación incremental)                      | ✗                                                             | ✗                                                                                  | ✗                                                | parcial ([10] asocia afirmación y consulta)                         | ✓ (versiones derivadas con `effect_sha256`)   |
| Informe narrativo automático                                    | ✗                                                | ✗                                                 | parcial ([35] infografías)                                        | ✗                                                         | ✗                                                             | ✗                                                                                  | ✓ ([20], [46])                                   | ✗                                                                   | ✓ (informe PDF)                               |
| Datos regionales / Excel heterogéneo                            | ✗                                                | ✗                                                 | ✗                                                                 | parcial ([14], [32] dialectos CSV; [33] hojas de cálculo) | ✗                                                             | parcial ([38] contenido sucio)                                                     | parcial ([20] parte de una hoja de cálculo)      | ✗                                                                   | ✓ (`regional-values-v1`, `xlsx-selection-v2`) |

Lectura: ningún grupo revisado combina automatización completa, varias tablas, cifras trazables que el
LLM no calcula y control estadístico de comparaciones múltiples; los trabajos más cercanos cubren uno o dos
de esos ejes cada uno (p. ej., [29] varias tablas, [8] corrección múltiple, [10] verificación de cifras,
[20] narrativa automática).

## 5. Marco conceptual (2.1)

El **análisis exploratorio de datos (EDA)** es la etapa en la que se resumen e inspeccionan los datos para
encontrar patrones antes de modelar; las bibliotecas actuales lo automatizan parcialmente orientándolo a
tareas [16]. El **descubrimiento automático de _insights_** busca y puntúa patrones interesantes en datos
multidimensionales sin que el usuario los formule [11], [17], y la **recomendación de visualizaciones**
elige automáticamente los gráficos adecuados para una tabla [12], [15], [26]. **AutoML** automatiza etapas
de la canalización de aprendizaje automático y se clasifica por niveles de autonomía [22], [23]; la
**ciencia de datos automática** extiende esa idea a todo el proceso analítico [24]. La **calidad de datos**
se mide por dimensiones y métricas mediante perfilado y monitorización [28], y la **validación de datos**
la comprueba con restricciones declarativas o patrones inferidos, a modo de «pruebas unitarias» de los
datos [7], [18]; previamente, la **detección del dialecto** de un CSV (delimitador, comillas) decide cómo
leer el archivo [14], [32]. Una **clave foránea** es una columna cuyos valores están contenidos en la clave
primaria de otra tabla y puede detectarse a partir de los datos [13]; el _**schema matching**_ establece
correspondencias entre columnas de esquemas distintos [19], [48]. La **procedencia o linaje** registra de
dónde viene cada dato y cómo se transformó [6]. En los LLM, la **alucinación** es la generación de
contenido no respaldado por la fuente [39], [50], y el **texto a SQL** traduce preguntas en lenguaje
natural a consultas ejecutables [49]. El **problema de las comparaciones múltiples** aumenta los falsos
descubrimientos al examinar muchas hipótesis, también en la exploración visual [8], [9]; la **tasa de falsos
descubrimientos (FDR)** y su control por el procedimiento de Benjamini-Hochberg lo acotan [1]. La prueba
**chi²** contrasta frecuencias observadas y esperadas [3] y la prueba de **Kruskal-Wallis** compara
distribuciones de varios grupos mediante rangos [2]. La **visualización narrativa** organiza hechos de datos
en una historia, cada vez con más automatización [20], [47]. Por último, la calidad del producto software se
evalúa con el modelo de **ISO/IEC 25010** [5] y la usabilidad percibida con la escala **SUS** [4].

## Verificación

- Referencias totales: **51**, todas con DOI resuelto en Crossref (salvo [5], norma ISO con URL del editor).
- De 2021–2026: **37 de 51 = 72,5 %** ([5], [15]–[50]).
- Primer nivel **verificado**: **35 de 51 = 68,6 %** — 26 en conferencias A\* de CORE2023 (o sus actas
  PVLDB/PACMMOD) y 9 en revistas Q1 confirmadas en SJR 2024 (7 IEEE TVCG, 2 ACM Computing Surveys).
- Sin verificar el cuartil (SCImago bloqueó el acceso): 12 revistas ([1], [2], [3], [6], [13], [14], [22],
  [24], [28], [36], [49], [50]); por su prestigio probablemente sean Q1 o Q2, pero no se contabilizan.
- No contabilizados como primer nivel: [4] (capítulo de libro), [5] (norma), [35] (demo de ACL),
  [37] (Findings de EMNLP).
- Estado del arte: **28 trabajos** de 2021–2026 en la tabla del §1 (el TDDR §2.2 añade [21], [22], [24], [25], [35], [49] y [50] sólo con su tipo, sin cifras); cifras sólo cuando aparecen en el
  resumen publicado.
- No se usó arXiv, blogs ni Wikipedia como referencia.
