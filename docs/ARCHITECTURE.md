# Application architecture

The application remains a single Python desktop program. Publication cleanup does not change its calculation algorithms or move public imports.

| Responsibility | Modules |
| --- | --- |
| Entry points | `main.py`, `wizard_app.py` |
| Forms and orchestration | `lv_assist/gui.py` |
| Desktop shell and direction | `precision_ui.py`, `ui_direction.py`, `ui_theme.py` |
| Typed inputs and outputs | `models.py`, `scenario_dialog.py` |
| Electrical calculation | `engine.py`, `busbar.py`, `field_wizard_engine.py` |
| Additional checks | `scenario_rules.py`, `pe_spd_engine.py`, `core_verification.py` |
| Catalog and provenance | `catalog.py`, `catalog_provenance.py` |
| Unverified extraction library | `data_validator.py`, `reference_library.py` |
| Search | `catalog_smart_search.py`, `web_catalog.py`, `gui_helpers.py` |
| Summary and workflow state | `summary_workflow.py` |
| Reporting and drawings | `exporters.py`, `outputs.py`, `layout.py`, `gui_output_bridge.py`, SVG generators |
| Commercial calculations | `bom.py`, `commercial.py` |
| Resources and configuration | `paths.py`, `i18n.py`, `translations/`, `data/`, `templates/` |

## Data flow

Forms produce Pydantic project and feeder models. The engine reads the SQLite catalog and returns feeder outputs, a panel summary and validation findings. The UI renders those outputs and marks them stale when inputs change. Exporters consume calculation results; they do not replace the engine.

Automation inputs can contribute to the control-power calculation. Scenario checks are preliminary and preserve missing-data findings. Summary fields separate design current from the selected device's rated current.

## Persistence

JSON seed files are versioned. `migrate_to_sqlite.py` creates the local database and calls the retained catalog-extension scripts. Those scripts are runtime migration dependencies, so they remain under `scripts/`. Existing user data and prices are handled by the catalog migration helpers.

Mutable SQLite files, local `config.json`, generated reports, executables and build intermediates are excluded from Git. The compiled distribution keeps editable data beside the EXE.

The [reference-library importer](REFERENCE_LIBRARY.md) stores extracted tables in a separate local SQLite database. Its Pydantic models, source hashes and quarantine records support review; raw imports do not replace the engine catalog or standards registry and are excluded from release data.

## Boundaries to preserve

- UI code owns Tk widgets; background network workers deliver results through the main-thread queue.
- Engine outputs remain independent of display language and layout.
- Search similarity is not proof of technical interchangeability.
- Unknown device fields and incomplete scenario evidence are not manufactured or approved automatically.
- DXF and EPLAN macro/import-package modules remain disabled.

`gui.py` is still the principal orchestration module. Splitting it further would be a separate refactor with regression coverage; this publication does not claim that work has been done.
