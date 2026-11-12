# ChessVision Lab 1.1 — analisador de xadrez local

**Projeto educacional de leitura de tabuleiro no navegador + Stockfish 19 (NNUE).**

O aplicativo tem uma **janela de desktop Python/Tkinter** com duas fontes de posição: **extensão Chrome/Edge** ou **captura local da tela**. A extensão lê o DOM do tabuleiro aberto no Chess.com e envia a posição para `127.0.0.1:8765`. A captura reconhece um tabuleiro 2D calibrado, sem extensão. O aplicativo calcula até cinco variantes com o motor UCI **Stockfish 19**, sem enviar imagens a serviços externos. Não clica ou joga lances automaticamente.

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
- **FEN manual**: na aba **Ajustes**, cole uma posição FEN válida e clique em **Analisar FEN**.
- **Turno manual**: útil em tabuleiros abertos no meio da partida, quando o histórico não está disponível.
- **Sempre visível**: mantém a janela acima de outras janelas.
- **Mostrar variante**: escolha da **1ª até a 5ª melhor opção**, **Todas** (seta na 1ª) ou a alternância opcional a cada 3 segundos. A busca sempre solicita cinco variantes, independentemente da qualidade do seu último lance; posições com menos de cinco lances legais oferecem menos opções. A seta e o texto acompanham o ranking selecionado. Se a variante ainda não existir, o programa aguarda sem substituir por outra.
- **F11 compacto**: tabuleiro de análise preservado em **440 × 440 px**, com seletores pequenos **abaixo** dele e janela de **440 × 510 px**. Clique na opção ou use **1 a 5**; **Hum. / H** seleciona a sugestão humanizada. **Mais** reúne painel, nova área, tentar novamente, parar, copiar FEN e sempre visível. **Esc**, **F11**, **Mais → Painel** ou **duplo clique** retornam ao painel de **880 × 550 px**, organizado em **Análise / Leitura / Ajustes**.

## Perfil Humanizado (treino)

Escolha **Humanizado (treino)** no seletor de perfil. Ajuste **Nível** de **0 a 19**
e clique em **Aplicar** na aba Análise; o padrão é **12**. Números maiores representam
maior força do motor. Esses níveis não são um Elo nem uma classificação humana.
**Análise máxima** restaura o nível máximo nativo do motor.

