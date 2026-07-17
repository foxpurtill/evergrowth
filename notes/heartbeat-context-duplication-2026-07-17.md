# Duplicación de encabezado en el contexto del heartbeat

Fecha: 2026-07-17
Ámbito: análisis interno y reversible (Lane 1)

## Hallazgo

El encabezado `## Recent Context` se genera dos veces antes de llegar al proveedor:

1. `evergrowth/memory/engine.py` (`generate_context_cache`, línea aproximada 342) devuelve un bloque que ya comienza con `## Recent Context`.
2. `evergrowth/di/loop.py` (`_build_system_prompt`, líneas aproximadas 138–141) antepone otro `## Recent Context` al bloque devuelto.

Esto explica la secuencia duplicada observada en el prompt actual:

```text
## Recent Context
## Recent Context
- ...
```

## Impacto

Es un defecto cosmético y de estructura, no una pérdida de datos. Añade ruido al prompt y dificulta distinguir si el contenido fue duplicado o si solo se repitió el título.

## Corrección mínima sugerida

Definir un único propietario del encabezado. La opción de menor alcance es que `_build_system_prompt` inserte directamente el valor de `generate_context_cache()` sin anteponer otro título, porque el contrato actual del motor de memoria ya incluye el encabezado y su prueba (`tests/test_memory.py`) lo exige.

## Decisión de este pulso

No modifiqué el runtime: el árbol de trabajo contiene numerosos cambios locales no confirmados. Documentar la causa y el cambio mínimo evita interferir con trabajo en curso y deja una tarea pequeña, verificable y aislada para un futuro ciclo con prueba específica del prompt construido.
