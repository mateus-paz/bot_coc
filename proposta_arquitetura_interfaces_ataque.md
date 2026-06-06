# Proposta de Arquitetura: Interfaces para Vila e Estrategia de Ataque

## Objetivo

Separar melhor a logica do bot em contratos claros, permitindo:

- identificar tipos de vila ou centros de vila
- escolher estrategias de ataque diferentes
- manter a configuracao do ataque fora da implementacao
- evoluir o projeto sem concentrar tudo em um unico servico

## Pergunta central

O Python permite algo equivalente a interfaces?

Sim. As abordagens mais comuns sao:

- classes abstratas com `abc.ABC`
- `Protocol` com `typing`
- composicao entre servicos

Para este projeto, a melhor opcao inicial e usar classes abstratas para os contratos principais.

## Modelo conceitual

Separar o problema em 3 partes:

1. classificacao da vila
2. escolha da estrategia de ataque
3. execucao do plano configurado

Ou seja:

- o codigo decide *como* executar
- os dados externos definem *o que* executar

## Contratos sugeridos

### `ClassificadorVila`

Responsavel por analisar a tela e identificar o tipo de vila, centro ou categoria da base.

Exemplo de responsabilidade:

- detectar o centro da vila
- detectar layout conhecido
- classificar por tipo

Exemplo de contrato:

```python
from abc import ABC, abstractmethod

class ClassificadorVila(ABC):
    @abstractmethod
    def classificar(self, contexto) -> str:
        """Retorna um identificador do tipo de vila."""
```

### `EstrategiaAtaque`

Responsavel por dizer se suporta um tipo de vila e como executar o ataque.

Exemplo de contrato:

```python
from abc import ABC, abstractmethod

class EstrategiaAtaque(ABC):
    @abstractmethod
    def suporta(self, tipo_vila: str) -> bool:
        """Indica se a estrategia atende esse tipo de vila."""

    @abstractmethod
    def executar(self, contexto, plano) -> None:
        """Executa o ataque usando um plano externo."""
```

## Ideia principal

A implementacao da estrategia nao deve guardar tudo "hardcoded" dentro do codigo.

O ideal e separar:

- `estrategia`: regra de execucao
- `plano`: pontos, tropas, ordem e parametros
- `classificacao`: como descobrir qual ataque aplicar

## Fluxo desejado

O bot faria algo assim:

1. captura a tela
2. classifica a vila
3. escolhe a estrategia compativel
4. carrega o plano correspondente
5. executa o ataque

## Exemplo de uso conceitual

```python
tipo_vila = classificador.classificar(contexto)
estrategia = seletor.encontrar_para(tipo_vila)
plano = repositorio_planos.buscar_por_tipo(tipo_vila)
estrategia.executar(contexto, plano)
```

## Beneficios

- menos acoplamento
- mais facilidade para trocar ataques
- mais facilidade para testar
- mais clareza sobre onde fica cada responsabilidade
- melhor caminho para migrar configuracoes para banco depois

## Organizacao sugerida de pastas

```text
domain/
  classificador_vila.py
  estrategia_ataque.py

services/
  seletor_estrategia.py
  executor_ataque.py

strategies/
  ataque_cv13.py
  ataque_cv17.py
  ataque_lateral.py

repositories/
  repositorio_planos.py
```

## Como isso conversa com SQLite no futuro

Essa arquitetura combina muito bem com banco relacional.

O banco pode armazenar:

- perfis de ataque
- planos de deploy
- coordenadas
- pontos por tipo de vila
- historico de execucao

O codigo da estrategia continua limpo, enquanto os dados mudam sem precisar editar implementacao.

## Recomendacao pratica

Fazer em etapas:

### Etapa 1

Introduzir os contratos:

- `ClassificadorVila`
- `EstrategiaAtaque`

### Etapa 2

Extrair uma estrategia concreta do codigo atual.

Por exemplo:

- `EstrategiaAtaqueRoteirizada`
- `EstrategiaAtaqueDeployAutomatico`

### Etapa 3

Criar um seletor de estrategia.

### Etapa 4

Mover os planos de ataque para fonte externa:

- primeiro YAML simplificado
- depois SQLite

## Observacao final

O ideal aqui nao e usar "interface" apenas por usar.

O valor real vem de separar claramente:

- reconhecimento da vila
- selecao da estrategia
- configuracao do ataque
- execucao operacional

Se isso for feito bem, o projeto fica mais simples de manter, mesmo crescendo.
