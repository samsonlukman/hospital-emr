# Department pricing

Hospital selling prices are managed by the department that owns the catalogue item. Clinical identity stays in the existing hospital list. Billing stays in the existing financial records.

## Architecture

```text
Hospital catalogue item
    → clinical identity (existing test / medicine / card)
    → commercial price (current selling price)
    → charge created at that moment copies the price onto the bill
```

Changing a catalogue price does **not** change bills that already exist. A new registration, laboratory fee, or pharmacy sale uses the price current at that moment.

Re-running laboratory catalogue configuration creates missing products and may fill a placeholder selling price (₦1.00). It does **not** overwrite a selling price already set through Department Pricing. `--reset-prices` is the only explicit overwrite.

## Where prices live

| Department | What staff edit | Stored as | Used when |
|---|---|---|---|
| Reception | Individual Card, Family Card | Current selling price on the existing card product | New registration fee |
| Laboratory | Hospital laboratory tests | Current selling price on the existing test product | New laboratory fee |
| Pharmacy | Hospital medicines | Current selling price on the existing medicine product | New pharmacy sale (existing Drug Catalogue path) |

There is no second test list and no second invoice book.

Laboratory Test Pricing shows the hospital laboratory list already used for ordering. It does not show the full processing-system dictionary and does not create tests.

Pharmacy Drug Pricing uses the same medicine prices as Drug Catalogue.

Reception Pricing only covers the two hospital cards. Reception does not set laboratory or pharmacy prices.

## Who can change prices

| Role | Reception | Laboratory | Pharmacy |
|---|---|---|---|
| Reception | Read + write | Denied | Denied |
| Laboratory | Denied | Read + write | Denied |
| Pharmacy | Denied | Denied | Read + write |
| Doctor | Denied | Denied | Denied |
| Nurse | Denied | Denied | Denied |
| Accountant | Read only | Read only | Read only |
| Hospital Admin | Read only | Read only | Read only |
| SuperAdmin | Read + write | Read + write | Read + write |
| Not signed in | Denied | Denied | Denied |

Frontend hiding is not security. The server rejects unauthorized reads and writes.

Hospital Admin can see prices and history. They cannot change department prices from this feature.

## Price history

Each actual change stores:

- item
- department
- old price
- new price
- signed-in user
- person name when available
- server time (UTC)
- optional reason

Saving the same amount again does not create another history row. Two staff saving different amounts each get their own history row. If someone else saved first, the next save is refused until the screen is refreshed.

## Historical bills

The amount on a bill is copied when the charge is created. Later catalogue changes leave that bill, its payments, and its outstanding amount unchanged.

## Screens

- Reception → Pricing
- Laboratory → Test Pricing
- Pharmacy → Drug Pricing (Drug Catalogue still adds and edits medicines, including selling price)

## Currency

Staff see ₦ (NGN). Prices are not shown as `$`.
