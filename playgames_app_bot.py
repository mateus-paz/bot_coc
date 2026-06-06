"""Wrapper de compatibilidade para o comando antigo do bot."""

from tasks.executar_fluxo import executar_fluxo


if __name__ == '__main__':
    raise SystemExit(executar_fluxo())
