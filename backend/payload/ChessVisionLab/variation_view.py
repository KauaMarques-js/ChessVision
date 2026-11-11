"""Escolha da variante exibida no tabuleiro, independente do motor UCI."""

DISPLAY_LABELS = {
    'all': 'Todas (seta na 1ª)',
    'first': 'Somente a 1ª melhor',
    'second': 'Somente a 2ª melhor',
    'third': 'Somente a 3ª melhor',
    'fourth': 'Somente a 4ª melhor',
    'fifth': 'Somente a 5ª melhor',
    'alternate': 'Alternar 1ª até 5ª',
    'human': 'Sugestão humanizada',
}

RANK_MODES = ('first', 'second', 'third', 'fourth', 'fifth')

CYCLE_SECONDS = 3.0


def selected_line(lines, mode, current_rank=1, human_line=None):
    """Retorna somente a variante solicitada; nunca substitui a 3ª pela 1ª."""
    if mode == 'human':
        return human_line
    available = {item['rank']: item for item in lines if 1 <= item['rank'] <= 5}
    if mode == 'alternate':
        rank = current_rank if current_rank in available else min(available, default=None)
    else:
        rank = RANK_MODES.index(mode) + 1 if mode in RANK_MODES else 1
    return available.get(rank)


def next_cycle_rank(lines, current_rank):
    """Alterna apenas entre variantes já recebidas da análise atual."""
    ranks = sorted({item['rank'] for item in lines if 1 <= item['rank'] <= 5})
    if not ranks:
        return 1
    if current_rank not in ranks:
        return ranks[0]
    return ranks[(ranks.index(current_rank) + 1) % len(ranks)]
