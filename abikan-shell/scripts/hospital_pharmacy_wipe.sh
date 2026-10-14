#!/bin/bash
# Empty the hospital Pharmacy medicine list and shelf stock so staff can add
# the medicines they actually have.
# Keeps: patients, staff, visits, lab/radiology/consultation products, bills.
# Does not docker compose down -v. Does not print secrets.
set -euo pipefail

LOG=/tmp/abikan-pharmacy-wipe.log
MAP=/opt/abikan/abikan-shell/server/patient-account/data/pharmacy_catalogue_map.json
RUNTIME=/opt/abikan/abikan-shell/server/patient-account/data/pharmacy_catalogue_runtime.json
REASON='Pharmacy restart: hospital will add current medicines'

log() { echo "[$(date -u +%H:%M:%S)] $*" | tee -a "$LOG"; }

count_openmrs() {
  docker exec bahmni-standard-openmrsdb-1 sh -c 'mysql -N -uroot -p"$MYSQL_ROOT_PASSWORD" openmrs -e "
SELECT CONCAT(\"drugs_active=\", COUNT(*)) FROM drug WHERE retired=0
UNION ALL SELECT CONCAT(\"drugs_retired=\", COUNT(*)) FROM drug WHERE retired=1
UNION ALL SELECT CONCAT(\"patients=\", COUNT(*)) FROM patient WHERE voided=0;
"'
}

count_odoo() {
  docker exec bahmni-standard-odoodb-1 psql -U odoo -d odoo -Atc "
WITH RECURSIVE cats AS (
  SELECT id FROM product_category WHERE name = 'Drugs'
  UNION
  SELECT c.id FROM product_category c JOIN cats ON c.parent_id = cats.id
)
SELECT 'drug_products_active='||count(*) FROM product_product p
  JOIN product_template t ON t.id=p.product_tmpl_id
  WHERE t.categ_id IN (SELECT id FROM cats) AND p.active
UNION ALL SELECT 'drug_stock_nonzero='||count(*) FROM stock_quant q
  JOIN product_product p ON p.id=q.product_id
  JOIN product_template t ON t.id=p.product_tmpl_id
  WHERE t.categ_id IN (SELECT id FROM cats) AND q.quantity <> 0
UNION ALL SELECT 'lab_products_active='||count(*) FROM product_product p
  JOIN product_template t ON t.id=p.product_tmpl_id
  JOIN product_category c ON c.id=t.categ_id
  WHERE p.active AND (c.name ILIKE '%lab%' OR c.complete_name ILIKE '%lab%' OR c.name ILIKE '%test%')
UNION ALL SELECT 'products_active='||count(*) FROM product_product WHERE active
UNION ALL SELECT 'partners='||count(*) FROM res_partner
UNION ALL SELECT 'sale_order='||count(*) FROM sale_order;
"
}

count_map() {
  python3 - <<'PY'
import json
from pathlib import Path
p = Path("/opt/abikan/abikan-shell/server/patient-account/data/pharmacy_catalogue_map.json")
items = json.loads(p.read_text()).get("items") or []
mapped = sum(1 for i in items if i.get("action") in {"reuse", "create"})
print(f"map_items={len(items)}")
print(f"map_mapped={mapped}")
PY
}

log "===== BEFORE ====="
count_map | tee -a "$LOG"
count_openmrs | tee -a "$LOG"
count_odoo | tee -a "$LOG"

log "Stopping medicine feed briefly"
docker stop bahmni-standard-odoo-connect-1 >/dev/null

log "Hiding the current Pharmacy list"
python3 - <<'PY'
import json, shutil, time
from pathlib import Path

map_path = Path("/opt/abikan/abikan-shell/server/patient-account/data/pharmacy_catalogue_map.json")
runtime_path = Path("/opt/abikan/abikan-shell/server/patient-account/data/pharmacy_catalogue_runtime.json")
stamp = int(time.time())
if map_path.exists():
    shutil.copy(map_path, f"{map_path}.bak.{stamp}")
    data = json.loads(map_path.read_text(encoding="utf-8"))
    for item in data.get("items") or []:
        if item.get("action") in {"reuse", "create"}:
            item["action"] = "skip"
            item["skipReason"] = "cleared_for_hospital_stock_entry"
            item["note"] = "Removed so pharmacy can add the medicines on the shelf."
    map_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print("map_skipped")
if runtime_path.exists():
    shutil.copy(runtime_path, f"{runtime_path}.bak.{stamp}")
runtime_path.write_text(json.dumps({"drugBySn": {}}, indent=2) + "\n", encoding="utf-8")
print("runtime_cleared")
PY

log "Retiring OpenMRS medicines (generics stay so staff can add again)"
docker exec -i bahmni-standard-openmrsdb-1 sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" openmrs' <<SQL
UPDATE drug
   SET retired=1,
       retired_by=1,
       date_retired=UTC_TIMESTAMP(),
       retire_reason='${REASON}'
 WHERE retired=0;
SQL

log "Archiving billing medicines and zeroing shelf stock"
docker exec -i bahmni-standard-odoodb-1 psql -U odoo -d odoo -v ON_ERROR_STOP=1 <<'SQL'
BEGIN;
CREATE TEMP TABLE pharmacy_product AS
WITH RECURSIVE cats AS (
  SELECT id FROM product_category WHERE name = 'Drugs'
  UNION
  SELECT c.id FROM product_category c JOIN cats ON c.parent_id = cats.id
)
SELECT p.id AS product_id, t.id AS tmpl_id
  FROM product_product p
  JOIN product_template t ON t.id = p.product_tmpl_id
 WHERE t.categ_id IN (SELECT id FROM cats);

UPDATE product_product
   SET active = false
 WHERE id IN (SELECT product_id FROM pharmacy_product);

UPDATE product_template
   SET active = false, sale_ok = false, purchase_ok = false
 WHERE id IN (SELECT tmpl_id FROM pharmacy_product);

UPDATE stock_quant
   SET quantity = 0,
       reserved_quantity = 0,
       inventory_quantity = 0
 WHERE product_id IN (SELECT product_id FROM pharmacy_product);

UPDATE ir_config_parameter
   SET value = '[]'
 WHERE key = 'abikan.pharmacy.hospital_catalogue';

INSERT INTO ir_config_parameter (key, value)
SELECT 'abikan.pharmacy.hospital_catalogue', '[]'
WHERE NOT EXISTS (
  SELECT 1 FROM ir_config_parameter WHERE key = 'abikan.pharmacy.hospital_catalogue'
);

COMMIT;
SQL

log "Restarting medicine feed and Pharmacy service"
docker exec bahmni-standard-odoodb-1 psql -U odoo -d odoo -v ON_ERROR_STOP=1 -c \
  "UPDATE liquibasechangeloglock SET locked=false, lockgranted=NULL, lockedby=NULL WHERE id=1 AND locked;" \
  >/dev/null || true
docker start bahmni-standard-odoo-connect-1 >/dev/null
docker restart bahmni-standard-abikan-api-1 >/dev/null

sleep 8
log "===== AFTER ====="
count_map | tee -a "$LOG"
count_openmrs | tee -a "$LOG"
count_odoo | tee -a "$LOG"
docker inspect --format '{{.State.Health.Status}}' bahmni-standard-abikan-api-1 || true
log "Pharmacy medicine list cleared. Staff can add the medicines they have."
