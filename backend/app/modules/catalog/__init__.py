"""Catalog: items (RAW, PACK, BULK, FG), customers, suppliers, price lists, effective-dated settings.

Owning MP: MP02-MP05
Layer: L2
May depend on: core, identity, audit, uom

Files (created by the owning MP): api.py, service.py, domain.py (pure, no DB), models.py, schemas.py, tests/.
Other modules call this one only through service.py.
"""
