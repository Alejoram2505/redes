# Guion de exposición con la GUI (7–8 minutos)

Este es el recorrido principal para presentar el proyecto. Durante la exposición se utiliza una sola terminal para abrir la interfaz gráfica; no se ejecutan manualmente todos los servidores ni los comandos de instalación. La GUI inicia los servidores locales, conecta Render y ejecuta las demostraciones.

## 1. Preparación antes de entrar al salón

Hacer esto con anticipación, no frente al catedrático:

```powershell
cd C:\ruta\al\proyecto1
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-official-mcp.txt
python -m pip install -r requirements-dev.txt
python -m unittest discover -v
```

El resultado esperado de la última instrucción es `Ran 22 tests` y `OK`.

También preparar lo siguiente:

1. confirmar que Render muestre el servicio como **Live**;
2. abrir una vez `https://plant-energy-mcp.onrender.com/health` y verificar `{"status":"ok"}`;
3. tener disponibles la API key de Gemini y el token MCP configurado en Render;
4. cerrar programas y notificaciones que puedan revelar información privada;
5. guardar previamente una captura Wireshark real y sanitizada como respaldo;
6. ejecutar la demo completa una vez para evitar descargas de `npx` durante la exposición.

No mostrar, dictar ni pegar las claves en una terminal visible. Los campos de la GUI las ocultan y solo las conservan durante el proceso actual.

## 2. Abrir y preparar la interfaz

Usar una sola ventana de PowerShell:

```powershell
cd C:\ruta\al\proyecto1
.\.venv\Scripts\Activate.ps1
python -m project_gui
```

En el panel:

1. pegar la API key en **API key de Gemini**;
2. conservar el modelo `gemini-3.1-flash-lite`;
3. conservar la URL MCP `https://plant-energy-mcp.onrender.com/mcp`;
4. pegar el token privado en **Token MCP de Render**;
5. dejar seleccionados **Industrial local**, **Filesystem oficial**, **Git oficial** e **Industrial remoto**;
6. pulsar **Conectar proyecto**.

Resultado esperado: estado **Conectado · 4 servidores** y el número de herramientas descubiertas. El aviso sobre Git usando el intérprete de Python no es un error si el servidor se conectó.

## 3. Guion minuto a minuto

### 0:00–0:40 — problema y objetivo

Mantener visible la pestaña **Conversación** y decir:

> Este proyecto implementa un chatbot anfitrión para monitoreo energético industrial. El anfitrión se conecta a Gemini, conserva contexto durante la sesión y coordina cuatro servidores MCP: el industrial local, su equivalente remoto en Render y los servidores oficiales Filesystem y Git. El cliente, JSON-RPC y los transportes MCP fueron implementados manualmente, sin FastMCP ni un SDK MCP.

No abrir código todavía. Primero demostrar funcionamiento.

### 0:40–1:15 — conexión y arquitectura

Señalar los cuatro servidores marcados y pulsar **Comprobar Render**. La GUI cambia a **Demostraciones**.

Resultado esperado:

```text
HTTP 200 · https://plant-energy-mcp.onrender.com/health
{"status":"ok"}
```

Decir:

> El anfitrión inicia los servidores locales como subprocesos mediante stdio. Para Render usa HTTPS. Antes de ofrecer herramientas, cada cliente ejecuta `initialize`, envía `notifications/initialized` y solicita `tools/list`.

Volver a **Conversación**.

### 1:15–2:15 — selector `/tools` y llamada MCP directa

Escribir y enviar:

```text
/tools
```

También se puede pulsar **Herramientas**. En el selector:

1. elegir `plant_remote__list_equipment`;
2. dejar los parámetros como `{}`;
3. pulsar **Ejecutar herramienta**.

Mostrar el resultado JSON con `chiller-01`, `compressor-01` y `press-01`.

Decir:

> Esta llamada no usa Gemini. La GUI toma la herramienta descubierta, envía `tools/call` directamente al servidor MCP de Render y presenta su respuesta estructurada. Así separo claramente el funcionamiento de MCP de la disponibilidad del LLM.

Si se escribe exactamente `plant_remote__list_equipment` en la entrada, la GUI también la ejecuta directamente con `{}`.

### 2:15–2:55 — log y secuencia JSON-RPC

Pulsar **Ver log** o escribir:

```text
/log
```

La GUI abre **Demostraciones** y muestra las entradas recientes. Localizar una entrada con:

```text
server: plant-remote
transport: streamable-http
method: tools/call
```

Señalar también dirección, `id`, duración y respuesta. Decir:

