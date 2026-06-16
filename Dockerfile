FROM python:3.12-slim
# Opoznienie chmury emulujemy kierunkowo przez toxiproxy (osobny kontener),
# wiec obraz nie wymaga `tc`/iproute2 ani uprawnienia NET_ADMIN.
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Note: run.py and scripts/ are run on the host, they are not copied into the container
COPY detector.py device_sim.py edge_node.py central.py ./
CMD ["python", "edge_node.py"]
