# gogcli fuera de Docker sin tocar compose ni .env

Esta guia reutiliza exactamente el mismo store de `gogcli` que ya monta Docker.
No cambia `docker-compose.yml` ni escribe nada nuevo en `lobster-cage/.env`.

## Que esta usando el stack ahora mismo

- `docker-compose.yml` exporta `GOG_KEYRING_BACKEND=file`
- `docker-compose.yml` exporta `GOG_KEYRING_PASSWORD=${GOG_KEYRING_PASSWORD:-}`
- `docker-compose.yml` monta `${GOGCLI_DATA_PATH}` en `/opt/data/.config/gogcli`

Eso significa que, si en host haces que `gog` use la misma carpeta `gogcli`, los tokens quedan compartidos automaticamente entre host y contenedor.

## Paso 1. Preparar el shell del host

Desde `lobster-cage/`:

```bash
cd /home/mbpro/repos/my-lobster/lobster-cage

export GOGCLI_SHARED_DIR="$(sed -n 's/^GOGCLI_DATA_PATH=//p' .env)"
export XDG_CONFIG_HOME="$(dirname "$GOGCLI_SHARED_DIR")"
export GOG_KEYRING_BACKEND=file
export GOG_KEYRING_PASSWORD="$(sed -n 's/^GOG_KEYRING_PASSWORD=//p' .env)"
```

Con eso, `gog` en host pasa a leer y escribir en:

```bash
$XDG_CONFIG_HOME/gogcli
```

## Paso 2. Verificar que apunta al store compartido

```bash
gog auth keyring
gog auth status
gog auth credentials list
```

Debes ver backend `file` y una ruta dentro de `XDG_CONFIG_HOME/gogcli`.

## Paso 3. Guardar el OAuth client si aun no esta

Si aun no habias metido el `credentials.json` en ese store compartido:

```bash
gog auth credentials ~/Downloads/client_secret.json
```

Si ya existe, puedes saltarte este paso.

## Paso 4. Autenticar la cuenta en host

Flujo normal con navegador local:

```bash
gog auth add tu-correo@gmail.com --services all
```

Si prefieres un flujo manual:

```bash
gog auth add tu-correo@gmail.com --services all --manual
```

Si quieres minimo privilegio, cambia `--services all` por algo mas concreto, por ejemplo:

```bash
gog auth add tu-correo@gmail.com --services gmail,calendar,drive,docs,sheets
```

## Paso 5. Validar que quedo bien

```bash
gog auth list --check
gog auth status
```

## Paso 6. Usarlo ya desde Docker

No hay que tocar nada mas.

Hermes y OpenClaw ya montan esa misma carpeta del host, asi que el token que acabas de guardar fuera del contenedor queda disponible dentro del contenedor en el siguiente uso.

## Atajo opcional para no exportar variables cada vez

Puedes meter esta funcion en tu `~/.bashrc` o `~/.zshrc` local:

```bash
gog-shared() {
  local cage_dir="/home/mbpro/repos/my-lobster/lobster-cage"
  local shared_dir

  shared_dir="$(sed -n 's/^GOGCLI_DATA_PATH=//p' "$cage_dir/.env")"

  XDG_CONFIG_HOME="$(dirname "$shared_dir")" \
  GOG_KEYRING_BACKEND=file \
  GOG_KEYRING_PASSWORD="$(sed -n 's/^GOG_KEYRING_PASSWORD=//p' "$cage_dir/.env")" \
  gog "$@"
}
```

Uso:

```bash
gog-shared auth status
gog-shared auth credentials ~/Downloads/client_secret.json
gog-shared auth add tu-correo@gmail.com --services all
gog-shared auth list --check
```