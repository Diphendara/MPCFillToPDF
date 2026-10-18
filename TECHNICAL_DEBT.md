# 🔧 MEJORAS FUTURAS - MPCFillToPDF

> **Fecha de análisis:** 2026-10-18  
> **Estado:** Pendiente de implementación  
> **Prioridad general:** Media-Baja (el proyecto funciona correctamente)

---

## 📊 **RESUMEN EJECUTIVO**

El proyecto está **bien estructurado** (8/10) con buenas prácticas generales. Las mejoras identificadas son principalmente de **refactoring**, **testing** y **documentación**.

**Total de tareas identificadas:** 10  
**Esfuerzo estimado total:** 3-5 días de desarrollo

---

## 🔴 **PRIORIDAD ALTA**

### **1. Agregar tests para `tcg_batches.py`**

**Problema:**  
El módulo `src/tcg_batches.py` contiene lógica crítica de batches (Riftbound, Lorcana, Yu-Gi-Oh) pero **no tiene tests**.

**Impacto:**  
- Riesgo de regresiones al modificar la lógica de batches
- Dificulta refactoring seguro

**Solución propuesta:**
```python
# tests/test_tcg_batches.py
def test_riftbound_batch_adapter_filters_sideboard():
    """Test that sideboard cards are excluded when include_sideboard=False."""
    # ...

def test_riftbound_batch_adapter_includes_sideboard():
    """Test that sideboard cards are included when include_sideboard=True."""
    # ...
```

**Esfuerzo:** 2-3 horas  
**Archivos afectados:** `tests/test_tcg_batches.py` (nuevo)

---

### **2. Reducir complejidad ciclomática de funciones críticas**

**Problema:**  
10 funciones exceden el límite de complejidad ciclomática (10):

| Función | Complejidad | Archivo |
|---------|-------------|---------|
| `main()` | 38 | `cli/main.py` |
| `_update_preflight()` | 22 | `gui/main.py` |
| `_open_url_dialog()` | 19 | `gui/decks_tab.py` |
| `_render_mtg_rows()` | 15 | `gui/decks_tab.py` |
| `_render_rb_rows()` | 13 | `gui/decks_tab.py` |
| `_on_drop_xmls()` | 12 | `gui/main.py` |
| `_render_op_rows()` | 12 | `gui/decks_tab.py` |
| `_do_import()` | 11 | `gui/universal_import.py` |
| `_pick_xmls()` | 11 | `gui/main.py` |
| `_render_ygo_rows()` | 11 | `gui/decks_tab.py` |

**Impacto:**  
- Dificulta lectura y mantenimiento
- Aumenta riesgo de bugs
- Dificulta testing

**Solución propuesta:**
- **Refactorizar `main()`** dividiendo en funciones más pequeñas:
  ```python
  def main() -> None:
      args = _parse_args()
      _setup_logging(args.verbose)
      config = _load_config(args)
      plan = _build_execution_plan(config)
      _execute_plan(plan)
  ```

- **Extraer lógica de renderizado** en `decks_tab.py` a métodos auxiliares
- **Simplificar `_update_preflight`** dividiendo validaciones

**Esfuerzo:** 4-6 horas  
**Archivos afectados:** `cli/main.py`, `gui/main.py`, `gui/decks_tab.py`

---

## 🟡 **PRIORIDAD MEDIA**

### **3. Reemplazar excepciones genéricas por específicas**

**Problema:**  
35 usos de `except Exception:` que pueden ocultar bugs.

**Ejemplos críticos:**
```python
# src/text_importer.py:138
except Exception:
    return {}  # ¿Qué errores se están ocultando?

# gui/decks_tab.py:351
except Exception:
    pass  # ¿Por qué se ignora?
```

**Solución propuesta:**
```python
# ❌ ANTES
except Exception:
    pass

# ✅ DESPUÉS
except (requests.RequestException, json.JSONDecodeError) as exc:
    _log.warning("Failed to fetch data: %s", exc)
    return {}
```

**Archivos afectados:**
- `src/downloader.py` (9 casos)
- `src/scryfall.py` (10 casos)
- `gui/decks_tab.py` (14 casos)
- `gui/main.py` (16 casos)
- Otros: `src/lorcana_scraper.py`, `src/precheck.py`, `src/text_importer.py`

**Esfuerzo:** 2-3 horas  
**Beneficio:** Mejor debugging y manejo de errores

---

### **4. Eliminar duplicación de código en `decks_tab.py`**