> El identificador correlaciona solicitud y respuesta. El log registra hora, servidor, transporte, dirección, método y duración, pero redacta claves, tokens y rutas privadas.

Volver a **Conversación**.

### 2:55–3:45 — Gemini y contexto conversacional

Pulsar **Alan Turing** y después **Enviar**. Cuando responda, pulsar **Continuación** y **Enviar**.

Las preguntas son:

```text
¿Quién fue Alan Turing?
¿En qué año nació?
```

Decir:

> La segunda pregunta no repite el nombre. Gemini entiende que se refiere a Alan Turing porque el anfitrión conserva el historial únicamente durante la sesión activa.

Esta parte demuestra la conexión real con el LLM y el contexto; no necesita herramientas MCP.

### 3:45–4:40 — Gemini usando el MCP remoto

Escribir:

```text
Usa plant_remote__get_energy_report y dime en español qué equipo supera su umbral. No muestres el JSON completo.
```

Decir mientras se procesa:

> Ahora Gemini recibe las definiciones de herramientas. El modelo elige `plant_remote__get_energy_report`; el anfitrión ejecuta la llamada en Render, devuelve el resultado estructurado al modelo y Gemini genera la explicación final.

Resultado esperado: `compressor-01` supera su umbral; `chiller-01` y `press-01` aparecen normales. La comunicación sigue este orden:

```text
usuario → Gemini → MCP Render → Gemini → respuesta
```

Gemini 3 requiere conservar su `thought_signature` cifrada entre las dos llamadas; el adaptador la reenvía sin modificarla.

### 4:40–5:30 — Filesystem y Git oficiales

Entrar a **Demostraciones** y pulsar **3 Filesystem + Git**.

Mientras se ejecuta, decir:

> La demostración crea un repositorio temporal dentro de `demo_workspace`. Filesystem escribe un README; Git lo agrega al índice y crea un commit. Nunca utiliza el repositorio principal.

Mostrar:

- la ruta única del repositorio temporal;
- `Successfully wrote`;
- `Files staged successfully`;
- el hash del commit.

El hash y el nombre del directorio cambian en cada ejecución.

### 5:30–6:10 — paridad local y remota

Pulsar **2 Local ↔ remoto**.

Mostrar:

```json
"equal": true
```

Señalar los tres equipos y el total de `548.0 kWh`. Decir:

> El servidor local usa stdio y el remoto usa HTTPS, pero ambos reutilizan la misma lógica, los mismos nombres de herramientas y los mismos esquemas. `equal: true` prueba la paridad funcional con datos deterministas.

### 6:10–6:40 — pruebas automatizadas

Pulsar **4 Pruebas**.

Mostrar al final:

```text
Ran 22 tests
OK
```

Decir:

> Las pruebas no necesitan una clave real ni recursos con costo. Cubren JSON-RPC, handshake, herramientas, validación, contexto, stdio, HTTP, autenticación, timeouts, cierre, redacción, GUI, reintentos del LLM, `thought_signature` y ejecución directa sin Gemini.

No ejecutar Ruff, mypy ni `compileall` durante la exposición salvo que lo soliciten; son verificaciones previas.

### 6:40–7:35 — Wireshark y las cuatro capas

Mostrar la captura preparada del tráfico generado al ejecutar directamente `plant_remote__list_equipment`.

Primero enseñar el flujo DNS:

```wireshark
dns.qry.name contains "plant-energy-mcp.onrender.com"
```

Después enseñar el inicio TLS o la conexión resuelta:

```wireshark
tls.handshake.extensions_server_name contains "plant-energy-mcp.onrender.com"
```

Si se identificó la IP real en la respuesta DNS, usar:

```wireshark
ip.addr == DIRECCION_OBSERVADA and tcp.port == 443
```

Explicar solamente datos realmente visibles:

- **Enlace:** la interfaz capturada y las direcciones de la trama local; Windows puede presentarla como Ethernet II aunque la interfaz física sea Wi‑Fi.
- **Red:** consulta DNS y direcciones IPv4 o IPv6 observadas.
- **Transporte:** UDP 53 para DNS y TCP 443 para HTTPS; señalar SYN, SYN/ACK y ACK si están en la captura.
- **Aplicación:** DNS es visible; MCP viaja sobre HTTPS/TLS. El JSON-RPC permanece cifrado, por lo que el método `tools/call` se demuestra correlacionando la hora con el log MCP.

Decir:

> No afirmo que Wireshark muestre el JSON-RPC si TLS continúa cifrado. La captura demuestra el flujo de red hacia Render y el log de la aplicación demuestra el método MCP asociado.

