"""Analytics API: serves read-only results from the analytics/ package (forecasts, SPC). Never writes the ledger.

Owning MP: MP16
Layer: L7
May depend on: core, L1-L6

Files (created by the owning MP): api.py, service.py, domain.py (pure, no DB), models.py, schemas.py, tests/.
Other modules call this one only through service.py.
"""
