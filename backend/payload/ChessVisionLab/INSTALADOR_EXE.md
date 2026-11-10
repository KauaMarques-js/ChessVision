# ChessVision Lab 2.1 — instalador automático de Windows

Este projeto é uma prova de conceito acadêmica de leitura de posições e análise com motor UCI. **O arquivo `ChessVisionLab-Instalador-Windows-x64-v2.1.exe` é um executável real para Windows 10/11 (x64), produzido em Go.** Ele é um **instalador/lançador**, não uma tradução do aplicativo Python para binário nativo. O aplicativo de interface continua utilizando Python/Tkinter, instalado automaticamente quando necessário.

## Instalar em sete etapas

1. Execute `ChessVisionLab-Instalador-Windows-x64-v2.1.exe` com duplo clique. O instalador extrai os arquivos embutidos para `%LOCALAPPDATA%\ChessVisionLab`.
2. Detecta Python capaz de **abrir uma janela Tk real**, verificando os arquivos `init.tcl` e `tk.tcl`. Caso o Python 3.13 existente esteja incompleto, ignora a instalação defeituosa e utiliza um runtime próprio. Se ausente, baixa e instala **Python 3.14.10** do domínio oficial `python.org` em uma pasta local do projeto, sem exigir que você instale Python manualmente.
3. Cria ambiente Python isolado e instala `python-chess`.
4. Baixa e extrai **Stockfish 19** da distribuição oficial, se necessário; executa um teste direto do protocolo UCI.
5. Realiza um diagnóstico de ponta a ponta: reconstrução de lances, servidor localhost e busca real do Stockfish com três variantes.
6. Cria um atalho no Menu Iniciar e abre a pasta `extension/` no Explorador. **A autorização para carregar uma extensão local ainda precisa ser feita pelo usuário no Chrome/Edge:** ativar o *Modo do desenvolvedor* e selecionar *Carregar sem compactação* > `%LOCALAPPDATA%\ChessVisionLab\extension`.
7. Inicia a interface do ChessVision Lab. Ao executar de novo, reaproveita as dependências instaladas.

O instalador precisa de Internet **na primeira instalação** para buscar Python, as dependências e Stockfish. As análises posteriores são locais, sem API paga. A instalação ocupa bem mais espaço em disco do que o instalador compacto.

## Controles disponíveis

- `ChessVisionLab.exe -diagnostico`: executar diagnóstico novamente.
- `ChessVisionLab.exe -reparar`: reinstalar dependências e obter novamente o Stockfish (feche o programa antes).
- `ChessVisionLab.exe -extensao`: abrir novamente a pasta de extensão do navegador.
- `ChessVisionLab.exe -apenas-instalar`: preparar todos os componentes sem abrir a interface.

Para usar argumentos, abra o **PowerShell** ou **Prompt de Comando** no diretório de instalação e execute o comando. O executável persistente, após o primeiro uso, fica em `%LOCALAPPDATA%\ChessVisionLab\ChessVisionLab.exe`.

## Onde procurar erros

- `%LOCALAPPDATA%\ChessVisionLab\instalacao.log` — etapas do instalador.
- `%LOCALAPPDATA%\ChessVisionLab\diagnostico_resultado.txt` — testes Python, ponte local e busca UCI.
- `%LOCALAPPDATA%\ChessVisionLab\aplicativo.log` — mensagens de falha da interface.

Se o antivírus, a rede da empresa ou a política do Windows bloquear um download ou a instalação, consulte os logs. Não é necessário desativar a proteção do sistema. O código-fonte do instalador está incluído no pacote de desenvolvimento e pode ser auditado.

## Testes e limites reais

O instalador PE64 foi compilado para Windows x64 e os arquivos embutidos foram extraídos em teste automatizado; a sintaxe Python foi conferida e a extensão passou por 11 testes JavaScript. **Ainda não foi executado numa sessão real de Windows/Chess.com neste ambiente Linux**, nem foi possível testar os downloads e o binário Windows do Stockfish. O teste no computador de destino será decisivo.

- Profundidade de análise pode ser configurada até 99 meios-lances; não há garantia de alcançá-la em tempo fixo, nem de Elo nominal constante.
- Pode precisar de adaptação quando o DOM do site for alterado.
- O uso de motores para assistência em partidas online contra outros jogadores pode violar as regras do Chess.com. Faça testes em partidas contra bots, tabuleiros de estudo ou ambientes autorizados.
- O Stockfish tem licença **GPLv3**. Se for redistribuir o binário, consulte as obrigações da licença e forneça os avisos/código-fonte necessários. O instalador baixa o motor oficial no computador do usuário.

Downloads oficiais utilizados: https://stockfishchess.org/download/ e https://www.python.org/downloads/windows/


## Correção Tcl/Tk — atualização 2.1

O instalador 2.0 validava apenas `import tkinter`. Isso pode passar mesmo que `tk.Tk()` falhe com `Can't find a usable init.tcl`. A versão 2.1 executa `Tk()` na escolha do Python, no ambiente `.venv` e no diagnóstico; falhas forçam a recuperação automática, sem tocar nos arquivos da instalação global. Para verificar manualmente: `py -3.13 -m tkinter`. Não rode `app.py` diretamente na pasta `payload` antes de reparar o Python ou usar o instalador.
