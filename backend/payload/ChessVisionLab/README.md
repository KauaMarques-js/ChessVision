# ChessVision Lab 1.1 — analisador de xadrez local

**Projeto educacional de leitura de tabuleiro no navegador + Stockfish 19 (NNUE).**

O aplicativo tem dois componentes: **janela de desktop Python/Tkinter** e **extensão Chrome/Edge**. A extensão lê o DOM do tabuleiro aberto no Chess.com e envia a posição para `127.0.0.1:8765`. O aplicativo acompanha a partida e calcula até três variantes com o motor UCI **Stockfish 19**, sem enviar dados a serviços externos. Não clica ou joga lances automaticamente.

> **Uso responsável:** o Chess.com proíbe assistência de motores em partidas em andamento contra outros jogadores, inclusive em partidas sem rating. O uso da ferramenta cabe ao responsável, para análise de posições próprias, estudo, testes de percepção de tabuleiro e partidas contra bots. Política oficial: https://www.chess.com/legal/fair-play

## Requisitos

- Windows 10/11 64-bit (para o instalador e o Stockfish x64 incluído por download).
- Python 3.11 ou superior, com `tkinter` (incluído na instalação oficial do Python Windows).
- Internet **somente na instalação**, para baixar `python-chess` e Stockfish 19.
- Chrome ou Edge atualizado para carregar a extensão local.

## Instalação (Windows)

1. Extraia a pasta deste ZIP.
2. Instale o Python de https://www.python.org/downloads/ marcando a opção **Add Python to PATH**.
3. Clique duas vezes em **`instalar_windows.bat`**. O script cria `.venv`, instala `python-chess`, baixa e extrai a versão **Stockfish 19** oficial em `engine/`.
4. Clique duas vezes em **`ABRIR_CHESSVISION.bat`**. Uma janela aparecerá, com leitor local e painel de variantes.
5. Chrome: abra `chrome://extensions`. Edge: abra `edge://extensions`. Ative **Modo do desenvolvedor** > **Carregar sem compactação** > selecione a subpasta **`extension`** deste projeto.
6. Abra ou atualize a página com um tabuleiro Chess.com e faça um teste contra um **bot**. O painel do programa deve atualizar o FEN automaticamente e mostrar a análise.

### Como obter um EXE

Depois de instalar, execute `GERAR_EXE_WINDOWS.bat`. O executável fica em **`dist/ChessVisionLab.exe`**, acompanhado das pastas `engine/` e `extension/`. **Este ZIP inclui código-fonte, não contém um EXE Windows pré-compilado.**

## Ajustes

- **Depth**: `42` por padrão (42 *meios-lances* ≈ 21 lances completos por lado, se alcançados). Pode selecionar de 1 a 99. Profundidade alcançada é mostrada separadamente: não é garantido atingir o limite.
- **Tempo (s)**: `0` por padrão, sem limite artificial de tempo: a busca segue até o limite de profundidade definido; pode consumir muito CPU.
- **CPU threads / Hash MB**: número de threads e cache, ajustáveis para desempenho/bateria.
- **FEN manual**: teste sem navegador — cole uma posição FEN válida e clique em **Analisar FEN digitado**.
- **Turno manual**: útil em tabuleiros abertos no meio da partida, quando o histórico não está disponível.
- **Sempre visível**: mantém a janela acima de outras janelas.
- **Mostrar variante**: escolha **Todas** (com seta na 1ª), **Somente a 1ª**, **Somente a 2ª**, **Somente a 3ª** ou **Alternar 1ª / 2ª / 3ª**. A seta do tabuleiro e o texto acompanham a escolha. A alternância muda a cada 3 segundos entre as variantes disponíveis, sem interromper a busca do motor. Se a variante selecionada ainda não existir, o programa aguarda sem mostrar outra no lugar.
- **Só tabuleiro (F11)**: reduz a janela ao tabuleiro e mantém a seta do lance selecionado. No modo compacto, use o **botão direito** para escolher variantes e ativar **Sempre visível**. Teclas **1**, **2**, **3**, **A** (alternar) e **T** (todas) também mudam a exibição. **Esc**, **F11** ou **duplo clique** retornam ao painel completo. As preferências de exibição são lembradas.

## Como funciona a leitura

A extensão localiza `wc-chess-board`, `chess-board` ou `.board` e lê classes de peças como `piece wp square-52`; a informação é transformada em um **FEN de posicionamento**. Tenta extrair o histórico SAN do painel de lances; o aplicativo só confia nesse histórico se reproduzir **exatamente** as peças visíveis. Em sua ausência, acompanha até dois meios-lances legais a partir do estado já conhecido. Se o usuário entrou no meio da partida ou perdeu lances, recompõe a posição de forma aproximada, exibindo aviso: roque, en passant e turno dependem do histórico.

O programa não depende de API ou conta OpenAI. A rede é utilizada exclusivamente para baixar as dependências na instalação. Após isso, a conexão entre extensão e aplicativo é feita em **localhost**.

## Limitações verificáveis

- A leitura foi implementada com seletores conhecidos da interface do Chess.com, mas **não foi testada aqui numa sessão real de Chrome/Chess.com**. A interface do site pode mudar; nesse caso ajuste os seletores em `extension/board_reader.js`.
- Um tabuleiro aberto no meio da partida sem histórico pode ficar com turno/roque estimados. Para estado preciso, observe a partida desde o lance inicial.
- O motor deve ser instalado antes da análise; **não** está embutido no ZIP porque o arquivo oficial tem dezenas de MB e é distribuído separadamente.
- A avaliação não é uma garantia de Elo fixo nem de 20 jogadas completas de horizonte. A profundidade efetiva depende do hardware, do tempo e da posição.
- Use apenas versões oficiais do Stockfish; distribuições que embutirem seu binário devem cumprir a licença GPLv3 do projeto.

## Organização

```text
ChessVisionLab/
  app.py                   # Janela GUI, servidor localhost, motor UCI
  tracker.py               # Reconstrução FEN / SAN / jogadas legais
  extension/
    manifest.json          # Extensão Manifest V3
    board_reader.js        # DOM -> peças, orientação e lances
    background.js          # Extensão -> localhost
  engine/                  # Stockfish 19 baixado pelo instalador
  instalar_windows.bat
  instalar_stockfish19.ps1
  ABRIR_CHESSVISION.bat
  GERAR_EXE_WINDOWS.bat
  requirements.txt
  tests/
```

## Testes de desenvolvimento

```shell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
node tests/test_reader.js
node tests/test_background.js
python diagnostico.py
```

Fontes: https://stockfishchess.org/download/ • https://python-chess.readthedocs.io/en/stable/engine.html

## Atualização 1.1 — confiabilidade e testes

Esta versão corrige o cache de estados de xadrez em posições repetidas, adiciona heartbeat da extensão para identificar desconexões, evita exibir recomendações quando a partida começou no meio com turno incerto e limita a frequência de atualizações da interface. Também existe um mecanismo de detecção opcional por atributos `data-piece`/`data-square` para diferentes componentes de tabuleiro.

**Execute `DIAGNOSTICAR_WINDOWS.bat` antes de usar.** O diagnóstico salva `diagnostico_resultado.txt` e valida: dependências, reconstrução de lances, comunicação local de ponta a ponta e uma busca UCI real com 3 variantes do Stockfish 19. Caso ele falhe, **não considere a instalação concluída**. Para conferir o projeto e os testes manuais recomendados, leia `ARCHITECTURE.md`.

Uma execução bem-sucedida dos autotestes ainda não substitui um teste real da interface da Chess.com no seu Windows.
