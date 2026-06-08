"""Public news provider adapters."""

from crypto_probability_engine.news.adapters.fred import FredMacroAdapter
from crypto_probability_engine.news.adapters.gdelt import GdeltDocAdapter
from crypto_probability_engine.news.adapters.newsapi import NewsApiAdapter

__all__ = ["FredMacroAdapter", "GdeltDocAdapter", "NewsApiAdapter"]
