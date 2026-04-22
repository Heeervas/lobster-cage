[22/4/26 12:03] Adan: Informe de auditoría interna de Hermes

- Runtime efectivo: OK
- Config principal: NO OK
- Perfiles coach/lab/vault: NO OK
- .env principal y de perfiles: NO OK
- Browser runtime real: OK
- Model runtime real: OK

Source of truth real en runtime

1) Browser / CDP
- Manda el env.
- Confirmado en código:
  - /opt/hermes/tools/browser_tool.py:262-269
  - _get_cdp_override() devuelve _resolve_cdp_override(os.environ.get("BROWSER_CDP_URL", ""))
- Resultado real dentro del runtime:
  - BROWSER_CDP_URL efectivo:
    ws://browserless:3000/chromium?token=...&stealth=true&launch={"headless":false}
  - resolved_cdp_override:
    ese mismo valor
- Conclusión explícita:
  - manda el env, no el YAML

2) Browser flags relevantes
- browser.cdp_url en YAML principal:
  - viejo/root endpoint: ws://browserless:3000?token=...
- browser.headless en YAML principal:
  - false
- browser.default_profile en YAML principal:
  - stealth
- Runtime real:
  - el browser tool está entrando por CDP override del entorno, así que browser.cdp_url del YAML queda bypassed para esta sesión
  - la sesión real visible en Browserless fue lanzada con:
    - headless: false
    - stealth: true

3) Modelo / proveedor
- Runtime efectivo actual:
  - provider resuelto: custom
  - base_url resuelto: http://clawroute:18790/v1
  - api_mode: chat_completions
  - source: pool:custom:custom-1
- Eso funciona ahora mismo.

Inspección de archivos

1) /opt/data/config.yaml
- model.default: clawroute/auto
- model.provider: custom
- model.base_url: http://clawroute:18790/v1
- model.api_key_env: CUSTOM_1_API_KEY
- browser.headless: false
- browser.default_profile: stealth
- browser.cdp_url: ws://browserless:3000?token=...
- browser.profiles.stealth.cdp_url: ws://browserless:3000?token=...
- browser.profiles.stealth.headless: false

Lectura:
- modelo principal está razonablemente alineado con el runtime
- browser.cdp_url está en drift, porque apunta al root antiguo, no al /chromium gestionado
- default_profile está OK
- headless del principal está OK

2) /opt/data/.env
- HERMES_GATEWAY_TOKEN: presente
- CUSTOM_1_API_KEY: presente
- OPENAI_BASE_URL: vacío
- NO define BROWSER_CDP_URL

Lectura:
- si el contenedor vivo realmente trae OPENAI_BASE_URL=http://clawroute:18790/v1, eso no viene de este .env
- si el contenedor vivo trae BROWSER_CDP_URL, tampoco viene de este .env
- o sea: runtime vivo depende de inyección externa / compose / entorno de arranque, no de los archivos persistidos

3) /opt/data/profiles/coach/config.yaml
- model.default: clawroute/auto
- model.provider: custom
- model.base_url: http://clawroute:18790/v1
- browser.headless: true
- browser.default_profile: stealth
- browser.cdp_url: http://browserless:3000
- profiles.stealth.cdp_url: http://browserless:3000

4) /opt/data/profiles/lab/config.yaml
- model.default: custom-1/clawroute/auto
- model.provider: auto
- model.base_url: http://clawroute:18790/v1
- browser.headless: true
- browser.default_profile: stealth
- browser.cdp_url: http://browserless:3000
- custom_providers: custom-1 -> clawroute base_url con CUSTOM_1_API_KEY

5) /opt/data/profiles/vault/config.yaml
- mismo patrón que lab:
  - provider: auto
  - default: custom-1/clawroute/auto
  - browser.headless: true
  - browser.cdp_url: http://browserless:3000
  - custom_providers presente

6) /opt/data/profiles/coach/.env
- HERMES_GATEWAY_TOKEN: presente
- OPENAI_BASE_URL: vacío
- no BROWSER_CDP_URL
- no CUSTOM_1_API_KEY visible en ese fichero

