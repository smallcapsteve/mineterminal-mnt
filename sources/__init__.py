"""
Source-module registry. Each source exposes:
  list_recent(cfg, limit) -> Iterator[summary dict]
  fetch_body(summary)     -> summary dict
  event_id_for(url, date) -> sha256 hex
"""
from . import accesswire, cnw, companysite, company_ir_wp, globenewswire, globenewswire_gnews, newsfile, selfhosted

_REGISTRY = {
    "accesswire":    accesswire,
    "cnw":           cnw,
    "companysite":   companysite,
    "company_ir_wp": company_ir_wp,
    "globenewswire": globenewswire,
    "globenewswire_gnews": globenewswire_gnews,
    "newsfile":      newsfile,
    "selfhosted":    selfhosted,
}


def get(name: str):
    """Return the source module for the given name, or raise KeyError."""
    mod = _REGISTRY.get(name)
    if mod is None:
        raise KeyError(
            f"unknown source '{name}'; known: {sorted(_REGISTRY)}"
        )
    return mod


def names():
    return sorted(_REGISTRY)