**Problema:**  
La función `_make_qty_updater` aparece **15 veces** duplicada en `decks_tab.py`.

**Impacto:**  
- Cambios globales requieren editar 15 lugares
- Riesgo de inconsistencias
- Dificulta mantenimiento

**Solución propuesta:**
```python
# Crear clase base
class TCGRowRenderer:
    """Base class for TCG row renderers with shared logic."""
    
    def _make_qty_updater(self, card, label):
        """Shared quantity updater logic."""
        # ...
    
    def _render_card_row(self, card, parent):
        """Shared card row rendering."""
        # ...

# Renderers específicos heredan
class RiftboundRowRenderer(TCGRowRenderer):
    def _render_rb_specific(self):
        # Lógica específica de Riftbound
```

**Esfuerzo:** 3-4 horas  
**Archivos afectados:** `gui/decks_tab.py` (refactor mayor)

---

### **5. Refactorizar función `main()` en `cli/main.py`**

**Problema:**  
La función `main()` tiene complejidad 38 y probablemente >200 líneas.

**Solución propuesta:**
```python
def main() -> None:
    """CLI entry point."""
    args = _parse_args()
    _setup_logging(args.verbose)
    
    try:
        config = _load_config(args)
        plan = _build_execution_plan(config)
        _execute_plan(plan)
    except Exception as exc:
        _handle_error(exc)
        sys.exit(1)

def _parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    # ...

def _load_config(args) -> Config:
    """Load and validate configuration."""
    # ...

def _build_execution_plan(config) -> ExecutionPlan:
    """Build execution plan from config."""
    # ...

def _execute_plan(plan) -> None:
    """Execute the plan."""
    # ...
```

**Esfuerzo:** 2-3 horas  
**Archivos afectados:** `cli/main.py`

---

## 🟢 **PRIORIDAD BAJA**

### **6. Agregar docstrings faltantes**

**Problema:**  
94 funciones/clases sin docstrings (reglas D101, D102 de ruff).

**Ejemplos:**
```python
# ❌ SIN DOCSTRING
def _fetch_dotgg_cards_db() -> dict[str, dict]:
    # ...

# ✅ CON DOCSTRING
def _fetch_dotgg_cards_db() -> dict[str, dict]:
    """Fetch all Riftbound cards from dotgg API.
    
    Returns:
        Dictionary mapping card_id to card data.
        Returns empty dict on failure.
    """
    # ...
```

**Esfuerzo:** 2-3 horas  
**Beneficio:** Mejor documentación y IDE support

---

### **7. Extraer magic numbers a constantes**

**Problema:**  
Valores hardcodeados sin constantes descriptivas.

**Ejemplos:**
```python
# gui/decks_tab.py
width=4   # ¿Por qué 4?
width=25  # ¿Por qué 25?
width=10  # ¿Por qué 10?
```

**Solución propuesta:**
```python
# src/constants.py
class UIConstants:
    """UI-related constants."""
    SPINBOX_WIDTH = 4
    BUTTON_WIDTH = 10
    LABEL_WIDTH = 25
    ICON_SIZE = 16

# Uso
width=UIConstants.SPINBOX_WIDTH
```

**Esfuerzo:** 1-2 horas  
**Archivos afectados:** `src/constants.py`, `gui/decks_tab.py`, `gui/widgets.py`

---

### **8. Centralizar URLs de APIs**

**Problema:**  
URLs de APIs dispersas por el código.

**Ejemplos actuales:**
```python
# src/deck_importer.py
_MOXFIELD_API = "https://api2.moxfield.com/v3/decks/all/{deck_id}"
_ARCHIDEKT_API = "https://archidekt.com/api/decks/{deck_id}/"

# src/lorcana_scraper.py
_DOTGG_DECK_API = "https://api.dotgg.gg/cgfw/getdeck?game=lorcana&slug={slug}"
```

**Solución propuesta:**
```python
# src/api_endpoints.py
"""Centralized API endpoints for external services."""

class MTGEndpoints:
    MOXFIELD = "https://api2.moxfield.com/v3/decks/all/{deck_id}"
    ARCHIDEKT = "https://archidekt.com/api/decks/{deck_id}/"
    DECKSTATS = "https://deckstats.net/api.php"
    TAPPEDOUT = "https://tappedout.net/mtg-decks/{slug}/?fmt=txt"

class LorcanaEndpoints:
    DOTGG_DECK = "https://api.dotgg.gg/cgfw/getdeck?game=lorcana&slug={slug}"
    DOTGG_CARDS = "https://api.dotgg.gg/cgfw/getcards?game=lorcana&mode=indexed"
    DOTGG_IMAGE = "https://static.dotgg.gg/lorcana/cards/{card_id}.webp"
    INKDECKS = "https://inkdecks.com/api/lorcana/decks/{deck_id}"

# Uso
from src.api_endpoints import MTGEndpoints
url = MTGEndpoints.MOXFIELD.format(deck_id=deck_id)
```