O perfil usa o controle nativo **Skill Level** do Stockfish, com busca de até
**2 segundos** por posição (respeita um limite de tempo ou profundidade menor
configurado). A sugestão vem do lance final escolhido pelo motor com força
reduzida, e não é simplesmente a primeira linha da análise. Pode escolher a
melhor jogada ou uma inferior, conforme a posição e o nível. Não há garantia de
vitória, reprodução fiel de raciocínio humano ou de evitar detecção/banimentos.
Referência: [controle de força do Stockfish](https://official-stockfish.github.io/docs/stockfish-wiki/Stockfish-FAQ.html).

**Sugestão humanizada** mostra o lance do perfil, sua continuação quando
disponível e as **cinco prévias de análise para comparação**, com rolagem.
Se o lance final não estiver nas cinco linhas recebidas, a interface mostra
apenas o lance legal, sem inventar avaliação ou continuação. A avaliação vem
da perspectiva das brancas, como no restante do programa.

No F11, clique em **Hum.** ou pressione **H**. Os seletores **1 a 5**
continuam mostrando as respectivas variantes de análise; eles não substituem
a sugestão do perfil. Trocar de perfil ou de posição limpa a sugestão anterior.
As preferências são salvas. O aplicativo continua sem executar jogadas.

## Ler a tela sem extensão

1. Instale as dependências atualizadas (`python -m pip install -r requirements.txt`), incluindo Pillow.
2. **Primeira vez em um tema:** deixe o tabuleiro 2D na posição inicial. Depois dessa calibração, as referências das peças ficam salvas e permitem retomar **no meio da partida**, inclusive depois de fechar e abrir o programa. O jogo deve estar visível no **monitor principal**; não é captura de uma janela minimizada ou totalmente encoberta.
3. Na aba **Leitura**, escolha a orientação, selecione **Automático** e clique em **Iniciar**. O programa mantém um painel compacto visível com o progresso, procura grades 8×8 em segundo plano e exclui as janelas do próprio ChessVision. Encontrar uma grade abre a conferência mesmo se o estilo das peças ainda for desconhecido. Continua procurando se o jogo desaparecer. Duas observações estáveis abrem a confirmação. **Manual** continua disponível para selecionar os limites por arraste.
4. Confira as abas **Imagem do jogo** e **Peças lidas**, ambas em uma prévia pequena. Ajuste **X, Y, Largura e Altura** se necessário; **Enter** atualiza. **Tentar novamente** captura uma imagem nova; **Nova área** refaz a seleção. A resolução de reconhecimento continua sendo a original. Se houver vários candidatos, use **Outra região**.
5. Sem histórico compatível, confirme **de quem é a vez** e os direitos de **roque K/Q/k/q**. Roques desconhecidos começam desmarcados; a imagem isolada não recupera en passant, contadores ou repetições. Com histórico conhecido e transição legal, esses dados são preservados. O motor permanece aguardando até clicar em **Confirmar e continuar**; nenhuma posição candidata é aplicada antes disso.
6. Após confirmar, o tabuleiro de assistência volta no compacto, tenta se posicionar fora da área do jogo e continua acompanhando a posição. Se não há espaço, a janela é minimizada, mantendo a leitura ativa. As referências normalizadas das peças são salvas localmente; capturas completas da tela não são gravadas nem enviadas.
7. **Reencontrar ao perder a área** inicia outra busca após falhas persistentes ou vários lances perdidos, preservando o último estado confiável até a nova confirmação. Obstruções breves continuam sendo aguardadas normalmente. **Procurar jogo ao abrir o programa** ativa a busca ao iniciar quando há referências salvas. As opções podem ser desmarcadas. **Mais → Buscar jogo em segundo plano** também inicia a procura no F11.
8. **Copiar FEN reconhecido** copia a última posição aceita. **Parar** libera novamente a extensão. Analisar um FEN manual também para a captura. Enquanto a captura estiver ativa, a extensão é ignorada.

Janelas sobrepostas, animações, temas 3D, peças pouco distinguíveis e efeitos visuais podem impedir a leitura; o modo automático aguarda uma imagem visível. Uma região reencontrada pode usar as referências existentes em outro tamanho, se as peças continuarem distinguíveis. Tema desconhecido pode ser cadastrado em **Ensinar tema**, inclusive no meio da partida, desde que todos os tipos de peça estejam disponíveis como exemplos. A confirmação permite retomar uma posição atual com referências conhecidas, mas não inventa o histórico que não foi observado. A integração ainda precisa de validação manual com o tema real do Discord.

O localizador automático exige uma grade 2D completa, de pelo menos 160 pixels de lado, com fundos das casas aproximadamente uniformes e distintos. Temas com texturas, grades parcialmente ocultas ou efeitos intensos podem exigir seleção manual. Encontrar a região não garante reconhecer todas as peças: confira a prévia e a posição reconhecida. Não há garantia de 100% de precisão para qualquer aplicativo ou tema.

A captura usa [Pillow ImageGrab](https://pillow.readthedocs.io/en/stable/reference/ImageGrab.html). Não há mecanismo de ocultação do motor ou garantia de evitar identificação de assistência.

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

**Execute `DIAGNOSTICAR_WINDOWS.bat` antes de usar.** O diagnóstico salva `diagnostico_resultado.txt` e valida: dependências, reconstrução de lances, comunicação local de ponta a ponta e uma busca UCI real com 5 variantes do Stockfish 19. Caso ele falhe, **não considere a instalação concluída**. Para conferir o projeto e os testes manuais recomendados, leia `ARCHITECTURE.md`.

Uma execução bem-sucedida dos autotestes ainda não substitui um teste real da interface da Chess.com no seu Windows.


## Ensinar o estilo das peças

Na conferência, use **Alinhar grade** para ajustar uma seleção aproximada às bordas observadas. Clique em **Ensinar tema**: escolha o tipo e clique em uma casa que contenha a peça correspondente. Cadastre os 12 tipos (seis brancos e seis pretos) e uma casa vazia; o próximo tipo é selecionado automaticamente. Para torres pretas e outros tipos, selecione o tipo novamente e clique em uma peça numa casa de outra cor: os exemplos são somados, sem apagar o anterior. **Desfazer** remove a última alteração; **Limpar tipo selecionado** permite corrigir exemplos com rótulo errado.

Se **Usar perfil** encontrar uma casa incerta, ela aparece destacada e ampliada. Confira o tipo selecionado e clique na casa para adicionar o exemplo correto. O tipo sugerido é apenas o candidato mais próximo, não uma confirmação automática. A leitura tolera pequenos deslocamentos de rasterização sem dispensar os critérios de confiança ou aceitar peças indistinguíveis. Perfis foreground-ink-v2 já salvos continuam compatíveis.

**Importar casa…** permite fornecer o recorte de uma casa inteira (PNG, JPEG ou WebP), com peça e margens, útil quando um tipo já foi capturado na partida. Use o mesmo estilo e enquadramento. Não importe uma folha com várias peças. Dê um nome ao perfil e clique em **Usar perfil**. O programa exige todos os exemplos e uma posição reconhecida válida. Confira **Peças lidas**, a vez e os roques, depois **Confirmar e continuar**. Só essa confirmação salva o perfil e retoma a leitura.

O reconhecimento compara exemplos locais; não é um treinamento de rede neural. O último perfil confirmado permanece salvo para esse tema. A versão nova usa referências `foreground-ink-v2`: perfis de versões anteriores precisam ser ensinados novamente ou recalibrados na posição inicial. A tela do jogo deve estar visível; capturas incompletas e peças ambíguas continuam aguardando uma leitura confiável.
