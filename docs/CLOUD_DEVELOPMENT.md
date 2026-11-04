# Development in the managed Linux environment

Python 3.12 remains the repository's tested baseline. This image's managed Python 3.12 build uses Tk 9 without usable Persian font support: even an available Persian font measured zero width. The system Python 3.13/Tk 8.6 build correctly exposes installed fonts and renders the interface. This is a worker-runtime distinction, not a new requirement for Windows users.

The prepared GUI environment is outside the checkout at `/workspace/.lv-panel-environment/gui-venv`. To reproduce it on this image:

```bash
cd /workspace/LV_Panel-Assistant
uv venv --python /usr/bin/python3.13 /workspace/.lv-panel-environment/gui-venv
uv pip install --system-certs --python /workspace/.lv-panel-environment/gui-venv/bin/python -r requirements-dev.txt
```

Create the environment only if absent; refresh dependencies with the second command. Preserve inherited proxy/CA settings. No application credentials are needed for offline calculations.

After starting an available X display, use the same display for the application and tests:

```bash
DISPLAY=:99 /workspace/.lv-panel-environment/gui-venv/bin/python -B main.py
DISPLAY=:99 /workspace/.lv-panel-environment/gui-venv/bin/python -B -m pytest -q -k 'not test_html_to_pdf_roundtrip'
```

The managed environment's saved startup instructions contain the virtual-display readiness procedure. Use an existing desktop session's `DISPLAY` when interacting visually. Live processes must restart in new tasks. Use the existing isolated checkout; do not create worktrees unless explicitly requested.

Both Python 3.12 and this Python 3.13/Tk 8.6 environment pass the recorded regression suite. PDF export remains a separate failed Chromium runtime check. Windows packaging acceptance must be performed on Windows. See [the audit remediation record](REPORT_REMEDIATION.md) for scope, evidence and remaining manufacturer-data requirements.
