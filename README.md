# ChessVision

**Versão experimental v1.0.0-beta.1 — testes com Stockfish 19 e análise de xadrez em Python.**

ChessVision é um projeto de testes e aprendizado que integra o **Stockfish 19** a um analisador local feito com **Python, Tkinter e python-chess**. A central de instalação e administração utiliza **Electron + React**. O Stockfish é um motor de terceiros, desenvolvido pela comunidade; este projeto cria uma interface e integração para estudar posições e avaliar variantes.

### Baixar a versão de teste

**[Baixar ChessVision para Windows 10/11 x64 (.exe)](https://github.com/KauaMarques-js/ChessVision/releases/tag/v1.0.0-beta.1)**

Na página da versão, baixe **`ChessVision-Manager-Setup-1.0.0-x64.exe`** em *Assets*. A primeira instalação precisa de internet para baixar Python, bibliotecas e Stockfish. O instalador ainda não possui assinatura digital.

**Uso indicado:** análise de posições, estudos, desenvolvimento e testes contra bots. Não utilize assistência de engine em partidas ao vivo contra outras pessoas quando isso violar as regras de fair play da plataforma.

## ChessVision Manager 1.0

Central de administração desktop em **Electron + React**, integrada ao ChessVision Lab 2.1. Visual inspirado no programa original: azul escuro `#111723`, areia `#e8d7ba` e azul do tabuleiro `#8098ad`.

## Usar no Windows

1. Execute `ChessVision-Manager-Setup-1.0.0-x64.exe` e instale a central.
2. Abra o atalho **ChessVision Manager**.
3. Clique em **Instalar componentes**. O instalador reaproveita um Python compatível; quando necessário, baixa Python 3.14.10 com Tkinter, cria `.venv`, instala as bibliotecas e baixa Stockfish 19 universal x64.
4. Acompanhe as etapas e os detalhes em **Downloads**. Os downloads reais informam o progresso no registro.
5. Use **Abrir ChessVision** para iniciar o analisador original.
6. Em **Extensão**, siga as instruções para Chrome ou Edge. A ativação no navegador é manual.

Requer Windows 10/11 x64 e internet na primeira instalação. O EXE inclui a central e o instalador integrado, mas não inclui os binários de Python, Stockfish ou os pacotes do PyPI. O instalador não possui certificado de assinatura digital.

## O que a central faz

- Inclui um perfil de reconhecimento **cburnett pronto**, sem cadastro inicial para esse estilo. Em **Leitura → Perfis salvos**, selecione um tema existente ou crie outro. Cada exemplo ensinado é salvo automaticamente, inclusive cadastros incompletos.
- O leitor Python acompanha os movimentos em segundo plano e usa o histórico legal para resolver pequenas ambiguidades visuais. O histórico fica salvo por perfil para conferir e retomar após reabrir. A leitura ainda depende do tabuleiro visível e de um tema compatível; não há precisão universal garantida.

- Instala e verifica o ambiente com o instalador original adaptado, sem console aberto.
- Mostra o estado dos arquivos encontrados e se o servidor local responde em `127.0.0.1:8765`.
- Abre o analisador sem reinstalar dependências a cada execução.
- Ao abrir o analisador, atualiza os arquivos embarcados e completa dependências Python ausentes, como Pillow, no ambiente existente. Preserva preferências e motor. Se a atualização falhar, exibe o erro específico no registro.
- O painel usa abas **Análise / Leitura / Ajustes** em 880×550. O **F11** ocupa 440×510 com seletores pequenos abaixo do tabuleiro, preservado em 440×440. O menu **Mais** reúne ações de leitura e sempre visível.
- **Humanizado (treino)** oferece força reduzida ajustável de 0 a 19, sugestão nativa do motor e cinco prévias para comparação. O atalho **H** ou **Hum.** funciona no F11. Não há garantia de vitória, simulação humana fiel ou evasão de detecção.
- **Leitura → Automático → Iniciar** procura o jogo em segundo plano, exclui a janela do próprio programa e mostra **Imagem do jogo / Peças lidas** para confirmar. Após confirmar, volta à assistência no compacto. O jogo precisa estar visível no monitor principal.
- Referências do tema são salvas localmente para retomar **no meio da partida**, inclusive após reiniciar. Apenas a primeira calibração de um tema desconhecido exige posição inicial. Sem histórico compatível, é necessário confirmar a vez e os roques. Capturas completas não são salvas.
- O leitor pode reencontrar uma área perdida e pedir nova confirmação, além de procurar o jogo ao abrir. Durante obstruções breves, continua tentando. Consulte `backend/payload/ChessVisionLab/README.md` para os controles e limites da recuperação.
- Executa o diagnóstico do projeto e apresenta saída, falhas e conclusão reais.
- Repara dependências e Stockfish mediante confirmação na interface.
- Abre as pastas do programa e da extensão; copia o caminho da extensão.
- Exporta o registro da sessão para TXT.

A presença de arquivos é exibida como **Encontrado**, não como garantia de funcionamento. O diagnóstico verifica Tkinter e UCI. A central não modifica as regras de análise nem a leitura do tabuleiro.

## Instalação existente

Os dados do ChessVision continuam em `%LOCALAPPDATA%\ChessVisionLab`. A central detecta a `.venv` e a engine nessa pasta. O reparo preserva a configuração do aplicativo; a instalação atualiza os arquivos de código embutidos da versão 2.1. O atalho antigo pode continuar abrindo o lançador anterior; utilize o novo atalho **ChessVision Manager** para administrar.

A desinstalação da central remove o Electron instalado e seus atalhos. O ambiente da engine, seus downloads e registros permanecem em `%LOCALAPPDATA%\ChessVisionLab`.

## Desenvolvimento

Requisitos: Node.js LTS compatível com Vite 7 e Go 1.25 ou superior para recompilar o helper.

```sh
npm ci
npm run build:helper
npm test
npm start
npm run dist:win
```

No Windows, também é possível executar `BUILD_WINDOWS.bat`. O instalador de saída fica em `release/`. O helper Windows já compilado está em `resources/`; use `build:helper` após alterações no backend.

Estrutura: `src/` contém React/CSS; `electron/` contém processo principal e preload; `backend/` contém o instalador Go e o payload original; `resources/` contém o helper e ícone; `tests/` contém testes de protocolo e interface.

O renderer usa isolamento de contexto, sandbox, CSP e API explícita via preload. Não recebe acesso ao Node.js nem caminhos/comandos arbitrários.

## Verificação desta entrega

- Build de produção React/Vite e empacotamento Electron/NSIS Windows x64.
- Testes do instalador Go e self-test de extração do payload.
- Testes do protocolo de ações e interpretação das etapas.
- Testes DOM da interface com ponte simulada, incluindo instalação, falha, reparo e navegação. Esses testes não executam downloads.
- Testes existentes do leitor e da ponte da extensão (8 + 3).
- Compilação sintática dos módulos Python.

Os testes automatizados Python, JavaScript e Go e a geração do instalador Windows x64 foram concluídos. Uma instalação completa e o uso com uma sessão real no navegador ainda exigem validação manual em Windows x64 conectado à internet: instalação limpa, instalação existente, lançamento, diagnóstico, falha de rede e ativação da extensão.

## Componentes e licenças

O payload mantém `LICENCAS_E_FONTES.md` com as fontes e licenças originais. Stockfish e python-chess são GPL-3.0 e são obtidos separadamente. React, lucide-react, Vite e Electron mantêm suas licenças de terceiros; os avisos do Electron acompanham a distribuição.