No usar **Seguir flujo UDP** para buscar HTTPS: esa opción muestra únicamente la consulta y respuesta DNS. Para la conexión remota seleccionar un paquete TCP 443 y usar **Seguir flujo TCP**.

### 7:35–8:00 — dificultades, seguridad y cierre

Decir:

> Las principales dificultades fueron separar JSON-RPC de los logs humanos, mantener la misma lógica en stdio y HTTP, y conservar la firma de razonamiento que Gemini 3 exige durante function calling. Se resolvieron reservando stdout para protocolo, reutilizando un dispatcher común y preservando la `thought_signature`. Las rutas se restringen a `demo_workspace`, las acciones sensibles piden confirmación y los secretos nunca se imprimen en el log.

Cerrar con:

> El resultado es una arquitectura desacoplada: puedo cambiar el proveedor del LLM o el transporte del servidor sin reescribir el caso de uso industrial.

## 4. Plan de contingencia durante la exposición

### Gemini devuelve HTTP 503

El adaptador reintenta cuatro veces con espera creciente. Si los cuatro intentos fallan:

1. explicar que es saturación temporal del proveedor;
2. demostrar MCP mediante `/tools` y `plant_remote__list_equipment`, que no usan Gemini;
3. continuar con log, Filesystem/Git, paridad y pruebas;
4. no cambiar la API key ni el token de Render.

### Gemini devuelve HTTP 400 al usar herramientas

Cerrar la GUI y volver a ejecutar `python -m project_gui` para asegurar que se cargó la versión actual. Esta conserva `extra_content.google.thought_signature`. Si persiste, mostrar el mensaje estructurado del proveedor sin revelar secretos y usar la ejecución directa.

### Render está dormido

Pulsar **Comprobar Render**, esperar hasta un minuto y repetir. No iniciar un servidor localhost para presentarlo como si fuera la nube.

### Git muestra el aviso del intérprete

No es un fallo si la conexión termina y la demo muestra `Files staged successfully` y un hash. Significa que el servidor Git oficial se ejecutó desde el entorno virtual porque `uvx` no estaba disponible.

### Wireshark no muestra DNS

El dominio puede estar en caché. Usar el filtro TLS por nombre de servidor o la IP realmente observada. Nunca inventar IP, puerto, duración o contenido descifrado.

## 5. Lo que no debe hacerse durante la presentación

- No mostrar API keys, tokens, `.env` ni archivos de claves TLS.
- No ejecutar todos los comandos del README uno detrás de otro.
- No iniciar `plant_energy_mcp` manualmente mientras la GUI ya está conectada.
- No ejecutar simultáneamente el servidor HTTP local y Docker en el mismo puerto 8080.
- No usar el repositorio principal para la demo Filesystem/Git.
- No afirmar que un 503 de Gemini significa que Render o MCP fallaron.
- No presentar una consulta DNS seguida por UDP como si fuera el flujo HTTPS; DNS y MCP son comunicaciones distintas.
- No decir que se observó JSON-RPC dentro de TLS si la captura no fue descifrada legítimamente.

## 6. Respuestas cortas para preguntas probables

**¿Qué implementaron manualmente?**

El anfitrión, los clientes MCP, JSON-RPC, el servidor industrial, el transporte stdio y el adaptador HTTP. No se utilizó FastMCP ni un SDK MCP.

**¿Qué partes son externas?**

Gemini como LLM, Render como alojamiento y los servidores oficiales Filesystem y Git requeridos por la guía.

**¿Por qué `/tools` funciona cuando Gemini está caído?**

Porque el selector ejecuta directamente el cliente MCP; Gemini solo es necesario cuando se quiere interpretar la intención o redactar una respuesta natural.

**¿Qué demuestra `equal: true`?**

Que la misma operación industrial devuelve el mismo resultado mediante el servidor local stdio y el servidor remoto HTTPS.

**¿Dónde vive el contexto?**

En memoria dentro de `ChatSession` durante la sesión activa. No se persiste al cerrar.

**¿Por qué no se ve JSON-RPC en Wireshark?**

Porque HTTPS lo cifra con TLS. Wireshark demuestra DNS, IP, TCP y TLS; el log MCP correlacionado demuestra el método de aplicación.

**¿Cómo se protege Filesystem?**

Solo recibe acceso a `demo_workspace`, no a todo el equipo.

**¿Por qué se confirma una herramienta sensible?**

Porque escrituras, movimientos y commits tienen efectos laterales y no deben ejecutarse solo por decisión del modelo.
