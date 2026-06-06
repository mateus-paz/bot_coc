# Proposta de Evolucao: SQLite e Interface Configuravel

## Objetivo

Reduzir a dependencia de configuracoes extensas em `yaml` e evoluir o projeto para um modelo mais facil de editar, visualizar e manter.

## Direcao recomendada

Usar:

- `SQLite` como banco local
- backend Python
- interface web local simples

Essa combinacao permite manter o projeto leve, sem servidor externo, com configuracao visual e historico persistido.

## O que faz sentido migrar do YAML para banco

Primeiro:

- perfis de ataque
- tropas por perfil
- pontos de deploy
- linhas/faixas de scatter
- regioes da tela (`ROI`)
- assets cadastrados

Depois:

- historico de execucoes
- cliques realizados por execucao
- screenshots e checkpoints associados

## Modelo relacional inicial sugerido

### `perfis_ataque`

- `id`
- `nome`
- `modo`
- `ativo`

### `acoes_ataque`

- `id`
- `perfil_id`
- `ordem`
- `tipo`
- `nome`
- `parametros_json`

### `tropas`

- `id`
- `perfil_id`
- `nome`
- `x`
- `y`
- `tecla`
- `batch_clicks`

### `regioes_tela`

- `id`
- `perfil_id`
- `tipo`
- `x`
- `y`
- `w`
- `h`

### `execucoes`

- `id`
- `iniciado_em`
- `perfil_id`
- `status`

### `cliques_execucao`

- `id`
- `execucao_id`
- `tipo`
- `x`
- `y`
- `timestamp`
- `tropa_nome`

## O que isso habilita

- cadastrar e editar perfis sem mexer no YAML
- visualizar coordenadas e ROIs
- comparar ataques por perfil
- registrar onde o bot clicou
- montar interface para clicar na screenshot e salvar pontos
- acompanhar execucoes e diagnosticar estrategia

## Stack recomendada

- `SQLite`
- `SQLAlchemy`
- `FastAPI` ou `Flask`
- frontend local simples em HTML + JavaScript

## Estrategia de migracao

### Fase 1

Manter o `config.yaml` apenas para configuracoes globais:

- caminho do banco
- titulo da janela
- diretorios base
- flags de runtime

### Fase 2

Mover para o banco:

- perfis de deploy
- tropas
- pontos
- acoes roteirizadas

### Fase 3

Persistir historico:

- execucoes
- cliques
- checkpoints

### Fase 4

Criar interface local para:

- editar perfis
- desenhar ROIs
- visualizar screenshots
- clicar na imagem para salvar coordenadas

## Recomendacao pratica

Implementar primeiro:

1. base SQLite e schema inicial
2. migracao dos perfis de deploy para banco
3. leitura das estrategias pelo bot a partir do banco

So depois partir para interface configuravel.

## Observacao

Nao e necessario remover o YAML de uma vez. O melhor caminho e reduzir o YAML ao minimo e transferir gradualmente os dados operacionais para o banco.
