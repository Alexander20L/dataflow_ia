/** Autogenerado desde OpenAPI. No editar manualmente. */
export interface paths {
    "/api/v1/auth/login": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Login */
        post: operations["login"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/logout": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Logout */
        post: operations["logout"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/me": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Me */
        get: operations["getSession"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/register": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Register */
        post: operations["register"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/datasets/summary": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Summary */
        get: operations["getIngestionSummary"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/executions/{execution_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Execution */
        get: operations["getExecution"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/executions/{execution_id}/analysis": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Result */
        get: operations["getExecutionAnalysis"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/executions/{execution_id}/analysis.csv": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Export Result
         * @description Resultado de análisis en CSV; cada cifra con su `evidence_id`.
         */
        get: operations["exportAnalysisCsv"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/executions/{execution_id}/artifacts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Execution Artifacts */
        get: operations["listExecutionArtifacts"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/executions/{execution_id}/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Cancel */
        post: operations["cancelImport"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/executions/{execution_id}/evidence/{evidence_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Evidence */
        get: operations["getEvidence"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/executions/{execution_id}/profile": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Execution Profile */
        get: operations["getExecutionProfile"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/executions/{execution_id}/quality": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Execution Quality */
        get: operations["getExecutionQuality"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/projects": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Projects */
        get: operations["listProjects"];
        put?: never;
        /** Create Project */
        post: operations["createProject"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/projects/{project_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Project */
        get: operations["getProject"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Update Project */
        patch: operations["updateProject"];
        trace?: never;
    };
    "/api/v1/projects/{project_id}/archive": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Archive Project */
        post: operations["archiveProject"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/projects/{project_id}/imports": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Upload Csv */
        post: operations["uploadCsv"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/projects/{project_id}/imports/pdf": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Upload Pdf
         * @description Fase 18B: importa las tablas de un PDF con texto (`pdf-selection-v1`). Devuelve la
         *     versión de la tabla principal; las demás tablas se registran como versiones propias y se
         *     indican en `source_origin`. PDF escaneado: 422 `PDF_NO_TEXT`; sin tablas: `PDF_NO_TABLES`.
         */
        post: operations["uploadPdf"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/projects/{project_id}/imports/sqlserver": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Import Sqlserver
         * @description Fase 18B: copia de un solo uso de las tablas de una base de SQL Server
         *     (`sqlserver-selection-v1`); cada tabla es una versión con su CSV original. La contraseña se
         *     usa para la copia y se descarta. Sólo servidores de `DATAFLOW_SQLSERVER_ALLOWED_HOSTS`.
         */
        post: operations["importSqlServer"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/projects/{project_id}/imports/xlsx": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Upload Xlsx
         * @description Importa un libro con ingestion.read_xlsx@1. Sin `sheet` ni `table` (Fase 13B), el
         *     sistema elige la hoja o tabla y la cabecera (`xlsx-selection-v1`) y lo informa en
         *     `source_selection`; con `table` hay que indicar también su `sheet`.
         */
        post: operations["uploadXlsx"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/projects/{project_id}/imports/xlsx/inspect": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Inspect Xlsx
         * @description Hojas, tablas con nombre y vista previa; no guarda nada. Sin `sheet` ni `table`
         *     muestra la elección automática del sistema (`selection`, Fase 13B).
         */
        post: operations["inspectXlsx"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/projects/{project_id}/versions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Versions */
        get: operations["listVersions"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/versions/{version_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Version */
        get: operations["getVersion"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/versions/{version_id}/automatic-analysis": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Automatic Analysis
         * @description Plan analítico automático y hallazgos con evidencia, guardados al importar.
         */
        get: operations["getAutomaticAnalysis"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/versions/{version_id}/automatic-analysis/evidence/{evidence_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Automatic Evidence
         * @description Procedencia exacta de una cifra del análisis automático (método y entradas).
         */
        get: operations["getAutomaticEvidence"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/versions/{version_id}/comprehension": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Comprehension
         * @description Escalas de medida, asociaciones, hipótesis de la IA y relaciones con su evidencia.
         */
        get: operations["getComprehension"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/versions/{version_id}/comprehension/feedback": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Judge
         * @description Valoración opcional (validar o rechazar una relación): no bloquea. Desde la Fase 24
         *     cuenta ya: se rehacen la exploración, el dashboard y el informe; la siguiente carga del mismo
         *     archivo también la tiene en cuenta. Vale la última.
         */
        post: operations["judgeRelationship"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/versions/{version_id}/comprehension/meanings": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Describe
         * @description Fase 24: significado de una columna escrito o confirmado por el usuario. Lo heredan las
         *     versiones siguientes del mismo archivo y no cambia ningún cálculo. Sin texto y sin confirmar
         *     vuelve al de la IA.
         */
        post: operations["describeColumn"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/versions/{version_id}/dashboard": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Dashboard
         * @description Fase 21: dashboard adaptado a los datos, con las marcas «sí va / no va» aplicadas.
         */
        get: operations["getDashboard"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/versions/{version_id}/dashboard/custom": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Save Dashboard Customization
         * @description Fase 26: guarda la versión personalizada del dashboard (secciones, orden, gráficos
         *     visibles, indicadores destacados y títulos) como una revisión nueva. La versión automática
         *     no cambia. 409 si la revisión esperada no es la vigente.
         */
        post: operations["saveDashboardCustomization"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/versions/{version_id}/dashboard/feedback": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Judge Finding
         * @description Marca opcional de un elemento («keep», «drop» o «none»). No recalcula nada: reordena el
         *     dashboard y encola una versión nueva del informe con ese orden.
         */
        post: operations["judgeFinding"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/versions/{version_id}/dashboard/filter": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Filter Dashboard
         * @description Fase 26: recalcula, con el motor exacto y sobre todas las filas que cumplen los filtros
         *     (meses y valores de dimensiones), los indicadores y los gráficos que dependen de ellos. No
         *     guarda nada ni cambia el dashboard.
         */
        post: operations["filterDashboard"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/versions/{version_id}/diagnostic": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Diagnostic */
        get: operations["getDiagnostic"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/versions/{version_id}/dictionary": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Annotate
         * @description Corrección manual de una columna (rol, naturaleza, interpretación temporal, observación
         *     o confirmación). Se guarda como metadato: no cambia el archivo ni ningún cálculo, y las
         *     versiones siguientes del mismo archivo la heredan. Vale la última.
         */
        post: operations["annotateColumn"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/versions/{version_id}/executions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Executions */
        get: operations["listVersionExecutions"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/versions/{version_id}/exploration": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Exploration
         * @description Plan, árbol, resultados exactos, evidencias y clasificación de la investigación. Con
         *     `execution_id`, una investigación anterior del historial.
         */
        get: operations["getExploration"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/versions/{version_id}/exploration/control": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Control
         * @description Fase 25: pausar o cancelar la investigación en marcha (se detiene al terminar la
         *     investigación en curso y conserva lo calculado), reanudar la pausada o volver a investigar.
         *     Responde 409 si la acción no corresponde al estado.
         */
        post: operations["controlInvestigation"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/versions/{version_id}/exploration/history": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * History
         * @description Fase 25: las investigaciones de la versión, de la más reciente a la primera.
         */
        get: operations["getInvestigationHistory"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/versions/{version_id}/export.csv": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Export Version
         * @description Tabla de la versión (también derivada) en el perfil `standard` o `excel_regional`.
         */
        get: operations["exportVersionCsv"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/versions/{version_id}/inspection": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Inspection
         * @description Resumen, perfil de cada columna, diagnóstico de calidad y lectura del archivo, calculados
         *     una vez sobre la tabla completa, y el diccionario vigente (con tus correcciones). Mientras
         *     se calcula devuelve el estado («queued» o «running»); las versiones anteriores a esta fase
         *     devuelven «unavailable».
         */
        get: operations["getInspection"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/versions/{version_id}/investigation": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Investigation
         * @description Seguimientos por reglas y propuestas de la IA validadas, con su explicación.
         */
        get: operations["getInvestigation"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/versions/{version_id}/investigation/evidence/{evidence_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Investigation Evidence
         * @description Procedencia de una cifra de la investigación o de los hallazgos que explica.
         */
        get: operations["getInvestigationEvidence"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/versions/{version_id}/lineage": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Lineage */
        get: operations["getVersionLineage"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/versions/{version_id}/original": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Original */
        get: operations["downloadOriginal"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/versions/{version_id}/overview-audit": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Overview Audit */
        get: operations["getOverviewAudit"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/versions/{version_id}/overview-audit/evidence/{evidence_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Overview Evidence */
        get: operations["getOverviewAuditEvidence"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/versions/{version_id}/preview": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Preview
         * @description Registros tal como se leyeron, paginados en el servidor. `sort` es el identificador de
         *     una columna; `search` busca el texto literal (sin distinguir mayúsculas) en todas.
         */
        get: operations["previewVersion"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/versions/{version_id}/progress": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Version Progress
         * @description Etapas de la carga (análisis, investigación e informe) con su estado.
         */
        get: operations["getVersionProgress"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/versions/{version_id}/reading": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Source Review
         * @description Cómo se leyó el archivo (codificación, separador, valores regionales) y qué columnas
         *     cambiaron respecto de la versión anterior del mismo archivo (Fase 18). Sólo lectura.
         */
        get: operations["getSourceReview"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/versions/{version_id}/report": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Report
         * @description Estado del informe automático de la versión.
         */
        get: operations["getReport"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/versions/{version_id}/report.pdf": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Report Pdf
         * @description PDF del informe automático (sólo cuando está listo). Fase 27: `execution_id` descarga
         *     una versión anterior del historial.
         */
        get: operations["downloadReport"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/versions/{version_id}/report/history": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Report History
         * @description Todas las versiones del informe, de la más reciente a la primera.
         */
        get: operations["getReportHistory"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/versions/{version_id}/report/review": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Report Review
         * @description Hallazgos candidatos con su revisión (pendiente, aprobado o rechazado) y si la selección
         *     difiere de la del último informe.
         */
        get: operations["getReportReview"];
        put?: never;
        /**
         * Review Report Finding
         * @description Aprueba, rechaza o deja pendiente un hallazgo. No genera el informe.
         */
        post: operations["reviewReportFinding"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/versions/{version_id}/report/versions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Generate Report Version
         * @description Genera una versión nueva del informe con la selección vigente; la anterior se conserva.
         *     409 `REPORT_UP_TO_DATE` si la selección no cambió.
         */
        post: operations["generateReportVersion"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/versions/{version_id}/report/versions/{execution_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Report Version
         * @description Una versión concreta del informe, con su documento para la vista previa.
         */
        get: operations["getReportVersion"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/versions/{version_id}/representations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Representations */
        get: operations["listVersionRepresentations"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/health/live": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Liveness */
        get: operations["liveness"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/health/ready": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Readiness */
        get: operations["readiness"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /**
         * AnalysisPlan
         * @description Plan versionado y acotado; sólo contiene análisis del catálogo automático.
         */
        AnalysisPlan: {
            /** Accepted */
            accepted: components["schemas"]["PlannedAnalysis"][];
            /** Estimated Cells */
            estimated_cells: number;
            /**
             * Interpretation Rules
             * @default automatic-interpretation-v2
             * @constant
             */
            interpretation_rules: "automatic-interpretation-v2";
            /** Max Analyses */
            max_analyses: number;
            /** Measure */
            measure: string | null;
            /** Omitted */
            omitted: components["schemas"]["PlannedAnalysis"][];
            /**
             * Rules Version
             * @default automatic-plan-v1
             * @constant
             */
            rules_version: "automatic-plan-v1";
        };
        /** AnalysisResult */
        AnalysisResult: {
            /** Avg Scale */
            avg_scale: number;
            /** Dimensions */
            dimensions: components["schemas"]["ResultColumn"][];
            /** Metrics */
            metrics: components["schemas"]["MetricDefinition"][];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            operation: "analytics.query@1";
            /** Row Count */
            row_count: number;
            /** Rows */
            rows: components["schemas"]["ResultRow"][];
            /**
             * Schema Version
             * @default 1
             * @constant
             */
            schema_version: 1;
            scope: components["schemas"]["EvidenceScope"];
        };
        /** AnalysisResultV2 */
        AnalysisResultV2: {
            /** Avg Scale */
            avg_scale: number;
            /** Change Scale */
            change_scale: number;
            /** Comparisons */
            comparisons: ("previous_period" | "same_period_last_year")[];
            /** Dimensions */
            dimensions: components["schemas"]["ResultColumn"][];
            /** Metrics */
            metrics: components["schemas"]["MetricDefinitionV2"][];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            operation: "analytics.query@2";
            ranking: components["schemas"]["RankingSummary"] | null;
            /** Row Count */
            row_count: number;
            /** Rows */
            rows: components["schemas"]["ResultRowV2"][];
            /**
             * Schema Version
             * @default 2
             * @constant
             */
            schema_version: 2;
            scope: components["schemas"]["EvidenceScope"];
            /** Share Scale */
            share_scale: number;
            /** Shares */
            shares: components["schemas"]["ShareTotal"][];
        };
        /** AnalysisResultV3 */
        AnalysisResultV3: {
            /** Avg Scale */
            avg_scale: number;
            /** Change Scale */
            change_scale: number;
            /** Comparisons */
            comparisons: ("previous_period" | "same_period_last_year")[];
            /** Dimensions */
            dimensions: components["schemas"]["ResultColumn"][];
            /** Metrics */
            metrics: components["schemas"]["MetricDefinitionV3"][];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            operation: "analytics.query@3";
            ranking: components["schemas"]["RankingSummary"] | null;
            /** Row Count */
            row_count: number;
            /** Rows */
            rows: components["schemas"]["ResultRowV3"][];
            /**
             * Schema Version
             * @default 3
             * @constant
             */
            schema_version: 3;
            scope: components["schemas"]["EvidenceScope"];
            /** Share Scale */
            share_scale: number;
            /** Shares */
            shares: components["schemas"]["ShareTotal"][];
        };
        /**
         * AnalyticalColumn
         * @description Papel de una columna según automatic-interpretation-v2, con su evidencia.
         */
        AnalyticalColumn: {
            /** Additivity */
            additivity?: ("additive" | "semi_additive" | "non_additive" | "unknown") | null;
            /** Currency */
            currency?: ("known" | "unknown" | "ambiguous") | null;
            /** Currency Code */
            currency_code?: string | null;
            /** Evidence */
            evidence: string[];
            /**
             * Monetary
             * @default false
             */
            monetary: boolean;
            /** Name */
            name: string;
            /** Ordinal */
            ordinal: number;
            /**
             * Role
             * @enum {string}
             */
            role: "identifier" | "dimension" | "measure" | "time" | "text" | "empty";
            /** Time Part */
            time_part?: ("date" | "year" | "month") | null;
            /** Unit */
            unit?: ("known" | "unknown" | "ambiguous") | null;
            /** Unit Label */
            unit_label?: string | null;
        };
        /**
         * AnalyticalFinding
         * @description Hallazgo de automatic-quality-v1: qué problema hay y qué análisis afecta.
         *
         *     `blocking` bloquea sólo los análisis listados, no el resto del dashboard. Una observación
         *     (`info`) no es un error: nada se corrige automáticamente.
         */
        AnalyticalFinding: {
            /** Affected Analyses */
            affected_analyses: string[];
            /** Affected Rows */
            affected_rows: number;
            /**
             * Check
             * @enum {string}
             */
            check: "AQ-001" | "AQ-002" | "AQ-003" | "AQ-004" | "AQ-005" | "AQ-006" | "AQ-007" | "AQ-008";
            /** Columns */
            columns: string[];
            /** Evidence */
            evidence: string[];
            /** Id */
            id: string;
            /** Sample Row Numbers */
            sample_row_numbers: number[];
            /**
             * Severity
             * @enum {string}
             */
            severity: "info" | "warning" | "blocking";
            /** Title */
            title: string;
        };
        /**
         * AnalyticalInterpretation
         * @description Interpretación sustentada por reglas: hipótesis con evidencia, no confirmaciones.
         */
        AnalyticalInterpretation: {
            /** Available Analyses */
            available_analyses: string[];
            /** Columns */
            columns: components["schemas"]["AnalyticalColumn"][];
            /**
             * Context
             * @enum {string}
             */
            context: "generic" | "sales" | "inventory" | "ambiguous";
            /** Dependencies */
            dependencies: components["schemas"]["ColumnDependency"][];
            /** Keys */
            keys: components["schemas"]["KeyCandidate"][];
            /** Label */
            label: string;
            /** Limitations */
            limitations: string[];
            /** Limited Analyses */
            limited_analyses: components["schemas"]["LimitedAnalysis"][];
            /** Relationships */
            relationships: components["schemas"]["MeasureRelationship"][];
            /** Row Meaning */
            row_meaning: string;
            /**
             * Rules Version
             * @default automatic-interpretation-v2
             * @constant
             */
            rules_version: "automatic-interpretation-v2";
            /** Summary */
            summary: string;
            time: components["schemas"]["TimeAxis"] | null;
        };
        /** AnalyticalQuality */
        AnalyticalQuality: {
            /** Blocking */
            blocking: number;
            /** Findings */
            findings: components["schemas"]["AnalyticalFinding"][];
            /**
             * Interpretation Rules
             * @default automatic-interpretation-v2
             * @constant
             */
            interpretation_rules: "automatic-interpretation-v2";
            /** Observations */
            observations: number;
            /**
             * Rules Version
             * @default automatic-quality-v1
             * @constant
             */
            rules_version: "automatic-quality-v1";
            /** Warnings */
            warnings: number;
        };
        /**
         * AnnotationRequest
         * @description Corrección de una columna. Sustituye a la anterior; todo vacío y sin confirmar vuelve a
         *     la clasificación automática. Nunca cambia el archivo: desde la Fase 23 la clasificación
         *     corregida se usa en la comprensión (que se recalcula) y los textos declarados como nulos
         *     crean una versión derivada.
         */
        AnnotationRequest: {
            /**
             * Column Id
             * Format: uuid
             */
            column_id: string;
            /**
             * Confirmed
             * @default false
             */
            confirmed: boolean;
            /** Nature */
            nature?: ("nominal" | "ordinal" | "discrete" | "continuous" | "temporal" | "unknown") | null;
            /** Notes */
            notes?: string | null;
            /** Null Tokens */
            null_tokens?: string[];
            /** Personal */
            personal?: boolean | null;
            /** Role */
            role?: ("identifier" | "dimension" | "measure" | "time" | "category" | "text" | "unknown") | null;
            /** Time Format */
            time_format?: ("day_month_year" | "month_day_year" | "year_month_day" | "year" | "month" | "year_month") | null;
        };
        /** ArchiveProjectRequest */
        ArchiveProjectRequest: {
            /** Expected Revision */
            expected_revision: number;
        };
        /**
         * Arrangement
         * @description El dashboard con las valoraciones aplicadas: fijados arriba y descartados aparte.
         */
        Arrangement: {
            /** Hidden */
            hidden: string[];
            /** Pinned */
            pinned: string[];
            /** Sections */
            sections: components["schemas"]["DashboardSection"][];
        };
        /** ArtifactResponse */
        ArtifactResponse: {
            /** Attempt Id */
            attempt_id: string | null;
            /** Byte Size */
            byte_size: number;
            /** Column Count */
            column_count: number | null;
            /** Columns */
            columns: {
                [key: string]: unknown;
            }[] | null;
            /**
             * Execution Id
             * Format: uuid
             */
            execution_id: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "table" | "profile" | "quality" | "legacy_diagnostic" | "effect" | "effect_samples" | "row_lineage" | "quality_rules" | "analysis_result" | "report_pdf" | "overview_audit" | "automatic_analysis" | "investigation" | "comprehension" | "exploration" | "dashboard" | "inspection" | "report_document";
            /** Logical Content Sha256 */
            logical_content_sha256: string | null;
            /**
             * Object Id
             * Format: uuid
             */
            object_id: string;
            /** Row Count */
            row_count: number | null;
            /** Sha256 */
            sha256: string;
            /** Slot */
            slot: string;
            /** Step Id */
            step_id: string;
            /**
             * Version Id
             * Format: uuid
             */
            version_id: string;
        };
        /**
         * Association
         * @description Medida de asociación entre dos columnas, calculada sobre las filas con ambos valores.
         */
        Association: {
            /** Columns */
            columns: [
                string,
                string
            ];
            /**
             * Measure
             * @enum {string}
             */
            measure: "pearson" | "spearman" | "cramers_v" | "eta" | "dependency";
            /** Method */
            method: string;
            /** Rows */
            rows: number;
            /**
             * Strength
             * @enum {string}
             */
            strength: "negligible" | "weak" | "moderate" | "strong";
            /** Value */
            value: string;
        };
        /** AttemptResponse */
        AttemptResponse: {
            /** Environment */
            environment: {
                [key: string]: unknown;
            };
            /** Environment Sha256 */
            environment_sha256: string;
            /** Error Code */
            error_code: string | null;
            /** Error Message */
            error_message: string | null;
            /** Finished At */
            finished_at: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Number */
            number: number;
            /**
             * Started At
             * Format: date-time
             */
            started_at: string;
            /** State */
            state: string;
        };
        /** AuditAlert */
        AuditAlert: {
            /** Detalle */
            detalle: components["schemas"]["Segment"][];
            /**
             * Severidad
             * @enum {string}
             */
            severidad: "alta" | "media" | "baja";
            /** Titulo */
            titulo: components["schemas"]["Segment"][];
        };
        /**
         * AuditContent
         * @description Auditoría ya verificada: cada cifra es un segmento con su evidencia y su ejecución.
         */
        AuditContent: {
            /** Alertas Criticas */
            alertas_criticas: components["schemas"]["AuditAlert"][];
            /** Recomendaciones */
            recomendaciones: components["schemas"]["Segment"][][];
            /** Resumen Ejecutivo */
            resumen_ejecutivo: components["schemas"]["Segment"][];
            /** Unverified Numbers */
            unverified_numbers: number;
        };
        /** AutomaticAnalysis */
        AutomaticAnalysis: {
            /** Evidence */
            evidence: components["schemas"]["AutomaticEvidence"][];
            /** Insights */
            insights: components["schemas"]["AutomaticInsight"][];
            /** Limitations */
            limitations: string[];
            /**
             * Operation
             * @default analytics.automatic@1
             * @constant
             */
            operation: "analytics.automatic@1";
            plan: components["schemas"]["AnalysisPlan"];
            /** Queries */
            queries: {
                [key: string]: components["schemas"]["AnalysisResultV2"];
            };
            /**
             * Rules Version
             * @default automatic-analysis-v1
             * @constant
             */
            rules_version: "automatic-analysis-v1";
            /**
             * Schema Version
             * @default 1
             * @constant
             */
            schema_version: 1;
            scope: components["schemas"]["AutomaticScope"];
        };
        /** AutomaticColumnHint */
        AutomaticColumnHint: {
            /** Evidence */
            evidence: string[];
            /** Name */
            name: string;
            /** Ordinal */
            ordinal: number;
            /**
             * Role
             * @enum {string}
             */
            role: "identifier" | "date" | "numeric" | "category" | "text" | "empty";
            /**
             * Statistics Allowed
             * @default false
             */
            statistics_allowed: boolean;
        };
        /**
         * AutomaticEvidence
         * @description Procedencia de una cifra: método y entradas exactas (otras evidencias o filas).
         */
        AutomaticEvidence: {
            /** Analysis Id */
            analysis_id: string;
            /** Evidence Id */
            evidence_id: string;
            /** Inputs */
            inputs: {
                [key: string]: unknown;
            };
            /** Label */
            label: string;
            /** Method */
            method: string;
            /**
             * Unit
             * @enum {string}
             */
            unit: "number" | "percent" | "count" | "index";
            /** Value */
            value: string | null;
        };
        /**
         * AutomaticInsight
         * @description Hallazgo verificable: texto determinista, cifras con evidencia y su cobertura.
         */
        AutomaticInsight: {
            /** Analysis Id */
            analysis_id: string;
            chart?: components["schemas"]["InsightChart"] | null;
            /** Coverage */
            coverage: string;
            /** Figures */
            figures: components["schemas"]["InsightFigure"][];
            /** Id */
            id: string;
            /** Importance */
            importance: number;
            /** Kind */
            kind: string;
            /** Notes */
            notes?: string[];
            /** Statement */
            statement: string;
            /** Title */
            title: string;
        };
        /**
         * AutomaticInterpretation
         * @description Lectura heurística, no una revisión semántica confirmada.
         */
        AutomaticInterpretation: {
            /** Available Analyses */
            available_analyses: string[];
            /** Candidates */
            candidates: components["schemas"]["AutomaticTemplateHint"][];
            /** Columns */
            columns: components["schemas"]["AutomaticColumnHint"][];
            /**
             * Context
             * @enum {string}
             */
            context: "generic" | "sales" | "inventory" | "ambiguous";
            /** Label */
            label: string;
            /** Limitations */
            limitations: string[];
            /**
             * Rules Version
             * @default automatic-interpretation-v1
             * @constant
             */
            rules_version: "automatic-interpretation-v1";
            /** Summary */
            summary: string;
        };
        /**
         * AutomaticOverview
         * @description Snapshot calculado al importar: no requiere semántica, política ni IA.
         */
        AutomaticOverview: {
            /**
             * Algorithm
             * @default automatic-overview-v1
             * @enum {string}
             */
            algorithm: "automatic-overview-v1" | "automatic-overview-v2" | "automatic-overview-v3";
            analysis?: components["schemas"]["AnalyticalInterpretation"] | null;
            /** Charts */
            charts: components["schemas"]["OverviewChart"][];
            interpretation?: components["schemas"]["AutomaticInterpretation"] | null;
            /** Kpis */
            kpis: components["schemas"]["OverviewKpi"][];
            /** Limitations */
            limitations: string[];
            /** Source Sha256 */
            source_sha256: string;
            table_detail: components["schemas"]["OverviewDetail"];
        };
        /**
         * AutomaticScope
         * @description La tabla de entrada la produce la propia carga: se identifica por su hash.
         */
        AutomaticScope: {
            /**
             * Execution Id
             * Format: uuid
             */
            execution_id: string;
            /** Step Id */
            step_id: string;
            /** Table Sha256 */
            table_sha256: string;
            /**
             * Version Id
             * Format: uuid
             */
            version_id: string;
        };
        /** AutomaticTemplateHint */
        AutomaticTemplateHint: {
            /** Label */
            label: string;
            /** Matched Roles */
            matched_roles: string[];
            /** Missing Roles */
            missing_roles: string[];
            /**
             * Template
             * @enum {string}
             */
            template: "sales@1" | "inventory@1";
        };
        /**
         * BaseCounts
         * @description Filas de la tabla y su destino en la base de una comparación (una métrica, un tipo).
         *
         *     `excluded_by_filters`: filtros de la consulta que no son de periodo y filtros de la
         *     métrica. `outside_base_periods`: filas sin fecha o fuera de los periodos base necesarios
         *     (el periodo consultado no se aplica a la base). Suma: `input_rows`.
         */
        BaseCounts: {
            /** Excluded By Filters */
            excluded_by_filters: number;
            /** Excluded By Nulls */
            excluded_by_nulls: number;
            /** Included Rows */
            included_rows: number;
            /** Input Rows */
            input_rows: number;
            /** Outside Base Periods */
            outside_base_periods: number;
        };
        /** BaseTable */
        BaseTable: {
            /**
             * Artifact Id
             * Format: uuid
             */
            artifact_id: string;
            /** Artifact Sha256 */
            artifact_sha256: string;
            /**
             * Version Id
             * Format: uuid
             */
            version_id: string;
        };
        /** Bin */
        Bin: {
            /** Count */
            count: number;
            /** Label */
            label: string;
            /** Lower */
            lower?: string | null;
            /** Upper */
            upper?: string | null;
        };
        /** CategoricalStats */
        CategoricalStats: {
            /** Distinct */
            distinct: number;
            /** Others */
            others: number;
            /** Top */
            top: components["schemas"]["Frequency"][];
        };
        /** CategoryFilter */
        CategoryFilter: {
            /** Column */
            column: string;
            /** Values */
            values: string[];
        };
        /** ColumnChange */
        ColumnChange: {
            /** After */
            after?: string | null;
            /** Before */
            before?: string | null;
            /**
             * Change
             * @enum {string}
             */
            change: "added" | "removed" | "type_changed" | "role_changed";
            /** Column */
            column: string;
            /**
             * Description
             * @default
             */
            description: string;
        };
        /**
         * ColumnDependency
         * @description Cada valor de `determinant` debería tener un único `dependent` (p. ej. código → nombre).
         */
        ColumnDependency: {
            /** Conflicting Rows */
            conflicting_rows: number;
            /** Conflicting Values */
            conflicting_values: number;
            /** Dependent */
            dependent: string;
            /** Determinant */
            determinant: string;
            /** Determinant Values */
            determinant_values: number;
            /** Examples */
            examples: string[];
            /**
             * Sample Row Numbers
             * @default []
             */
            sample_row_numbers: number[];
        };
        /** ColumnInspection */
        ColumnInspection: {
            categorical?: components["schemas"]["CategoricalStats"] | null;
            /** Count */
            count: number;
            /**
             * Dichotomous
             * @default false
             */
            dichotomous: boolean;
            /** Distinct */
            distinct: number;
            /** Distinct Percent */
            distinct_percent: string;
            domain?: components["schemas"]["ValueDomain"] | null;
            /** Examples */
            examples: string[];
            /**
             * Group
             * @enum {string}
             */
            group: "numeric" | "categorical" | "temporal" | "identifier" | "other";
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Leading Zeros
             * @default 0
             */
            leading_zeros: number;
            missing: components["schemas"]["Missing"];
            mixed?: components["schemas"]["MixedTypes"] | null;
            /** Name */
            name: string;
            /**
             * Nature
             * @enum {string}
             */
            nature: "nominal" | "ordinal" | "discrete" | "continuous" | "temporal" | "unknown";
            /** Nature Reason */
            nature_reason: string;
            /** Null Percent */
            null_percent: string;
            /** Nulls */
            nulls: number;
            numeric?: components["schemas"]["NumericStats"] | null;
            /** Ordinal */
            ordinal: number;
            ordinal_candidate?: components["schemas"]["OrdinalHint"] | null;
            personal?: components["schemas"]["PersonalHint"] | null;
            /** Reading */
            reading?: string | null;
            /**
             * Role
             * @enum {string}
             */
            role: "identifier" | "dimension" | "measure" | "time" | "category" | "text" | "unknown";
            /** Role Evidence */
            role_evidence: string[];
            /**
             * Technical Type
             * @enum {string}
             */
            technical_type: "string" | "integer" | "decimal" | "boolean" | "date" | "datetime" | "empty";
            temporal?: components["schemas"]["TemporalStats"] | null;
        };
        /**
         * ColumnMeaning
         * @description Hipótesis de la IA sobre una columna (no se usa para calcular). Fase 24: con su confianza
         *     (una columna con nombre de código nunca pasa de «baja») o escrita por el usuario. Fase 24B:
         *     con la justificación de la IA (`reason`, prompt v3) y `unknown` si el usuario la marcó como
         *     desconocida.
         */
        ColumnMeaning: {
            /** Column */
            column: string;
            /** Confidence */
            confidence?: ("high" | "medium" | "low") | null;
            /**
             * Confirmed
             * @default false
             */
            confirmed: boolean;
            /** Entity */
            entity?: string | null;
            /** Meaning */
            meaning: string;
            /** Reason */
            reason?: string | null;
            /**
             * Source
             * @default ai
             * @enum {string}
             */
            source: "ai" | "user";
            /**
             * Unknown
             * @default false
             */
            unknown: boolean;
        };
        /** ColumnProfile */
        ColumnProfile: {
            /** Examples */
            examples: string[];
            /** Name */
            name: string;
            /** Null Count */
            null_count: number;
            numeric?: components["schemas"]["NumericSummary"] | null;
            /**
             * Suggested Type
             * @enum {string}
             */
            suggested_type: "string" | "integer" | "decimal" | "date" | "boolean";
            /**
             * Technical Type
             * @default string
             * @enum {string}
             */
            technical_type: "string" | "integer" | "decimal" | "date" | "boolean";
            /** Unique Count */
            unique_count: number;
        };
        /**
         * ColumnScale
         * @description Escala de medida de una columna por reglas (`measurement-scale-v1`).
         */
        ColumnScale: {
            /** Column */
            column: string;
            /** Order */
            order?: string[];
            /** Order Source */
            order_source?: ("rules" | "ai" | "user") | null;
            /** Reason */
            reason: string;
            /**
             * Scale
             * @enum {string}
             */
            scale: "nominal" | "ordinal" | "interval" | "ratio" | "identifier" | "text" | "empty";
        };
        /**
         * ComparisonCell
         * @description Comparación de una cifra con su periodo base. Nunca se usa 0 en lugar de un nulo.
         *
         *     `base_status`: `no_base_data` (el periodo base no tiene filas para la métrica),
         *     `no_counterpart` (29 de febrero, semana 53 o fuera del calendario), `missing_period` (la
         *     fila es el grupo sin fecha). `change_status`: `base_zero` deja `change` y anula
         *     `change_pct`; `base_missing` y `current_missing` anulan ambos.
         */
        ComparisonCell: {
            /** Base */
            base: string | null;
            /** Base Label */
            base_label: string | null;
            /** Base Period */
            base_period: {
                [key: string]: string;
            } | null;
            /**
             * Base Status
             * @enum {string}
             */
            base_status: "available" | "no_base_data" | "no_counterpart" | "missing_period";
            /** Change */
            change: string | null;
            /** Change Pct */
            change_pct: string | null;
            /**
             * Change Status
             * @enum {string}
             */
            change_status: "available" | "base_zero" | "base_missing" | "current_missing";
            /** Evidence */
            evidence: {
                [key: string]: string;
            };
        };
        /**
         * Comprehension
         * @description Resultado del trabajo `comprehension` (operación `comprehension.understand@1`).
         */
        Comprehension: {
            /** Ai Reason */
            ai_reason?: string | null;
            /**
             * Ai State
             * @enum {string}
             */
            ai_state: "ready" | "unavailable" | "failed";
            /** Associations */
            associations: components["schemas"]["Association"][];
            /** Calls */
            calls?: {
                [key: string]: unknown;
            }[];
            /** Corrected Columns */
            corrected_columns?: string[];
            /** Dimensions */
            dimensions?: components["schemas"]["DimensionInfo"][];
            /** Discarded */
            discarded?: string[];
            /** Domain */
            domain?: string | null;
            /** Entities */
            entities?: components["schemas"]["Entity"][];
            /** Formulas */
            formulas?: components["schemas"]["Formula"][];
            grain?: components["schemas"]["Grain"] | null;
            /** Limitations */
            limitations: string[];
            /** Matrix Columns */
            matrix_columns: string[];
            /** Meanings */
            meanings?: components["schemas"]["ColumnMeaning"][];
            /** Measures */
            measures?: components["schemas"]["MeasureInfo"][];
            period?: components["schemas"]["Period"] | null;
            /** Personal Columns */
            personal_columns?: string[];
            /** Questions */
            questions?: string[];
            /** Relationships */
            relationships: components["schemas"]["Relationship"][];
            /**
             * Rules Version
             * @default business-comprehension-v3
             * @enum {string}
             */
            rules_version: "business-comprehension-v1" | "business-comprehension-v2" | "business-comprehension-v3";
            /** Scales */
            scales: components["schemas"]["ColumnScale"][];
            scope: components["schemas"]["ComprehensionScope"];
        };
        /** ComprehensionScope */
        ComprehensionScope: {
            /**
             * Execution Id
             * Format: uuid
             */
            execution_id: string;
            /** Profile Sha256 */
            profile_sha256: string;
            /** Table Sha256 */
            table_sha256: string;
            /**
             * Version Id
             * Format: uuid
             */
            version_id: string;
        };
        /** ComprehensionView */
        ComprehensionView: {
            comprehension?: components["schemas"]["Comprehension"] | null;
            /**
             * Execution Id
             * Format: uuid
             */
            execution_id: string;
            /** Feedback */
            feedback?: components["schemas"]["FeedbackItem"][];
            /** Reason */
            reason?: string | null;
            /**
             * Recalculating
             * @default false
             */
            recalculating: boolean;
            /**
             * State
             * @enum {string}
             */
            state: "queued" | "running" | "ready" | "failed";
        };
        /** Consumption */
        Consumption: {
            /** Ai Calls */
            ai_calls: number;
            /** Cost Usd */
            cost_usd: string;
            /** Elapsed Ms */
            elapsed_ms: number;
        };
        /**
         * ConvertedColumn
         * @description Columna leída con un formato regional (Fase 18, `regional-values-v1`).
         */
        ConvertedColumn: {
            /** By File Convention */
            by_file_convention: boolean;
            /** Column */
            column: string;
            /** Explanation */
            explanation: string;
            /**
             * Format
             * @enum {string}
             */
            format: "decimal_comma" | "decimal_point_grouped" | "day_month_year" | "month_day_year" | "year_month_day";
            /**
             * Kind
             * @enum {string}
             */
            kind: "number" | "date";
            /** Values */
            values: number;
        };
        /** CreateProjectRequest */
        CreateProjectRequest: {
            /**
             * Description
             * @default
             */
            description: string;
            /** File Name */
            file_name?: string | null;
            /** Name */
            name: string;
        };
        /**
         * Criterion
         * @description Un criterio de la evaluación (`relevance-v1`); las cifras salen del motor.
         */
        Criterion: {
            /** Assessment */
            assessment: string;
            /**
             * Name
             * @enum {string}
             */
            name: "magnitude" | "business" | "quality" | "consistency" | "evidence" | "limitations";
        };
        /** CustomSection */
        CustomSection: {
            /** Title */
            title: string;
            /** Widgets */
            widgets: components["schemas"]["CustomWidget"][];
        };
        /** CustomWidget */
        CustomWidget: {
            /** Evidence Id */
            evidence_id?: string | null;
            /** Item */
            item: string;
            /** Title */
            title?: string | null;
            /** Type */
            type: string;
        };
        /** Dashboard */
        Dashboard: {
            /** Ai Reason */
            ai_reason?: string | null;
            /**
             * Ai State
             * @enum {string}
             */
            ai_state: "ready" | "failed" | "unavailable";
            /** Calls */
            calls?: {
                [key: string]: unknown;
            }[];
            /** Computed */
            computed?: components["schemas"]["ExploreResult"][];
            /** Decisions */
            decisions?: components["schemas"]["DesignDecision"][];
            /**
             * Designed By
             * @enum {string}
             */
            designed_by: "ai" | "rules";
            filters?: components["schemas"]["FilterOptions"] | null;
            /** Indicators */
            indicators?: components["schemas"]["Indicator"][];
            /** Items */
            items?: components["schemas"]["DashboardItem"][];
            /** Notice */
            notice?: string | null;
            /**
             * Operation
             * @default delivery.dashboard@1
             * @enum {string}
             */
            operation: "delivery.dashboard@1" | "delivery.dashboard@2";
            /** Partial */
            partial?: string | null;
            /**
             * Rules Version
             * @default dashboard-design-v1
             * @enum {string}
             */
            rules_version: "dashboard-design-v1" | "dashboard-design-v2";
            /**
             * Schema Version
             * @default 1
             * @constant
             */
            schema_version: 1;
            scope: components["schemas"]["DashboardScope"];
            /** Sections */
            sections: components["schemas"]["DashboardSection"][];
            /** Title */
            title: string;
            /** Total Rows */
            total_rows?: number | null;
        };
        /** DashboardCustomization */
        DashboardCustomization: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Dashboard Execution Id
             * Format: uuid
             */
            dashboard_execution_id: string;
            /** Revision */
            revision: number;
            /** Sections */
            sections: components["schemas"]["CustomSection"][];
        };
        /**
         * DashboardCustomizationRequest
         * @description Guarda la versión personalizada: secciones en su orden, sólo los gráficos visibles (los
         *     ocultos no van), los indicadores destacados y los títulos. `expected_revision` es la
         *     revisión que se editó (0 si no había ninguna).
         */
        DashboardCustomizationRequest: {
            /** Expected Revision */
            expected_revision: number;
            /** Sections */
            sections: components["schemas"]["CustomSection"][];
        };
        /**
         * DashboardFilterRequest
         * @description Filtros del dashboard (Fase 26): un rango de meses («AAAA-MM», ambos incluidos) y valores
         *     de hasta tres dimensiones.
         */
        DashboardFilterRequest: {
            /** Categories */
            categories?: components["schemas"]["CategoryFilter"][];
            /** Period From */
            period_from?: string | null;
            /** Period To */
            period_to?: string | null;
        };
        /**
         * DashboardFilterResult
         * @description Los elementos recalculados con los filtros sobre todas las filas que los cumplen. No se
         *     guarda: las evidencias se derivan de los filtros y se pueden reproducir.
         */
        DashboardFilterResult: {
            /** Filters */
            filters: string[];
            /** Indicators */
            indicators: components["schemas"]["Indicator"][];
            /** Items */
            items: components["schemas"]["FilteredItem"][];
            /** Rows */
            rows: number;
            /** Total Rows */
            total_rows: number;
        };
        /**
         * DashboardItem
         * @description Elemento publicado que el dashboard puede mostrar (sin cifras: sólo su forma).
         *     Fase 26: también indicadores, distribuciones y relaciones que calcula el dashboard.
         */
        DashboardItem: {
            /** Classification */
            classification?: string | null;
            /** Figures */
            figures: string[];
            /**
             * Filterable
             * @default false
             */
            filterable: boolean;
            /** Groups */
            groups?: number | null;
            /** Id */
            id: string;
            /** Kind */
            kind: string;
            /**
             * Origin
             * @enum {string}
             */
            origin: "insight" | "exploration" | "computed";
            /** Title */
            title: string;
            trace?: components["schemas"]["Trace"] | null;
            /** Widgets */
            widgets: ("kpi" | "bar" | "line" | "heatmap" | "pie" | "table" | "histogram" | "scatter")[];
        };
        /** DashboardScope */
        DashboardScope: {
            /** Analysis Sha256 */
            analysis_sha256: string;
            /**
             * Execution Id
             * Format: uuid
             */
            execution_id: string;
            /** Exploration Sha256 */
            exploration_sha256: string;
            /**
             * Version Id
             * Format: uuid
             */
            version_id: string;
        };
        /** DashboardSection */
        DashboardSection: {
            /** Intro */
            intro?: string | null;
            /** Title */
            title: string;
            /** Widgets */
            widgets: components["schemas"]["DashboardWidget"][];
        };
        /**
         * DashboardView
         * @description Estado del dashboard de una versión, con las marcas aplicadas y los datos publicados que
         *     cita (hallazgos y resultados de la exploración); nunca recalcula.
         */
        DashboardView: {
            arrangement?: components["schemas"]["Arrangement"] | null;
            custom?: components["schemas"]["DashboardCustomization"] | null;
            /**
             * Custom Dropped
             * @default 0
             */
            custom_dropped: number;
            dashboard?: components["schemas"]["Dashboard"] | null;
            /** Execution Id */
            execution_id?: string | null;
            /** Feedback */
            feedback?: components["schemas"]["FindingFeedback"][];
            /** Insights */
            insights?: components["schemas"]["AutomaticInsight"][];
            /** Reason */
            reason?: string | null;
            /** Results */
            results?: components["schemas"]["ExploreResult"][];
            /**
             * State
             * @enum {string}
             */
            state: "queued" | "running" | "ready" | "failed";
        };
        /** DashboardWidget */
        DashboardWidget: {
            /** Evidence Id */
            evidence_id?: string | null;
            /** Item */
            item: string;
            /** Title */
            title: string;
            /**
             * Type
             * @enum {string}
             */
            type: "kpi" | "bar" | "line" | "heatmap" | "pie" | "table" | "histogram" | "scatter";
        };
        /** DatasetProfile */
        DatasetProfile: {
            /** Column Count */
            column_count: number;
            /** Columns */
            columns: components["schemas"]["ColumnProfile"][];
            /**
             * Encoding
             * @default utf-8-sig
             * @constant
             */
            encoding: "utf-8-sig";
            /** Engine Version */
            engine_version: string;
            overview?: components["schemas"]["AutomaticOverview"] | null;
            /** Polars Version */
            polars_version: string;
            /** Row Count */
            row_count: number;
            /**
             * Schema Version
             * @default 1
             * @constant
             */
            schema_version: 1;
            /** Separator */
            separator: string;
            /** Source Sha256 */
            source_sha256: string;
        };
        /**
         * DesignDecision
         * @description Qué pasó con cada elemento que propuso la IA (aceptado o rechazado con motivo).
         */
        DesignDecision: {
            /** Item */
            item: string;
            /** Reason */
            reason?: string | null;
            /**
             * Status
             * @enum {string}
             */
            status: "accepted" | "rejected";
            /** Type */
            type: string;
        };
        /** Diagnostic */
        Diagnostic: {
            profile: components["schemas"]["DatasetProfile"];
            quality: components["schemas"]["QualityReport"];
        };
        /** DictionaryEntry */
        DictionaryEntry: {
            /**
             * Automatic Nature
             * @enum {string}
             */
            automatic_nature: "nominal" | "ordinal" | "discrete" | "continuous" | "temporal" | "unknown";
            /**
             * Automatic Role
             * @enum {string}
             */
            automatic_role: "identifier" | "dimension" | "measure" | "time" | "category" | "text" | "unknown";
            /**
             * Column Id
             * Format: uuid
             */
            column_id: string;
            /** Description */
            description: string;
            /**
             * Dichotomous
             * @default false
             */
            dichotomous: boolean;
            /** Distinct */
            distinct: number;
            /**
             * Group
             * @enum {string}
             */
            group: "numeric" | "categorical" | "temporal" | "identifier" | "other";
            /**
             * Inherited
             * @default false
             */
            inherited: boolean;
            /** Name */
            name: string;
            /**
             * Nature
             * @enum {string}
             */
            nature: "nominal" | "ordinal" | "discrete" | "continuous" | "temporal" | "unknown";
            /** Notes */
            notes?: string | null;
            /** Null Tokens */
            null_tokens?: string[];
            /** Nulls */
            nulls: number;
            ordinal_candidate?: components["schemas"]["OrdinalHint"] | null;
            /** Origin */
            origin: string;
            /**
             * Personal
             * @default false
             */
            personal: boolean;
            /** Personal Kind */
            personal_kind?: ("name" | "document" | "email" | "phone" | "address") | null;
            /** Personal Status */
            personal_status?: ("automatic" | "confirmed" | "rejected" | "marked") | null;
            /**
             * Role
             * @enum {string}
             */
            role: "identifier" | "dimension" | "measure" | "time" | "category" | "text" | "unknown";
            /**
             * Status
             * @enum {string}
             */
            status: "automatic" | "corrected" | "confirmed";
            /**
             * Technical Type
             * @enum {string}
             */
            technical_type: "string" | "integer" | "decimal" | "boolean" | "date" | "datetime" | "empty";
            /** Time Format */
            time_format?: ("day_month_year" | "month_day_year" | "year_month_day" | "year" | "month" | "year_month") | null;
            /** Updated At */
            updated_at?: string | null;
        };
        /** DimensionFilter */
        DimensionFilter: {
            /** Column */
            column: string;
            /**
             * More
             * @default 0
             */
            more: number;
            /** Values */
            values: string[];
        };
        /** DimensionInfo */
        DimensionInfo: {
            /** Column */
            column: string;
            /** Distinct */
            distinct: number;
            /** Groupable */
            groupable: boolean;
            /** Reason */
            reason: string;
        };
        /** Entity */
        Entity: {
            /** Columns */
            columns: string[];
            /** Name */
            name: string;
        };
        /** ErrorDetail */
        ErrorDetail: {
            /** Field */
            field: string;
            /** Message */
            message: string;
        };
        /** ErrorResponse */
        ErrorResponse: {
            /** Code */
            code: string;
            /** Correlation Id */
            correlation_id: string;
            /** Details */
            details?: components["schemas"]["ErrorDetail"][] | null;
            /** Message */
            message: string;
        };
        /**
         * EvidenceReference
         * @description Dirección estable de una cifra: el mismo cálculo produce el mismo `evidence_id`.
         *
         *     `value` conserva la dirección de @1 (sin `detail`). Las cifras derivadas de @2 añaden
         *     `cell` y su `detail`: comparación y periodo base, escala de la variación o de la
         *     participación, o dirección, top N e indicador de empate de la posición.
         */
        EvidenceReference: {
            /**
             * Cell
             * @default value
             * @enum {string}
             */
            cell: "value" | "previous_period" | "same_period_last_year" | "change" | "change_pct" | "share_of_total" | "rank";
            /** Detail */
            detail?: {
                [key: string]: unknown;
            } | null;
            /** Evidence Id */
            evidence_id: string;
            /**
             * Execution Id
             * Format: uuid
             */
            execution_id: string;
            input: components["schemas"]["BaseTable"];
            metric: components["schemas"]["MetricReference"];
            /** Metric Filters */
            metric_filters: components["schemas"]["Filter"][];
            /** Query Filters */
            query_filters: components["schemas"]["Filter"][];
            /** Row Key */
            row_key: {
                [key: string]: unknown;
            };
            /** Semantic Ref */
            semantic_ref: {
                [key: string]: unknown;
            } | null;
            /** Slot */
            slot: string;
            /** Step Id */
            step_id: string;
            /** Time Grain */
            time_grain: ("day" | "week" | "month" | "quarter" | "year") | null;
            time_range: components["schemas"]["TimeRange"] | null;
        };
        /**
         * EvidenceScope
         * @description Partes comunes de toda referencia de evidencia de un resultado.
         */
        EvidenceScope: {
            /**
             * Execution Id
             * Format: uuid
             */
            execution_id: string;
            input: components["schemas"]["BaseTable"];
            /** Query Filters */
            query_filters: components["schemas"]["Filter"][];
            /** Semantic Ref */
            semantic_ref: {
                [key: string]: unknown;
            } | null;
            /**
             * Slot
             * @default analysis_result
             * @constant
             */
            slot: "analysis_result";
            /** Step Id */
            step_id: string;
            /** Time Grain */
            time_grain: ("day" | "week" | "month" | "quarter" | "year") | null;
            time_range: components["schemas"]["TimeRange"] | null;
        };
        /**
         * EvidenceView
         * @description Una cifra con su dirección completa y su contexto. `value` es la cifra de la celda
         *     direccionada (la posición, en `rank`); `metric_value`, la cifra del grupo en su métrica.
         */
        EvidenceView: {
            comparison?: components["schemas"]["ComparisonCell"] | null;
            /** Definition */
            definition: components["schemas"]["MetricDefinitionV3"] | components["schemas"]["MetricDefinitionV2"] | components["schemas"]["MetricDefinition"];
            /** Labels */
            labels: {
                [key: string]: string | null;
            };
            /** Metric Value */
            metric_value?: string | null;
            /**
             * Operation
             * @default analytics.query@1
             * @enum {string}
             */
            operation: "analytics.query@1" | "analytics.query@2" | "analytics.query@3";
            rank?: components["schemas"]["RankCell"] | null;
            ranking?: components["schemas"]["RankingSummary"] | null;
            reference: components["schemas"]["EvidenceReference"];
            share?: components["schemas"]["ShareCell"] | null;
            share_total?: components["schemas"]["ShareTotal"] | null;
            /** Snapshot */
            snapshot?: string | null;
            /** Value */
            value: string | null;
        };
        /** ExcludedColumn */
        ExcludedColumn: {
            /** Column */
            column: string;
            /** Reason */
            reason: string;
            /** Type */
            type: string;
        };
        /** ExecutionDetail */
        ExecutionDetail: {
            /** Attempt History */
            attempt_history: components["schemas"]["AttemptResponse"][];
            /** Attempts */
            attempts: number;
            /** Column Count */
            column_count: number | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Error Code */
            error_code: string | null;
            /** Error Message */
            error_message: string | null;
            /** Finished At */
            finished_at: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Input Artifact Id */
            input_artifact_id: string | null;
            /** Input Artifact Sha256 */
            input_artifact_sha256: string | null;
            /**
             * Kind
             * @enum {string}
             */
            kind: "csv_import" | "table_analysis" | "plan" | "cleaning_preview" | "cleaning_apply" | "report_render" | "overview_audit" | "investigation" | "automatic_report" | "comprehension" | "exploration" | "dashboard" | "inspection" | "null_cleaning";
            plan: components["schemas"]["PlanResponse"] | null;
            /**
             * Project Id
             * Format: uuid
             */
            project_id: string;
            /**
             * Reproducibility
             * @enum {string}
             */
            reproducibility: "complete" | "legacy_partial";
            /** Row Count */
            row_count: number | null;
            /**
             * State
             * @enum {string}
             */
            state: "queued" | "running" | "succeeded" | "failed" | "cancelled";
            /**
             * Version Id
             * Format: uuid
             */
            version_id: string;
        };
        /** ExecutionResponse */
        ExecutionResponse: {
            /** Attempts */
            attempts: number;
            /** Column Count */
            column_count: number | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Error Code */
            error_code: string | null;
            /** Error Message */
            error_message: string | null;
            /** Finished At */
            finished_at: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Input Artifact Id */
            input_artifact_id: string | null;
            /** Input Artifact Sha256 */
            input_artifact_sha256: string | null;
            /**
             * Kind
             * @enum {string}
             */
            kind: "csv_import" | "table_analysis" | "plan" | "cleaning_preview" | "cleaning_apply" | "report_render" | "overview_audit" | "investigation" | "automatic_report" | "comprehension" | "exploration" | "dashboard" | "inspection" | "null_cleaning";
            plan: components["schemas"]["PlanResponse"] | null;
            /**
             * Project Id
             * Format: uuid
             */
            project_id: string;
            /**
             * Reproducibility
             * @enum {string}
             */
            reproducibility: "complete" | "legacy_partial";
            /** Row Count */
            row_count: number | null;
            /**
             * State
             * @enum {string}
             */
            state: "queued" | "running" | "succeeded" | "failed" | "cancelled";
            /**
             * Version Id
             * Format: uuid
             */
            version_id: string;
        };
        /** Exploration */
        Exploration: {
            /** Ai Reason */
            ai_reason?: string | null;
            /**
             * Ai State
             * @enum {string}
             */
            ai_state: "ready" | "unavailable" | "failed";
            /** Calls */
            calls?: {
                [key: string]: unknown;
            }[];
            consumption?: components["schemas"]["InvestigationConsumption"] | null;
            /** Excluded */
            excluded?: string[];
            /** Limitations */
            limitations: string[];
            limits: components["schemas"]["ExplorationLimits"];
            /** Nodes */
            nodes?: components["schemas"]["InvestigationNode"][];
            /**
             * Operation
             * @default exploration.explore@1
             * @enum {string}
             */
            operation: "exploration.explore@1" | "exploration.explore@2";
            /** Proposals */
            proposals: components["schemas"]["ExploreProposal"][];
            /** Results */
            results: components["schemas"]["ExploreResult"][];
            /** Resumed From */
            resumed_from?: string | null;
            /**
             * Rules Version
             * @default explore-v1
             * @enum {string}
             */
            rules_version: "explore-v1" | "investigation-v2";
            scope: components["schemas"]["ExplorationScope"];
            /** Stopped */
            stopped?: ("completed" | "max_nodes" | "max_seconds" | "paused" | "cancelled") | null;
            /** Trigger */
            trigger?: ("load" | "feedback" | "restart" | "resume") | null;
        };
        /** ExplorationLimits */
        ExplorationLimits: {
            /**
             * Ai Rows
             * @default 100
             */
            ai_rows: number;
            /**
             * Max Ai Calls
             * @default 2
             */
            max_ai_calls: number;
            /**
             * Max Ai Proposals
             * @default 12
             */
            max_ai_proposals: number;
            /**
             * Max Children
             * @default 3
             */
            max_children: number;
            /**
             * Max Cost Usd
             * @default 0.05
             */
            max_cost_usd: string;
            /**
             * Max Depth
             * @default 2
             */
            max_depth: number;
            /**
             * Max Nodes
             * @default 20
             */
            max_nodes: number;
            /**
             * Max Queries
             * @default 20
             */
            max_queries: number;
            /**
             * Max Seconds
             * @default 60
             */
            max_seconds: number;
        };
        /** ExplorationScope */
        ExplorationScope: {
            /** Comprehension Sha256 */
            comprehension_sha256: string;
            /**
             * Execution Id
             * Format: uuid
             */
            execution_id: string;
            /** Table Sha256 */
            table_sha256: string;
            /**
             * Version Id
             * Format: uuid
             */
            version_id: string;
        };
        /** ExplorationView */
        ExplorationView: {
            /** Control */
            control?: ("pause" | "cancel") | null;
            /** Execution Id */
            execution_id?: string | null;
            exploration?: components["schemas"]["Exploration"] | null;
            /** Reason */
            reason?: string | null;
            /**
             * Resumable
             * @default false
             */
            resumable: boolean;
            /**
             * State
             * @enum {string}
             */
            state: "queued" | "running" | "ready" | "failed";
        };
        /** ExploreFigure */
        ExploreFigure: {
            /** Evidence Id */
            evidence_id: string;
            /** Label */
            label: string;
            /** Value */
            value: string | null;
        };
        /** ExploreProposal */
        ExploreProposal: {
            /** Key */
            key?: string | null;
            /** Motive */
            motive: string;
            /**
             * Origin
             * @enum {string}
             */
            origin: "rule" | "ai";
            /** Query */
            query: {
                [key: string]: unknown;
            };
            /** Reason */
            reason?: string | null;
            /**
             * Status
             * @enum {string}
             */
            status: "accepted" | "rejected";
        };
        /**
         * ExploreQuery
         * @description Una consulta del lenguaje cerrado. Columnas por nombre exacto de la tabla publicada.
         */
        ExploreQuery: {
            /** Aggregation */
            aggregation?: ("sum" | "mean" | "median" | "count") | null;
            /** Dimensions */
            dimensions?: string[];
            /** Filter Column */
            filter_column?: string | null;
            /** Filter Value */
            filter_value?: string | null;
            /**
             * Kind
             * @enum {string}
             */
            kind: "aggregate" | "crosstab" | "ratio" | "top" | "correlation_by_group" | "evolution" | "period_change" | "outliers" | "distribution" | "scatter";
            /** Limit */
            limit?: number | null;
            /** Measure */
            measure?: string | null;
            /** Measure B */
            measure_b?: string | null;
        };
        /** ExploreResult */
        ExploreResult: {
            /** Columns */
            columns: string[];
            /** Covered Rows */
            covered_rows: number;
            /** Judged By */
            judged_by?: ("ai" | "rules") | null;
            /** Key */
            key: string;
            /** Method */
            method: string;
            query: components["schemas"]["ExploreQuery"];
            /** Reason */
            reason?: string | null;
            /** Relevant */
            relevant?: boolean | null;
            /** Rows */
            rows: components["schemas"]["ExploreRow"][];
            /** Title */
            title: string;
            /** Total Groups */
            total_groups: number;
            /** Truncated */
            truncated: boolean;
        };
        /** ExploreRow */
        ExploreRow: {
            /** Figures */
            figures: components["schemas"]["ExploreFigure"][];
            /** Groups */
            groups: string[];
            /** Rows */
            rows: number;
        };
        /** FeedbackItem */
        FeedbackItem: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Relationship Key */
            relationship_key: string;
            /**
             * Verdict
             * @enum {string}
             */
            verdict: "relevant" | "not_relevant";
        };
        /** FeedbackRequest */
        FeedbackRequest: {
            /** Relationship Key */
            relationship_key: string;
            /**
             * Verdict
             * @enum {string}
             */
            verdict: "relevant" | "not_relevant";
        };
        /** FileInspection */
        FileInspection: {
            /** Blank Lines */
            blank_lines?: number | null;
            /** Converted */
            converted?: components["schemas"]["ConvertedColumn"][];
            /** Date Cells */
            date_cells?: number | null;
            /** Date Convention */
            date_convention: string | null;
            /** Decimal Convention */
            decimal_convention: string | null;
            /** Empty Columns */
            empty_columns?: string[];
            /** Empty Rows */
            empty_rows?: number | null;
            /** Encoding */
            encoding: string | null;
            /** File Name */
            file_name: string;
            /**
             * Format
             * @enum {string}
             */
            format: "csv" | "xlsx" | "pdf" | "sqlserver" | "other";
            /** Formula Cells */
            formula_cells?: number | null;
            /** Header */
            header: string;
            /** Inexact Numbers */
            inexact_numbers?: number | null;
            /** Kept As Text */
            kept_as_text?: components["schemas"]["KeptColumn"][];
            /** Problems */
            problems?: string[];
            /** Rules */
            rules: string[];
            /** Selection Rule */
            selection_rule?: string | null;
            /** Separator */
            separator: string | null;
            /** Sha256 */
            sha256: string;
            /** Sheet */
            sheet?: string | null;
            /** Sheets */
            sheets?: components["schemas"]["SheetFacts"][];
            /** Size Bytes */
            size_bytes: number | null;
            /** Table */
            table?: string | null;
            /**
             * Uploaded At
             * Format: date-time
             */
            uploaded_at: string;
            /** Used Range */
            used_range?: string | null;
        };
        /**
         * Filter
         * @description Filtro estructurado. Los valores se escriben como cadenas canónicas del tipo de la
         *     columna (decimal con punto, fecha ISO, `true`/`false`); el motor los interpreta.
         */
        Filter: {
            /**
             * Column Id
             * Format: uuid
             */
            column_id: string;
            /**
             * Operator
             * @enum {string}
             */
            operator: "eq" | "neq" | "in" | "not_in" | "gt" | "gte" | "lt" | "lte" | "between" | "is_null" | "is_not_null";
            /** Values */
            values?: string[];
        };
        /** FilterOptions */
        FilterOptions: {
            /** Dimensions */
            dimensions?: components["schemas"]["DimensionFilter"][];
            /** Months */
            months?: string[];
            /** Period Columns */
            period_columns?: string[];
        };
        /** FilteredItem */
        FilteredItem: {
            /** Item */
            item: string;
            /** Reason */
            reason?: string | null;
            result?: components["schemas"]["ExploreResult"] | null;
        };
        /** Finding */
        Finding: {
            /** Affected Rows */
            affected_rows: number;
            /** Columns */
            columns: string[];
            /** Description */
            description: string;
            /**
             * Dimension
             * @enum {string}
             */
            dimension: "completeness" | "uniqueness" | "validity" | "consistency" | "format" | "integrity";
            /** Examples */
            examples: string[];
            /** Id */
            id: string;
            /** Kind */
            kind: string;
            /** Percent */
            percent: string;
            /** Sample Rows */
            sample_rows: number[];
            /**
             * Severity
             * @enum {string}
             */
            severity: "high" | "medium" | "low" | "info";
            /**
             * Source
             * @enum {string}
             */
            source: "dataset-inspection-v1" | "dataset-inspection-v2" | "automatic-quality-v1";
            /** Title */
            title: string;
        };
        /** FindingFeedback */
        FindingFeedback: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Item */
            item: string;
            /**
             * Verdict
             * @enum {string}
             */
            verdict: "keep" | "drop" | "none";
        };
        /** FindingFeedbackRequest */
        FindingFeedbackRequest: {
            /** Item */
            item: string;
            /**
             * Verdict
             * @enum {string}
             */
            verdict: "keep" | "drop" | "none";
        };
        /**
         * FollowUpQuery
         * @description Una consulta de seguimiento del catálogo cerrado `investigation-v1`.
         *
         *     La propone una regla o la IA, pero sólo llega aquí después de validarse en Python contra el
         *     plan y los hallazgos: la medida es la del plan y la dimensión una de sus agrupaciones.
         */
        FollowUpQuery: {
            /** Dimension */
            dimension: string;
            /** Group */
            group?: string | null;
            /**
             * Kind
             * @enum {string}
             */
            kind: "month_by_group" | "change_by_group" | "group_evolution";
            /** Measure */
            measure: string;
            /** Month */
            month?: string | null;
            /** Year */
            year?: number | null;
        };
        /** FollowUpResult */
        FollowUpResult: {
            /** Evidence */
            evidence?: components["schemas"]["AutomaticEvidence"][];
            insight?: components["schemas"]["AutomaticInsight"] | null;
            /** Key */
            key: string;
            query: components["schemas"]["FollowUpQuery"];
            /** Reason */
            reason?: string | null;
            /**
             * Status
             * @enum {string}
             */
            status: "computed" | "empty";
        };
        /**
         * ForeignKey
         * @description Clave foránea declarada en la base (Fase 19): columna → esquema.tabla.columna.
         */
        ForeignKey: {
            /** Column */
            column: string;
            /** References */
            references: string;
        };
        /**
         * Formula
         * @description Columna calculada a partir de otras, comprobada fila a fila sobre todas las filas.
         */
        Formula: {
            /** Category */
            category?: string | null;
            /** Column */
            column: string;
            /** Expression */
            expression: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "weighted_sum" | "product" | "threshold";
            /** Matching Rows */
            matching_rows: number;
            /** Method */
            method: string;
            /** Rows */
            rows: number;
            /** Sources */
            sources: string[];
            /** Threshold */
            threshold?: string | null;
            /** Tolerance */
            tolerance: string;
            /** Weights */
            weights?: string[];
        };
        /** Frequency */
        Frequency: {
            /** Count */
            count: number;
            /** Percent */
            percent: string;
            /** Value */
            value: string;
        };
        /**
         * Grain
         * @description Qué representa una fila (Fase 24), por reglas: la clave única y la entidad que nombra.
         */
        Grain: {
            /** Entity */
            entity: string | null;
            /** Key */
            key: string[];
            /** Reason */
            reason: string;
            /** Sentence */
            sentence: string;
            /** Unique */
            unique: boolean;
        };
        /**
         * Indicator
         * @description Indicador del resumen ejecutivo (Fase 26): nombre, valor, unidad declarada, periodo de
         *     referencia, comparación y procedencia. Nunca inventa monedas ni unidades.
         */
        Indicator: {
            comparison?: components["schemas"]["IndicatorComparison"] | null;
            /** Evidence Id */
            evidence_id: string;
            /** Highlight */
            highlight?: string | null;
            /** Id */
            id: string;
            /** Item */
            item: string;
            /** Name */
            name: string;
            /** Reference */
            reference: string;
            trace: components["schemas"]["Trace"];
            /** Unit */
            unit?: string | null;
            /** Value */
            value: string | null;
        };
        /**
         * IndicatorComparison
         * @description Último mes con datos frente al anterior: sólo cuando hay una base válida (al menos dos
         *     meses con datos); las cifras salen del motor.
         */
        IndicatorComparison: {
            /** Change */
            change: string | null;
            /** Change Percent */
            change_percent: string | null;
            /** Current */
            current: string | null;
            /** Evidence Id */
            evidence_id: string;
            /** Label */
            label: string;
            /** Previous */
            previous: string | null;
        };
        /** IngestionSummary */
        IngestionSummary: {
            /** Datasets */
            datasets: number;
            /** Failed */
            failed: number;
            /** Pending */
            pending: number;
            /** Processed */
            processed: number;
            /** Versions */
            versions: number;
        };
        /** InsightChart */
        InsightChart: {
            /** Points */
            points: components["schemas"]["InsightPoint"][];
            /** Title */
            title: string;
            /**
             * Type
             * @enum {string}
             */
            type: "bar" | "line";
            /**
             * Unit
             * @enum {string}
             */
            unit: "number" | "percent" | "count" | "index";
        };
        /** InsightFigure */
        InsightFigure: {
            /** Evidence Id */
            evidence_id: string;
            /** Label */
            label: string;
            /**
             * Unit
             * @enum {string}
             */
            unit: "number" | "percent" | "count" | "index";
            /** Value */
            value: string | null;
        };
        /** InsightPoint */
        InsightPoint: {
            /** Evidence Id */
            evidence_id: string | null;
            /** Label */
            label: string;
            /** Value */
            value: string | null;
        };
        /** Inspection */
        Inspection: {
            /** Columns */
            columns: components["schemas"]["ColumnInspection"][];
            file: components["schemas"]["FileInspection"];
            /** Findings */
            findings: components["schemas"]["Finding"][];
            /** Limitations */
            limitations: string[];
            /** Periods */
            periods: components["schemas"]["PeriodCandidate"][];
            scope: components["schemas"]["InspectionScope"];
            summary: components["schemas"]["Summary"];
        };
        /** InspectionScope */
        InspectionScope: {
            /**
             * Computed At
             * Format: date-time
             */
            computed_at: string;
            /**
             * Execution Id
             * Format: uuid
             */
            execution_id: string;
            /** Profile Sha256 */
            profile_sha256: string;
            /**
             * Rules
             * @default dataset-inspection-v2
             * @enum {string}
             */
            rules: "dataset-inspection-v1" | "dataset-inspection-v2";
            /** Table Sha256 */
            table_sha256: string;
            /**
             * Version Id
             * Format: uuid
             */
            version_id: string;
        };
        /** InspectionView */
        InspectionView: {
            /** Dictionary */
            dictionary?: components["schemas"]["DictionaryEntry"][];
            /** Execution Id */
            execution_id?: string | null;
            /** Groups */
            groups?: {
                [key: string]: number;
            };
            inspection?: components["schemas"]["Inspection"] | null;
            /** Reason */
            reason?: string | null;
            recalculation?: components["schemas"]["Recalculation"] | null;
            /**
             * State
             * @enum {string}
             */
            state: "queued" | "running" | "ready" | "failed" | "unavailable";
        };
        /** Investigation */
        Investigation: {
            /**
             * Ai
             * @enum {string}
             */
            ai: "available" | "unavailable";
            /** Ai Reason */
            ai_reason?: string | null;
            /** Calls */
            calls: components["schemas"]["ModelCall"][];
            consumption: components["schemas"]["Consumption"];
            explanation?: components["schemas"]["AuditContent"] | null;
            /** Explanation Reason */
            explanation_reason?: string | null;
            /**
             * Explanation State
             * @enum {string}
             */
            explanation_state: "ready" | "unavailable" | "failed";
            /** Iterations */
            iterations: number;
            /** Limitations */
            limitations: string[];
            limits: components["schemas"]["InvestigationLimits"];
            /**
             * Operation
             * @default investigation.investigate@1
             * @constant
             */
            operation: "investigation.investigate@1";
            /** Proposals */
            proposals: components["schemas"]["Proposal"][];
            /** Results */
            results: components["schemas"]["FollowUpResult"][];
            /**
             * Rules Version
             * @default investigation-v1
             * @constant
             */
            rules_version: "investigation-v1";
            /**
             * Schema Version
             * @default 1
             * @constant
             */
            schema_version: 1;
            scope: components["schemas"]["InvestigationScope"];
            /**
             * Stopped
             * @enum {string}
             */
            stopped: "max_iterations" | "no_new_proposals" | "ai_unavailable" | "ai_error" | "max_ai_calls" | "max_cost" | "max_seconds" | "max_queries" | "nothing_to_investigate";
        };
        /**
         * InvestigationCommand
         * @description Control del usuario: pausar o cancelar la investigación en marcha, reanudar la pausada o
         *     volver a investigar la versión (Fase 25).
         */
        InvestigationCommand: {
            /**
             * Action
             * @enum {string}
             */
            action: "pause" | "cancel" | "resume" | "restart";
        };
        /** InvestigationConsumption */
        InvestigationConsumption: {
            /** Ai Calls */
            ai_calls: number;
            /** Cost Usd */
            cost_usd: string;
            /** Elapsed Ms */
            elapsed_ms: number;
            /** Nodes */
            nodes: number;
        };
        /** InvestigationHistory */
        InvestigationHistory: {
            /** Items */
            items: components["schemas"]["InvestigationRun"][];
        };
        /**
         * InvestigationLimits
         * @description Límites duros del ciclo; se guardan con cada investigación.
         */
        InvestigationLimits: {
            /**
             * Max Ai Calls
             * @default 4
             */
            max_ai_calls: number;
            /**
             * Max Cost Usd
             * @default 0.05
             */
            max_cost_usd: string;
            /**
             * Max Iterations
             * @default 3
             */
            max_iterations: number;
            /**
             * Max Proposals Per Call
             * @default 4
             */
            max_proposals_per_call: number;
            /**
             * Max Queries
             * @default 12
             */
            max_queries: number;
            /**
             * Max Seconds
             * @default 60
             */
            max_seconds: number;
        };
        /**
         * InvestigationNode
         * @description Una investigación del plan o del árbol (Fase 25): pregunta, hipótesis, operación del
         *     catálogo, evidencia, clasificación y decisión de profundizar o terminar.
         */
        InvestigationNode: {
            /** Classification */
            classification?: ("relevant" | "secondary" | "descriptive" | "inconclusive" | "discarded") | null;
            /** Columns */
            columns: string[];
            /** Criteria */
            criteria?: components["schemas"]["Criterion"][];
            /** Decision */
            decision?: ("deepen" | "finish") | null;
            /** Decision Reason */
            decision_reason?: string | null;
            /** Depends On */
            depends_on?: string[];
            /**
             * Depth
             * @default 0
             */
            depth: number;
            /** Execution Id */
            execution_id?: string | null;
            /** Expected */
            expected: string;
            /** Filters */
            filters?: string[];
            /** Hypothesis */
            hypothesis: string;
            /** Id */
            id: string;
            /** Interpretation */
            interpretation?: string | null;
            /**
             * Judged
             * @default false
             */
            judged: boolean;
            /** Key */
            key?: string | null;
            /** Limitations */
            limitations?: string[];
            /** Method */
            method: string;
            /** Motive */
            motive: string;
            /**
             * Origin
             * @enum {string}
             */
            origin: "rule" | "ai";
            /** Parent */
            parent?: string | null;
            /**
             * Priority
             * @enum {integer}
             */
            priority: 1 | 2 | 3;
            /** Query */
            query: {
                [key: string]: unknown;
            };
            /** Question */
            question: string;
            /** Reason */
            reason?: string | null;
            /** Rows Considered */
            rows_considered?: number | null;
            /**
             * Status
             * @enum {string}
             */
            status: "pending" | "rejected" | "computed" | "failed";
            /** Total Rows */
            total_rows?: number | null;
        };
        /**
         * InvestigationRun
         * @description Una ejecución del historial de investigaciones de la versión (Fase 25).
         */
        InvestigationRun: {
            /** Computed */
            computed?: number | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Error Code */
            error_code?: string | null;
            /**
             * Execution Id
             * Format: uuid
             */
            execution_id: string;
            /** Finished At */
            finished_at?: string | null;
            /** Nodes */
            nodes?: number | null;
            /** Relevant */
            relevant?: number | null;
            /** Resumed From */
            resumed_from?: string | null;
            /**
             * State
             * @enum {string}
             */
            state: "queued" | "running" | "succeeded" | "failed" | "cancelled";
            /** Stopped */
            stopped?: ("completed" | "max_nodes" | "max_seconds" | "paused" | "cancelled") | null;
            /** Trigger */
            trigger?: ("load" | "feedback" | "restart" | "resume") | null;
        };
        /** InvestigationScope */
        InvestigationScope: {
            /**
             * Analysis Artifact Id
             * Format: uuid
             */
            analysis_artifact_id: string;
            /**
             * Analysis Execution Id
             * Format: uuid
             */
            analysis_execution_id: string;
            /** Analysis Sha256 */
            analysis_sha256: string;
            /**
             * Execution Id
             * Format: uuid
             */
            execution_id: string;
            /** Table Sha256 */
            table_sha256: string;
            /**
             * Version Id
             * Format: uuid
             */
            version_id: string;
        };
        /**
         * InvestigationView
         * @description Estado de la investigación de una versión (sólo lectura).
         */
        InvestigationView: {
            /**
             * Execution Id
             * Format: uuid
             */
            execution_id: string;
            investigation?: components["schemas"]["Investigation"] | null;
            /** Reason */
            reason?: string | null;
            /**
             * State
             * @enum {string}
             */
            state: "queued" | "running" | "ready" | "failed";
        };
        /**
         * KeptColumn
         * @description Columna que parecía regional pero se dejó como texto por ambigua.
         */
        KeptColumn: {
            /** Column */
            column: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "number" | "date";
            /** Reason */
            reason: string;
        };
        /** KeyCandidate */
        KeyCandidate: {
            /** Columns */
            columns: string[];
            /** Duplicate Rows */
            duplicate_rows: number;
            /**
             * Duplicate Sample Rows
             * @default []
             */
            duplicate_sample_rows: number[];
            /** Evidence */
            evidence: string;
            /** Unique */
            unique: boolean;
        };
        /** LimitedAnalysis */
        LimitedAnalysis: {
            /** Columns */
            columns: string[];
            /** Reason */
            reason: string;
            /** Subject */
            subject: string;
        };
        /** LineageOperation */
        LineageOperation: {
            /** Operation */
            operation: string;
            /** Parameters */
            parameters: {
                [key: string]: unknown;
            };
            /** Step Id */
            step_id: string;
            /** Version */
            version: number;
        };
        /** LineageView */
        LineageView: {
            /** Effect Sha256 */
            effect_sha256: string | null;
            /**
             * Kind
             * @enum {string}
             */
            kind: "imported" | "derived";
            /** Operations */
            operations: components["schemas"]["LineageOperation"][];
            /** Parent Version Id */
            parent_version_id: string | null;
            /** Plan Revision Id */
            plan_revision_id: string | null;
            /** Producer Execution Id */
            producer_execution_id: string | null;
            /**
             * Version Id
             * Format: uuid
             */
            version_id: string;
        };
        /** LoginRequest */
        LoginRequest: {
            /**
             * Email
             * Format: email
             */
            email: string;
            /** Password */
            password: string;
        };
        /**
         * MeaningRequest
         * @description Fase 24: significado escrito o confirmado por el usuario (metadato de la fuente y la
         *     columna, heredado por las versiones siguientes). Sin texto, sin confirmar y sin marcar =
         *     vuelve al de la IA. Fase 24B: `unknown` marca la columna como desconocida (sin texto). No
         *     cambia ningún cálculo; el informe usa el significado vigente.
         */
        MeaningRequest: {
            /** Column */
            column: string;
            /**
             * Confirmed
             * @default false
             */
            confirmed: boolean;
            /** Meaning */
            meaning?: string | null;
            /**
             * Unknown
             * @default false
             */
            unknown: boolean;
        };
        /** MeasureInfo */
        MeasureInfo: {
            /**
             * Additivity
             * @enum {string}
             */
            additivity: "additive" | "semi_additive" | "non_additive" | "unknown";
            /**
             * Aggregation
             * @enum {string}
             */
            aggregation: "sum" | "mean" | "weighted_mean";
            /** Column */
            column: string;
            /**
             * Derived
             * @default false
             */
            derived: boolean;
            /**
             * Monetary
             * @default false
             */
            monetary: boolean;
            /** Reason */
            reason: string;
            /** Unit */
            unit?: string | null;
        };
        /**
         * MeasureRelationship
         * @description Relación comprobada fila a fila: `target` ≈ producto de `factors` con tolerancia.
         */
        MeasureRelationship: {
            /** Compared Rows */
            compared_rows: number;
            /**
             * Exception Sample Rows
             * @default []
             */
            exception_sample_rows: number[];
            /** Factors */
            factors: string[];
            /**
             * Kind
             * @default product
             * @constant
             */
            kind: "product";
            /** Matching Rows */
            matching_rows: number;
            /** Target */
            target: string;
            /** Tolerance */
            tolerance: string;
        };
        /**
         * MetricCounts
         * @description Filas de la tabla de entrada y su destino para una métrica.
         */
        MetricCounts: {
            /** Excluded By Filters */
            excluded_by_filters: number;
            /** Excluded By Nulls */
            excluded_by_nulls: number;
            /** Included Rows */
            included_rows: number;
            /** Input Rows */
            input_rows: number;
        };
        /**
         * MetricDefinition
         * @description Definición usada en el cálculo (copiada de la revisión exacta).
         */
        MetricDefinition: {
            /**
             * Aggregation
             * @enum {string}
             */
            aggregation: "sum" | "count" | "count_distinct" | "avg" | "min" | "max" | "sum_product";
            /** Content Sha256 */
            content_sha256: string;
            counts: components["schemas"]["MetricCounts"];
            /** Currency */
            currency: string | null;
            /** Filters */
            filters: components["schemas"]["Filter"][];
            /** Key */
            key: string;
            /** Label */
            label: string;
            /** Measure Column */
            measure_column: string;
            /**
             * Measure Column Id
             * Format: uuid
             */
            measure_column_id: string;
            /**
             * Null Policy
             * @constant
             */
            null_policy: "exclude";
            /** Revision */
            revision: number;
            /**
             * Revision Id
             * Format: uuid
             */
            revision_id: string;
            /** Scale */
            scale: number | null;
            /** Time Column Id */
            time_column_id: string | null;
            /** Unit */
            unit: string | null;
        };
        /**
         * MetricDefinitionV2
         * @description `counts` es el periodo consultado, igual que en @1; `base_counts`, la base de cada
         *     comparación.
         */
        MetricDefinitionV2: {
            /**
             * Aggregation
             * @enum {string}
             */
            aggregation: "sum" | "count" | "count_distinct" | "avg" | "min" | "max" | "sum_product";
            /** Base Counts */
            base_counts?: {
                [key: string]: components["schemas"]["BaseCounts"];
            };
            /** Content Sha256 */
            content_sha256: string;
            counts: components["schemas"]["MetricCounts"];
            /** Currency */
            currency: string | null;
            /** Filters */
            filters: components["schemas"]["Filter"][];
            /** Key */
            key: string;
            /** Label */
            label: string;
            /** Measure Column */
            measure_column: string;
            /**
             * Measure Column Id
             * Format: uuid
             */
            measure_column_id: string;
            /**
             * Null Policy
             * @constant
             */
            null_policy: "exclude";
            /** Revision */
            revision: number;
            /**
             * Revision Id
             * Format: uuid
             */
            revision_id: string;
            /** Scale */
            scale: number | null;
            /** Time Column Id */
            time_column_id: string | null;
            /** Unit */
            unit: string | null;
        };
        /** MetricDefinitionV3 */
        MetricDefinitionV3: {
            /**
             * Aggregation
             * @enum {string}
             */
            aggregation: "sum" | "count" | "count_distinct" | "avg" | "min" | "max" | "sum_product";
            /** Base Counts */
            base_counts?: {
                [key: string]: components["schemas"]["BaseCounts"];
            };
            /** Content Sha256 */
            content_sha256: string;
            counts: components["schemas"]["MetricCounts"];
            /** Currency */
            currency: string | null;
            /** Filters */
            filters: components["schemas"]["Filter"][];
            /** Key */
            key: string;
            /** Label */
            label: string;
            /** Measure Column */
            measure_column: string;
            /**
             * Measure Column Id
             * Format: uuid
             */
            measure_column_id: string;
            /**
             * Null Policy
             * @constant
             */
            null_policy: "exclude";
            /** Revision */
            revision: number;
            /**
             * Revision Id
             * Format: uuid
             */
            revision_id: string;
            /** Scale */
            scale: number | null;
            /** Second Measure Column */
            second_measure_column?: string | null;
            /** Second Measure Column Id */
            second_measure_column_id?: string | null;
            /** Semi Additive */
            semi_additive?: "last_snapshot" | null;
            snapshot?: components["schemas"]["SnapshotCounts"] | null;
            /** Time Column Id */
            time_column_id: string | null;
            /** Unit */
            unit: string | null;
        };
        /** MetricReference */
        MetricReference: {
            /** Content Sha256 */
            content_sha256: string;
            /**
             * Revision Id
             * Format: uuid
             */
            revision_id: string;
        };
        /**
         * Missing
         * @description Faltantes por clase: nunca se suman entre sí ni se convierten en nulos.
         */
        Missing: {
            /** Empty Strings */
            empty_strings: number;
            /** Nulls */
            nulls: number;
            /** Tokens */
            tokens: components["schemas"]["TokenCount"][];
            /** Whitespace */
            whitespace: number;
        };
        /** MixedTypes */
        MixedTypes: {
            /** Examples */
            examples: string[];
            /** Numeric */
            numeric: number;
            /** Text */
            text: number;
        };
        /**
         * ModelCall
         * @description Metadatos de una llamada al proveedor (nunca el contenido tabular).
         */
        ModelCall: {
            /** Cache Read Tokens */
            cache_read_tokens: number;
            /** Cache Write Tokens */
            cache_write_tokens: number;
            /** Context Sha256 */
            context_sha256: string;
            /** Cost Usd */
            cost_usd: string | null;
            /** Error Code */
            error_code?: string | null;
            /** Input Tokens */
            input_tokens: number;
            /** Iteration */
            iteration: number;
            /** Latency Ms */
            latency_ms: number;
            /** Model */
            model: string;
            /**
             * Outcome
             * @enum {string}
             */
            outcome: "accepted" | "rejected" | "provider_error";
            /** Output Tokens */
            output_tokens: number;
            /** Parameters */
            parameters: {
                [key: string]: unknown;
            };
            /** Prompt Id */
            prompt_id: string;
            /** Prompt Version */
            prompt_version: string;
            /** Provider */
            provider: string;
            /**
             * Purpose
             * @enum {string}
             */
            purpose: "proposal" | "explanation";
        };
        /** NumericStats */
        NumericStats: {
            /** Count */
            count: number;
            /** Histogram */
            histogram: components["schemas"]["Bin"][];
            /** Maximum */
            maximum: string;
            /** Mean */
            mean: string;
            /** Median */
            median: string;
            /** Method */
            method: string;
            /** Minimum */
            minimum: string;
            outliers?: components["schemas"]["Outliers"] | null;
            /** Q1 */
            q1: string;
            /** Q3 */
            q3: string;
            /** Std */
            std: string | null;
        };
        /** NumericSummary */
        NumericSummary: {
            /** Count */
            count: number;
            /** Maximum */
            maximum: string;
            /** Mean */
            mean: string;
            /** Minimum */
            minimum: string;
            /** Total */
            total: string;
        };
        /** OmittedSource */
        OmittedSource: {
            /** Reason */
            reason: string;
            /** Table */
            table: string;
        };
        /**
         * OrdinalHint
         * @description Enteros con pocos valores que parecen una escala ordenada. Es una candidata: sólo cambia la
         *     clasificación si el usuario la confirma en el Diccionario.
         */
        OrdinalHint: {
            /** Order */
            order: string[];
            /** Reason */
            reason: string;
        };
        /**
         * Outliers
         * @description Valores atípicos por las vallas de Tukey (Fase 23). Es un aviso: no se elimina nada.
         */
        Outliers: {
            /** Count */
            count: number;
            /** Extreme */
            extreme: number;
            /** Extreme Lower */
            extreme_lower: string;
            /** Extreme Upper */
            extreme_upper: string;
            /** Method */
            method: string;
            /** Mild Lower */
            mild_lower: string;
            /** Mild Upper */
            mild_upper: string;
        };
        /** OverviewAudit */
        OverviewAudit: {
            call?: components["schemas"]["OverviewCall"] | null;
            content?: components["schemas"]["AuditContent"] | null;
            /**
             * Evidence
             * @default []
             */
            evidence: components["schemas"]["OverviewEvidence"][];
            /**
             * Producer Execution Id
             * Format: uuid
             */
            producer_execution_id: string;
            /**
             * Profile Id
             * Format: uuid
             */
            profile_id: string;
            /** Profile Sha256 */
            profile_sha256: string;
            /**
             * Prompt Id
             * @default automatic-overview-audit
             */
            prompt_id: string;
            /**
             * Prompt Version
             * @default 1
             */
            prompt_version: string;
            /** Reason */
            reason?: string | null;
            /**
             * Schema Version
             * @default overview-audit-v1
             * @constant
             */
            schema_version: "overview-audit-v1";
            /**
             * State
             * @enum {string}
             */
            state: "ready" | "unavailable" | "failed";
        };
        /** OverviewAuditView */
        OverviewAuditView: {
            audit?: components["schemas"]["OverviewAudit"] | null;
            /** Execution Id */
            execution_id?: string | null;
            /** Reason */
            reason?: string | null;
            /**
             * State
             * @enum {string}
             */
            state: "queued" | "running" | "ready" | "unavailable" | "failed";
        };
        /** OverviewCall */
        OverviewCall: {
            /** Cache Read Tokens */
            cache_read_tokens: number;
            /** Cache Write Tokens */
            cache_write_tokens: number;
            /** Context Sha256 */
            context_sha256: string;
            /** Cost Usd */
            cost_usd: string | null;
            /** Error Code */
            error_code?: string | null;
            /** Input Tokens */
            input_tokens: number;
            /** Latency Ms */
            latency_ms: number;
            /** Model */
            model: string;
            /**
             * Outcome
             * @enum {string}
             */
            outcome: "accepted" | "rejected" | "provider_error";
            /** Output Tokens */
            output_tokens: number;
            /** Parameters */
            parameters: {
                [key: string]: unknown;
            };
            /** Provider */
            provider: string;
        };
        /** OverviewChart */
        OverviewChart: {
            /** Column */
            column?: string | null;
            /** Excluded Rows */
            excluded_rows: number;
            /** Id */
            id: string;
            /** Measure */
            measure?: string | null;
            /**
             * Omitted Groups
             * @default 0
             */
            omitted_groups: number;
            /** Points */
            points: components["schemas"]["OverviewPoint"][];
            /** Title */
            title: string;
            /**
             * Type
             * @enum {string}
             */
            type: "bar" | "line";
            /** Valid Rows */
            valid_rows: number;
        };
        /** OverviewDetail */
        OverviewDetail: {
            /**
             * Cells Truncated
             * @default false
             */
            cells_truncated: boolean;
            /** Columns */
            columns: string[];
            /** Rows */
            rows: (string | null)[][];
            /** Total Rows */
            total_rows: number;
            /** Truncated */
            truncated: boolean;
        };
        /** OverviewEvidence */
        OverviewEvidence: {
            /** Id */
            id: string;
            /** Label */
            label: string;
            /** Path */
            path: string;
            /** Unit */
            unit: string;
            /** Value */
            value: string;
        };
        /** OverviewKpi */
        OverviewKpi: {
            /** Column */
            column?: string | null;
            /** Excluded Rows */
            excluded_rows?: number | null;
            /** Id */
            id: string;
            /** Label */
            label: string;
            /**
             * Unit
             * @enum {string}
             */
            unit: "count" | "percent" | "number";
            /** Valid Rows */
            valid_rows?: number | null;
            /** Value */
            value: string;
        };
        /** OverviewPoint */
        OverviewPoint: {
            /** Amount */
            amount?: string | null;
            /** Label */
            label: string;
            /** Value */
            value: number;
        };
        /** Period */
        Period: {
            /** Columns */
            columns: string[];
            /** First */
            first: string | null;
            /**
             * Kind
             * @enum {string}
             */
            kind: "date" | "year_month";
            /** Last */
            last: string | null;
            /** Missing */
            missing: number;
            /** Note */
            note: string;
            /** Periods */
            periods: number;
        };
        /**
         * PeriodCandidate
         * @description Año + Mes que podrían formar un periodo: se informa, nunca se crea una fecha.
         */
        PeriodCandidate: {
            /** Columns */
            columns: string[];
            /** First */
            first: string | null;
            /** Last */
            last: string | null;
            /** Note */
            note: string;
            /** Periods */
            periods: number;
            /** Unparsed Rows */
            unparsed_rows: number;
        };
        /**
         * PersonalHint
         * @description Columna que parece contener datos personales (Fase 23).
         */
        PersonalHint: {
            /**
             * Kind
             * @enum {string}
             */
            kind: "name" | "document" | "email" | "phone" | "address";
            /** Reason */
            reason: string;
        };
        /** PlanResponse */
        PlanResponse: {
            /** Content */
            content: {
                [key: string]: unknown;
            };
            /** Content Sha256 */
            content_sha256: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Created By
             * Format: uuid
             */
            created_by: string;
            /**
             * Family Id
             * Format: uuid
             */
            family_id: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Previous Revision Id */
            previous_revision_id?: string | null;
            /** Revision */
            revision: number;
            /**
             * Schema Version
             * @default 1
             * @constant
             */
            schema_version: 1;
        };
        /**
         * PlannedAnalysis
         * @description Un análisis candidato con sus requisitos y la decisión del sistema (con motivo).
         */
        PlannedAnalysis: {
            /** Dimension */
            dimension?: string | null;
            /** Id */
            id: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "evolution" | "year_over_year" | "breakdown" | "weighted_average" | "seasonality" | "anomalies";
            /** Measure */
            measure?: string | null;
            /** Priority */
            priority: number;
            /** Reason */
            reason: string;
            /** Requirements */
            requirements: string[];
            /**
             * Status
             * @enum {string}
             */
            status: "accepted" | "omitted";
            /** Title */
            title: string;
            /** Weight */
            weight?: string | null;
        };
        /** PreviewRow */
        PreviewRow: {
            /** Row Number */
            row_number: number;
            /** Values */
            values: {
                [key: string]: string | null;
            };
        };
        /**
         * Progress
         * @description Etapas de una carga en orden; `complete` cuando ninguna queda pendiente.
         */
        Progress: {
            /** Complete */
            complete: boolean;
            /** Stages */
            stages: components["schemas"]["Stage"][];
            /**
             * Version Id
             * Format: uuid
             */
            version_id: string;
        };
        /** ProjectPageResponse */
        ProjectPageResponse: {
            /** Items */
            items: components["schemas"]["ProjectResponse"][];
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
            /** Total */
            total: number;
        };
        /** ProjectResponse */
        ProjectResponse: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Description */
            description: string;
            /** File Name */
            file_name: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /** Revision */
            revision: number;
            /**
             * Status
             * @enum {string}
             */
            status: "draft" | "archived";
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /**
         * Proposal
         * @description Una consulta propuesta (por regla o por la IA) y la decisión de Python, con motivo.
         */
        Proposal: {
            /** Dimension */
            dimension: string | null;
            /** Group */
            group?: string | null;
            /** Iteration */
            iteration: number;
            /** Key */
            key?: string | null;
            /** Kind */
            kind: string;
            /** Month */
            month?: string | null;
            /** Motive */
            motive: string;
            /**
             * Origin
             * @enum {string}
             */
            origin: "rule" | "ai";
            /** Reason */
            reason?: string | null;
            /**
             * Status
             * @enum {string}
             */
            status: "accepted" | "rejected";
            /** Year */
            year?: number | null;
        };
        /** QualityIssue */
        QualityIssue: {
            /** Affected Rows */
            affected_rows: number;
            /** Column */
            column: string | null;
            /** Description */
            description: string;
            /** Id */
            id: string;
            /** Proposed Action */
            proposed_action: string;
            /**
             * Rule
             * @enum {string}
             */
            rule: "Q-001" | "Q-002" | "Q-003";
            /** Sample Row Numbers */
            sample_row_numbers: number[];
            /**
             * Severity
             * @enum {string}
             */
            severity: "medium" | "low";
        };
        /** QualityReport */
        QualityReport: {
            analytical?: components["schemas"]["AnalyticalQuality"] | null;
            /** Cell Count */
            cell_count: number;
            /** Completeness Percent */
            completeness_percent: number;
            /** Duplicate Rows */
            duplicate_rows: number;
            /** Issues */
            issues: components["schemas"]["QualityIssue"][];
            /** Missing Cells */
            missing_cells: number;
            /** Row Count */
            row_count: number;
            /**
             * Rule Version
             * @default csv-quality-v1
             * @constant
             */
            rule_version: "csv-quality-v1";
            /** Whitespace Cells */
            whitespace_cells: number;
        };
        /** RankCell */
        RankCell: {
            /** Evidence */
            evidence: string;
            /** Position */
            position: number;
            /** Tied With Previous */
            tied_with_previous: boolean;
        };
        /** RankingPartition */
        RankingPartition: {
            /** Groups */
            groups: number;
            /** Hidden */
            hidden: number;
            /** Period */
            period: {
                [key: string]: unknown;
            } | null;
            /** Ranked */
            ranked: number;
            /** Shown */
            shown: number;
        };
        /** RankingSummary */
        RankingSummary: {
            /**
             * Direction
             * @enum {string}
             */
            direction: "desc" | "asc";
            /** Hidden Groups */
            hidden_groups: number;
            /** Metric */
            metric: string;
            /** Partitions */
            partitions: components["schemas"]["RankingPartition"][];
            /** Top N */
            top_n: number;
        };
        /**
         * Recalculation
         * @description Trabajo en marcha o terminado que provocó la última corrección (Fase 23).
         */
        Recalculation: {
            /** Derived Version Id */
            derived_version_id?: string | null;
            /**
             * Execution Id
             * Format: uuid
             */
            execution_id: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "comprehension" | "null_cleaning";
            /** Reason */
            reason?: string | null;
            /**
             * State
             * @enum {string}
             */
            state: "queued" | "running" | "succeeded" | "failed" | "cancelled";
        };
        /**
         * RecordsPage
         * @description Fase 22: página de registros con los identificadores de columna (mismo orden que
         *     `columns`) y el orden y la búsqueda aplicados; `total` cuenta las filas que cumplen el
         *     filtro y la búsqueda. `PreviewPage` no cambia.
         */
        RecordsPage: {
            /** Column Ids */
            column_ids?: string[];
            /** Columns */
            columns: string[];
            /**
             * Descending
             * @default false
             */
            descending: boolean;
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
            /** Rows */
            rows: components["schemas"]["PreviewRow"][];
            /** Search */
            search?: string | null;
            /** Sort */
            sort?: string | null;
            /** Total */
            total: number;
        };
        /** RegisterRequest */
        RegisterRequest: {
            /**
             * Email
             * Format: email
             */
            email: string;
            /** Name */
            name: string;
            /** Password */
            password: string;
        };
        /**
         * Relationship
         * @description Relación candidata con la evidencia que la respalda o no.
         *
         *     `key` es estable entre versiones del mismo archivo (columnas ordenadas y tipo): con ella se
         *     guarda la valoración del usuario. Fase 24: `derived` (una columna calculada y una de sus
         *     fuentes), `same_entity` (dos columnas que nombran lo mismo, 1:1) y `period` (columnas que
         *     forman un periodo), con su familia y su estado.
         */
        Relationship: {
            /** Columns */
            columns: [
                string,
                string
            ];
            /** Detail */
            detail: string;
            evidence?: components["schemas"]["Association"] | null;
            /**
             * Family
             * @default statistical
             * @enum {string}
             */
            family: "structural" | "statistical" | "temporal";
            /** Hypothesis */
            hypothesis?: string | null;
            /** Key */
            key: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "association" | "dependency" | "declared" | "derived" | "same_entity" | "period";
            /**
             * Origin
             * @enum {string}
             */
            origin: "ai" | "data" | "declared";
            /**
             * State
             * @default pending
             * @enum {string}
             */
            state: "pending" | "validated" | "rejected" | "ambiguous";
            /**
             * Status
             * @enum {string}
             */
            status: "confirmed" | "not_supported" | "not_testable";
            /** Verdict */
            verdict?: ("relevant" | "not_relevant") | null;
        };
        /** ReportBlock */
        ReportBlock: {
            /** Badge */
            badge?: string | null;
            chart?: components["schemas"]["ReportChart"] | null;
            /** Paragraphs */
            paragraphs?: string[];
            table?: components["schemas"]["ReportTable"] | null;
            /** Title */
            title?: string | null;
        };
        /**
         * ReportChart
         * @description Ilustración vectorial de una serie ya calculada; la trazabilidad está en la tabla.
         */
        ReportChart: {
            /** Labels */
            labels: string[];
            /** Title */
            title: string;
            /**
             * Type
             * @enum {string}
             */
            type: "bar" | "line";
            /** Values */
            values: string[];
        };
        /** ReportDocument */
        ReportDocument: {
            /** Calls */
            calls?: {
                [key: string]: unknown;
            }[];
            /** Evidence Ids */
            evidence_ids: string[];
            /**
             * Generated At
             * Format: date-time
             */
            generated_at: string;
            /** Narrative By */
            narrative_by?: ("ai" | "rules") | null;
            /** Narrative Reason */
            narrative_reason?: string | null;
            /**
             * Operation
             * @default delivery.report@1
             * @enum {string}
             */
            operation: "delivery.report@1" | "delivery.report@2";
            /** Review */
            review?: components["schemas"]["ReviewItem"][];
            /**
             * Rules Version
             * @default automatic-report-v1
             * @enum {string}
             */
            rules_version: "automatic-report-v1" | "automatic-report-v2";
            /**
             * Schema Version
             * @default 1
             * @enum {integer}
             */
            schema_version: 1 | 2;
            /** Sections */
            sections: components["schemas"]["ReportSection"][];
            source: components["schemas"]["ReportSource"];
            /** Title */
            title: string;
        };
        /** ReportHistory */
        ReportHistory: {
            /** Items */
            items: components["schemas"]["ReportVersion"][];
        };
        /**
         * ReportReview
         * @description Los hallazgos candidatos con su revisión vigente (Fase 27). `changed`: la selección
         *     difiere de la usada por la última versión del informe.
         */
        ReportReview: {
            /** Changed */
            changed: boolean;
            /** Items */
            items: components["schemas"]["ReviewItem"][];
        };
        /** ReportSection */
        ReportSection: {
            /** Blocks */
            blocks: components["schemas"]["ReportBlock"][];
            /** Id */
            id: string;
            /** Intro */
            intro?: string | null;
            /** Title */
            title: string;
        };
        /**
         * ReportSource
         * @description De dónde sale cada parte del informe (ids y hashes de lo publicado).
         */
        ReportSource: {
            /**
             * Analysis Execution Id
             * Format: uuid
             */
            analysis_execution_id: string;
            /** Analysis Sha256 */
            analysis_sha256: string;
            /** Dashboard Execution Id */
            dashboard_execution_id?: string | null;
            /** Dashboard Sha256 */
            dashboard_sha256?: string | null;
            /** Execution Id */
            execution_id?: string | null;
            /** Exploration Execution Id */
            exploration_execution_id?: string | null;
            /** Exploration Sha256 */
            exploration_sha256?: string | null;
            /** Feedback Sha256 */
            feedback_sha256?: string | null;
            /** File Name */
            file_name: string;
            /** Inspection Sha256 */
            inspection_sha256?: string | null;
            /** Investigation Execution Id */
            investigation_execution_id?: string | null;
            /** Investigation Sha256 */
            investigation_sha256?: string | null;
            /** Meanings Sha256 */
            meanings_sha256?: string | null;
            /**
             * Project Id
             * Format: uuid
             */
            project_id: string;
            /** Quality Sha256 */
            quality_sha256?: string | null;
            /**
             * Version Id
             * Format: uuid
             */
            version_id: string;
            /** Version Number */
            version_number: number;
        };
        /** ReportTable */
        ReportTable: {
            /** Headers */
            headers: string[];
            /** Rows */
            rows: string[][];
        };
        /**
         * ReportVersion
         * @description Una versión del historial del informe (Fase 27).
         */
        ReportVersion: {
            /** Approved */
            approved?: number | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Execution Id
             * Format: uuid
             */
            execution_id: string;
            /** Finished At */
            finished_at?: string | null;
            /** Number */
            number: number;
            /** Principal */
            principal?: number | null;
            /** Rules Version */
            rules_version?: string | null;
            /**
             * State
             * @enum {string}
             */
            state: "queued" | "running" | "succeeded" | "failed" | "cancelled";
            /** Trigger */
            trigger: string;
        };
        /**
         * ReportView
         * @description Estado del informe de una versión (sólo lectura).
         */
        ReportView: {
            /** Byte Size */
            byte_size?: number | null;
            document?: components["schemas"]["ReportDocument"] | null;
            /** Evidence Count */
            evidence_count?: number | null;
            /** Execution Id */
            execution_id?: string | null;
            /** File Name */
            file_name?: string | null;
            /** Generated At */
            generated_at?: string | null;
            /** Number */
            number?: number | null;
            /** Reason */
            reason?: string | null;
            /** Sha256 */
            sha256?: string | null;
            /**
             * State
             * @enum {string}
             */
            state: "queued" | "running" | "ready" | "failed";
            /**
             * Updating
             * @default false
             */
            updating: boolean;
        };
        /** ResultColumn */
        ResultColumn: {
            /** Column Id */
            column_id: string | null;
            /** Key */
            key: string;
            /** Name */
            name: string;
            /** Technical Type */
            technical_type: string | null;
            /** Time Grain */
            time_grain?: ("day" | "week" | "month" | "quarter" | "year") | null;
        };
        /** ResultRow */
        ResultRow: {
            /** Evidence */
            evidence: {
                [key: string]: string;
            };
            /** Key */
            key: {
                [key: string]: unknown;
            };
            /** Labels */
            labels: {
                [key: string]: string | null;
            };
            /** Values */
            values: {
                [key: string]: string | null;
            };
        };
        /** ResultRowV2 */
        ResultRowV2: {
            /** Comparisons */
            comparisons?: {
                [key: string]: {
                    [key: string]: components["schemas"]["ComparisonCell"];
                };
            };
            /** Evidence */
            evidence: {
                [key: string]: string;
            };
            /** Key */
            key: {
                [key: string]: unknown;
            };
            /** Labels */
            labels: {
                [key: string]: string | null;
            };
            rank?: components["schemas"]["RankCell"] | null;
            /** Share */
            share?: {
                [key: string]: components["schemas"]["ShareCell"];
            };
            /** Values */
            values: {
                [key: string]: string | null;
            };
        };
        /** ResultRowV3 */
        ResultRowV3: {
            /** Comparisons */
            comparisons?: {
                [key: string]: {
                    [key: string]: components["schemas"]["ComparisonCell"];
                };
            };
            /** Evidence */
            evidence: {
                [key: string]: string;
            };
            /** Key */
            key: {
                [key: string]: unknown;
            };
            /** Labels */
            labels: {
                [key: string]: string | null;
            };
            rank?: components["schemas"]["RankCell"] | null;
            /** Share */
            share?: {
                [key: string]: components["schemas"]["ShareCell"];
            };
            /** Snapshots */
            snapshots?: {
                [key: string]: string;
            };
            /** Values */
            values: {
                [key: string]: string | null;
            };
        };
        /**
         * ReviewItem
         * @description Un hallazgo candidato del informe (Fase 27) y su revisión: pendiente, aprobado o
         *     rechazado. `principal`: si aparece entre los hallazgos principales.
         */
        ReviewItem: {
            /** Classification */
            classification?: string | null;
            /** Item */
            item: string;
            /**
             * Origin
             * @enum {string}
             */
            origin: "exploration" | "insight";
            /** Principal */
            principal: boolean;
            /**
             * Status
             * @enum {string}
             */
            status: "pending" | "approved" | "rejected";
            /** Title */
            title: string;
        };
        /** ReviewRequest */
        ReviewRequest: {
            /** Item */
            item: string;
            /**
             * Status
             * @enum {string}
             */
            status: "pending" | "approved" | "rejected";
        };
        /**
         * Segment
         * @description Trozo de texto que se muestra: texto libre, cifra verificada (con su evidencia) o una
         *     cifra escrita por el modelo que se retiró.
         */
        Segment: {
            /** Evidence Id */
            evidence_id?: string | null;
            /** Execution Id */
            execution_id?: string | null;
            /**
             * Kind
             * @enum {string}
             */
            kind: "text" | "evidence" | "unverified";
            /** Text */
            text: string;
        };
        /** SessionResponse */
        SessionResponse: {
            /** Csrf Token */
            csrf_token: string;
            /**
             * Expires At
             * Format: date-time
             */
            expires_at: string;
            user: components["schemas"]["UserResponse"];
        };
        /**
         * ShareCell
         * @description Porcentaje del grupo sobre el total de su periodo (o del resultado), redondeado por
         *     separado con `share_scale` y HALF_EVEN. `total_zero`/`value_missing`: nulo, nunca 0.
         */
        ShareCell: {
            /** Evidence */
            evidence: string;
            /**
             * Status
             * @enum {string}
             */
            status: "available" | "total_zero" | "value_missing";
            /** Value */
            value: string | null;
        };
        /**
         * ShareTotal
         * @description Total de una partición, calculado ANTES del top N y del presupuesto: los porcentajes
         *     de las filas visibles pueden sumar menos de 100. Cada porcentaje se redondea por separado,
         *     así que la suma de todos los grupos puede desviarse de 100 hasta `tolerance` puntos
         *     (n × media unidad de `share_scale`).
         */
        ShareTotal: {
            /** Groups */
            groups: number;
            /** Metric */
            metric: string;
            /** Mixed Signs */
            mixed_signs: boolean;
            /** Period */
            period: {
                [key: string]: unknown;
            } | null;
            /** Tolerance */
            tolerance: string;
            /** Total */
            total: string;
        };
        /** SheetFacts */
        SheetFacts: {
            /** Hidden */
            hidden: boolean;
            /** Name */
            name: string;
            /** Selected */
            selected: boolean;
            /** Tables */
            tables: string[];
        };
        /**
         * SnapshotCounts
         * @description Último corte de una métrica semi-aditiva. `superseded_rows`: filas incluidas (pasan
         *     filtros y nulos) de fechas anteriores al corte de su periodo; no entran en el valor. Las
         *     filas que forman el valor son `included_rows - superseded_rows`.
         */
        SnapshotCounts: {
            /** Base Superseded Rows */
            base_superseded_rows?: {
                [key: string]: number;
            };
            /** Superseded Rows */
            superseded_rows: number;
        };
        /**
         * SourceOrigin
         * @description De dónde sale una versión que no es un archivo tabular (Fase 18B): una tabla copiada de
         *     SQL Server o una tabla de un PDF. Decisión del sistema; no hay nada que elegir.
         */
        SourceOrigin: {
            /** Analyzed Together */
            analyzed_together?: string[];
            /** Captured At */
            captured_at?: string | null;
            /** Database */
            database?: string | null;
            /** Excluded Columns */
            excluded_columns?: components["schemas"]["ExcludedColumn"][];
            /** Foreign Keys */
            foreign_keys?: components["schemas"]["ForeignKey"][];
            /**
             * Kind
             * @enum {string}
             */
            kind: "sqlserver" | "pdf";
            /** Omitted */
            omitted?: components["schemas"]["OmittedSource"][];
            /** Pages */
            pages?: number[];
            /**
             * Rule
             * @enum {string}
             */
            rule: "sqlserver-selection-v1" | "pdf-selection-v1";
            /** Server */
            server?: string | null;
            /** Table */
            table: string;
        };
        /**
         * SourceReading
         * @description Cómo se leyó el original: codificación, separador y valores regionales. Se guarda en
         *     los metadatos de la tabla leída (no es un artefacto aparte).
         */
        SourceReading: {
            /** Convention */
            convention?: ("decimal_comma" | "decimal_point_grouped") | null;
            /** Converted */
            converted?: components["schemas"]["ConvertedColumn"][];
            /** Encoding */
            encoding?: ("utf-8-sig" | "cp1252") | null;
            /**
             * Format
             * @enum {string}
             */
            format: "csv" | "xlsx" | "pdf";
            /** Kept As Text */
            kept_as_text?: components["schemas"]["KeptColumn"][];
            /**
             * Rule
             * @default regional-values-v1
             * @constant
             */
            rule: "regional-values-v1";
            /** Separator */
            separator?: string | null;
        };
        /**
         * SourceReview
         * @description Lectura del archivo y cambios de estructura de una versión (GET /versions/{id}/reading).
         *     `reading` es None en versiones leídas antes de la Fase 18; `structure`, si no hay una
         *     versión anterior comparable.
         */
        SourceReview: {
            origin?: components["schemas"]["SourceOrigin"] | null;
            reading: components["schemas"]["SourceReading"] | null;
            structure: components["schemas"]["StructureComparison"] | null;
        };
        /**
         * SqlServerConnection
         * @description Datos de conexión de un solo uso (Fase 18B). La contraseña se usa para copiar las tablas
         *     y se descarta: no se guarda, no entra en el plan ni en la huella de idempotencia.
         */
        SqlServerConnection: {
            /** Database */
            database: string;
            /**
             * Password
             * Format: password
             */
            password: string;
            /**
             * Port
             * @default 1433
             */
            port: number;
            /** Server */
            server: string;
            /** User */
            user: string;
        };
        /** Stage */
        Stage: {
            /** Detail */
            detail: string;
            /** Execution Id */
            execution_id?: string | null;
            /** Finished At */
            finished_at?: string | null;
            /**
             * Id
             * @enum {string}
             */
            id: "analysis" | "comprehension" | "exploration" | "dashboard" | "investigation" | "report";
            /**
             * State
             * @enum {string}
             */
            state: "pending" | "queued" | "running" | "done" | "failed" | "skipped";
            /** Title */
            title: string;
        };
        /**
         * StructureComparison
         * @description Cambios de columnas respecto de la versión anterior del mismo archivo (Fase 18).
         *     Sólo se informa: no se renombra ni se mapea nada.
         */
        StructureComparison: {
            /** Changes */
            changes: components["schemas"]["ColumnChange"][];
            /** Previous Version Id */
            previous_version_id: string;
            /** Previous Version Number */
            previous_version_number: number;
            /**
             * Rule
             * @default structure-comparison-v1
             * @constant
             */
            rule: "structure-comparison-v1";
            /** Unchanged */
            unchanged: number;
        };
        /** Summary */
        Summary: {
            /** Cells */
            cells: number;
            /** Columns */
            columns: number;
            /** Completeness Percent */
            completeness_percent: string;
            /** Duplicate Rows */
            duplicate_rows: number;
            /** Duplicate Rows Without Ids */
            duplicate_rows_without_ids?: number | null;
            /** Groups */
            groups: {
                [key: string]: number;
            };
            /** Identifier Columns */
            identifier_columns?: string[];
            /** Memory Bytes */
            memory_bytes: number | null;
            /** Missing Cells */
            missing_cells: number;
            /** Personal Columns */
            personal_columns?: string[];
            /** Rows */
            rows: number;
        };
        /** TemporalStats */
        TemporalStats: {
            /** Distinct Periods */
            distinct_periods: number;
            /** Frequency */
            frequency: ("daily" | "weekly" | "monthly" | "quarterly" | "yearly" | "irregular") | null;
            /** Maximum */
            maximum: string;
            /** Method */
            method: string;
            /** Minimum */
            minimum: string;
            /** Missing Periods */
            missing_periods: number | null;
            /** Missing Sample */
            missing_sample: string[];
            /** Span Days */
            span_days: number | null;
        };
        /**
         * TimeAxis
         * @description Eje temporal mensual: una fecha o Año + Mes compuestos. No rellena meses vacíos.
         */
        TimeAxis: {
            /** Columns */
            columns: string[];
            /** First */
            first: string | null;
            /**
             * Granularity
             * @default month
             * @constant
             */
            granularity: "month";
            /** Incomplete */
            incomplete: string[];
            /**
             * Kind
             * @enum {string}
             */
            kind: "date" | "year_month";
            /** Last */
            last: string | null;
            /** Missing */
            missing: string[];
            /** Missing Count */
            missing_count: number;
            /** Periods */
            periods: number;
            /** Unparsed Rows */
            unparsed_rows: number;
            /**
             * Unparsed Sample Rows
             * @default []
             */
            unparsed_sample_rows: number[];
            /** Years */
            years: string[];
        };
        /**
         * TimeRange
         * @description Rango inclusivo de fechas de negocio (ISO).
         */
        TimeRange: {
            /** End */
            end?: string | null;
            /** Start */
            start?: string | null;
        };
        /** TokenCount */
        TokenCount: {
            /** Count */
            count: number;
            /** Token */
            token: string;
            /** Variants */
            variants?: string[];
        };
        /**
         * Trace
         * @description Origen reproducible de un gráfico (Fase 26): la investigación o el cálculo que lo produce
         *     y sus parámetros.
         */
        Trace: {
            /** Aggregation */
            aggregation?: string | null;
            /** Columns */
            columns?: string[];
            /** Filters */
            filters?: string[];
            /** Grouping */
            grouping?: string[];
            /** Investigation */
            investigation?: string | null;
            /** Measure */
            measure?: string | null;
            /** Method */
            method: string;
            /** Operation */
            operation: string;
            /** Period Columns */
            period_columns?: string[];
            /** Question */
            question?: string | null;
            /** Rows */
            rows?: number | null;
            /**
             * Source
             * @enum {string}
             */
            source: "investigation" | "analysis" | "dashboard";
            /** Total Rows */
            total_rows?: number | null;
        };
        /** UpdateProjectRequest */
        UpdateProjectRequest: {
            /**
             * Description
             * @default
             */
            description: string;
            /** Expected Revision */
            expected_revision: number;
            /** Name */
            name: string;
        };
        /** UserResponse */
        UserResponse: {
            /** Email */
            email: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
        };
        /**
         * ValueDomain
         * @description Dominio evidente de una columna numérica (Fase 23) y cuántos valores lo incumplen.
         */
        ValueDomain: {
            /**
             * Kind
             * @enum {string}
             */
            kind: "percent" | "non_negative";
            /** Lower */
            lower: string;
            /** Outside */
            outside: number;
            /** Reason */
            reason: string;
            /** Upper */
            upper: string | null;
        };
        /** VersionPage */
        VersionPage: {
            /** Items */
            items: components["schemas"]["VersionResponse"][];
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
            /** Total */
            total: number;
        };
        /** VersionResponse */
        VersionResponse: {
            /** Attempts */
            attempts: number;
            /** Byte Size */
            byte_size: number;
            /** Column Count */
            column_count: number | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Dataset Id
             * Format: uuid
             */
            dataset_id: string;
            /** Error Code */
            error_code: string | null;
            /** Error Message */
            error_message: string | null;
            /**
             * Execution Id
             * Format: uuid
             */
            execution_id: string;
            /** File Name */
            file_name: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "imported" | "derived";
            /** Number */
            number: number;
            /** Parent Version Id */
            parent_version_id: string | null;
            /**
             * Project Id
             * Format: uuid
             */
            project_id: string;
            /** Row Count */
            row_count: number | null;
            /** Sha256 */
            sha256: string;
            source_origin?: components["schemas"]["SourceOrigin"] | null;
            source_selection?: components["schemas"]["XlsxSelection"] | null;
            /**
             * State
             * @enum {string}
             */
            state: "queued" | "processing" | "succeeded" | "failed" | "cancelled";
        };
        /** XlsxCandidate */
        XlsxCandidate: {
            /** Sheet */
            sheet: string;
            /** Table */
            table: string | null;
        };
        /**
         * XlsxChoice
         * @description Una tabla del libro que `xlsx-selection-v2` analiza (con su fila de cabecera).
         */
        XlsxChoice: {
            /** Header Row */
            header_row: number;
            /** Sheet */
            sheet: string;
            /** Table */
            table: string | null;
        };
        /**
         * XlsxInspection
         * @description Hojas y tablas del libro y vista previa de la selección, antes de importar.
         */
        XlsxInspection: {
            /** Additional */
            additional?: components["schemas"]["XlsxChoice"][];
            /** Columns */
            columns: string[];
            /** Header Row */
            header_row: number;
            problem?: components["schemas"]["XlsxProblem"] | null;
            /** Row Count */
            row_count: number;
            /** Rows */
            rows: (string | null)[][];
            selection?: components["schemas"]["XlsxSelection"] | null;
            /** Sheet */
            sheet: string;
            /** Sheets */
            sheets: components["schemas"]["XlsxSheet"][];
            /** Table */
            table: string | null;
            /** Warning Count */
            warning_count: number;
            /** Warnings */
            warnings: components["schemas"]["XlsxWarning"][];
        };
        /** XlsxProblem */
        XlsxProblem: {
            /** Code */
            code: string;
            /** Message */
            message: string;
        };
        /**
         * XlsxSelection
         * @description Decisión automática del sistema (Fase 13B, regla `xlsx-selection-v1`): hoja o tabla
         *     importada, fila de cabecera y lo que quedó fuera. Desde la Fase 18 (`xlsx-selection-v2`)
         *     las demás tablas con datos del libro se analizan como versiones propias de la misma carga
         *     (`analyzed_together`); `omitted` sólo lista lo que no se analiza.
         */
        XlsxSelection: {
            /** Analyzed Together */
            analyzed_together?: components["schemas"]["XlsxCandidate"][];
            /** Header Row */
            header_row: number;
            /** Omitted */
            omitted: components["schemas"]["XlsxCandidate"][];
            /**
             * Rule
             * @enum {string}
             */
            rule: "xlsx-selection-v1" | "xlsx-selection-v2";
            /** Sheet */
            sheet: string;
            /** Table */
            table: string | null;
        };
        /** XlsxSheet */
        XlsxSheet: {
            /** Hidden */
            hidden: boolean;
            /** Name */
            name: string;
            /** Tables */
            tables: string[];
        };
        /** XlsxWarning */
        XlsxWarning: {
            /** Cell */
            cell: string;
            /** Code */
            code: string;
            /** Message */
            message: string;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    login: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LoginRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionResponse"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    logout: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    getSession: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionResponse"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    register: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RegisterRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionResponse"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    getIngestionSummary: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IngestionSummary"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    getExecution: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                execution_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExecutionDetail"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    getExecutionAnalysis: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                execution_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AnalysisResult"] | components["schemas"]["AnalysisResultV2"] | components["schemas"]["AnalysisResultV3"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    exportAnalysisCsv: {
        parameters: {
            query?: {
                profile?: "standard" | "excel_regional";
            };
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                execution_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "text/csv": Blob;
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    listExecutionArtifacts: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                execution_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ArtifactResponse"][];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    cancelImport: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                execution_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VersionResponse"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    getEvidence: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                execution_id: string;
                evidence_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EvidenceView"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    getExecutionProfile: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                execution_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DatasetProfile"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    getExecutionQuality: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                execution_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["QualityReport"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    listProjects: {
        parameters: {
            query?: {
                q?: string;
                status?: ("draft" | "archived") | null;
                limit?: number;
                offset?: number;
            };
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectPageResponse"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    createProject: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateProjectRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectResponse"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    getProject: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectResponse"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    updateProject: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UpdateProjectRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectResponse"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    archiveProject: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ArchiveProjectRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectResponse"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    uploadCsv: {
        parameters: {
            query: {
                file_name: string;
                separator?: "auto" | "," | ";" | "tab";
            };
            header: {
                "Idempotency-Key": string;
                "X-CSRF-Token"?: string | null;
            };
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "text/csv": Blob;
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VersionResponse"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    uploadPdf: {
        parameters: {
            query: {
                file_name: string;
            };
            header: {
                "Idempotency-Key": string;
                "X-CSRF-Token"?: string | null;
            };
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/pdf": Blob;
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VersionResponse"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    importSqlServer: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "X-CSRF-Token"?: string | null;
            };
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SqlServerConnection"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VersionResponse"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    uploadXlsx: {
        parameters: {
            query: {
                file_name: string;
                sheet?: string | null;
                table?: string | null;
                header_row?: number;
            };
            header: {
                "Idempotency-Key": string;
                "X-CSRF-Token"?: string | null;
            };
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": Blob;
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VersionResponse"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    inspectXlsx: {
        parameters: {
            query: {
                file_name: string;
                sheet?: string | null;
                table?: string | null;
                header_row?: number;
            };
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": Blob;
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["XlsxInspection"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    listVersions: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
            };
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VersionPage"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    getVersion: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                version_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VersionResponse"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    getAutomaticAnalysis: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                version_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AutomaticAnalysis"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    getAutomaticEvidence: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                version_id: string;
                evidence_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AutomaticEvidence"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    getComprehension: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                version_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ComprehensionView"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    judgeRelationship: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                version_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["FeedbackRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ComprehensionView"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    describeColumn: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                version_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MeaningRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ComprehensionView"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    getDashboard: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                version_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DashboardView"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    saveDashboardCustomization: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                version_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DashboardCustomizationRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DashboardView"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    judgeFinding: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                version_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["FindingFeedbackRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DashboardView"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    filterDashboard: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                version_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DashboardFilterRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DashboardFilterResult"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    getDiagnostic: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                version_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Diagnostic"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    annotateColumn: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                version_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AnnotationRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InspectionView"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    listVersionExecutions: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                version_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExecutionResponse"][];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    getExploration: {
        parameters: {
            query?: {
                execution_id?: string | null;
            };
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                version_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExplorationView"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    controlInvestigation: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                version_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["InvestigationCommand"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExplorationView"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    getInvestigationHistory: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                version_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InvestigationHistory"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    exportVersionCsv: {
        parameters: {
            query?: {
                profile?: "standard" | "excel_regional";
            };
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                version_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "text/csv": Blob;
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    getInspection: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                version_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InspectionView"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    getInvestigation: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                version_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InvestigationView"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    getInvestigationEvidence: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                version_id: string;
                evidence_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AutomaticEvidence"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    getVersionLineage: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                version_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LineageView"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    downloadOriginal: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                version_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/octet-stream": Blob;
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    getOverviewAudit: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                version_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OverviewAuditView"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    getOverviewAuditEvidence: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                version_id: string;
                evidence_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OverviewEvidence"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    previewVersion: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
                issue_id?: string | null;
                sort?: string | null;
                descending?: boolean;
                search?: string | null;
            };
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                version_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RecordsPage"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    getVersionProgress: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                version_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Progress"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    getSourceReview: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                version_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SourceReview"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    getReport: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                version_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReportView"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    downloadReport: {
        parameters: {
            query?: {
                execution_id?: string | null;
            };
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                version_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/pdf": unknown;
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    getReportHistory: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                version_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReportHistory"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    getReportReview: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                version_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReportReview"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    reviewReportFinding: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                version_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ReviewRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReportReview"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    generateReportVersion: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                version_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReportView"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    getReportVersion: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                version_id: string;
                execution_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReportView"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    listVersionRepresentations: {
        parameters: {
            query?: never;
            header?: {
                "X-CSRF-Token"?: string | null;
            };
            path: {
                version_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ArtifactResponse"][];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    liveness: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string;
                    };
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    readiness: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string;
                    };
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unsupported Media Type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
}