7) /opt/data/profiles/lab/.env
- HERMES_GATEWAY_TOKEN: presente
- CUSTOM_1_API_KEY: presente
- no OPENAI_BASE_URL
- no BROWSER_CDP_URL

8) /opt/data/profiles/vault/.env
- HERMES_GATEWAY_TOKEN: presente
- CUSTOM_1_API_KEY: presente
- no OPENAI_BASE_URL
- no BROWSER_CDP_URL

Prueba de ejecución: browser_tool y CDP override

Código inspeccionado: (1/4)
[22/4/26 12:03] Adan: - /opt/hermes/tools/browser_tool.py:213-269
- Lo importante:
  - _get_cdp_override() solo mira BROWSER_CDP_URL
  - si existe, normaliza/resuelve y lo usa
  - eso salta Browserbase/local launcher y conecta directo al endpoint dado

Prueba real dentro del runtime:
- env.BROWSER_CDP_URL:
  ws://browserless:3000/chromium?token=...&stealth=true&launch={"headless":false}
- config.browser.cdp_url:
  ws://browserless:3000?token=...
- resolved_cdp_override:
  ws://browserless:3000/chromium?token=...&stealth=true&launch={"headless":false}

Conclusión explícita:
- manda el env

Prueba real de navegador

Destino:
- https://www.kiwi.com

Resultado de navegación:
- URL final:
  https://www.kiwi.com/en/
- Título:
  Kiwi.com | Find Cheap Flights & Discover New Destinations

Evaluación JS:
- navigator.userAgent:
  Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36
- navigator.webdriver:
  false
- location.href:
  https://www.kiwi.com/en/
- document.title:
  Kiwi.com | Find Cheap Flights & Discover New Destinations

Lectura:
- el runtime real del browser está bien
- la señal importante sale buena: webdriver=false
- no hubo síntoma de HeadlessChrome en esta sesión

Browserless desde dentro: /sessions y /json/list

Sin token:
- /sessions -> 401
- /json/list -> 401

Con token:
- /sessions?token=... -> 200
- /json/list?token=... -> 200

La sesión aparece y es visible:
- browser:
  - type: browser
  - browser: ChromiumCDP
  - launchOptions:
    - headless: false
    - stealth: true
- page:
  - url: https://www.kiwi.com/en/
  - title: Kiwi.com | Find Cheap Flights & Discover New Destinations

Conclusión:
- sí, la sesión gestionada aparece como sesión visible en Browserless
- no es una sesión opaca ni “fantasma”; Browserless la lista correctamente

Verificación modelo/proveedor

Pruebas desde dentro:
1) GET http://clawroute:18790/v1/models
- 200 OK
- devuelve lista de modelos, incluyendo clawroute/auto

2) POST http://clawroute:18790/v1/chat/completions
- usando runtime resuelto por Hermes
- 200 OK
- respuesta válida con contenido “ok”

Resolución real de Hermes:
- resolve_requested_provider() -> custom
- resolve_runtime_provider() ->
  - provider: custom
  - base_url: http://clawroute:18790/v1
  - api_mode: chat_completions
  - source: pool:custom:custom-1

Sobre la mezcla provider/model
- Config principal:
  - provider: custom
  - model.default: clawroute/auto
  - api_key_env: CUSTOM_1_API_KEY
- Perfiles lab/vault:
  - provider: auto
  - model.default: custom-1/clawroute/auto
  - custom_providers define custom-1

Juicio:
- funcional, sí
- limpio/coherente, no del todo

Mi lectura:
- provider: custom + base_url fijo funciona hoy
- provider: auto + custom_providers también funciona hoy cuando el modelo viene nombrado como custom-1/...
- pero mezclar ambos estilos entre principal y perfiles es inconsistente operativamente
- no está roto; está feo y favorece drift y futuras confusiones

Mismatches exactos

1) Browser CDP
- Runtime efectivo:
  - BROWSER_CDP_URL=/chromium?...&stealth=true&launch={"headless":false}
- /opt/data/config.yaml:
  - browser.cdp_url=ws://browserless:3000?token=...
