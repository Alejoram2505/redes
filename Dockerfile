FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PLANT_MCP_HOST=0.0.0.0 PORT=8080
WORKDIR /app
COPY plant_energy_mcp ./plant_energy_mcp
USER 65532:65532
EXPOSE 8080
CMD ["python", "-m", "plant_energy_mcp.http_server"]
