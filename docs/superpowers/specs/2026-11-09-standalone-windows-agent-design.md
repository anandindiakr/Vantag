# Standalone Windows Edge Agent Package

## Approved outcome

Windows customers download an account-specific ZIP, extract it, and run `VantagAgent.exe`. The package includes its own Python runtime and required runtime libraries. Customers must not need to install Python, run `pip`, open a command prompt, or have administrator rights.

## Package architecture

- Build a reproducible PyInstaller onedir application using the package entry point, not the relative-import module as a script.
- Include the native Python runtime, OpenCV, ONNX Runtime, Ultralytics/PyTorch runtime dependencies, MediaPipe, tray-icon dependencies, application assets, and required core model assets.
- Resolve bundled assets through the executable's runtime directory. Resolve the account-specific `config.json` beside `VantagAgent.exe`, while preserving `%APPDATA%/Vantag` for runtime state, logs, and the incident outbox.
- Bundle the verified native YOLO26 ONNX graph and validate its `[1, 300, 6]` architecture before packaging. Bundle the hand-landmark asset and available core pose/product-counter weights so normal first use does not depend on PyPI or a model export.
- Keep optional VisionAI embedding/index dependencies outside this package. Their existing fail-open status must remain honest; this work does not claim to enable VisionAI.
- Preserve the Linux source package and existing agent behavior. Do not change detection logic beyond what is required to locate packaged resources.

## Download and deployment

- Keep the authenticated `/api/agent/download` account provisioning and regional backend/MQTT configuration behavior.
- For Windows, add the tenant's `config.json`, version information, and concise run instructions to a copy of the prebuilt standalone archive. Stream the resulting file without loading the full archive into memory, and remove temporary files after the response.
- Store the large prebuilt archive in a persistent VPS artifact directory outside the Git working tree. Do not commit generated executables, runtime libraries, credentials, or customer configuration to GitHub.
- Commit the reproducible build script, packaging configuration, focused runtime fixes, tests, and download-serving changes. Preserve the artifact across backend rebuilds and deployments.
- Increase the agent version so users can distinguish the standalone package from v1.11.3.

## Verification and acceptance

- Automated tests cover executable-directory configuration lookup, packaged resource resolution, archive assembly, per-tenant configuration isolation, and temporary-file cleanup.
- Build the actual Windows package and measure compressed and extracted sizes.
- Run the packaged executable in a smoke-test mode with isolated application data and no customer credentials. Verify critical imports, native YOLO26 ONNX loading, output shape `[1, 300, 6]`, and one real inference.
- Verify that the smoke test does not invoke a system Python installation or `pip`.
- Deploy the backend, confirm container health/readiness, and verify the VPS serves the new standalone version. An authenticated end-to-end customer download requires an authorized test account; without one, report that limitation rather than claiming it was tested.
- A clean-PC result cannot be claimed from a development machine. The local packaged smoke test must use an isolated runtime environment, and the first customer PC remains a required field validation.

## Failure behavior

- Missing or corrupt packaged core models must produce an explicit error/status; the package must not silently report YOLO26 when another architecture is loaded.
- If the standalone artifact is unavailable, the download endpoint must return a clear server error rather than silently serving the old Python-dependent ZIP.
- Existing incidents, cached state, and tenant credentials must not be included in build or smoke-test artifacts.
