# Reporte final — Proyecto 1: uso de un protocolo existente

## 1. Estado de cumplimiento

| Inciso | Requisito | Estado y evidencia |
|---:|---|---|
| 1 | Conexión con LLM | Adaptadores implementados y pruebas deterministas aprobadas. El estudiante verificó una llamada real a Gemini `gemini-3.1-flash-lite` mediante su endpoint compatible con OpenAI. |
| 2 | Contexto conversacional | Implementado en memoria por sesión y probado con doble de LLM. |
| 3 | Log MCP visible | Implementado en JSONL, visible con `/log`, con redacción probada. |
| 4 | Filesystem y Git oficiales | Implementado y probado en repositorio aislado el 26-08-2026. |
| 5 | Servidor MCP local propio | Implementado y probado: `plant-energy-mcp`, cinco herramientas. |
| 6 | Mismo servidor remoto | Desplegado en Render y probado mediante `https://plant-energy-mcp.onrender.com/mcp`; la paridad local/remota devolvió `equal: true`. |
| 7 | Captura Wireshark | Wireshark/TShark 4.6.7 está instalado y se verificó una captura HTTP local de ensayo. La captura HTTPS final contra Render sigue pendiente. |
| 8 | Especificación | Documentada aquí y en README. |
| 9 | Capas de red | Metodología de análisis documentada; no se reportan valores de red sin una captura real. |
| 10 | Conclusiones | Incluidas con el alcance y las limitaciones de la verificación ejecutada. |

## 2. Arquitectura

El anfitrión mantiene el historial de la sesión, envía mensajes y esquemas de herramientas al LLM, interpreta llamadas a herramientas y solicita autorización para efectos laterales. Se ofrece tanto la terminal original como `project_gui`, una interfaz gráfica que centraliza conversación, log y demostraciones sin sustituir el protocolo manual. Cada herramienta tiene un nombre con prefijo del servidor para evitar colisiones. Los clientes MCP manuales realizan `initialize`, reciben la versión negociada, envían `notifications/initialized`, descubren `tools/list` y ejecutan `tools/call`.

Los servidores locales se ejecutan como subprocesos con JSON delimitado por salto de línea sobre stdin/stdout. El remoto emplea un único endpoint `/mcp` con JSON-RPC sobre HTTP. Ambos adaptadores del servidor industrial reutilizan `McpDispatcher`, `ToolRegistry` y `EnergyService`; por ello no duplican lógica de negocio.

## 3. Especificación MCP industrial

- Nombre: `plant-energy-mcp`.
- Versión MCP: `2025-11-25`.
- JSON-RPC: `2.0`.
- Transportes: stdio local y Streamable HTTP remoto.
- Estado: lecturas acumulativas en memoria por instancia/sesión.

### Herramientas

1. `list_equipment(area?)`: lista equipos, opcionalmente `Forming` o `Utilities`.
2. `record_energy_reading(equipment_id, timestamp, energy_kwh)`: agrega una lectura acumulativa posterior a la última. Rechaza duplicados, retrocesos temporales o de energía y valores fuera de rango.
3. `calculate_consumption(equipment_id, start_timestamp, end_timestamp)`: exige dos marcas ya registradas y calcula kWh y promedio horario.
4. `detect_usage_alerts(...)`: compara el promedio con el umbral del equipo.
5. `get_energy_report(area?)`: resume consumo y estado por equipo.

Los esquemas completos viven en `plant_energy_mcp/tools.py` y son la fuente que retorna `tools/list`. Los resultados incluyen contenido textual y `structuredContent`. Los códigos relevantes son `-32700` parseo, `-32600` solicitud inválida, `-32601` método desconocido, `-32602` parámetros/versión incompatibles, `-32603` fallo interno seguro y `-32002` servidor no inicializado.

### Secuencia JSON-RPC

```text
Cliente -> initialize (id=1, protocolVersion=2025-11-25)
Servidor -> result (id=1, capabilities y serverInfo)
Cliente -> notifications/initialized (sin id)
Cliente -> tools/list (id=2)
Servidor -> result (id=2, tools[])
Cliente -> tools/call (id=3, name + arguments)
Servidor -> result o error (id=3)
```

El cliente correlaciona respuestas por `id`, permite notificaciones sin `id`, detecta texto inválido, final inesperado del proceso y timeout. stdout del servidor stdio contiene únicamente JSON-RPC; los mensajes humanos van a stderr.

## 4. Servidores oficiales

Filesystem se ejecuta con el paquete oficial `@modelcontextprotocol/server-filesystem` y recibe únicamente `demo_workspace`. Git usa el paquete oficial `mcp-server-git` y recibe únicamente `demo_workspace/git_repo`. Aunque esos servidores externos usan sus dependencias oficiales, el anfitrión, cliente y servidor propios no usan un SDK MCP.

La demostración real del 26-08-2026 inicializó un repositorio aislado, creó `README.md` con `write_file`, lo agregó con `git_add` y produjo un commit con `git_commit`. El repositorio principal no fue usado por esa automatización.

## 5. Transporte HTTP remoto

`POST /mcp` procesa JSON-RPC. `GET /mcp` responde 405 porque no se ofrece un canal SSE independiente. `DELETE /mcp` elimina una sesión y `GET /health` comprueba salud sin confundirse con MCP.

La inicialización crea un identificador criptográficamente aleatorio y lo devuelve en `MCP-Session-Id`. Solicitudes posteriores deben incluirlo y enviar `MCP-Protocol-Version: 2025-11-25`. Se validan `Origin`, `Content-Type: application/json`, `Accept: application/json, text/event-stream`, tamaño máximo, autenticación y estructura JSON. Una escucha fuera de loopback exige `PLANT_MCP_AUTH_TOKEN`. Los errores HTTP no revelan trazas internas.

