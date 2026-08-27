# Guion de presentación (5–8 minutos)

## Preparación

1. Activar `.venv`, exportar la clave/modelo del LLM sin mostrarlos y abrir tres terminales.
2. Terminal 1: `python -m plant_energy_mcp.http_server`.
3. Terminal 2: `python -m mcp_host --servers plant-local,filesystem,git,plant-remote`.
4. Terminal 3: dejar listo `python -m unittest discover -v`.
5. Verificar que `.runtime/mcp_interactions.jsonl` no contenga secretos antes de mostrarlo.

## Guion

**0:00–0:45 — problema.** Una planta necesita consultar equipos, consumo y alertas desde lenguaje natural. El anfitrión conecta el LLM a herramientas MCP sin darle acceso arbitrario al sistema.

**0:45–1:45 — arquitectura.** Mostrar `mcp_host`, `plant_energy_mcp` y el diagrama del README. Explicar anfitrión, cliente, servidor, herramienta, JSON-RPC y transportes. Aclarar que el cliente, servidor industrial y adaptadores son manuales; Filesystem/Git son los oficiales requeridos.

**1:45–3:15 — demostración LLM y contexto.** Preguntar: “¿Quién fue Alan Turing?”, luego “¿En qué año nació?”. Después pedir “Genera el reporte energético e indica qué equipo está sobre el umbral”. El texto exacto del LLM es variable; señalar la llamada `plant_local__get_energy_report` y la confirmación si se solicita una herramienta sensible.

**3:15–4:15 — Filesystem + Git.** Ejecutar `python -m demos.filesystem_git_demo`. Mostrar que el repositorio está bajo `demo_workspace`, no es el principal, y que el resultado real incluye escritura, staging y commit.

**4:15–5:15 — local/remoto y log.** Ejecutar `python -m demos.local_remote_parity_demo`; mostrar `equal: true`. En el chatbot ejecutar `/log` y explicar timestamp, transporte, dirección, método, id, duración, resumen y redacción.

**5:15–6:15 — pruebas y dificultades.** Ejecutar pruebas. Explicar negociación MCP, correlación de IDs, timeouts, aislamiento de servidores y diferencia entre error HTTP y JSON-RPC.

**6:15–7:00 — red y alcance.** Mostrar el procedimiento Wireshark y el estado de evidencia. Explicar que HTTPS cifra JSON-RPC y que el reporte no atribuye IP ni paquetes que no fueron observados. Describir los requisitos de autorización y credenciales del despliegue.

## Preguntas probables

1. **¿Por qué MCP?** Estandariza descubrimiento y ejecución de herramientas entre un anfitrión y servidores independientes.
2. **¿Qué diferencia MCP de JSON-RPC?** JSON-RPC define el formato de mensajes; MCP define ciclo de vida, capacidades y métodos sobre ese formato.
3. **¿Usaron FastMCP?** No en el cliente, anfitrión ni servidor propio; los servidores oficiales externos conservan sus dependencias upstream.
4. **¿Cómo correlacionan respuestas?** Cada request obtiene un `id`; un mapa de esperas entrega la respuesta al solicitante correcto.
5. **¿Por qué `notifications/initialized` no tiene respuesta?** Es una notificación JSON-RPC y por definición no incluye `id`.
6. **¿Dónde vive el contexto?** En la lista de mensajes del proceso activo; se elimina al cerrar.
7. **¿Qué pasa si un servidor falla?** Se registra el fallo y los demás clientes continúan disponibles cuando es posible.
8. **¿Cómo protegen las rutas?** Filesystem y Git reciben exclusivamente `demo_workspace` y su repositorio hijo.
9. **¿Qué operaciones se confirman?** Escrituras, creación/eliminación, staging, commits y registro de lecturas.
10. **¿Cómo evitan filtrar la clave?** Solo se lee del entorno; no se imprime y el log redacta nombres sensibles.
11. **¿Por qué dos transportes?** stdio es apropiado para subprocesos locales; HTTP permite acceso remoto usando la misma lógica.
12. **¿Cómo demuestran paridad?** La demo llama `get_energy_report` por ambos transportes y compara las estructuras.
13. **¿Por qué `GET /mcp` da 405?** Streamable HTTP permite no ofrecer un stream SSE independiente; las respuestas se entregan por POST JSON.
14. **¿Qué contiene la sesión HTTP?** Un dispatcher independiente con estado de inicialización y datos en memoria.
15. **¿Por qué no se ven los métodos JSON-RPC en Wireshark?** TLS los cifra; se necesita key log legítimo del cliente o correlación temporal.
16. **¿Qué capa maneja TCP?** Transporte; TLS/HTTP/JSON-RPC se analizan como protocolos superiores de sesión/aplicación según el modelo empleado.
17. **¿Qué falta para cerrar el proyecto?** Probar el LLM con la cuenta real, desplegar con autorización y capturar/anotar tráfico real.
18. **¿Qué aprendieron?** Separar negocio de transporte facilita pruebas y evita que local/remoto diverjan.

## Plan alterno si Internet falla

Ejecutar las 13 pruebas y la paridad local HTTP. Declarar explícitamente que el texto LLM y la nube son pruebas opt-in; nunca presentar el doble de prueba como una llamada real.
