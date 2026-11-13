# Fonte do perfil cburnett

As peças SVG são de Colin M. L. Burnett, distribuídas pelo Lichess sob
GPL-2.0-or-later. Fonte e atribuição:
https://github.com/lichess-org/lila/tree/master/public/piece/cburnett
https://github.com/lichess-org/lila/blob/master/COPYING.md
A licença acompanha este diretório em COPYING.

initial.png é a renderização das 64 casas da posição inicial com essas peças,
casas de 93 pixels e fundos #f0d9b5 / #b58863. Os SVGs ocupam a casa inteira.
Não contém captura de dados pessoais. cburnett.json contém características
normalizadas derivadas dessa imagem, não pesos de rede neural.

Para reconstruir o perfil, na pasta ChessVisionLab:

```python
from pathlib import Path
from PIL import Image
from screen_reader import ScreenBoardReader

reader = ScreenBoardReader(Image.open('profiles/cburnett-source/initial.png'))
reader.profile_name = 'cburnett (pronto)'
reader.templates = {
    symbol: list({tile.tobytes(): tile for tile in tiles}.values())
    for symbol, tiles in reader.templates.items()
}
reader.save(Path('profiles/cburnett.json'))
```

Este perfil identifica esse estilo 2D. Outros desenhos precisam de um perfil
próprio. A confirmação da posição e os limites de confiança continuam ativos.
