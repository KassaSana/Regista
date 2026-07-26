"""Allow ``python -m regista`` to use the same composition root as the CLI."""

from regista.cli import main

raise SystemExit(main())