La prueba contra Render devolvió `equal: true` para `get_energy_report`: local y remoto reportaron 3 equipos, 548.0 kWh totales y los mismos estados. Antes de la prueba, `https://plant-energy-mcp.onrender.com/health` respondió HTTP 200 cinco veces consecutivas. El endpoint `/mcp` está protegido mediante `PLANT_MCP_AUTH_TOKEN`, almacenado como variable secreta del servicio y no en el repositorio.

Se intentó `docker build -t plant-energy-mcp:local .`, pero Docker Desktop no tenía activo el motor Linux (`dockerDesktopLinuxEngine`). Por lo tanto, el Dockerfile está preparado pero su build no se presenta como aprobado.

## 6. LLM, contexto y seguridad

El LLM se configura exclusivamente con `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL` y `LLM_BASE_URL`. La clave no se imprime ni se registra. El contexto se conserva solo en `ChatSession.messages` hasta cerrar el proceso. Las pruebas usan un LLM falso: comprueban que una pregunta genera una llamada MCP, que el resultado vuelve al modelo y que los mensajes anteriores continúan presentes.

Las operaciones cuyo nombre implica escribir, crear, eliminar, mover, agregar, confirmar cambios o registrar datos requieren confirmación. El anfitrión no expone ejecución arbitraria de comandos. El log redacta claves, tokens, autorización, contraseñas, secretos, raíz privada del proyecto y contenido excesivamente largo.

## 7. Alcance de la captura Wireshark

Se realizó una captura local de ensayo sobre el adaptador loopback y el puerto 8080: registró 54 paquetes, tres solicitudes `POST /mcp` y una `DELETE /mcp`; la demo produjo `equal: true`. El servidor remoto ya está disponible en Render, pero todavía debe realizarse y documentarse la captura HTTPS final contra ese dominio.

### Procedimiento reproducible

1. Abrir `https://plant-energy-mcp.onrender.com/health` y esperar HTTP 200 para despertar la instancia gratuita.
2. Ejecutar `Resolve-DnsName plant-energy-mcp.onrender.com` y seleccionar en Wireshark la interfaz Wi-Fi/Ethernet que transporta esa conexión.
3. Filtro de captura: `host IP_RESUELTA and tcp port 443`.
4. Iniciar captura y ejecutar `python -m demos.local_remote_parity_demo` con la URL remota.
5. Filtro de visualización: `dns or tcp.port == 443 or tls or http2`.
6. Para descifrado legítimo del cliente propio, definir `SSLKEYLOGFILE` antes de ejecutar Python y configurar ese archivo en Preferences > Protocols > TLS. Nunca publicar el token ni tráfico personal.
7. Sanitizar y guardar solo la evidencia necesaria.

### Disponibilidad de evidencia en el entorno verificado

| Campo real | Valor |
|---|---|
| Fecha/hora | No observada: captura no disponible |
| Interfaz y tipo de enlace | No observado |
| MAC origen/destino o explicación del enlace | No observado |
| DNS consultado y respuestas | No observado |
| IP local/remota | No observada |
| Puerto origen/destino | No observado |
| SYN, SYN-ACK, ACK y cierre | No observado |
| TLS versión/cifrado/ALPN | No observado |
| HTTP método, ruta y estado | No observado; requiere captura y descifrado legítimo |
| JSON-RPC método/id | No observado; requiere captura y descifrado legítimo |
| Latencia observada | No observada |

## 8. Análisis por capas (marco, no observación inventada)

- Enlace: describir Ethernet o 802.11 según la interfaz y las direcciones visibles. En una captura Wi-Fi administrada, la MAC de destino normalmente pertenece al siguiente salto local, no al servidor cloud; debe verificarse.
- Red: registrar IPv4/IPv6, DNS y encaminamiento observable. TTL, fragmentación e ICMP solo se mencionarán si aparecen.
- Transporte: identificar puertos efímeros, puerto 443, handshake TCP, números de secuencia/retransmisiones y cierre, o QUIC/UDP si la conexión real lo usa.
- Aplicación: describir TLS, ALPN y HTTP. Los mensajes JSON-RPC solo pueden afirmarse si la sesión fue descifrada legítimamente; de otro modo se describen como datos cifrados y se correlacionan por tiempo con el log MCP.

## 9. Dificultades y lecciones

- La distribución actual del servidor Git oficial es Python (`mcp-server-git`) y depende del SDK oficial; se mantuvo como servidor externo requerido, mientras el código evaluado implementa MCP manualmente.
- Filesystem interpreta cada argumento posicional como una raíz, por lo que se proporciona una única carpeta aislada.
- El transporte HTTP requiere separar sesión, protocolo y errores HTTP/JSON-RPC; compartir el dispatcher evitó divergencias funcionales.
- Las pruebas no deben depender de Internet o claves: el LLM falso y el servidor HTTP efímero permitieron validar el flujo determinísticamente.
- Una captura TLS no revela JSON-RPC sin descifrado autorizado; el log del cliente sirve para correlación, no para inventar contenido de paquetes.

## 10. Conclusiones

La solución demuestra la arquitectura anfitrión–cliente–servidor, una implementación manual de JSON-RPC/MCP y la reutilización de una misma lógica industrial en dos transportes. Gemini, los servidores locales y el despliegue Render ya fueron verificados, incluida la paridad local/remota. Antes de declarar la entrega totalmente completa falta realizar la captura HTTPS contra Render y completar la tabla de valores realmente observados.

## Fuentes

- [Especificación de transportes MCP 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)
- [Servidor Filesystem oficial](https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem)
- [Servidor Git oficial](https://github.com/modelcontextprotocol/servers/tree/main/src/git)
- [JSON-RPC 2.0](https://www.jsonrpc.org/specification)