**Esfuerzo:** 1-2 horas  
**Beneficio:** Facilita cambios si las APIs cambian

---

### **9. Completar type hints faltantes**

**Problema:**  
137 funciones sin type hints completos (regla ANN de ruff).

**Ejemplos:**
```python
# ❌ FALTA RETURN TYPE
def _build_ui(self):
    # ...

# ✅ CORRECTO
def _build_ui(self) -> None:
    # ...
```

**Esfuerzo:** 2-3 horas  
**Beneficio:** Mejor type safety y IDE support

---

### **10. Agregar tests para módulos sin cobertura**

**Módulos sin tests:**
- `cache_key.py` (baja prioridad - simple)
- `cancellation.py` (baja prioridad - simple)
- `constants.py` (baja prioridad - simple)
- `execution_plan.py` (media prioridad)
- `http_client.py` (media prioridad)
- `print_run.py` (media prioridad)

**Esfuerzo:** 3-4 horas  
**Beneficio:** Mayor confianza en refactoring

---

## 📋 **PLAN DE IMPLEMENTACIÓN SUGERIDO**

### **Sprint 1 (1 día) - Fundamentos**
- ✅ Agregar tests para `tcg_batches.py` (2-3h)
- ✅ Reemplazar excepciones genéricas (2-3h)
- ✅ Agregar docstrings a funciones públicas (2-3h)

### **Sprint 2 (1 día) - Refactoring**
- ✅ Refactorizar `main()` en `cli/main.py` (2-3h)
- ✅ Extraer constantes de UI (1-2h)
- ✅ Centralizar URLs de APIs (1-2h)
- ✅ Completar type hints (2-3h)

### **Sprint 3 (2 días) - Refactoring mayor**
- ✅ Reducir complejidad de funciones críticas (4-6h)
- ✅ Eliminar duplicación en `decks_tab.py` (3-4h)
- ✅ Agregar tests para módulos sin cobertura (3-4h)

---

## 🎯 **MÉTRICAS DE ÉXITO**

Al completar estas mejoras, el proyecto debería tener:

- ✅ **0 funciones** con complejidad ciclomática > 10
- ✅ **100% de módulos** con tests (excepto `__init__.py`, `constants.py`)
- ✅ **0 excepciones genéricas** (`except Exception:`)
- ✅ **100% de funciones públicas** con docstrings
- ✅ **100% de type hints** completos
- ✅ **0 duplicación** de código en renderers

---

## 📝 **NOTAS ADICIONALES**

### **Herramientas recomendadas:**
- **radon** - Para medir complejidad ciclomática
- **mypy** - Para verificar type hints
- **pytest-cov** - Para medir cobertura de tests
- **pylint** - Análisis estático adicional (complementa ruff)

### **Comandos útiles:**
```bash
# Medir complejidad
python3 -m ruff check --select C901 src/ gui/ cli/

# Verificar type hints
python3 -m mypy src/ gui/ cli/

# Medir cobertura
python3 -m pytest --cov=src --cov=gui --cov-report=html

# Análisis completo
python3 -m ruff check --select ALL src/ gui/ cli/
```

---

## ✅ **CHECKLIST DE IMPLEMENTACIÓN**

- [ ] Tests para `tcg_batches.py`
- [ ] Reducir complejidad de `main()` (cli)
- [ ] Reducir complejidad de `_update_preflight()`
- [ ] Reducir complejidad de `_open_url_dialog()`
- [ ] Reducir complejidad de renderers en `decks_tab.py`
- [ ] Reemplazar excepciones genéricas
- [ ] Eliminar duplicación en `decks_tab.py`
- [ ] Agregar docstrings faltantes
- [ ] Extraer magic numbers a constantes
- [ ] Centralizar URLs de APIs
- [ ] Completar type hints
- [ ] Tests para `execution_plan.py`
- [ ] Tests para `http_client.py`
- [ ] Tests para `print_run.py`

---

**Última actualización:** 2026-10-18  
**Autor:** Análisis automático de código  
**Estado:** 📋 Pendiente de implementación
