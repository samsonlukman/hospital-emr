#!/bin/bash
# Remove Accounting bills and the lab/scan/medicine orders that created them.
# Keeps patients, staff, admission, vitals, notes, pharmacy medicines, and stock.
# Does not docker compose down -v. Does not print secrets.
set -euo pipefail

VOID_USER=17
VOID_REASON='Clear accounting history 2026-10-01'
LOG=/tmp/abikan-accounting-wipe.log

log() { echo "[$(date -u +%H:%M:%S)] $*" | tee -a "$LOG"; }

count_odoo() {
  docker exec bahmni-standard-odoodb-1 psql -U odoo -d odoo -Atc "
SELECT 'sale_order='||count(*) FROM sale_order
UNION ALL SELECT 'invoices_posted='||count(*) FROM account_move WHERE move_type LIKE 'out_%' AND state='posted'
UNION ALL SELECT 'outstanding='||round(COALESCE(sum(amount_residual),0)::numeric,2) FROM account_move WHERE move_type LIKE 'out_%' AND state='posted'
UNION ALL SELECT 'payments='||count(*) FROM account_payment
UNION ALL SELECT 'account_move='||count(*) FROM account_move;
"
}

count_orders() {
  docker exec bahmni-standard-openmrsdb-1 sh -c 'mysql -N -uroot -p"$MYSQL_ROOT_PASSWORD" openmrs -e "
SELECT CONCAT(\"orders_active=\", COUNT(*)) FROM orders WHERE voided=0;
SELECT CONCAT(\"patients=\", COUNT(*)) FROM patient WHERE voided=0;
SELECT CONCAT(\"visits_open=\", COUNT(*)) FROM visit WHERE voided=0 AND date_stopped IS NULL;
SELECT CONCAT(\"obs=\", COUNT(*)) FROM obs WHERE voided=0;
SELECT CONCAT(\"beds_occupied=\", COUNT(*)) FROM bed WHERE status=\"OCCUPIED\";
"'
}

log "===== BEFORE ====="
count_odoo | tee -a "$LOG"
count_orders | tee -a "$LOG"

log "Stopping billing feed"
docker stop bahmni-standard-odoo-connect-1 bahmni-standard-odoo-1 >/dev/null

log "Removing bills, payments, and room/lab charges"
docker exec -i bahmni-standard-odoodb-1 psql -U odoo -d odoo -v ON_ERROR_STOP=1 <<'SQL'
BEGIN;
SET session_replication_role = replica;

DELETE FROM account_partial_reconcile;
DELETE FROM account_full_reconcile;
DELETE FROM account_move_line_account_tax_rel;
DELETE FROM account_analytic_line;
DELETE FROM account_edi_document;
DELETE FROM account_payment_outstanding_invoice_line;
DELETE FROM account_payment_credit_invoice_line;
DELETE FROM account_payment_account_bank_statement_line_rel;
DELETE FROM account_payment_register_move_line_rel;
DELETE FROM account_move_reversal_move;
DELETE FROM account_move_reversal_new_move;
DELETE FROM account_invoice_transaction_rel;
DELETE FROM account_move_purchase_order_rel;
DELETE FROM account_move_account_invoice_send_rel;
DELETE FROM account_move_line;
DELETE FROM account_payment;
DELETE FROM account_bank_statement_line;
DELETE FROM account_bank_statement;
DELETE FROM sale_order_line_invoice_rel;
DELETE FROM account_tax_sale_order_line_rel;
DELETE FROM account_move;

DELETE FROM stock_move_line WHERE picking_id IN (
  SELECT p.id FROM stock_picking p JOIN stock_picking_type t ON t.id=p.picking_type_id WHERE t.code='outgoing'
);
DELETE FROM stock_valuation_layer WHERE stock_move_id IN (
  SELECT m.id FROM stock_move m JOIN stock_picking p ON p.id=m.picking_id
  JOIN stock_picking_type t ON t.id=p.picking_type_id WHERE t.code='outgoing'
);
DELETE FROM stock_move WHERE picking_id IN (
  SELECT p.id FROM stock_picking p JOIN stock_picking_type t ON t.id=p.picking_type_id WHERE t.code='outgoing'
);
DELETE FROM stock_picking WHERE picking_type_id IN (
  SELECT id FROM stock_picking_type WHERE code='outgoing'
);

DELETE FROM sale_order_line;
DELETE FROM sale_order;
DELETE FROM failed_events;
DELETE FROM mail_message WHERE model IN ('account.move','sale.order','account.payment','stock.picking');
DELETE FROM ir_attachment WHERE res_model IN ('account.move','sale.order','account.payment');

UPDATE ir_sequence SET number_next=1
 WHERE code IN ('sale.order')
    OR name ILIKE '%sales order%'
    OR name ILIKE '%customer invoice%'
    OR name ILIKE '%customer payment%';
UPDATE ir_sequence_date_range SET number_next=1;

SET session_replication_role = origin;
COMMIT;
SQL

log "Removing the lab, scan, and medicine orders that created those bills"
docker exec -i bahmni-standard-openmrsdb-1 sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" openmrs' <<SQL
SET @u := ${VOID_USER};
SET @r := '${VOID_REASON}';
UPDATE orders o
   JOIN order_type ot ON ot.order_type_id = o.order_type_id
   SET o.voided=1, o.voided_by=@u, o.date_voided=UTC_TIMESTAMP(), o.void_reason=@r
 WHERE o.voided=0
   AND ot.name IN ('Lab Order', 'Radiology Order', 'Drug Order');
DELETE FROM failed_events;
DELETE FROM failed_event_retry_log;
SQL

log "Starting billing services"
docker start bahmni-standard-odoo-1 >/dev/null
sleep 8
docker exec bahmni-standard-odoodb-1 psql -U odoo -d odoo -v ON_ERROR_STOP=1 -c \
  "UPDATE liquibasechangeloglock SET locked=false, lockgranted=NULL, lockedby=NULL WHERE id=1 AND locked;" \
  >/dev/null || true
docker start bahmni-standard-odoo-connect-1 >/dev/null
docker restart bahmni-standard-abikan-api-1 >/dev/null

sleep 12
log "===== AFTER ====="
count_odoo | tee -a "$LOG"
count_orders | tee -a "$LOG"
docker inspect --format '{{.State.Health.Status}}' bahmni-standard-abikan-api-1 || true
log "Accounting history cleared. Patients, admission, vitals, notes, and medicines were kept."
