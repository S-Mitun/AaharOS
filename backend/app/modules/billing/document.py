"""The printable tax invoice (MP10, J4): server-rendered HTML with print styles; the browser saves it as PDF.

Pure: an invoice view in, HTML out. It carries the Rule 46 particulars (supplier and recipient names, addresses and
GSTINs, serial number and date, HSN, description, quantity and unit, taxable value, rate and amount of each tax,
place of supply with state name and code, reverse charge, signature line), the amount in words, the DEMO FSSAI and
Udyam numbers, batch / lot numbers once dispatched, and a DEMO UPI QR that must never be paid.
"""

from html import escape
from typing import Any
from urllib.parse import quote

import segno


def _e(value: Any) -> str:
    return escape("" if value is None else str(value))


def _money(text: str) -> str:
    whole, _, frac = text.partition(".")
    neg = whole.startswith("-")
    digits = whole.lstrip("-")
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join(groups) + "," + tail
    return f"{'-' if neg else ''}₹{digits}.{(frac or '00')[:2].ljust(2, '0')}"


def upi_link(vpa: str, payee: str, amount: str, note: str) -> str:
    return f"upi://pay?pa={quote(vpa)}&pn={quote(payee)}&am={quote(amount)}&cu=INR&tn={quote(note)}"


def render(view: dict[str, Any]) -> str:
    supplier, customer, profile = view["supplier"], view["customer"], view["profile"]
    rows = []
    for ln in view["lines"]:
        heads = " · ".join(f"{t['tax']} {_e(t['rate_pct'])}% {_money(t['amount'])}" for t in ln["taxes"])
        rows.append(
            "<tr>"
            f"<td>{ln['line_no']}</td><td>{_e(ln['item_name'])}</td><td>{_e(ln['hsn'])}</td>"
            f"<td class=r>{_e(ln['qty'])} {_e(ln['unit'])}</td><td class=r>{_money(ln['rate'])}</td>"
            f"<td class=r>{_money(ln['taxable'])}</td><td>{heads}</td>"
            "</tr>"
        )
    tax_rows = "".join(
        f"<tr><th>{_e(head)}</th><td class=r>{_money(amount)}</td></tr>" for head, amount in view["by_tax"].items()
    )
    lots = view.get("lots") or []
    lot_text = (
        ", ".join(f"{_e(lt['lot_no'])} ({_e(lt['qty'])})" for lt in lots)
        if lots
        else "assigned at dispatch (first expiry, first out)"
    )
    vpa = profile.get("upi_vpa")
    qr = ""
    if vpa:
        link = upi_link(str(vpa), supplier["name"], view["total"], view["invoice_no"])
        qr = (
            "<div class=qr><div class=demo-stamp>DEMO - do not pay</div>"
            f"{segno.make(link, error='m').svg_inline(scale=3)}"
            "<p class=small>DEMO UPI QR for a fictional payee</p></div>"
        )
    cancelled = (
        f"<div class=cancelled>CANCELLED: {_e(view.get('cancel_reason'))}</div>"
        if view["status"] == "CANCELLED"
        else ""
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(view['invoice_no'])} · DEMO tax invoice</title>
<style>
  body {{ font-family: system-ui, sans-serif; color: #1f1c17; margin: 24px; font-size: 13px; }}
  h1 {{ font-size: 20px; margin: 0; }} .small {{ font-size: 11px; color: #5f584c; }}
  .head {{ display: flex; justify-content: space-between;
    gap: 16px; border-bottom: 2px solid #b86e00; padding-bottom: 8px; }}
  .parties {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin: 12px 0; }}
  .box {{ border: 1px solid #e3ddd1; border-radius: 8px; padding: 8px; }}
  table {{ width: 100%; border-collapse: collapse; margin: 8px 0; }}
  th, td {{ border-bottom: 1px solid #e3ddd1; padding: 5px; text-align: left; vertical-align: top; }}
  .r {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .totals {{ width: 320px; margin-left: auto; }} .grand th, .grand td {{ font-size: 15px; font-weight: 700; }}
  .foot {{ display: flex; justify-content: space-between; align-items: flex-end; margin-top: 16px; }}
  .qr {{ position: relative; text-align: center; }}
  .demo-stamp {{ position: absolute; inset: 40% 0 auto; color: #a3231b; font-weight: 800; transform: rotate(-20deg);
                 background: rgba(255,255,255,.75); }}
  .cancelled {{ border: 3px solid #a3231b; color: #a3231b; font-weight: 800;
    padding: 6px; margin: 8px 0; text-align: center; }}
  .watermark {{ position: fixed; top: 45%; left: 0;
    right: 0; text-align: center; font-size: 72px; color: rgba(184,110,0,.08); }}
                transform: rotate(-25deg); pointer-events: none; }}
  @media print {{ .noprint {{ display: none; }} body {{ margin: 0; }} }}
</style></head><body>
<div class=watermark>DEMO</div>
<p class=noprint><button onclick="window.print()">Print or save as PDF</button></p>
{cancelled}
<div class=head>
  <div><h1>{_e(supplier['name'])}</h1>
    <div>{_e(profile.get('address'))}</div>
    <div>GSTIN: <b>{_e(profile.get('gstin'))}</b> · State: {_e(supplier['state_label'])}</div>
    <div class=small>FSSAI Lic. No.: {_e(profile.get('fssai_no'))} · Udyam: {_e(profile.get('udyam_no'))}</div></div>
  <div style="text-align:right"><h1>TAX INVOICE</h1>
    <div>Invoice No.: <b>{_e(view['invoice_no'])}</b></div><div>Date: {_e(view['invoice_date'])}</div>
    <div>Order: {_e(view.get('order_no'))}</div><div>Due: {_e(view.get('due_date'))}</div></div>
</div>
<div class=parties>
  <div class=box><b>Bill to / Ship to</b><div>{_e(customer['name'])}</div>
    <div>GSTIN: {_e(customer.get('gstin') or 'Unregistered')}</div><div>State: {_e(customer['state_label'])}</div></div>
  <div class=box><div>Place of supply: <b>{_e(view['place_of_supply'])}</b></div>
    <div>Tax: {'CGST + SGST (intra-state)' if view['regime'] == 'INTRA' else 'IGST (inter-state)'}</div>
    <div>Reverse charge: No</div><div>Batch / lot: {lot_text}</div></div>
</div>
<table><thead><tr><th>#</th><th>Description</th><th>HSN</th><th class=r>Qty</th><th class=r>Rate</th>
<th class=r>Taxable value</th><th>Tax</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<table class=totals><tbody>
<tr><th>Taxable value</th><td class=r>{_money(view['taxable'])}</td></tr>{tax_rows}
<tr><th>Round off</th><td class=r>{_money(view['round_off'])}</td></tr>
<tr class=grand><th>Total</th><td class=r>{_money(view['total'])}</td></tr></tbody></table>
<p><b>Amount in words:</b> {_e(view['amount_in_words'])}</p>
<div class=foot>{qr}
  <div style="text-align:right">For {_e(supplier['name'])}<br><br><br>Authorised signatory</div></div>
<p class=small>DEMO document generated by AaharOS for the NIT Tiruchirappalli CDI internship task. All names, GSTINs and
licence numbers are fictional. HSN and rate to be verified with a chartered accountant.</p>
</body></html>"""
