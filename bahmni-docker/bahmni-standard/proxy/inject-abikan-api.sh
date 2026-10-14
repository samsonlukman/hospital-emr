#!/bin/sh
set -eu
CONF=/usr/local/apache2/conf/bahmni-proxy.conf
HTDOCS=/usr/local/apache2/htdocs
ABIKAN_INDEX="$HTDOCS/abikan/index.html"

if [ -f "$CONF" ] && ! grep -q "abikan-api" "$CONF"; then
  sed -i '/ProxyPassReverse \/openmrs\/auth/a\
\
# Hospital EMR Patient Account API (read-only)\
ProxyPass /openmrs/abikan-api http://abikan-api:8787/\
ProxyPassReverse /openmrs/abikan-api http://abikan-api:8787/
' "$CONF"
fi

# Exact /bahmni and /bahmni/ have no index on bahmni-web (403). Send them
# to Bahmni home. ProxyPassMatch ! must sit before ProxyPass /bahmni so
# the redirect is not swallowed. Subpaths stay proxied unchanged.
if [ -f "$CONF" ] && ! grep -q "RedirectMatch \^/bahmni" "$CONF"; then
  sed -i '1a\
RedirectMatch ^/bahmni/?$ /bahmni/home/
' "$CONF"
fi
if [ -f "$CONF" ] && ! grep -q "ProxyPassMatch \^/bahmni" "$CONF"; then
  sed -i '/ProxyPass \/bahmni http:\/\/bahmni-web:8091\/bahmni/i\
ProxyPassMatch ^/bahmni/?$ !\
' "$CONF"
fi

# Staff entry points go to Hospital EMR. Bahmni is only via /bahmni.
# Use 302 (not permanent) so browsers do not keep an old /home → Bahmni cache.
if [ -f "$CONF" ]; then
  if grep -q "Redirect permanent /home /bahmni/home/" "$CONF"; then
    sed -i 's|Redirect permanent /home /bahmni/home/|RedirectMatch 302 ^/home/?$ /abikan/|' "$CONF"
  fi
  if ! grep -q "RedirectMatch 302 ^/home/?\\$ /abikan/" "$CONF"; then
    if grep -q "RedirectMatch ^/bahmni/?\\$ /bahmni/home/" "$CONF"; then
      sed -i '/RedirectMatch \^\/bahmni\/?\$ \/bahmni\/home\//i\
RedirectMatch 302 ^/home/?$ /abikan/
' "$CONF"
    else
      sed -i '1a\
RedirectMatch 302 ^/home/?$ /abikan/
' "$CONF"
    fi
  fi
  if ! grep -q "RedirectMatch 302 ^/\\$ /abikan/" "$CONF"; then
    sed -i '/RedirectMatch 302 \^\/home\/?\$ \/abikan\//a\
RedirectMatch 302 ^/$ /abikan/
' "$CONF"
  fi
fi

# Browsers that previously cached Bahmni or a stale Hospital EMR shell must revalidate.
if [ -f "$CONF" ] && ! grep -q "Hospital EMR HTML entry cache" "$CONF"; then
  sed -i '/RedirectMatch 302 \^\/\$ \/abikan\//a\
\
# Hospital EMR HTML entry cache\
<LocationMatch "^/(index\\.html)?$">\
  Header set Cache-Control "no-cache, no-store, must-revalidate"\
</LocationMatch>\
<LocationMatch "^/abikan(/|/index\\.html|/log)?$">\
  Header set Cache-Control "no-cache, no-store, must-revalidate"\
</LocationMatch>\
<LocationMatch "^/home/?$">\
  Header set Cache-Control "no-cache, no-store, must-revalidate"\
</LocationMatch>
' "$CONF"
fi

# Keep DocumentRoot index in sync with the live Hospital EMR build (bind mount).
# Assets stay under /abikan/ (Vite base). Prefer /abikan/ as the canonical URL.
if [ -f "$ABIKAN_INDEX" ]; then
  if [ -f "$HTDOCS/index.html" ] && ! grep -q "Hospital EMR" "$HTDOCS/index.html"; then
    cp "$HTDOCS/index.html" "$HTDOCS/bahmni-landing.html"
  fi
  cp "$ABIKAN_INDEX" "$HTDOCS/index.html"
fi

# Serve Hospital EMR JS/CSS compressed. Without this, the first load over a slow link
# can sit on a blank screen for a long time while the uncompressed bundle downloads.
HTTPD_CONF=/usr/local/apache2/conf/httpd.conf
if [ -f "$HTTPD_CONF" ]; then
  sed -i 's|^#LoadModule deflate_module|LoadModule deflate_module|' "$HTTPD_CONF"
  if ! grep -q "Hospital EMR gzip" "$HTTPD_CONF"; then
    cat >> "$HTTPD_CONF" <<'EOF'

# Hospital EMR gzip
<IfModule deflate_module>
  AddOutputFilterByType DEFLATE text/html text/plain text/xml text/css text/javascript application/javascript application/json application/xml image/svg+xml
</IfModule>
EOF
  fi
fi

# Staff log terminal at /abikan/log. Serve the Hospital EMR HTML so the kiosk URL
# does not look like a missing file. Hash #/log also opens the same screen.
if [ -f "$CONF" ] && ! grep -q "Hospital EMR staff log terminal" "$CONF"; then
  sed -i '1a\
# Hospital EMR staff log terminal\
Alias /abikan/log /usr/local/apache2/htdocs/abikan/index.html
' "$CONF"
fi

exec httpd-foreground