- coach/lab/vault config.yaml:
  - browser.cdp_url=http://browserless:3000
  - profiles.stealth.cdp_url=http://browserless:3000

2) Headless
- Runtime real de browser sesión:
  - false
- /opt/data/config.yaml:
  - false
- coach/lab/vault:
  - true

3) default_profile
- Runtime/config principal/perfiles:
  - stealth
- No mismatch real aquí

4) OPENAI_BASE_URL
- Runtime actual en este proceso:
  - null / no definido
- /opt/data/.env y coach/.env:
  - vacío
- Tú reportas que el contenedor vivo trae OPENAI_BASE_URL=http://clawroute:18790/v1
- En esta sesión/proceso no aparece
- Conclusión: (2/4)
[22/4/26 12:03] Adan: - hay inconsistencia entre “contenedor vivo externo” y el entorno visible a este proceso Hermes
  - pero no rompe el runtime de modelo actual porque este camino usa model.base_url + provider resolution, no OPENAI_BASE_URL

5) CUSTOM_1_API_KEY
- Runtime:
  - presente
- /opt/data/.env:
  - presente
- lab/.env y vault/.env:
  - presente
- coach/.env:
  - no aparece
- Riesgo:
  - coach depende de otro mecanismo o no podría resolver ese proveedor si hiciera falta

6) HERMES_GATEWAY_TOKEN
- Runtime:
  - presente
- /opt/data/.env, coach/.env, lab/.env, vault/.env:
  - presente
- Sin mismatch relevante aparente

Riesgo real de cada mismatch

1) browser.cdp_url viejo en YAML
- Riesgo: alto
- Motivo:
  - si desaparece BROWSER_CDP_URL inyectado en arranque, Hermes cae al YAML viejo/root y vuelves a HeadlessChrome/webdriver=true o a un comportamiento distinto
- Traducción:
  - ahora va bien por suerte/control externo; el persisted config sigue mal

2) headless:true en coach/lab/vault
- Riesgo: medio-alto
- Motivo:
  - si cualquiera de esos perfiles arranca sin override externo correcto, lanzará en headless
  - eso no siempre rompe, pero sí empeora stealth y te puede devolver señales viejas

3) mezcla provider: custom vs provider: auto + custom_providers
- Riesgo: medio
- Motivo:
  - funciona, pero crea dos superficies de verdad
  - mantenimiento, debugging y migraciones se vuelven más idiotas de lo necesario

4) OPENAI_BASE_URL no persistido/alineado
- Riesgo: medio-bajo para este flujo, medio para tooling auxiliar legacy
- Motivo:
  - el runtime principal actual no lo necesita para funcionar
  - pero herramientas o rutas antiguas que lean OPENAI_BASE_URL sí pueden comportarse distinto según proceso/perfil

5) coach sin CUSTOM_1_API_KEY en .env
- Riesgo: medio
- Motivo:
  - si coach usa provider custom/custom-1 por archivo y no hereda la key de fuera, puede romper resolución de credenciales

Comandos usados

- Lectura de ficheros:
  - read_file sobre:
    - /opt/data/config.yaml
    - /opt/data/.env
    - /opt/data/profiles/coach/config.yaml
    - /opt/data/profiles/coach/.env
    - /opt/data/profiles/lab/config.yaml
    - /opt/data/profiles/lab/.env
    - /opt/data/profiles/vault/config.yaml
    - /opt/data/profiles/vault/.env

- Inspección de código:
  - /opt/hermes/tools/browser_tool.py
  - /opt/hermes/hermes_cli/runtime_provider.py
  - búsquedas en /opt/hermes por BROWSER_CDP_URL, cdp_url, OPENAI_BASE_URL, custom_providers, api_key_env

- Pruebas Python dentro del runtime:
  - load_config()
  - tools.browser_tool._get_cdp_override()
  - hermes_cli.runtime_provider.resolve_requested_provider()
  - hermes_cli.runtime_provider.resolve_runtime_provider()

- Navegador real:
  - browser_navigate("https://www.kiwi.com")
  - browser_console(expression="({ userAgent, webdriver, href, title })")

- Browserless:
  - GET /sessions
  - GET /json/list
  - con y sin token

