# Contributing

Use Python 3.12. Install `src/requirements.txt` in a virtual environment and run:

```sh
python -m unittest discover -s tests -t . -v
python -m compileall -q src tests
```

Create a branch for one feature and open a pull request into `main`. Separate fishing perception, fishing control, and UI work when using multiple coding tools. Avoid concurrent edits to `app.py`; integrate through small panel modules.

Explain the behavior change, tests run, and Windows/gameplay checks still needed. Never commit `data/`, models, logs, credentials or gameplay recordings. Share a cropped, reviewed sample explicitly when reporting recognition problems.

Windows testing must check Preview sends no keys, F8 releases held inputs, focus loss releases inputs, and existing Repeat/Hold/Auto modes still work. CI covers pure logic and synthetic images; it cannot validate the game or Windows overlay.

See RIGHTS.md before contributing; a general open-source license has not yet been selected.
