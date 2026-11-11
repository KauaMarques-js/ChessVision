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
Interface Tkinter: posição, até 5 linhas, seleção manual no F11 e diagnóstico
```

## Invariantes

Fonte adicional: `ImageGrab` captura uma região do monitor principal a cada 0,7 s;
`screen_reader.py` compara as casas com amostras calibradas na posição inicial.
Duas leituras iguais passam ao mesmo `AnalysisState.receive` / `BoardTracker`.
Enquanto a tela está ativa, a extensão é ignorada. Leitura incerta invalida a
revisão, limpa as sugestões e suspende o motor até uma leitura estável.
Capturas completas ficam somente em memória. Referências normalizadas de
peças são persistidas em `.reader_templates.json`, com formato versionado,
validação de tamanho e atualização atômica. O arquivo é local e excluído do Git
e do payload Go por ser oculto. Não há automação de lances.
Um tema desconhecido exige calibração; regiões de outro tamanho/orientação
podem reutilizar referências reconhecíveis via `for_region`.

Recuperação: leitura incerta mantém a thread ativa e preserva a calibração.
Snapshots sem transição legal não substituem o histórico confiável da captura;
ficam pendentes até a imagem se recuperar ou uma confirmação manual de turno.
A representação das peças separa contraste claro/escuro da cor do fundo para
reduzir falhas com destaques de último lance. Erros indicam a casa ambígua.
Recapturar a prévia obtém uma nova imagem com as janelas do programa ocultas;
repetir leitura em andamento reutiliza o leitor e o histórico, sem recalibrar.

Interface: painel 880×550 em três abas; F11 440×510 com barra inferior. Os
dois tabuleiros de análise continuam em 440×440. A prévia de calibração usa
280 px apenas para exibição. Ao iniciar a captura, o compacto é colocado fora
da região de origem ou minimizado se não há espaço, mantendo o processamento.

Identificação da região: modo Manual (arraste) ou Automático (`detect_boards`).
O localizador cruza oito segmentos horizontais e verticais de cores alternadas,
valida os cantos das 64 casas e retorna limites em pixels da imagem original.
A busca roda fora da thread Tk; uma geração invalida resultados após Parar.
Ambos os modos abrem uma prévia com grade, ajuste numérico dos limites e início
explícito da leitura. Várias regiões podem ser percorridas antes da calibração.
Sem grade completa, o automático continua aguardando em uma thread com espera
interruptível. Duas observações iguais publicam `search_ready`; uma geração
invalida resultados de buscas canceladas. As áreas do próprio programa são
excluídas da imagem de detecção. A janela é minimizada durante a procura.

Retomada: referências salvas permitem classificar as peças sem reaprender a
posição inicial. A confirmação mostra imagem e tabuleiro reconhecido. O método
`confirm_screen_position` preserva histórico legal compatível ou exige turno e
roques explícitos para uma posição reconstruída. Pesquisa do motor fica suspensa
até a confirmação; candidatos da busca nunca alimentam o tracker diretamente.
Falhas persistentes, inclusive posições legíveis mas fora do histórico, emitem
`relocalize` e reiniciam a busca quando a recuperação automática está habilitada.

Evolução solicitada: cinco opções manuais no modo F11, ranking preservado até
nova escolha, sem depender da qualidade do último lance. O motor solicita
MultiPV=5; menos lances legais podem resultar em menos variantes. A alternância
continua opcional no painel e é desativada ao entrar no modo compacto.

Perfil Humanizado (treino): usa `Skill Level` de 0 a 19, padrão 12, com
`UCI_LimitStrength=false` (não mistura dois controles nativos de força).
O limite de tempo efetivo é de até 2 segundos; respeita limites menores.
O worker lê `analysis.wait().move` depois do fluxo MultiPV, valida a legalidade
e publica `human_line` com revisão e FEN. A UI nunca usa a PV 1 como substituta
enquanto aguarda a sugestão. Se o lance não aparece entre as cinco variantes,
avaliação e continuação ficam indisponíveis, sem dados inventados.
Trocar perfil invalida a revisão e limpa sugestões; retornar à análise máxima
restaura `Skill Level=20`. Não há simulação cognitiva humana ou evasão de detecção.

1. A localização de cada peça é uma coordenada lógica absoluta (a1 a h8); girar o tabuleiro **não** pode alterar o FEN.
2. Um histórico só é aceito se sua reprodução legal produzir exatamente a configuração de peças observada.
3. Mesmas peças em duas capturas **não** significam o mesmo estado: turno, roque, en passant, contadores e três repetições importam.
4. Se um tabuleiro for visto pela primeira vez no meio da partida sem histórico, não calcular variantes até confirmação de turno (estado marcado *estimado*).
5. Lances recomendados somente são exibidos se a revisão da análise corresponde à revisão atual do tabuleiro; linhas antigas não podem aparecer após um movimento.
6. Comunicações ficam em localhost. O cliente só envia posição e metadados do tabuleiro; não acessa senhas, cookies ou nomes de conta.
7. A análise máxima usa a força máxima nativa; o perfil Humanizado limita explicitamente Skill Level. A profundidade **alcançada** é exibida. Profundidade configurada não é garantia de execução até esse limite.

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