- Modelo:
  - GET http://clawroute:18790/v1/models
  - POST http://clawroute:18790/v1/chat/completions

Diff lógico exacto que propondría

1) /opt/data/config.yaml
- Mantener:
  - model.default: clawroute/auto
  - model.provider: custom
  - model.base_url: http://clawroute:18790/v1
  - model.api_key_env: CUSTOM_1_API_KEY
  - browser.default_profile: stealth
  - browser.headless: false
- Cambiar:
  - browser.cdp_url
    de:
      ws://browserless:3000?token=...
    a:
      ws://browserless:3000/chromium?token=...&stealth=true&launch={"headless":false}
  - browser.profiles.stealth.cdp_url
    de:
      ws://browserless:3000?token=...
    a:
      ws://browserless:3000/chromium?token=...&stealth=true&launch={"headless":false}
- Opcional, para dejarlo idiot-proof:
  - añadir BROWSER_CDP_URL al .env principal con ese mismo valor
  - si quieres que el source of truth sea persisted y no solo inyectado al arrancar
 (3/4)
[22/4/26 12:03] Adan: 2) /opt/data/profiles/coach/config.yaml
- Cambiar:
  - browser.headless: true -> false
  - browser.cdp_url: http://browserless:3000 -> ws://browserless:3000/chromium?token=...&stealth=true&launch={"headless":false}
  - browser.profiles.stealth.cdp_url: http://browserless:3000 -> mismo valor gestionado
- Mantener:
  - browser.default_profile: stealth
- Modelo:
  - ahora mismo está en el estilo principal:
    - provider: custom
    - default: clawroute/auto
    - base_url clawroute
  - eso está bien si quieres homogeneizar con principal

3) /opt/data/profiles/lab/config.yaml
- Browser:
  - headless: true -> false
  - cdp_url root -> /chromium gestionado
  - profiles.stealth.cdp_url root -> /chromium gestionado
- Modelo:
  - recomendaría elegir un solo estilo:
    Opción A, más simple:
    - model.default: clawroute/auto
    - model.provider: custom
    - model.base_url: http://clawroute:18790/v1
    - model.api_key_env: CUSTOM_1_API_KEY
    - eliminar dependencia conceptual de custom-1/clawroute/auto para el modelo principal
    - dejar custom_providers solo si de verdad lo necesitas para auxiliares/menús
    Esta es mi recomendación.

4) /opt/data/profiles/vault/config.yaml
- Igual que lab

5) .env principal y perfiles
- Añadir donde proceda:
  - BROWSER_CDP_URL=ws://browserless:3000/chromium?token=...&stealth=true&launch={"headless":false}
- OPENAI_BASE_URL
  - si de verdad quieres que sea parte del contrato persistido:
    - OPENAI_BASE_URL=http://clawroute:18790/v1
  - si no, mejor dejar de depender de él y usar solo model.base_url/custom provider. Mitad y mitad es la receta clásica para el dolor.
- coach/.env:
  - si coach debe poder resolver custom/custom-1 por sí solo:
    - añadir CUSTOM_1_API_KEY

Recomendación final

- El runtime real bueno está OK.
- La config persistida está en drift, sobre todo en browser.
- El mayor riesgo real es simple: hoy funciona porque manda el env; mañana quitas esa inyección o reinicias distinto y te comes el endpoint viejo otra vez.

Mi recomendación:
1) Alinear YA los YAML al endpoint gestionado /chromium con stealth=true y headless=false.
2) Poner BROWSER_CDP_URL persistido en .env principal y, si quieres perfiles autónomos, también en los .env de perfiles.
3) Homogeneizar el modelo a un solo patrón:
   - preferencia mía: model.provider=custom + model.default=clawroute/auto + model.base_url=http://clawroute:18790/v1 + api_key_env=CUSTOM_1_API_KEY
4) Dejar custom_providers solo si aporta algo real; si no, es ornamento explosivo.

Resumen en una línea:
- Runtime: bien.
- Persistencia: drift clara.
- Veredicto: manda el env. El YAML del browser sigue viejo y es deuda peligrosa. (4/4)