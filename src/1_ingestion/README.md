# Tarea 1: Ingesta y Segmentación Dinámica

Módulo encargado de analizar la densidad técnica del manual y segmentarlo en chunks adaptativos, respetando la estructura semántica del documento.

---

## Archivos

### `term_loader.py`
Carga y cachea los términos técnicos del dominio desde fuentes ontológicas externas.

**Fuentes:**
- **ESDBpedia** (`es.dbpedia.org/sparql`) — términos en español via SPARQL
- **AAS / ECLASS** — conceptos industriales en inglés, traducidos al español con Helsinki-NLP (`opus-mt-en-es`)

**Comportamiento del cache:**
- Primera ejecución → consulta las ontologías, traduce y guarda `cache/terms_cache.json`
- Ejecuciones siguientes → usa el cache directamente (mucho más rápido)
- El cache expira cada 30 días y se regenera automáticamente

**Salida:** `cache/terms_cache.json`

---

### `density_analyzer.py`
Analiza la densidad de términos técnicos en cada sección del manual para determinar el tamaño óptimo del chunk.

**Entrada:** archivo `.txt` con el manual segmentado en secciones con el siguiente formato:
```
--- Páginas: [N] | Sección: X.X | Título: - ---
Texto de la sección...
```

**Lógica:**
- Calcula un score de densidad por sección: `términos técnicos / total palabras`
- Si densidad ≥ 5% → nivel **alto** → chunk de 256 tokens (evita saturación)
- Si densidad < 5% → nivel **bajo** → chunk de 512 tokens (maximiza contexto)
- Solapamiento del 15% entre chunks

**Salida:** `data/raw/density_report.json`
```json
{
  "chunk_id": 1,
  "paginas": "[3]",
  "seccion": "0.2",
  "word_count": 87,
  "technical_terms_count": 3,
  "terms_found": ["mantenimiento", "máquina", "montaje"],
  "density_score": 0.034,
  "density_level": "baja",
  "chunk_size_tokens": 512,
  "overlap_tokens": 76
}
```

> **Nota:** `density_report.json` no se versiona en el repo (ver `.gitignore`). Se regenera ejecutando el script.

---

### `chunker.py`
Segmenta el manual en chunks adaptativos listos para la extracción de entidades (Tarea 2).

**Entrada:** archivo `.txt` del manual + `density_report.json`

**Autodetección:** si `density_report.json` no existe, ejecuta `density_analyzer.py` automáticamente antes de continuar.

**Reglas de segmentación:**
- **Header-bound:** cada nueva sección del manual fuerza el inicio de un chunk nuevo
- **Sentence-safe:** nunca corta una frase a la mitad (respeta `.`, `!`, `?`)
- **Ventana adaptativa:** tamaño del chunk según el nivel de densidad de la sección
- **Overlap:** los últimos ~15% de tokens del chunk anterior se copian al inicio del siguiente para mantener continuidad de contexto

**Salida:** `data/raw/chunks_output.json`
```json
{
  "chunk_id": 1,
  "seccion": "0.2",
  "titulo": "-",
  "paginas": "[3]",
  "density_level": "baja",
  "max_tokens": 512,
  "tokens_approx": 134,
  "text": "USO DEL MANUAL Este manual proporciona..."
}
```

> **Nota:** `chunks_output.json` no se versiona en el repo. Se regenera ejecutando el script.

---

## Uso

```bash
# Opción 1: ejecutar todo el pipeline de ingesta de una vez
python src/1_ingestion/chunker.py --input data/raw/chunks_manual_instrucciones_a218_reduced.txt

# Opción 2: ejecutar paso a paso
python src/1_ingestion/density_analyzer.py --input data/raw/chunks_manual_instrucciones_a218_reduced.txt
python src/1_ingestion/chunker.py --input data/raw/chunks_manual_instrucciones_a218_reduced.txt

# Forzar regeneración del cache de términos ontológicos
python src/1_ingestion/density_analyzer.py --input data/raw/... --refresh-terms
```

---

## Dependencias

```
rdflib
SPARQLWrapper
transformers
sentencepiece
requests
```

Instalación:
```bash
pip install SPARQLWrapper requests transformers sentencepiece
```

---

## Archivos generados (no versionados)

| Archivo | Generado por | Descripción |
|---|---|---|
| `cache/terms_cache.json` | `term_loader.py` | Cache de términos ontológicos (30 días TTL) |
| `data/raw/density_report.json` | `density_analyzer.py` | Score de densidad por sección |
| `data/raw/chunks_output.json` | `chunker.py` | Chunks finales listos para Tarea 2 |

---

## Relación con otros módulos

- **Siguiente paso:** `src/2_extraction/` consume `chunks_output.json` para la extracción de entidades y relaciones (Tarea 2)
- **Issues relacionados:** `#1 Density Analyzer` (cerrado), `#2 Chunker`