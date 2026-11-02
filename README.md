# Part 2 — Data Engineering

| Folder | Task | Level |
|---|---|---|
| d1_1_resilient_ingest | CSV ingest with quarantine | Core |
| d1_2_dates | UTC normalisation, partition keys | Core |
| d1_3_text_cleaning | phones, emails, PII masking, HTML strip | Core |
| d1_4_incremental_loader | watermark loader | Advanced |
| d1_5_retry | backoff decorator | Advanced |
| d1_6_sessions | clickstream sessions | Challenge |
| d2_1_order_model | frozen `Order` dataclass | Core |
| d2_2_sources_sinks | Source/Sink ABCs + 6 connectors | Core |
| d2_3_transforms | `Source \| Transform \| ...` pipelines | Core |
| d2_4_quality_checks | checks + QualitySuite | Advanced |
| d2_5_lsp | contract tests, LSP fixes | Advanced |
| d2_6_registry | `__init_subclass__` registry, JSON configs | Challenge |
| capstone_minietl | minietl CLI | Capstone |

`data/orders.csv` is the sample shared by D1.1–D1.3 and D2.3/D2.6.

```bash
cd part2
python -m pytest -q
```
