# Development instructions

Read README.md and docs/FISHING.md before changing behavior. Keep internal `src/orcpresser` and `data/` paths compatible with existing installations. Do not overwrite user fishing notes.

All input must pass through the existing WinIO output guard. Preview must not emit input. Focus loss, stop, stale capture and watchdog must release held keys. Workers capture only; the main thread owns decisions and input.

Use pure logic tests for state changes and synthetic images for perception. Run `python -m unittest discover -s tests -t . -v`. Do not claim Windows or live-game testing from Linux. Never add user data, recordings, models or credentials to the repository.

One feature per branch/PR. Avoid unrelated formatting changes in app.py. Document experimental behavior and unverified game cues.
