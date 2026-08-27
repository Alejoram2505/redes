# Servidor MCP de energía industrial

[English documentation](README.md)

`plant-energy-mcp` es un servidor local del Model Context Protocol (MCP) para un caso industrial pequeño de gestión energética. Permite consultar equipos, registrar lecturas acumuladas, calcular consumo, detectar alertas por umbral y generar reportes.

La implementación de MCP es manual sobre JSON-RPC 2.0. **No utiliza FastMCP, SDK de MCP ni frameworks que oculten el intercambio del protocolo.**

## Alcance de la entrega parcial

Esta entrega incluye únicamente el servidor MCP local definido por el estudiante:

- versión objetivo de MCP `2025-11-25`;
- transporte local `stdio`;
- un mensaje JSON por línea;
- `initialize` y `notifications/initialized`;
- `ping`, `tools/list` y `tools/call`;
- errores JSON-RPC para JSON inválido, solicitudes o parámetros inválidos, métodos desconocidos y fallos internos;
- cinco herramientas para gestión energética;
- demostración reproducible y pruebas de integración ejecutadas contra un subproceso real.

No incluye servidor MCP remoto, nube, Wireshark, análisis OSI/TCP-IP, interfaz gráfica ni reporte final.

## Arquitectura

```text
Cliente MCP / demo.py
        |
        | JSON-RPC 2.0 por stdin/stdout, un JSON por línea
        v
plant_energy_mcp/server.py       transporte stdio
        |
plant_energy_mcp/protocol.py     ciclo MCP, parser, despacho y errores
        |
plant_energy_mcp/tools.py        esquemas y validación de herramientas
        |
plant_energy_mcp/service.py      reglas de negocio y datos de demostración
```

Los mensajes humanos se escriben en `stderr`. Las respuestas JSON-RPC son el único contenido enviado a `stdout`.

### Estructura de archivos

```text
plant_energy_mcp/   paquete del servidor
tests/              pruebas de integración por subproceso
demo.py             cliente mínimo para demostrar el ciclo completo
.env.example        plantilla segura de configuración
README.md           documentación obligatoria en inglés
README_ES.md        documentación en español
```

## Requisitos

- Python 3.10 o superior.
- No se requieren paquetes de terceros.

## Instalación

### PowerShell

```powershell
git clone https://github.com/Alejoram2505/redes.git
cd redes
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m unittest discover -v
```

### Linux o macOS

```bash
git clone https://github.com/Alejoram2505/redes.git
cd redes
python3 -m venv .venv
. .venv/bin/activate
python -m unittest discover -v
```

No existe un comando para instalar dependencias porque el proyecto utiliza solamente la biblioteca estándar de Python.

## Variables de entorno

El servidor actual no requiere variables de entorno. `.env.example` lo documenta explícitamente. No se deben guardar archivos `.env`, claves API, credenciales, lecturas reales ni otros datos sensibles en Git.

## Ejecutar el servidor

```bash
python -m plant_energy_mcp
```

El proceso espera mensajes JSON-RPC de una sola línea por `stdin`. Al cerrar la entrada estándar, el servidor termina limpiamente.

## Ejecutar las pruebas

```bash
python -m unittest discover -v
```

Las pruebas inician el servidor real como subproceso y verifican:

- handshake y orden de inicialización;
- `ping` y `tools/list`;
- ejecución exitosa de las cinco herramientas;
- validación de parámetros y errores principales;
- contenido exclusivamente JSON en `stdout`;
- finalización limpia al cerrar `stdin`.

## Ejecutar la demostración

```bash
python demo.py
```

La salida esperada demuestra:

1. `initialize` devuelve la versión `2025-11-25` y el servidor `plant-energy-mcp`.
2. `tools/list` devuelve cinco herramientas con sus esquemas JSON Schema.
3. `calculate_consumption` calcula `220.0 kWh` y `55.0 kWh/h` para `press-01`.
4. `detect_usage_alerts` devuelve `status: normal` para ese período.
5. El servidor termina con código `0` cuando el harness cierra `stdin`.

## Especificación del servidor MCP

El transporte utiliza JSON delimitado por saltos de línea. Cada mensaje de entrada y salida ocupa exactamente una línea. Las solicitudes siguen JSON-RPC 2.0 y las respuestas conservan el `id` recibido.

### Ciclo de inicialización

El orden obligatorio es:

```text
solicitud initialize
respuesta initialize
notificación notifications/initialized sin respuesta
solicitudes ping, tools/list o tools/call
```

Una solicitud de herramientas antes de completar el ciclo devuelve el error `-32002`.

### Métodos soportados

| Método | Propósito |
|---|---|
| `initialize` | Negocia la versión de MCP y las capacidades del servidor. |
| `notifications/initialized` | Confirma que el cliente terminó la inicialización; no produce respuesta. |
| `ping` | Confirma que el servidor inicializado responde. |
| `tools/list` | Devuelve nombres, descripciones y esquemas de las herramientas. |
| `tools/call` | Valida parámetros y ejecuta una herramienta. |

### Errores JSON-RPC

