#!/bin/bash
# Wrapper entrypoint for wger — installs whitenoise for static file serving
# (the official image uses nginx; we serve directly from gunicorn)

pip install --break-system-packages -q whitenoise 2>/dev/null

# Compile Bootstrap SCSS → CSS (needs npm sass, uses npx for one-off)
if [ -f /home/wger/src/wger/core/static/scss/main.scss ] && ! [ -f /home/wger/src/wger/core/static/bootstrap-compiled.css ]; then
    echo "Compiling bootstrap-compiled.css from SCSS..."
    cd /home/wger/src && npx -y sass wger/core/static/scss/main.scss wger/core/static/bootstrap-compiled.css 2>/dev/null && cd /home/wger
fi

# The original entrypoint only runs collectstatic when DJANGO_DEBUG=False,
# but we need DEBUG=True for live reload. Run it here so whitenoise can serve them.
# Skip --clear to make it incremental (only copies changed/new files).
if [[ "${DJANGO_COLLECTSTATIC_ON_STARTUP:-True}" == "True" ]]; then
    echo "Running collectstatic (whitenoise wrapper, DEBUG=$DJANGO_DEBUG)"
    python3 manage.py collectstatic --no-input 2>/dev/null
fi

# Run the original entrypoint
exec /home/wger/entrypoint.sh
