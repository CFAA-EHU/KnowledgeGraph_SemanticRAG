# src/1_ingestion

Ingesta ligera, descubrimiento de terminos y segmentacion fisica del material de entrada.

## Estado tras T20

La ingesta sigue produciendo un solo carril operativo, pero ahora marca el idioma de cada chunk:
- `source_language`
- `language_confidence`

Ese metadato viaja despues a `density_report.json`, `abox_input.json` y `language_detection_report.json`.
En T21 tambien se reutiliza para onboarding piloto real de `chunks_8070_quick_ref.txt`, generando:
- `data/processed/quick_ref_density_report.json`
- `data/processed/quick_ref_language_detection_report.json`

## Componentes principales

### `termLoader.py`
- descubre y cachea terminos tecnicos en `cache/terms_cache.json`
- mantiene compatibilidad con el shape historico `termino` + `uri`
- admite ahora metadata opcional:
  - `source_language`
  - `surface_es`
  - `surface_en`
  - `aliases`

### `language_utils.py`
- deteccion ligera y determinista ES/EN
- normalizacion comun de texto
- seleccion de surfaces de terminos por idioma

### `density_analyzer.py`
- segmenta el material de entrada respetando oraciones
- calcula densidad tecnica
- detecta idioma por chunk/manual
- acepta rutas de salida parametrizadas para pilotos de onboarding
- persiste:
  - `data/raw/density_report.json`
  - `data/processed/language_detection_report.json`

## Contrato bilingue

- no se traduce todo el manual antes de extraer
- `textoExtracto` debe mantenerse en idioma original aguas abajo
- el bilinguismo operativo se apoya en metadata de idioma + lexicalizacion posterior, no en duplicar chunks o grafo

## Uso

```bash
python src/1_ingestion/density_analyzer.py --input data/raw/chunks_manual_instrucciones_a218.txt
```

```bash
python src/1_ingestion/density_analyzer.py --input data/raw/chunks_8070_quick_ref.txt --manual-id 8070_quick_ref --output data/processed/quick_ref_density_report.json --language-report-path data/processed/quick_ref_language_detection_report.json
```