| Código | Significado |
|---:|---|
| `-32700` | JSON inválido o error de análisis |
| `-32600` | Solicitud JSON-RPC inválida |
| `-32601` | Método desconocido |
| `-32602` | Parámetros del método o herramienta inválidos |
| `-32603` | Error interno sin exponer detalles privados |
| `-32002` | El ciclo de inicialización no ha terminado |

## Herramientas MCP

### `list_equipment`

Lista los equipos ficticios registrados. Acepta el parámetro opcional `area`, cuyo valor puede ser `Forming` o `Utilities`.

```json
{"area":"Utilities"}
```

### `record_energy_reading`

Registra una lectura acumulada durante la sesión actual. La fecha debe incluir zona horaria, ser posterior a la última lectura y no estar duplicada. La energía acumulada no puede disminuir.

```json
{"equipment_id":"press-01","timestamp":"2026-08-20T13:00:00Z","energy_kwh":12770}
```

### `calculate_consumption`

Resta dos lecturas acumuladas existentes y calcula el consumo promedio por hora. Ambas fechas deben coincidir exactamente con lecturas registradas.

```json
{"equipment_id":"press-01","start_timestamp":"2026-08-20T08:00:00Z","end_timestamp":"2026-08-20T12:00:00Z"}
```

Respuesta estructurada de ejemplo:

```json
{"equipment_id":"press-01","start_timestamp":"2026-08-20T08:00:00Z","end_timestamp":"2026-08-20T12:00:00Z","consumption_kwh":220.0,"average_kwh_per_hour":55.0}
```

### `detect_usage_alerts`

Recibe los mismos parámetros de período que `calculate_consumption` y compara el consumo promedio con el umbral configurado para el equipo.

### `get_energy_report`

Resume el consumo desde la primera hasta la última lectura de cada equipo. Acepta el filtro opcional `area` con los valores `Forming` o `Utilities`.

```json
{}
```

## Ejemplo JSON-RPC manual

Ejecuta `python -m plant_energy_mcp` y pega cada objeto JSON en una sola línea:

```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"manual-client","version":"1.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}
{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"calculate_consumption","arguments":{"equipment_id":"press-01","start_timestamp":"2026-08-20T08:00:00Z","end_timestamp":"2026-08-20T12:00:00Z"}}}
```

La notificación `notifications/initialized` no genera respuesta. Cada una de las demás líneas devueltas por `stdout` es una respuesta JSON-RPC válida.

## Guion de demostración

1. Explica que las lecturas acumuladas deben convertirse en consumo comprensible y alertas operativas.
2. Muestra las cuatro capas de la arquitectura.
3. Ejecuta `python demo.py` para demostrar inicialización, descubrimiento, cálculo y evaluación de alertas.
4. Envía un `tools/call` con un `equipment_id` desconocido para mostrar un error controlado `-32602`.
5. Ejecuta `python -m unittest discover -v` y muestra las pruebas aprobadas.

## Datos y reinicio

Los equipos y lecturas iniciales son datos ficticios y deterministas. Las nuevas lecturas existen únicamente en la memoria del proceso. Reiniciar el servidor restaura los datos originales; no se modifican archivos ni bases de datos.

## Seguridad

- El servidor no ejecuta código, comandos del sistema ni solicitudes de red.
- No permite leer rutas arbitrarias.
- Rechaza campos desconocidos, tipos incorrectos, parámetros faltantes, equipos inexistentes, fechas fuera de orden, valores acumulados decrecientes y valores excesivos.
- Los errores enviados al cliente no contienen stack traces, rutas privadas ni secretos.
- Todos los datos de demostración son ficticios.
- `stdout` se reserva para JSON-RPC y los mensajes humanos se envían a `stderr`.

## Limitaciones

- El estado existe solamente en memoria y no se comparte entre procesos.
- El cálculo requiere fechas que coincidan exactamente con lecturas registradas.
- Los umbrales son valores ficticios, no recomendaciones de ingeniería.
- No hay autenticación porque el transporte es un subproceso local por `stdio`.
- El estado del servidor industrial se conserva en memoria y se reinicia al cerrar la sesión.

## Estado de la integración final

La implementación final amplía este servidor local con los siguientes componentes:

- chatbot de terminal con adaptadores configurables para OpenAI y Anthropic;
- contexto conversacional en memoria durante la sesión;
- log correlacionado y sanitizado de solicitudes y respuestas MCP;
- integración de los servidores oficiales Filesystem y Git en un espacio aislado;
- transporte HTTP con sesiones para ejecutar el mismo servidor industrial de forma remota;
- pruebas automatizadas de protocolo, herramientas, contexto, logging y paridad de transportes.

La documentación vigente de la solución completa está en `README.md`, `docs/FINAL_REPORT.md` y
`docs/PRESENTATION_GUIDE.md`. La ejecución con servicios externos depende de credenciales provistas mediante variables de
entorno; el repositorio no contiene secretos.

## Lista de verificación antes de entregar

```bash
python -m unittest discover -v
python demo.py
git status --short
git diff --check
git log --oneline --decorate -n 15
```

También se debe verificar manualmente que el repositorio siga siendo privado y que el catedrático y los auxiliares tengan acceso.

## Referencias

- Especificación de Model Context Protocol `2025-11-25`: <https://modelcontextprotocol.io/specification/2025-11-25>
- Especificación JSON-RPC 2.0: <https://www.jsonrpc.org/specification>
