# Single shared invoice log instead of per-client files

The "log invoices" TODO item named the file `invoices-<client nickname>.csv`, implying
one CSV per client. We chose a single shared `invoices_log.csv` instead. Invoice
numbers are assigned from one global sequential counter (`invoices.json`'s
`next_invoice`), not namespaced per client, so a per-client layout would force the
`mark-paid` command to search every client's file to find which one contains a given
invoice number. A single file, mirroring how `time_log.csv` already uses a `Client`
column instead of per-client files, makes invoice-number lookup and cross-client
listing trivial.