# 📦 Pull Request

## Descripción
<!-- Explica brevemente qué hace este PR y por qué -->

## Tipo de cambio
- [ ] 🐛 Bug fix
- [ ] ✨ Nueva funcionalidad
- [ ] ♻️ Refactoring (sin cambio de funcionalidad)
- [ ] 📄 Documentación
- [ ] 🔧 Configuración / CI-CD
- [ ] 🧪 Tests

## Etapa del Pipeline afectada
- [ ] Tarea 1: Ingesta
- [ ] Tarea 2: Extracción CoT
- [ ] Tarea 3: Merging
- [ ] Tarea 4: Golden Set
- [ ] Tarea 5: SPARQL
- [ ] Tarea 6: Ejecución
- [ ] Tarea 7: Diagnóstico
- [ ] Tarea 8: Refinamiento

## Checklist
- [ ] El código pasa todos los tests existentes (`pytest tests/`)
- [ ] Los archivos `.ttl` generados son válidos (validación con `rdflib`)
- [ ] Las consultas SPARQL nuevas pasan validación de esquema (T-Box)
- [ ] Se han añadido tests para los cambios introducidos
- [ ] La documentación está actualizada (si aplica)

## Cambios en la Ontología
<!-- Si este PR modifica o genera archivos TTL, describe las tripletas añadidas/eliminadas -->
```turtle
# Ejemplo de tripletas nuevas:
# :NuevoIndividuo rdf:type :ClaseExistente .
```

## Métricas (si aplica)
| Métrica | Antes | Después |
|---|---|---|
| SBERT Coseno | — | — |
| BERTScore | — | — |
| Jaccard | — | — |
| Tasa de aciertos | — | — |

## Issue relacionado
Closes #<!-- número del issue -->
