"""Limits shared by the CLI, scraper and offline analysis."""

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class ScraperConfig:
    videos: int = 10
    comments: int = 20
    video_delay: float = 2.0
    comment_wait: float = 2.0
    profile_scroll_wait: float = 3.0
    max_scrolls: int = 30
    profile_idle_rounds: int = 5
    comment_rounds: int = 30
    comment_idle_rounds: int = 8
    navigation_timeout: int = 30000
    selector_timeout: int = 30000
    response_timeout: float = 10.0
    comment_deadline: float = 90.0
    headless: bool = False
    link_method: str = 'auto'

    def __post_init__(self):
        for name in ('videos', 'comments', 'max_scrolls', 'profile_idle_rounds',
                     'comment_rounds', 'comment_idle_rounds', 'navigation_timeout',
                     'selector_timeout'):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f'{name} debe ser un entero positivo.')
        for name in ('video_delay', 'comment_wait', 'profile_scroll_wait',
                     'response_timeout', 'comment_deadline'):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f'{name} debe ser un numero positivo finito.')
        if self.video_delay < 2 or self.comment_wait < 2:
            raise ValueError('Las pausas entre videos y comentarios deben ser de al menos 2 segundos.')
        if self.link_method not in ('auto', 'playwright', 'beautifulsoup'):
            raise ValueError('Metodo de enlaces no reconocido.')
        if type(self.headless) is not bool:
            raise ValueError('headless debe ser booleano.')


DEFAULT_CONFIG = ScraperConfig()
