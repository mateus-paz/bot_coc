"""Ponto de entrada do app desktop instalavel."""

from __future__ import annotations

from app.bootstrap import bootstrap_desktop_app


if __name__ == '__main__':
    raise SystemExit(bootstrap_desktop_app())
