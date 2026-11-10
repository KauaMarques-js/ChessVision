# ChessVision Lab — arquitetura e critérios de aceite

**Objetivo:** prova de conceito acadêmica de captura de posição no navegador e análise local com motor UCI. **Não** automatiza cliques, não usa API externa, não captura senhas nem cookies.

## Fluxo de dados

```text
Chess.com (DOM visível)
   │  board_reader.js: peças, casas, orientação, SAN (se disponível)
   ▼
Extensão Chrome/Edge Manifest V3
   │  background.js: JSON via HTTP 127.0.0.1:8765
   ▼
Processo Python: LocalHandler / AnalysisState
   │  tracker.py: FEN, histórico SAN validado, transição legal ou aviso
   ▼
engine_worker: python-chess + UCI Stockfish 19
   │  principal variation + depth + avaliação
   ▼
Interface Tkinter: posição, 3 linhas, análise incremental e diagnóstico
```

## Invariantes

1. A localização de cada peça é uma coordenada lógica absoluta (a1 a h8); girar o tabuleiro **não** pode alterar o FEN.
2. Um histórico só é aceito se sua reprodução legal produzir exatamente a configuração de peças observada.
3. Mesmas peças em duas capturas **não** significam o mesmo estado: turno, roque, en passant, contadores e três repetições importam.
4. Se um tabuleiro for visto pela primeira vez no meio da partida sem histórico, não calcular variantes até confirmação de turno (estado marcado *estimado*).
5. Lances recomendados somente são exibidos se a revisão da análise corresponde à revisão atual do tabuleiro; linhas antigas não podem aparecer após um movimento.
6. Comunicações ficam em localhost. O cliente só envia posição e metadados do tabuleiro; não acessa senhas, cookies ou nomes de conta.
7. O motor não tem limite artificial de Elo, mas a profundidade **alcançada** é exibida. Profundidade configurada não é garantia de execução até esse limite.

## Degradação controlada

| Falha | Comportamento esperado |
|---|---|
| Sem motor | Mensagem de motor ausente; manual de instalação e diagnóstico |
| Navegador fechado ou extensão parada | Última atualização indicada como antiga após 8 segundos |
| Tabuleiro durante animação | Snapshot com peças duplicadas ou reis ausentes é descartado |
| Histórico SAN incompleto | Sincronização por 1 ou 2 meios-lances legais a partir do estado conhecido |
| Partida iniciada no meio | Estado incerto, análise suspensa e aviso visível |
| Posição alterada enquanto o motor pensa | Pesquisa anterior é interrompida e o resultado fica obsoleto |
| Análise muito demorada | Linhas aparecem progressivamente conforme o motor aprofunda |

## Critérios de aceite local

- [ ] `DIAGNOSTICAR_WINDOWS.bat`: testes Python aprovados, motor id `Stockfish 19`, três variantes legais, HTTP de ponta a ponta aprovado.
- [ ] `tests/test_reader.js`: testes DOM de posição inicial, e4, inversão, heartbeat, turno do FEN, animação e king missing.
- [ ] `tests/test_background.js`: verificação da origem e envio para localhost.
- [ ] **Teste manual 1:** abrir Chrome/Edge, extensão instalada e programa ativo; iniciar posição contra bot, confirmar FEN inicial idêntico ao tabuleiro.
- [ ] **Teste manual 2:** fazer `e4`, `...e5`, `Nf3`; confirmar a mudança da vez e a seta atualizada após cada lance.
- [ ] **Teste manual 3:** virar o tabuleiro; a posição lógica não muda, somente a orientação na janela.
- [ ] **Teste manual 4:** fechar a aba; a comunicação é marcada como desatualizada após alguns segundos.
- [ ] **Teste manual 5:** abrir o programa com Stockfish ausente; a interface não deve travar e o erro aparece claramente.

**Não validados neste ambiente:** downloads do GitHub, execução do Stockfish 19 em Windows, GUI nativa do Windows e sessão real do Chess.com. O diagnóstico deve ser executado no computador-alvo.
