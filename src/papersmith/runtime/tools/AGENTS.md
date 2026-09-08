# PaperSmith Runtime Tools

Development-only guidance. The installed product tools live in `papersmith/`
and are packaged by `pyproject.toml` for the installer. Tools are deterministic
control programs: state, hashing, source/material/review/conversion/acceptance
contracts and backend discovery. They never embed credentials or provider
sessions and never grant the model a shell or Docker control surface.
