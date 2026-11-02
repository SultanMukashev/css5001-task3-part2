# D2.1 Typed record model

`Order` is a frozen dataclass. `__post_init__` checks: `order_id` is an `int`, `amount` a finite positive
`Decimal`, `currency` three uppercase letters, `ordered_at` timezone-aware. The timestamp is then stored in
UTC (via `object.__setattr__`, the standard way to adjust a frozen dataclass once).

`from_row(row, source_tz="UTC")` parses strings (dates via D1.2 `parse_ts`) and turns every parse problem
into `OrderError` chained from the original exception. `to_row()` gives back strings;
`Order.from_row(o.to_row()) == o` holds and is tested over several amounts, formats and a DST edge case.

Known limit: `email` is not validated here (D1.3 has the email pattern); keys must use the model's field names (use D2.3 `Rename` first for `customer_email`/`order_date`).
