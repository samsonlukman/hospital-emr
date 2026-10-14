#!/bin/bash
# Go-live wipe of clinical, billing, lab, and messaging history on the hospital EMR.
# Keeps: patients, family cards, staff, catalogues, pharmacy stock on-hand, prices, attendance codes.
# Does not docker compose down -v. Does not print secrets.
set -euo pipefail

VOID_USER=17
VOID_REASON='Go-live wipe 2026-09-25'
LOG=/tmp/abikan-golive-wipe.log

log() { echo "[$(date -u +%H:%M:%S)] $*" | tee -a "$LOG"; }

psql_odoo() {
  docker exec -i bahmni-standard-odoodb-1 psql -U odoo -d odoo -v ON_ERROR_STOP=1
}

psql_elis() {
  docker exec -i bahmni-standard-openelisdb-1 psql -U clinlims -d clinlims -v ON_ERROR_STOP=1
}

psql_pacs_int() {
  docker exec -i bahmni-standard-pacsdb-1 psql -U pacs_integration -d pacs_integration_db -v ON_ERROR_STOP=1
}

count_openmrs() {
  docker exec bahmni-standard-openmrsdb-1 sh -c 'mysql -N -uroot -p"$MYSQL_ROOT_PASSWORD" openmrs -e "
SELECT CONCAT_WS(\"=\", \"patients\", COUNT(*)) FROM patient WHERE voided=0
UNION ALL SELECT CONCAT_WS(\"=\", \"visits_open\", COUNT(*)) FROM visit WHERE voided=0 AND date_stopped IS NULL
UNION ALL SELECT CONCAT_WS(\"=\", \"visits\", COUNT(*)) FROM visit WHERE voided=0
UNION ALL SELECT CONCAT_WS(\"=\", \"encounters\", COUNT(*)) FROM encounter WHERE voided=0
UNION ALL SELECT CONCAT_WS(\"=\", \"obs\", COUNT(*)) FROM obs WHERE voided=0
UNION ALL SELECT CONCAT_WS(\"=\", \"orders\", COUNT(*)) FROM orders WHERE voided=0
UNION ALL SELECT CONCAT_WS(\"=\", \"appointments\", COUNT(*)) FROM patient_appointment WHERE voided=0
UNION ALL SELECT CONCAT_WS(\"=\", \"allergies\", COUNT(*)) FROM allergy WHERE voided=0
UNION ALL SELECT CONCAT_WS(\"=\", \"med_admin\", COUNT(*)) FROM medication_administration WHERE voided=0
UNION ALL SELECT CONCAT_WS(\"=\", \"beds_open\", COUNT(*)) FROM bed_patient_assignment_map WHERE date_stopped IS NULL
UNION ALL SELECT CONCAT_WS(\"=\", \"beds_occupied\", COUNT(*)) FROM bed WHERE status=\"OCCUPIED\"
UNION ALL SELECT CONCAT_WS(\"=\", \"encounter_events\", COUNT(*)) FROM event_records WHERE category=\"Encounter\";
"'
}

count_odoo() {
  docker exec bahmni-standard-odoodb-1 psql -U odoo -d odoo -Atc "
SELECT 'sale_order='||count(*) FROM sale_order
UNION ALL SELECT 'invoices_posted='||count(*) FROM account_move WHERE move_type LIKE 'out_%' AND state='posted'
UNION ALL SELECT 'outstanding='||round(COALESCE(sum(amount_residual),0)::numeric,2) FROM account_move WHERE move_type LIKE 'out_%' AND state='posted'
UNION ALL SELECT 'payments='||count(*) FROM account_payment
UNION ALL SELECT 'account_move='||count(*) FROM account_move
UNION ALL SELECT 'partners='||count(*) FROM res_partner
UNION ALL SELECT 'products='||count(*) FROM product_product
UNION ALL SELECT 'incoming_pickings='||count(*) FROM stock_picking p JOIN stock_picking_type t ON t.id=p.picking_type_id WHERE t.code='incoming'
UNION ALL SELECT 'outgoing_pickings='||count(*) FROM stock_picking p JOIN stock_picking_type t ON t.id=p.picking_type_id WHERE t.code='outgoing'
UNION ALL SELECT 'stock_quants='||count(*) FROM stock_quant WHERE quantity <> 0
UNION ALL SELECT 'failed_events='||count(*) FROM failed_events;
"
}

count_elis() {
  docker exec bahmni-standard-openelisdb-1 psql -U clinlims -d clinlims -Atc "
SELECT 'elis_patients='||count(*) FROM patient
UNION ALL SELECT 'samples='||count(*) FROM sample
UNION ALL SELECT 'analysis='||count(*) FROM analysis
UNION ALL SELECT 'results='||count(*) FROM result;
"
}

log "===== BEFORE ====="
count_openmrs | tee -a "$LOG"
count_odoo | tee -a "$LOG"
count_elis | tee -a "$LOG"

log "Stopping feed and clinical engines"
docker stop \
  bahmni-standard-odoo-connect-1 \
  bahmni-standard-openelis-1 \
  bahmni-standard-pacs-integration-1 \
  bahmni-standard-odoo-1 \
  bahmni-standard-openmrs-1 \
  bahmni-standard-appointments-1 \
  ipd >/dev/null

log "Wiping OpenMRS visits, encounters, orders, appointments, allergies, IPD"
docker exec -i bahmni-standard-openmrsdb-1 sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" openmrs' <<SQL
SET @u := ${VOID_USER};
SET @r := '${VOID_REASON}';
SET FOREIGN_KEY_CHECKS=0;

UPDATE bed_patient_assignment_map SET date_stopped = UTC_TIMESTAMP() WHERE date_stopped IS NULL;
UPDATE bed SET status='AVAILABLE' WHERE status='OCCUPIED';

UPDATE obs SET voided=1, voided_by=@u, date_voided=UTC_TIMESTAMP(), void_reason=@r WHERE voided=0;
UPDATE encounter_diagnosis SET voided=1, voided_by=@u, date_voided=UTC_TIMESTAMP(), void_reason=@r WHERE voided=0;
UPDATE orders SET voided=1, voided_by=@u, date_voided=UTC_TIMESTAMP(), void_reason=@r WHERE voided=0;
UPDATE encounter SET voided=1, voided_by=@u, date_voided=UTC_TIMESTAMP(), void_reason=@r WHERE voided=0;
UPDATE visit SET voided=1, voided_by=@u, date_voided=UTC_TIMESTAMP(), void_reason=@r,
  date_stopped=IFNULL(date_stopped, UTC_TIMESTAMP()) WHERE voided=0;
UPDATE patient_appointment SET voided=1, voided_by=@u, date_voided=UTC_TIMESTAMP(), void_reason=@r, status='Cancelled' WHERE voided=0;
UPDATE allergy SET voided=1, voided_by=@u, date_voided=UTC_TIMESTAMP(), void_reason=@r WHERE voided=0;
UPDATE conditions SET voided=1, voided_by=@u, date_voided=UTC_TIMESTAMP(), void_reason=@r WHERE voided=0;
UPDATE patient_program SET voided=1, voided_by=@u, date_voided=UTC_TIMESTAMP(), void_reason=@r WHERE voided=0;
UPDATE medication_administration SET voided=1, voided_by=@u, date_voided=UTC_TIMESTAMP(), void_reason=@r WHERE voided=0;
UPDATE surgical_appointment SET voided=1, voided_by=@u, date_voided=UTC_TIMESTAMP(), void_reason=@r WHERE voided=0;
UPDATE order_group SET voided=1, voided_by=@u, date_voided=UTC_TIMESTAMP(), void_reason=@r WHERE voided=0;
UPDATE notes SET is_voided=1, voided_by=@u, date_voided=UTC_TIMESTAMP(), void_reason=@r WHERE is_voided=0;
DELETE FROM note;

DELETE FROM event_records WHERE category IN ('Encounter','appointments');
DELETE FROM event_records_queue;
DELETE FROM failed_events;
DELETE FROM failed_event_retry_log;

SET FOREIGN_KEY_CHECKS=1;
SQL

log "Wiping Odoo invoices, payments, sale orders, outgoing dispenses"
psql_odoo <<'SQL'
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

log "Wiping OpenELIS samples and results"
psql_elis <<'SQL'
BEGIN;
TRUNCATE TABLE
  result_signature,
  result_inventory,
  result,
  analysis_qaevent_action,
  analysis_qaevent,
  analysis_storages,
  analysis_users,
  analysis,
  sample_qaevent_action,
  sample_qaevent,
  sample_human,
  sample_item,
  sample_organization,
  sample_pdf,
  sample_projects,
  sample_requester,
  sample_animal,
  sample_environmental,
  sample_newborn,
  sample,
  note,
  observation_history
RESTART IDENTITY CASCADE;
COMMIT;
SQL

log "Wiping PACS integration orders"
psql_pacs_int <<'SQL'
BEGIN;
TRUNCATE TABLE test_order, order_details, failed_events, failed_event_retry_log RESTART IDENTITY CASCADE;
COMMIT;
SQL

log "Wiping Hospital EMR messages, alerts, lab movements"
docker exec -i bahmni-standard-abikan-api-1 python - <<'PY'
import sqlite3
from pathlib import Path

def wipe(path, statements):
    p = Path(path)
    if not p.exists():
        print("missing", path)
        return
    con = sqlite3.connect(path)
    try:
        con.execute("PRAGMA foreign_keys=OFF")
        for sql in statements:
            try:
                con.execute(sql)
            except sqlite3.OperationalError as error:
                print("skip", path, sql, error)
        con.commit()
        print("wiped", path)
    finally:
        con.close()

wipe("/var/lib/abikan/messaging.sqlite3", [
    "DELETE FROM message",
    "DELETE FROM conversation_user_state",
    "DELETE FROM conversation_participant",
    "DELETE FROM attention_request",
    "DELETE FROM messaging_audit_event",
    "DELETE FROM conversation",
    "DELETE FROM staff_presence",
])
wipe("/var/lib/abikan/notifications.sqlite3", [
    "DELETE FROM staff_notification",
    "DELETE FROM pharmacy_unlisted_order",
])
wipe("/var/lib/abikan/attendance.sqlite3", [
    "DELETE FROM attendance_attempt",
    "DELETE FROM attendance_session",
])
wipe("/var/lib/abikan/laboratory_inventory.sqlite3", [
    "DELETE FROM lab_consumable_move",
    "DELETE FROM blood_unit",
])
wipe("/var/lib/abikan/admin-audit.sqlite3", [
    "DELETE FROM admin_export_event",
    "DELETE FROM radiology_external_study",
    "DELETE FROM laboratory_external_patient",
    "DELETE FROM anc_visit",
    "DELETE FROM anc_pregnancy",
    "DELETE FROM hospital_family_event",
])
print("sqlite done")
PY

log "Restarting abikan-api so it drops cached lists"
docker restart bahmni-standard-abikan-api-1 >/dev/null

log "Starting engines"
docker start bahmni-standard-openmrs-1 bahmni-standard-odoo-1 bahmni-standard-appointments-1 ipd >/dev/null

log "Waiting for OpenMRS"
for _ in $(seq 1 40); do
  if docker exec bahmni-standard-openmrs-1 curl -sf -o /dev/null http://localhost:8080/openmrs/ 2>/dev/null; then
    log "OpenMRS responded"
    break
  fi
  sleep 5
done

log "Starting feed workers"
docker start bahmni-standard-odoo-connect-1 bahmni-standard-openelis-1 bahmni-standard-pacs-integration-1 >/dev/null

log "Waiting for abikan-api"
for _ in $(seq 1 20); do
  status=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' bahmni-standard-abikan-api-1 2>/dev/null || echo missing)
  log "abikan-api $status"
  if [ "$status" = "healthy" ]; then
    break
  fi
  sleep 3
done

log "===== AFTER ====="
count_openmrs | tee -a "$LOG"
count_odoo | tee -a "$LOG"
count_elis | tee -a "$LOG"
log "Done. Patients, staff, catalogues, family cards, and stock on-hand were kept."
